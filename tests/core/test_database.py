"""데이터베이스 연결과 마이그레이션의 통합 테스트 (TC-0.2.1 ~ TC-0.2.4).

tests/conftest.py의 fixture가 testcontainers로 띄운 컨테이너에만 접속한다. 개발자의 `.env`나
compose로 띄운 개발용 데이터베이스에는 접속하지 않는다(docs/DEVELOPMENT.md 4.3절).
"""

import asyncio
import math
from pathlib import Path

import pytest
import yaml
from alembic import command
from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, MetaData, String, Table, select, text
from testcontainers.community.postgres import PostgresContainer

from app.core.config import get_settings
from app.core.database import create_engine, create_session_factory
from tests.support.postgres import alembic_config

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
