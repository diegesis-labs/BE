"""허용 목록, 사용자, 로그인 상태를 읽고 쓰는 repository.

스키마와 로그인 상태의 수명은 docs/ARCHITECTURE.md 6절에 있다. 이 모듈이 지키는 것은 다음과 같다.

- 커밋하지 않는다. 트랜잭션의 경계는 get_db_session(app/core/database.py)이 정한다. 로그인에
  성공했을 때의 쓰기가 한 트랜잭션이어야 하기 때문이다(E1 S1.3).
- 이메일은 받은 그대로 비교한다. 소문자로 바꾸는 것은 service의 일이다.
- 쿠키 값이 아니라 그 해시만 다룬다. 허용 목록을 바꾸는 메서드는 두지 않는다(ADR-024).
- 읽은 값을 담아 두지 않는다. SQL로 바꾼 허용 목록이 다음 요청부터 반영되어야 한다(ADR-024).
- "지금"은 데이터베이스의 now()다. 만료를 거르는 조회와 만료된 행을 지우는 삭제가 같은 기준을 쓰고,
  login_sessions.created_at과 allowed_emails.created_at도 같은 시계에서 나온다.

ORM 객체가 아니라 컬럼을 읽고 문장을 실행한다. 세션의 identity map에 남은 옛 값을 돌려주지 않기
위해서다.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import ColumnElement, RowMapping, delete, func, insert, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import AllowedEmailModel, LoginSessionModel, UserModel
from app.core.database import DbSession

_USER_COLUMNS = (UserModel.id, UserModel.email, UserModel.google_sub, UserModel.display_name)


@dataclass(frozen=True)
class AllowedEmail:
    email: str
    role: str  # "user" 또는 "admin"
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
        row = (
            await self._session.execute(
                select(
                    AllowedEmailModel.email, AllowedEmailModel.role, AllowedEmailModel.created_at
                ).where(AllowedEmailModel.email == email)
            )
        ).one_or_none()
        if row is None:
            return None
        return AllowedEmail(email=row.email, role=row.role, created_at=row.created_at)

    async def find_users_by_email_or_sub(self, *, email: str, google_sub: str) -> list[UserRecord]:
        """이메일이 같거나 google_sub가 같은 행을 모두 돌려준다.

        이메일만으로 찾는 메서드는 두지 않는다. 같은 이메일을 새로 가진 다른 Google 계정이 기존
        사람의 기록을 넘겨받으면 안 되기 때문이다(ADR-027).
        """
        rows = await self._session.execute(
            select(*_USER_COLUMNS)
            .where(or_(UserModel.email == email, UserModel.google_sub == google_sub))
            .order_by(UserModel.email)
        )
        return [_user_record(row._mapping) for row in rows]

    async def create_user(
        self, *, email: str, google_sub: str, display_name: str | None
    ) -> UserRecord:
        row = (
            await self._session.execute(
                insert(UserModel)
                .values(email=email, google_sub=google_sub, display_name=display_name)
                .returning(*_USER_COLUMNS)
            )
        ).one()
        return _user_record(row._mapping)

    async def update_display_name(self, user_id: UUID, display_name: str | None) -> None:
        await self._session.execute(
            update(UserModel).where(UserModel.id == user_id).values(display_name=display_name)
        )

    async def add_login_session(
        self, *, token_hash: str, user_id: UUID, expires_at: datetime
    ) -> None:
        # created_at은 넘기지 않고 데이터베이스의 기본값(now())에 맡긴다. 관문이 이 값을
        # allowed_emails.created_at과 비교하므로 같은 시계에서 나와야 한다.
        await self._session.execute(
            insert(LoginSessionModel).values(
                token_hash=token_hash, user_id=user_id, expires_at=expires_at
            )
        )

    async def find_active_login(self, token_hash: str) -> ActiveLogin | None:
        """해시가 가리키는 만료되지 않은 로그인 상태와 그 사용자, 그 사용자의 허용 목록 행.

        행을 바꾸지 않는다. 로그인 상태의 만료 시각은 늘리지 않는다(ADR-027).
        """
        row = (
            await self._session.execute(
                select(
                    *_USER_COLUMNS,
                    LoginSessionModel.created_at.label("session_created_at"),
                    AllowedEmailModel.email.label("allowed_email"),
                    AllowedEmailModel.role.label("allowed_role"),
                    AllowedEmailModel.created_at.label("allowed_created_at"),
                )
                .select_from(LoginSessionModel)
                .join(UserModel, UserModel.id == LoginSessionModel.user_id)
                .outerjoin(AllowedEmailModel, AllowedEmailModel.email == UserModel.email)
                .where(LoginSessionModel.token_hash == token_hash, _active())
            )
        ).one_or_none()
        if row is None:
            return None
        allowed = (
            None
            if row.allowed_email is None
            else AllowedEmail(
                email=row.allowed_email, role=row.allowed_role, created_at=row.allowed_created_at
            )
        )
        return ActiveLogin(
            user=_user_record(row._mapping),
            session_created_at=row.session_created_at,
            allowed=allowed,
        )

    async def delete_login_session(self, token_hash: str) -> None:
        """해시가 가리키는 행 하나만 지운다. 없으면 아무 일도 하지 않는다."""
        await self._session.execute(
            delete(LoginSessionModel).where(LoginSessionModel.token_hash == token_hash)
        )

    async def delete_expired_login_sessions(self, user_id: UUID) -> None:
        """그 사용자의 만료된 행만 지운다. 만료되지 않은 행과 다른 사용자의 행은 그대로 둔다."""
        await self._session.execute(
            delete(LoginSessionModel).where(LoginSessionModel.user_id == user_id, ~_active())
        )


def _active() -> ColumnElement[bool]:
    """만료되지 않은 로그인 상태의 조건. 만료된 행은 이 조건의 부정으로 고른다.

    두 쪽이 한 조건에서 나오므로, 조회에서 걸러지는 행과 삭제에서 지워지는 행이 정확히 같다.
    """
    return LoginSessionModel.expires_at > func.now()


def _user_record(row: RowMapping) -> UserRecord:
    """_USER_COLUMNS를 읽은 행의 사용자."""
    return UserRecord(
        id=row["id"],
        email=row["email"],
        google_sub=row["google_sub"],
        display_name=row["display_name"],
    )


def get_auth_repository(session: DbSession) -> AuthRepository:
    """요청의 세션으로 만든 repository. FastAPI 의존성이다."""
    return AuthRepository(session)
