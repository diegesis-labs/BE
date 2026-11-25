"""로그인 시작, 로그인 결과 처리, 로그아웃의 규칙(E1 S1.3).

결과 처리의 순서는 docs/API.md 4.2절의 동작 순서이며, 순서가 곧 규칙이다. 로그인 상태의 수명은
docs/ARCHITECTURE.md 6절에, 결정의 이유는 ADR-024, ADR-025, ADR-027에 있다.

- HTTP(리디렉션 주소, 쿠키의 속성)는 라우터가 맡는다. service는 무엇을 확인하고 무엇을 쓰고 어떤
  결과인지만 정한다. 그래서 FastAPI, SQLAlchemy, httpx, 어댑터를 import하지 않고, Google은
  IdentityProvider 포트를 거친다(docs/ARCHITECTURE.md 8절).
- 결과는 성공, NOT_ALLOWED, LOGIN_FAILED의 셋뿐이다. 실패의 원인은 공격자에게 단서가 되므로 결과에
  담지 않고 로그에만 남긴다(ADR-025).
- 실패하거나 허용 목록 밖이면 users와 login_sessions를 바꾸지 않는다. 쌍을 확인한 뒤 등록하려다
  겹친 요청이 먼저 만든 행과 부딪힌 경우 말고는 저장소의 쓰기 메서드를 부르지도 않는다. 성공했을
  때의 쓰기는 요청 하나의 트랜잭션(get_db_session) 안에서 일어나므로, service가 커밋하거나
  트랜잭션을 열지 않는다.
- 로그에는 쿠키 값, code, 토큰, 클라이언트 비밀값, state, nonce, code_verifier를 남기지 않는다(E1
  "못 박을 것"). LoginFailedError의 메시지는 어댑터가 원인만 적으므로 남긴다.
- 역할은 결과에 담지 않는다. 관문이 요청마다 허용 목록에서 읽는다(ADR-024).
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol
from uuid import UUID

from app.core import security
from app.core.ports import AllowedEmail, Identity, IdentityProvider, LoginFailedError, UserRecord

logger = logging.getLogger(__name__)

# diegesis_oauth_state 쿠키는 "{state}.{nonce}.{code_verifier}"다. 세 값은 base64url 문자만 쓰므로
# `.`이 들어 있지 않다(docs/API.md 4.2절).
STATE_COOKIE_SEPARATOR = "."


class AuthStore(Protocol):
    """service가 저장소에 기대하는 것.

    app/auth/repository.py의 AuthRepository가 구조적으로 만족한다.
    """

    async def get_allowed_email(self, email: str) -> AllowedEmail | None: ...

    async def find_users_by_email_or_sub(
        self, *, email: str, google_sub: str
    ) -> list[UserRecord]: ...

    async def create_user(
        self, *, email: str, google_sub: str, display_name: str | None
    ) -> UserRecord | None:
        """같은 이메일이나 같은 google_sub의 행이 이미 있으면 만들지 않고 None을 돌려준다."""
        ...

    async def update_display_name(self, user_id: UUID, display_name: str | None) -> None: ...

    async def add_login_session(
        self, *, token_hash: str, user_id: UUID, expires_at: datetime
    ) -> None: ...

    async def delete_login_session(self, token_hash: str) -> None: ...

    async def delete_expired_login_sessions(self, user_id: UUID) -> None: ...


@dataclass(frozen=True)
class LoginStart:
    authorization_url: str
    state_cookie: str  # "{state}.{nonce}.{code_verifier}"


@dataclass(frozen=True)
class LoginSucceeded:
    session_token: str  # 쿠키에 담을 값. 저장소에는 hash_token(session_token)만 들어간다.


@dataclass(frozen=True)
class LoginRejected:
    error: Literal["NOT_ALLOWED", "LOGIN_FAILED"]


LoginResult = LoginSucceeded | LoginRejected

_LOGIN_FAILED = LoginRejected(error="LOGIN_FAILED")
_NOT_ALLOWED = LoginRejected(error="NOT_ALLOWED")


class _PairMismatchError(Exception):
    """이메일만 같거나 google_sub만 같은 사용자가 있다. 원인은 이미 로그에 남겼다."""


class AuthService:
    def __init__(
        self, store: AuthStore, identity_provider: IdentityProvider, *, session_ttl: timedelta
    ) -> None:
        self._store = store
        self._identity_provider = identity_provider
        self._session_ttl = session_ttl

    def start_login(self) -> LoginStart:
        """state, nonce, code_verifier를 하나씩 만들고 인가 주소와 state 쿠키의 값을 돌려준다.

        세 값은 security.new_token()으로 만든다. 모듈을 거쳐 부르는 이유는 그 함수의 독스트링에
        있다.
        """
        state = security.new_token()
        nonce = security.new_token()
        code_verifier = security.new_token()
        authorization_url = self._identity_provider.authorization_url(
            state=state, nonce=nonce, code_verifier=code_verifier
        )
        return LoginStart(
            authorization_url=authorization_url,
            state_cookie=STATE_COOKIE_SEPARATOR.join((state, nonce, code_verifier)),
        )

    async def complete_login(
        self,
        *,
        state_cookie: str | None,  # diegesis_oauth_state 쿠키
        state: str | None,  # 쿼리의 state
        code: str | None,  # 쿼리의 code
        error: str | None,  # 쿼리의 error (사용자가 동의 화면에서 취소하면 온다)
        current_session_token: str | None,  # 요청에 붙어 온 로그인 상태의 쿠키
    ) -> LoginResult:
        identity = await self._verified_identity(
            state_cookie=state_cookie, state=state, code=code, error=error
        )
        if identity is None:
            return _LOGIN_FAILED

        # 이후의 조회와 저장은 모두 소문자로 바꾼 이메일로 한다(ADR-024).
        email = identity.email.lower()
        if await self._store.get_allowed_email(email) is None:
            # 허용 목록 밖이면 users와 login_sessions를 바꾸지 않는다(docs/ARCHITECTURE.md 6절).
            logger.warning("로그인 거부: 이메일이 허용 목록에 없음")
            return _NOT_ALLOWED

        try:
            user = await self._paired_user(email=email, google_sub=identity.sub)
            # 여기서부터의 쓰기는 요청 하나의 트랜잭션이다.
            if user is not None:
                await self._store.update_display_name(user.id, identity.name)
            else:
                user = await self._store.create_user(
                    email=email, google_sub=identity.sub, display_name=identity.name
                )
                if user is None:
                    # 같은 사람의 결과 처리 두 개가 겹치면, 위에서 쌍을 확인한 뒤 등록하기 전에 다른
                    # 요청이 행을 먼저 만든다. 그 행으로 쌍을 다시 확인한다. 고유 제약 위반으로
                    # 500을 내지 않는다(E1 S1.3).
                    logger.info("로그인: 겹친 요청이 사용자를 먼저 등록해 쌍을 다시 확인함")
                    user = await self._paired_user(email=email, google_sub=identity.sub)
                    if user is None:
                        logger.warning("로그인 실패: 등록하지 못했고 쌍이 맞는 사용자도 없음")
                        return _LOGIN_FAILED
        except _PairMismatchError:
            return _LOGIN_FAILED

        if current_session_token:
            # 요청에 붙어 온 쿠키의 행 하나만 지운다. 같은 사람의 다른 기기 행은 그대로 둔다.
            await self._store.delete_login_session(security.hash_token(current_session_token))
        await self._store.delete_expired_login_sessions(user.id)

        session_token = security.new_token()
        await self._store.add_login_session(
            token_hash=security.hash_token(session_token),
            user_id=user.id,
            expires_at=datetime.now(UTC) + self._session_ttl,
        )
        return LoginSucceeded(session_token=session_token)

    async def logout(self, session_token: str | None) -> None:
        """쿠키가 가리키는 로그인 상태 하나만 지운다.

        쿠키가 없거나 모르는 값이어도 예외 없이 끝난다.
        """
        if session_token:
            await self._store.delete_login_session(security.hash_token(session_token))

    async def _paired_user(self, *, email: str, google_sub: str) -> UserRecord | None:
        """이메일과 google_sub가 모두 같은 사용자. 없으면 None이다.

        이메일만 같거나 google_sub만 같은 행이 있으면 거부의 원인을 로그에 남기고
        _PairMismatchError를 낸다. 그 행을 고치거나 새 행을 만들지 않는다(ADR-027). 이 확인이
        google_sub의 고유 제약 위반도 미리 막는다.
        """
        users = await self._store.find_users_by_email_or_sub(email=email, google_sub=google_sub)
        conflicts = [user for user in users if user.email != email or user.google_sub != google_sub]
        for user in conflicts:
            if user.email == email:
                logger.warning(
                    "로그인 거부: 이메일은 같고 google_sub가 다른 사용자가 있음 (user_id=%s)",
                    user.id,
                )
            else:
                logger.warning(
                    "로그인 거부: google_sub는 같고 이메일이 다른 사용자가 있음 (user_id=%s)",
                    user.id,
                )
        if conflicts:
            raise _PairMismatchError
        # 남은 행은 이메일과 google_sub가 모두 같다. 두 컬럼이 고유하므로 많아야 하나다.
        return users[0] if users else None

    async def _verified_identity(
        self, *, state_cookie: str | None, state: str | None, code: str | None, error: str | None
    ) -> Identity | None:
        """docs/API.md 4.2절의 동작 순서에서 신원이 확인될 때까지.

        실패하면 원인을 로그에 남기고 None을 돌려준다.

        이 단계에서는 저장소에 닿지 않는다.
        """
        if error is not None:
            logger.warning("로그인 실패: Google이 error 쿼리를 돌려줌")
            return None
        if state_cookie is None:
            logger.warning("로그인 실패: state 쿠키가 없음")
            return None
        parts = state_cookie.split(STATE_COOKIE_SEPARATOR)
        if len(parts) != 3:
            logger.warning("로그인 실패: state 쿠키가 세 부분이 아님")
            return None
        cookie_state, nonce, code_verifier = parts
        # secure_equals는 어느 한쪽이 비어 있으면 False다. 빈 state끼리 같다고 보지 않는다(ADR-027).
        if not security.secure_equals(cookie_state, state or ""):
            logger.warning("로그인 실패: state가 맞지 않음")
            return None
        if not code:
            logger.warning("로그인 실패: code가 없음")
            return None
        try:
            identity = await self._identity_provider.exchange_code(
                code=code, code_verifier=code_verifier, expected_nonce=nonce
            )
        except LoginFailedError as exc:
            logger.warning("로그인 실패: 신원을 확인하지 못함 (%s)", exc)
            return None
        if not identity.email_verified:
            logger.warning(
                "로그인 실패: Google이 이메일을 확인하지 않은 계정 (email_verified가 false)"
            )
            return None
        return identity
