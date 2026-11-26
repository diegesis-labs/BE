"""허용 목록, 사용자, 로그인 상태의 테이블을 만든다.

스키마는 docs/ARCHITECTURE.md 6절에 있고, 모델은 app/auth/models.py에 있다. 기본값은 모두
데이터베이스 쪽에 둔다. README의 허용 목록 SQL이 created_at을 적지 않고 넣기 때문이다.

Revision ID: 8bb879ed9e41
Revises: d98e11845e03
Create Date: 2026-11-25 14:20:49.028537

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8bb879ed9e41"
down_revision: str | Sequence[str] | None = "d98e11845e03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "allowed_emails",
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("email = lower(email)", name=op.f("ck_allowed_emails_email_lowercase")),
        sa.CheckConstraint("role IN ('user', 'admin')", name=op.f("ck_allowed_emails_role")),
        sa.PrimaryKeyConstraint("email", name=op.f("pk_allowed_emails")),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("google_sub", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("email = lower(email)", name=op.f("ck_users_email_lowercase")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
        sa.UniqueConstraint("google_sub", name=op.f("uq_users_google_sub")),
    )
    op.create_table(
        "login_sessions",
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_login_sessions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("token_hash", name=op.f("pk_login_sessions")),
    )
    op.create_index(op.f("ix_login_sessions_user_id"), "login_sessions", ["user_id"])


def downgrade() -> None:
    # vector 확장은 이 리비전이 켠 것이 아니므로 지우지 않는다.
    op.drop_index(op.f("ix_login_sessions_user_id"), table_name="login_sessions")
    op.drop_table("login_sessions")
    op.drop_table("users")
    op.drop_table("allowed_emails")
