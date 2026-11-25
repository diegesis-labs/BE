"""허용 목록, 사용자, 로그인 상태를 읽고 쓰는 repository."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import DbSession


@dataclass(frozen=True)
class AllowedEmail:
    email: str
    role: str
    created_at: datetime


@dataclass(frozen=True)
class UserRecord:
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


class AuthRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_allowed_email(self, email: str) -> AllowedEmail | None:
        raise NotImplementedError

    async def find_users_by_email_or_sub(self, *, email: str, google_sub: str) -> list[UserRecord]:
        raise NotImplementedError

    async def create_user(
        self, *, email: str, google_sub: str, display_name: str | None
    ) -> UserRecord:
        raise NotImplementedError

    async def update_display_name(self, user_id: UUID, display_name: str | None) -> None:
        raise NotImplementedError

    async def add_login_session(
        self, *, token_hash: str, user_id: UUID, expires_at: datetime
    ) -> None:
        raise NotImplementedError

    async def find_active_login(self, token_hash: str) -> ActiveLogin | None:
        raise NotImplementedError

    async def delete_login_session(self, token_hash: str) -> None:
        raise NotImplementedError

    async def delete_expired_login_sessions(self, user_id: UUID) -> None:
        raise NotImplementedError


def get_auth_repository(session: DbSession) -> AuthRepository:
    raise NotImplementedError
