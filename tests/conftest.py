"""여러 테스트 파일이 함께 쓰는 fixture.

통합 테스트용 데이터베이스는 testcontainers로 띄운다(docs/ADR.md의 ADR-011).
아래 fixture는 autouse가 아니므로, 컨테이너는 이 fixture를 요청한 통합 테스트가 있을 때만 뜬다.
단위 테스트만 돌릴 때에는 Docker가 필요 없다.
"""

from collections.abc import Iterator

import pytest
from alembic import command
from testcontainers.community.postgres import PostgresContainer

from tests.support.postgres import alembic_config, start_database


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[PostgresContainer]:
    """compose.yaml의 db 이미지로 띄운 데이터베이스 컨테이너. 테스트가 모두 끝나면 지운다."""
    container = start_database()
    try:
        yield container
    finally:
        container.stop()


@pytest.fixture(scope="session")
def database_url(postgres_container: PostgresContainer) -> str:
    """마이그레이션을 끝까지 적용한 컨테이너의 주소. asyncpg 형식(postgresql+asyncpg://...)이다.

    개발자의 `.env`나 개발용 데이터베이스가 아니라 이 주소에만 접속해야 한다
    (docs/DEVELOPMENT.md 4.3절).
    """
    url = postgres_container.get_connection_url()
    command.upgrade(alembic_config(url), "head")
    return url
