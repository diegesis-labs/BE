"""pgvector 확장을 켠다.

장면과 음악 구간의 벡터를 저장하고 검색하는 데 쓴다(docs/ADR.md의 ADR-002). 테이블은 만들지 않는다.
기능 테이블은 그 기능의 Epic이 요구사항과 함께 설계한다.

Revision ID: d98e11845e03
Revises:
Create Date: 2026-11-23 11:21:24.077826

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d98e11845e03"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    # CASCADE를 붙이지 않는다. 확장을 쓰는 테이블이 남아 있으면 지우지 않고 실패하게 둔다.
    op.execute("DROP EXTENSION IF EXISTS vector")
