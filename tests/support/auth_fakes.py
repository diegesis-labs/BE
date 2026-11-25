"""로그인 기능의 테스트가 함께 쓰는 가짜.

- FakeIdentityProvider: IdentityProvider 포트(app/core/ports.py)의 가짜. Google에 닿지 않는다.
- FakeAuthStore: AuthStore(app/auth/service.py)를 만족하는 메모리 저장소. 데이터베이스에 닿지
  않는다. 관문(app/core/gate.py)이 쓰는 find_active_login도 가진다.

service, 관문, 라우터의 테스트가 이 가짜를 쓴다. 가짜가 지키는 약속은
tests/support/test_auth_fakes.py가 본다.
"""

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode
from uuid import UUID, uuid4

from app.core.ports import ActiveLogin, AllowedEmail, Identity, LoginFailedError, UserRecord

# docs/backlog/epic-1/testcase.md의 "정상 ID 토큰"과 같은 신원.
READER_IDENTITY = Identity(
    sub="1234567890", email="reader@example.com", email_verified=True, name="독자"
)

FAKE_AUTHORIZATION_ENDPOINT = "https://idp.fake.example/authorize"


def fake_authorization_url(*, state: str, nonce: str) -> str:
    """FakeIdentityProvider.authorization_url이 돌려주는 주소.

    code_verifier는 담지 않는다. 실제 인가 주소에도 code_verifier가 아니라 그 해시가 담긴다.
    """
    return f"{FAKE_AUTHORIZATION_ENDPOINT}?{urlencode({'state': state, 'nonce': nonce})}"


@dataclass(frozen=True)
class AuthorizationUrlCall:
    state: str
    nonce: str
    code_verifier: str


@dataclass(frozen=True)
class ExchangeCodeCall:
    code: str
    code_verifier: str
    expected_nonce: str


class FakeIdentityProvider:
    """IdentityProvider의 가짜. 받은 인자를 모두 기록한다.

    exchange_code는 error가 있으면 그 예외를 내고, 없으면 identity를 돌려준다. 두 값은 테스트 중간에
    바꿔도 된다. 실제 어댑터와 달리 nonce를 확인하지 않으므로, 넘긴 값은 exchange_code_calls로
    확인한다.
    """

    def __init__(
        self, identity: Identity = READER_IDENTITY, *, error: LoginFailedError | None = None
    ) -> None:
        self.identity = identity
        self.error = error
        self.authorization_url_calls: list[AuthorizationUrlCall] = []
        self.exchange_code_calls: list[ExchangeCodeCall] = []

    def authorization_url(self, *, state: str, nonce: str, code_verifier: str) -> str:
        self.authorization_url_calls.append(
            AuthorizationUrlCall(state=state, nonce=nonce, code_verifier=code_verifier)
        )
        return fake_authorization_url(state=state, nonce=nonce)

    async def exchange_code(
        self, *, code: str, code_verifier: str, expected_nonce: str
    ) -> Identity:
        self.exchange_code_calls.append(
            ExchangeCodeCall(code=code, code_verifier=code_verifier, expected_nonce=expected_nonce)
        )
        if self.error is not None:
            raise self.error
        return self.identity


class FakeConstraintError(Exception):
    """FakeAuthStore가 흉내 내는 데이터베이스의 제약을 어겼다."""


@dataclass(frozen=True)
class FakeLoginSession:
    user_id: UUID
    expires_at: datetime
    created_at: datetime


@dataclass(frozen=True)
class StoreWrite:
    """FakeAuthStore의 쓰기 메서드가 한 번 불린 기록."""

    method: str
    arguments: dict[str, Any]


class FakeAuthStore:
    """AuthStore를 만족하는 메모리 저장소.

    - 쓰기 메서드가 불릴 때마다 writes에 메서드 이름과 인자를 남긴다. 실패하거나 허용 목록 밖일 때
      "저장소에 쓰지 않았다"를 writes == []로 확인한다.
    - 데이터베이스의 제약 가운데 로그인에 걸린 것을 흉내 내서, 어기면 FakeConstraintError를 낸다.
      이메일은 소문자만, users.email과 users.google_sub는 고유, login_sessions.token_hash는 고유,
      login_sessions.user_id는 있는 사용자(docs/ARCHITECTURE.md 6절). 다만 create_user는
      AuthRepository와 같이, 같은 이메일이나 같은 google_sub의 행이 있으면 만들지 않고 None을
      돌려준다(INSERT … ON CONFLICT DO NOTHING).
    - 이메일은 받은 그대로 비교한다. 소문자로 바꾸는 것은 service의 일이다(AuthRepository와 같다).
    - "지금"은 이 컴퓨터의 시각이다. 만료 시각이 지금과 같거나 그보다 이르면 만료된 것이다.
    - find_active_login은 읽기이므로 writes에 남기지 않고, 받은 해시를 lookups에 남긴다. 쿠키가
      없을 때 "조회하지 않았다"를 lookups == []로 확인한다.

    allow, put_user, put_login_session은 테스트가 준비할 때 쓰며 writes에 남기지 않는다. 두 시각
    (허용 목록에 들어간 시각과 로그인 상태를 만든 시각)을 주지 않으면 지금으로 정한다.

    before_create_user에 함수를 넣어 두면 create_user가 행을 넣기 직전에 부른다. 쌍을 확인한 뒤
    등록하기 전에 겹친 다른 요청이 행을 먼저 만드는 경합을 흉내 낸다.
    """

    def __init__(self) -> None:
        self.allowed_emails: dict[str, AllowedEmail] = {}
        self.users: dict[UUID, UserRecord] = {}
        self.login_sessions: dict[str, FakeLoginSession] = {}
        self.writes: list[StoreWrite] = []
        self.lookups: list[str] = []
        self.before_create_user: Callable[[], object] | None = None

    # --- 테스트의 준비 -------------------------------------------------------

    def allow(
        self, email: str, role: str = "user", *, created_at: datetime | None = None
    ) -> AllowedEmail:
        _check_lowercase(email)
        allowed = AllowedEmail(
            email=email,
            role=role,
            created_at=datetime.now(UTC) if created_at is None else created_at,
        )
        self.allowed_emails[email] = allowed
        return allowed

    def put_user(self, email: str, google_sub: str, display_name: str | None = None) -> UserRecord:
        return self._insert_user(email=email, google_sub=google_sub, display_name=display_name)

    def put_login_session(
        self,
        token_hash: str,
        user_id: UUID,
        expires_at: datetime,
        *,
        created_at: datetime | None = None,
    ) -> None:
        self._insert_login_session(
            token_hash=token_hash, user_id=user_id, expires_at=expires_at, created_at=created_at
        )

    # --- AuthStore ------------------------------------------------------------

    async def get_allowed_email(self, email: str) -> AllowedEmail | None:
        return self.allowed_emails.get(email)

    async def find_users_by_email_or_sub(self, *, email: str, google_sub: str) -> list[UserRecord]:
        return [
            user
            for user in self.users.values()
            if user.email == email or user.google_sub == google_sub
        ]

    async def create_user(
        self, *, email: str, google_sub: str, display_name: str | None
    ) -> UserRecord | None:
        self._record("create_user", email=email, google_sub=google_sub, display_name=display_name)
        if self.before_create_user is not None:
            self.before_create_user()
        if any(
            user.email == email or user.google_sub == google_sub for user in self.users.values()
        ):
            return None
        return self._insert_user(email=email, google_sub=google_sub, display_name=display_name)

    async def update_display_name(self, user_id: UUID, display_name: str | None) -> None:
        self._record("update_display_name", user_id=user_id, display_name=display_name)
        user = self.users.get(user_id)
        if user is not None:
            self.users[user_id] = replace(user, display_name=display_name)

    async def add_login_session(
        self, *, token_hash: str, user_id: UUID, expires_at: datetime
    ) -> None:
        self._record(
            "add_login_session", token_hash=token_hash, user_id=user_id, expires_at=expires_at
        )
        self._insert_login_session(token_hash=token_hash, user_id=user_id, expires_at=expires_at)

    # --- 관문(app/core/gate.py) ------------------------------------------------

    async def find_active_login(self, token_hash: str) -> ActiveLogin | None:
        """AuthRepository.find_active_login과 같다. 만료된 로그인 상태는 없는 것으로 본다."""
        self.lookups.append(token_hash)
        session = self.login_sessions.get(token_hash)
        if session is None or session.expires_at <= datetime.now(UTC):
            return None
        user = self.users[session.user_id]
        return ActiveLogin(
            user=user,
            session_created_at=session.created_at,
            allowed=self.allowed_emails.get(user.email),
        )

    async def delete_login_session(self, token_hash: str) -> None:
        self._record("delete_login_session", token_hash=token_hash)
        self.login_sessions.pop(token_hash, None)

    async def delete_expired_login_sessions(self, user_id: UUID) -> None:
        self._record("delete_expired_login_sessions", user_id=user_id)
        now = datetime.now(UTC)
        self.login_sessions = {
            token_hash: session
            for token_hash, session in self.login_sessions.items()
            if not (session.user_id == user_id and session.expires_at <= now)
        }

    # --- 내부 -----------------------------------------------------------------

    def _record(self, method: str, **arguments: Any) -> None:
        self.writes.append(StoreWrite(method=method, arguments=arguments))

    def _insert_user(self, *, email: str, google_sub: str, display_name: str | None) -> UserRecord:
        _check_lowercase(email)
        for user in self.users.values():
            if user.email == email:
                raise FakeConstraintError("uq_users_email")
            if user.google_sub == google_sub:
                raise FakeConstraintError("uq_users_google_sub")
        user = UserRecord(id=uuid4(), email=email, google_sub=google_sub, display_name=display_name)
        self.users[user.id] = user
        return user

    def _insert_login_session(
        self,
        *,
        token_hash: str,
        user_id: UUID,
        expires_at: datetime,
        created_at: datetime | None = None,
    ) -> None:
        if token_hash in self.login_sessions:
            raise FakeConstraintError("pk_login_sessions")
        if user_id not in self.users:
            raise FakeConstraintError("fk_login_sessions_user_id_users")
        self.login_sessions[token_hash] = FakeLoginSession(
            user_id=user_id,
            expires_at=expires_at,
            created_at=datetime.now(UTC) if created_at is None else created_at,
        )


def _check_lowercase(email: str) -> None:
    if email != email.lower():
        raise FakeConstraintError("ck_email_lowercase")
