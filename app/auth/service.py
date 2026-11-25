"""로그인 시작, 로그인 결과 처리, 로그아웃의 규칙(E1 S1.3)."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal, Protocol
from uuid import UUID

from app.auth.repository import AllowedEmail, UserRecord
from app.core.ports import IdentityProvider


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
    ) -> UserRecord: ...

    async def update_display_name(self, user_id: UUID, display_name: str | None) -> None: ...

    async def add_login_session(
        self, *, token_hash: str, user_id: UUID, expires_at: datetime
    ) -> None: ...

    async def delete_login_session(self, token_hash: str) -> None: ...

    async def delete_expired_login_sessions(self, user_id: UUID) -> None: ...


@dataclass(frozen=True)
class LoginStart:
    authorization_url: str
    state_cookie: str


@dataclass(frozen=True)
class LoginSucceeded:
    session_token: str


@dataclass(frozen=True)
class LoginRejected:
    error: Literal["NOT_ALLOWED", "LOGIN_FAILED"]


LoginResult = LoginSucceeded | LoginRejected


class AuthService:
    def __init__(
        self, store: AuthStore, identity_provider: IdentityProvider, *, session_ttl: timedelta
    ) -> None:
        self._store = store
        self._identity_provider = identity_provider
        self._session_ttl = session_ttl

    def start_login(self) -> LoginStart:
        raise NotImplementedError

    async def complete_login(
        self,
        *,
        state_cookie: str | None,
        state: str | None,
        code: str | None,
        error: str | None,
        current_session_token: str | None,
    ) -> LoginResult:
        raise NotImplementedError

    async def logout(self, session_token: str | None) -> None:
        raise NotImplementedError
