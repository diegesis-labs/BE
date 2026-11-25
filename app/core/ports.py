"""핵심 로직이 바깥 세계에 기대하는 기능의 약속(포트). 구조는 docs/ARCHITECTURE.md 8절에 있다.

이 파일에는 선언만 둔다. 포트는 특정 기술의 이름을 알지 못하며, 실제 구현은 app/adapters/의
어댑터나 기능 폴더의 repository가 맡는다. 그 기능의 Epic이 필요한 포트만 여기에 더한다.

app/core/는 기능 폴더를 import하지 않는다. 그래서 공통 층(관문)과 기능 폴더의 service가 함께 쓰는
저장소의 레코드도 여기에 둔다(ADR-029).
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class AllowedEmail:
    """허용 목록의 행 하나."""

    email: str
    role: str  # "user" 또는 "admin"
    created_at: datetime


@dataclass(frozen=True)
class UserRecord:
    """users의 행 하나."""

    id: UUID
    email: str
    google_sub: str
    display_name: str | None


@dataclass(frozen=True)
class ActiveLogin:
    """만료되지 않은 로그인 상태 하나와 그 사용자.

    allowed는 그 사용자의 이메일에 해당하는 허용 목록 행이며, 없으면 None이다.
    """

    user: UserRecord
    session_created_at: datetime
    allowed: AllowedEmail | None


class LoginLookup(Protocol):
    """관문(app/core/gate.py)이 로그인 상태를 찾는 곳.

    app/auth/repository.py의 AuthRepository가 구조적으로 만족하며, create_app()이 넣는다.
    요청마다 저장소에서 읽어야 하며 읽은 값을 담아 두면 안 된다(ADR-024). 로그인 상태의 행을
    바꾸지 않는다(ADR-027).
    """

    async def find_active_login(self, token_hash: str) -> ActiveLogin | None:
        """쿠키 값의 해시로 만료되지 않은 로그인 상태를 찾는다. 없거나 만료됐으면 None이다."""
        ...


@dataclass(frozen=True)
class Identity:
    """Google이 확인해 준 신원. 이메일은 Google이 준 그대로다(소문자로 바꾸는 것은 service의 일)."""

    sub: str
    email: str
    email_verified: bool
    name: str | None


class LoginFailedError(Exception):
    """Google과의 로그인이 끝나지 못했다.

    메시지에는 원인(예: "토큰 교환이 400으로 실패", "ID 토큰의 aud가 다름")만 적는다.
    code, code_verifier, 토큰, 클라이언트 비밀값은 메시지에 넣지 않는다.
    """


class IdentityProvider(Protocol):
    """로그인한 사람의 신원을 확인해 주는 바깥 서비스(docs/ARCHITECTURE.md 8절).

    email_verified가 false인 신원을 거르는 것은 어댑터가 아니라 service의 일이다. 어댑터는 Google이
    준 값을 그대로 돌려준다.
    """

    def authorization_url(self, *, state: str, nonce: str, code_verifier: str) -> str:
        """Google의 인가 주소.

        state와 nonce를 붙이고, code_verifier로 만든 code_challenge(S256)를 붙인다.
        """
        ...

    async def exchange_code(
        self, *, code: str, code_verifier: str, expected_nonce: str
    ) -> Identity:
        """code를 토큰으로 바꾸고 ID 토큰의 클레임을 모두 확인해서 신원을 돌려준다.

        통신 실패, 오류 응답, 형식이 틀린 응답, 클레임이 하나라도 맞지 않는 경우에 모두
        LoginFailedError 하나만 낸다.
        """
        ...
