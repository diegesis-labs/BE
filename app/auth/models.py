"""허용 목록, 사용자, 로그인 상태의 테이블 선언. 판정하는 로직은 두지 않는다.

스키마는 docs/ARCHITECTURE.md 6절에 있다. 기본값은 모두 데이터베이스 쪽(server_default)에 둔다.
README의 허용 목록 SQL은 created_at을 적지 않고 넣으며, 관문은 login_sessions.created_at과
allowed_emails.created_at을 비교하므로 두 시각이 같은 시계(데이터베이스의 now())에서 나와야 한다.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base


class AllowedEmailModel(Base):
    """허용 목록. SQL로만 넣고 뺀다(docs/ADR.md의 ADR-024).

    users와 외래 키로 잇지 않는다. 아직 로그인하지 않은 사람도 허용 목록에 있을 수 있고, 목록에서
    빠진 사람의 users 행은 남아야 하기 때문이다.
    """

    __tablename__ = "allowed_emails"
    __table_args__ = (
        CheckConstraint("email = lower(email)", name="email_lowercase"),
        CheckConstraint("role IN ('user', 'admin')", name="role"),
    )

    email: Mapped[str] = mapped_column(Text, primary_key=True)
    role: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserModel(Base):
    """허용 목록을 통과해 로그인한 적이 있는 사람.

    이메일과 google_sub의 쌍으로 식별한다(docs/ADR.md의 ADR-027).
    """

    __tablename__ = "users"
    __table_args__ = (CheckConstraint("email = lower(email)", name="email_lowercase"),)

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=func.gen_random_uuid()
    )
    email: Mapped[str] = mapped_column(Text, unique=True)
    google_sub: Mapped[str] = mapped_column(Text, unique=True)
    display_name: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LoginSessionModel(Base):
    """로그인 상태. 쿠키의 값이 아니라 그 SHA-256 해시를 담는다."""

    __tablename__ = "login_sessions"

    token_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
