"""데이터베이스 연결과 마이그레이션의 통합 테스트 (TC-0.2.1 ~ TC-0.2.4).

tests/conftest.py의 fixture가 testcontainers로 띄운 컨테이너에만 접속한다. 개발자의 `.env`나
compose로 띄운 개발용 데이터베이스에는 접속하지 않는다(docs/DEVELOPMENT.md 4.3절).
"""

import asyncio
import hashlib
import logging
import math
from pathlib import Path

import pytest
import yaml
from alembic import command
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, MetaData, String, Table, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession
from testcontainers.community.postgres import PostgresContainer

from app.core.config import get_settings
from app.core.database import DbSession, create_engine, create_session_factory
from app.core.errors import AppError
from app.main import create_app
from tests.support.postgres import alembic_config
from tests.support.settings import TEST_FRONTEND_URL

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]

# docs/ARCHITECTURE.md 4절의 반복 스캔이 pgvector 0.8.0부터 있다.
MINIMUM_PGVECTOR = (0, 8, 0)

# vector 확장을 켜는 리비전(migrations/versions/d98e11845e03_enable_pgvector_extension.py).
VECTOR_REVISION = "d98e11845e03"

# 닿을 수 없는 주소. 마이그레이션이 이 주소를 쓰면 접속에 실패한다.
UNREACHABLE_DATABASE_URL = "postgresql+asyncpg://nobody:nothing@127.0.0.1:1/nowhere"


def version_tuple(version: str) -> tuple[int, ...]:
    """'0.10.2'를 (0, 10, 2)로 바꾼다. 문자열로 비교하면 '0.10.0' < '0.8.0'이 참이 된다."""
    return tuple(int(part) for part in version.split("."))


async def vector_extension_version(url: str) -> str | None:
    """설치된 vector 확장의 버전. 확장이 없으면 None이다."""
    engine = create_engine(url)
    try:
        async with engine.connect() as connection:
            return await connection.scalar(
                text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            )
    finally:
        await engine.dispose()


# --- TC-0.2.1 ---------------------------------------------------------------


async def test_migration_installs_vector_extension_0_8_0_or_newer(database_url: str) -> None:
    version = await vector_extension_version(database_url)

    assert version is not None, "마이그레이션을 끝까지 적용했는데 vector 확장이 없다"
    assert version_tuple(version) >= MINIMUM_PGVECTOR, f"pgvector {version}은 0.8.0보다 낮다"


# --- TC-0.2.2 ---------------------------------------------------------------


async def test_cosine_distance_search_returns_the_row_nearest_by_cosine(
    database_url: str,
) -> None:
    """코사인 거리로 가장 가까운 행을 찾는다.

    픽스처는 유클리드 거리로 찾으면 답이 달라지게 만들었다.

    질의 [1, 0]에 대해
      A [10, 1]  — 코사인 거리 ≈ 0.005, 유클리드 거리 ≈ 9.06
      B [0, 0.5] — 코사인 거리 1,      유클리드 거리 ≈ 1.12
    """
    metadata = MetaData()
    probe = Table(
        "vector_probe",
        metadata,
        Column("name", String, primary_key=True),
        Column("embedding", Vector(2), nullable=False),
        prefixes=["TEMPORARY"],
    )
    query = [1.0, 0.0]
    cosine_distance = probe.c.embedding.cosine_distance(query)

    engine = create_engine(database_url)
    session_factory = create_session_factory(engine)
    try:
        async with session_factory() as session:
            # 임시 테이블은 그 연결에서만 보이므로, 같은 세션의 연결로 만들고 질의한다.
            connection = await session.connection()
            await connection.run_sync(probe.create)
            await session.execute(
                probe.insert(),
                [
                    {"name": "A", "embedding": [10.0, 1.0]},
                    {"name": "B", "embedding": [0.0, 0.5]},
                ],
            )

            nearest = (
                await session.execute(
                    select(probe.c.name, cosine_distance).order_by(cosine_distance).limit(1)
                )
            ).one()
            nearest_by_euclid = await session.scalar(
                select(probe.c.name).order_by(probe.c.embedding.l2_distance(query)).limit(1)
            )
            await session.rollback()
    finally:
        await engine.dispose()

    # 전제: 이 픽스처에서는 유클리드 거리로 찾은 답이 B다. 그래야 아래의 단언이 두 거리를 가려낸다.
    assert nearest_by_euclid == "B"

    name, distance = nearest
    assert name == "A"
    # 거리의 값도 코사인 거리여야 한다.
    # 음의 내적(<#>)으로 정렬해도 A가 먼저 나오므로 순서만으로는 모자라다.
    assert distance == pytest.approx(1 - 10 / math.sqrt(101))


# --- TC-0.2.3 ---------------------------------------------------------------


async def test_downgrade_removes_and_upgrade_restores_vector_extension(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """vector 확장을 켜는 리비전을 한 단계 되돌리면 vector 확장이 없고, 다시 올리면 있다.

    그 위에 쌓인 리비전도 함께 되돌린다. 이 테스트는 다른 테스트와 같은 컨테이너의 상태를 바꾼다.
    실패하더라도 끝날 때 head로 되돌린다.
    """
    # 마이그레이션은 넘겨준 주소에만 접속해야 한다. 설정 클래스가 읽는 주소를
    # 닿을 수 없는 곳으로 두어, env.py가 넘겨준 주소 대신 설정을 읽으면 이 테스트가 실패하게 한다.
    monkeypatch.setenv("DATABASE_URL", UNREACHABLE_DATABASE_URL)
    get_settings.cache_clear()
    config = alembic_config(database_url)

    # env.py는 asyncio.run()으로 마이그레이션을 돌린다.
    # 이 테스트의 이벤트 루프 안에서는 그것을 부를 수 없으므로 다른 스레드에서 실행한다.
    try:
        await asyncio.to_thread(command.downgrade, config, f"{VECTOR_REVISION}-1")
        after_downgrade = await vector_extension_version(database_url)
        await asyncio.to_thread(command.upgrade, config, "head")
        after_upgrade = await vector_extension_version(database_url)
    finally:
        await asyncio.to_thread(command.upgrade, config, "head")
        get_settings.cache_clear()

    assert after_downgrade is None
    assert after_upgrade is not None


# --- TC-0.2.4 ---------------------------------------------------------------


def test_database_container_runs_the_compose_db_image(
    postgres_container: PostgresContainer,
) -> None:
    """통합 테스트가 띄운 컨테이너의 이미지는 compose.yaml의 db 서비스의 이미지와 같다."""
    # tests/support/postgres.py의 db_image()를 거치지 않고 compose.yaml을 직접 읽는다.
    # db_image()가 compose.yaml을 읽지 않고 이미지를 따로 적어 두어도 이 테스트가 걸러 낸다.
    compose = yaml.safe_load((REPO_ROOT / "compose.yaml").read_text(encoding="utf-8"))
    expected = compose["services"]["db"]["image"]

    running = postgres_container.get_wrapped_container()
    running.reload()

    assert running.attrs["Config"]["Image"] == expected


# --- 모델과 마이그레이션 ----------------------------------------------------


def test_models_match_migrations(database_url: str) -> None:
    """마이그레이션을 끝까지 적용한 데이터베이스와 모델(Base.metadata) 사이에 차이가 없다.

    `alembic check`와 같다. migrations/env.py가 넘기는 target_metadata로 비교하므로, env.py가 모델을
    싣지 않아도 실패한다. 차이가 있으면 AutogenerateDiffsDetected가 나고, 그 메시지에 차이의 목록이
    있다.

    동기 테스트로 둔다. env.py가 asyncio.run()을 부르므로, 이벤트 루프가 도는 비동기 테스트 안에서는
    Alembic 명령을 부를 수 없다.
    """
    command.check(alembic_config(database_url))


# --- 요청마다의 세션과 트랜잭션 (get_db_session) ----------------------------
#
# 아래 테스트는 create_app()으로 만든 앱에 테스트 안에서만 쓰는 경로를 붙여서 확인한다. 경로는
# DbSession으로 세션을 받는다. 쓰는 요청에는 프론트엔드와 같은 Origin을 붙인다. 실제 프론트엔드의
# 요청과 같은 모양으로 보내기 위해서다(docs/API.md 2.4절).

TEST_ROUTE = "/test/database"
WRITTEN_EMAIL = "written@example.com"
SAME_ORIGIN = {"Origin": TEST_FRONTEND_URL}


def app_with_writing_route(failure: Exception | None = None) -> FastAPI:
    """allowed_emails에 한 행을 넣는 경로를 붙인 앱.

    failure를 주면 행을 넣은 뒤에 그 예외를 낸다.
    """
    app = create_app()

    @app.post(TEST_ROUTE)
    async def write(session: DbSession) -> None:
        await session.execute(
            text("INSERT INTO allowed_emails (email, role) VALUES (:email, 'user')"),
            {"email": WRITTEN_EMAIL},
        )
        if failure is not None:
            raise failure

    return app


def app_with_reading_route() -> FastAPI:
    """allowed_emails의 행 수를 읽는 경로를 붙인 앱."""
    app = create_app()

    @app.get(TEST_ROUTE)
    async def read(session: DbSession) -> int:
        return int(await session.scalar(text("SELECT count(*) FROM allowed_emails")) or 0)

    return app


async def allowed_emails(url: str) -> list[str]:
    """allowed_emails에 남은 이메일. 앱과 다른 엔진과 연결로 읽는다."""
    engine = create_engine(url)
    try:
        async with engine.connect() as connection:
            rows = await connection.execute(text("SELECT email FROM allowed_emails"))
            return list(rows.scalars())
    finally:
        await engine.dispose()


def test_db_session_commits_when_route_finishes(clean_db: str) -> None:
    with TestClient(app_with_writing_route()) as client:
        response = client.post(TEST_ROUTE, headers=SAME_ORIGIN)

    assert response.status_code == 200
    assert asyncio.run(allowed_emails(clean_db)) == [WRITTEN_EMAIL]


@pytest.mark.parametrize(
    ("failure", "status_code"),
    [
        (RuntimeError("경로에서 예상하지 못한 문제"), 500),
        # 정해진 에러 응답으로 끝나는 경우에도 그 전에 쓴 것은 남지 않는다.
        (AppError(403, "NOT_ALLOWED", "허용 목록에 없는 계정입니다."), 403),
    ],
)
def test_db_session_rolls_back_when_route_raises(
    clean_db: str, failure: Exception, status_code: int
) -> None:
    with TestClient(app_with_writing_route(failure), raise_server_exceptions=False) as client:
        response = client.post(TEST_ROUTE, headers=SAME_ORIGIN)

    assert response.status_code == status_code
    assert asyncio.run(allowed_emails(clean_db)) == []


def test_db_session_commit_failure_is_500(clean_db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """커밋은 응답을 보내기 전에 끝난다. 그래서 커밋이 실패하면 클라이언트는 500을 받는다.

    FastAPI의 yield 의존성은 기본값(scope="request")에서 응답을 보낸 뒤에 정리되므로, 그렇게 두면
    커밋이 실패해도 클라이언트는 이미 200을 받는다.
    """

    async def failing_commit(self: AsyncSession) -> None:
        raise RuntimeError("커밋 실패")

    monkeypatch.setattr(AsyncSession, "commit", failing_commit)

    with TestClient(app_with_writing_route(), raise_server_exceptions=False) as client:
        response = client.post(TEST_ROUTE, headers=SAME_ORIGIN)

    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"
    assert asyncio.run(allowed_emails(clean_db)) == []


def test_each_app_has_its_own_engine(clean_db: str) -> None:
    """앱 두 개를 차례로 만들어 번갈아 요청해도 모두 성공한다.

    TestClient는 앱마다 다른 스레드의 이벤트 루프에서 앱을 돌린다. 엔진을 모듈 전역에 하나만 두면,
    앞의 앱의 이벤트 루프에서 만든 연결을 뒤의 앱이 다시 써서 asyncpg가 실패한다. 두 앱을 함께
    띄워 둔 채로 번갈아 요청하므로, 앱이 내려갈 때 전역 엔진을 정리하는 구현도 걸러 낸다.
    """
    with (
        TestClient(app_with_reading_route(), raise_server_exceptions=False) as first,
        TestClient(app_with_reading_route(), raise_server_exceptions=False) as second,
    ):
        responses = [client.get(TEST_ROUTE) for client in (first, second, first, second)]

    assert [response.status_code for response in responses] == [200, 200, 200, 200]
    assert [response.json() for response in responses] == [0, 0, 0, 0]


def test_db_session_does_not_connect_until_first_query(app_env: None) -> None:
    """세션을 받기만 하고 질의하지 않는 경로는 데이터베이스에 닿지 않는다.

    `app_env`의 DATABASE_URL은 닿지 않는 주소다. 세션을 만들거나 커밋할 때 접속하면 500이 난다.
    이후의 관문은 쿠키가 없으면 데이터베이스에 닿지 않고 401을 내야 한다. 이 테스트는 컨테이너를
    쓰지 않지만, get_db_session의 테스트를 한곳에 두기 위해 이 파일에 둔다.
    """
    app = create_app()

    @app.get(TEST_ROUTE)
    async def untouched(session: DbSession) -> None:
        return None

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(TEST_ROUTE)

    assert response.status_code == 200


# --- 문장 오류에 바인딩 값을 싣지 않는다 (2차 리뷰 SEC-1) -------------------------
#
# 데이터베이스가 문장을 거부하면(ADR-030의 500) 그 예외가 서버 로그에 추적과 함께 남는다. 엔진이
# 예외에 바인딩 값을 담으면 허용 목록 밖의 이메일이나 token_hash가 로그에 실린다. 아래 문장은 없는
# 테이블을 읽으므로 데이터베이스의 오류 문장에는 바인딩 값이 나오지 않는다. 그래서 로그에 값이
# 나온다면 엔진이 담은 것이다.

LOGGED_EMAIL = "victim.pii@example.com"
LOGGED_TOKEN_HASH = hashlib.sha256(b"cookie-value-of-victim").hexdigest()
FAILING_STATEMENT = text(
    "SELECT 1 FROM no_such_table WHERE email = :email AND token_hash = :token_hash"
)
FAILING_PARAMETERS = {"email": LOGGED_EMAIL, "token_hash": LOGGED_TOKEN_HASH}


async def test_statement_error_from_engine_carries_no_bound_values(database_url: str) -> None:
    engine = create_engine(database_url)
    try:
        async with engine.connect() as connection:
            with pytest.raises(DBAPIError) as raised:
                await connection.execute(FAILING_STATEMENT, FAILING_PARAMETERS)
    finally:
        await engine.dispose()

    message = str(raised.value)
    # 전제: 데이터베이스가 문장을 거부했고, 예외의 문장에는 그 SQL이 있다.
    assert "no_such_table" in message
    assert LOGGED_EMAIL not in message
    assert LOGGED_TOKEN_HASH not in message


def test_server_error_log_of_failed_statement_has_no_bound_values(
    clean_db: str, caplog: pytest.LogCaptureFixture
) -> None:
    app = create_app()

    @app.get(TEST_ROUTE)
    async def failing(session: DbSession) -> None:
        await session.execute(FAILING_STATEMENT, FAILING_PARAMETERS)

    caplog.set_level(logging.DEBUG)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(TEST_ROUTE)

    assert response.status_code == 500
    # 전제: 처리되지 않은 예외가 추적과 함께 로그에 남았다.
    assert "처리되지 않은 예외" in caplog.text
    assert "no_such_table" in caplog.text
    assert LOGGED_EMAIL not in caplog.text
    assert LOGGED_TOKEN_HASH not in caplog.text
