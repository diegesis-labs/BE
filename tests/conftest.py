"""여러 테스트 파일이 함께 쓰는 fixture.

통합 테스트용 데이터베이스는 testcontainers로 띄운다(docs/ADR.md의 ADR-011).
아래 fixture는 autouse가 아니므로, 컨테이너는 이 fixture를 요청한 통합 테스트가 있을 때만 뜬다.
단위 테스트만 돌릴 때에는 Docker가 필요 없다.

앱을 만드는 테스트는 `app_env`로 설정을 준비한다. 설정을 준비하는 방법을 테스트마다 따로 두지
않는다.
"""

from collections.abc import Iterator

import pytest
from alembic import command
from testcontainers.community.postgres import PostgresContainer

from app.core.config import get_settings
from tests.support.postgres import alembic_config, start_database
from tests.support.settings import (
    SETTING_ENV_NAMES,
    TEST_FRONTEND_URL,
    TEST_GOOGLE_CLIENT_ID,
    TEST_GOOGLE_CLIENT_SECRET,
    UNREACHABLE_DATABASE_URL,
)

# 아래 fixture를 쓰는 테스트 실행을 따로 돌려서 그 결과(건너뛰기인지 오류인지)를 확인하는 데 쓴다
# (tests/support/test_postgres.py의 TC-0.2.5).
pytest_plugins = ["pytester"]


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


@pytest.fixture
def app_env(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    """테스트용 설정값(tests/support/settings.py)으로 get_settings()가 읽히는 상태를 만든다.

    - 작업 경로를 빈 임시 폴더로 옮긴다. 개발자의 `.env`에 다른 값이 있으면 테스트가 그 값으로
      돌기 때문이다. 테스트가 쓰는 tmp_path와는 다른 폴더라서, 테스트가 만든 파일도 보이지 않는다.
    - 설정 클래스의 환경변수를 모두 지운 뒤 기본값이 없는 값만 넣는다. 나머지는 기본값으로 읽힌다.
    - DATABASE_URL은 닿지 않는 주소다. 단위 테스트가 실수로 데이터베이스에 닿으면 연결 오류로
      드러난다. 통합 테스트는 이 값을 컨테이너의 주소로 바꾼다.
    """
    monkeypatch.chdir(tmp_path_factory.mktemp("app-env-cwd"))
    for name in SETTING_ENV_NAMES:
        # pydantic-settings는 이름의 대소문자를 가리지 않고 읽는다.
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name.lower(), raising=False)
    monkeypatch.setenv("DATABASE_URL", UNREACHABLE_DATABASE_URL)
    monkeypatch.setenv("FRONTEND_URL", TEST_FRONTEND_URL)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", TEST_GOOGLE_CLIENT_ID)
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", TEST_GOOGLE_CLIENT_SECRET)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
