"""Alembic이 마이그레이션을 실행하는 환경. 비동기 엔진(asyncpg)으로 접속한다.

접속 주소는 호출한 쪽이 Alembic 설정의 sqlalchemy.url로 넘긴 것이 있으면 그것을 쓰고,
없으면 설정 클래스의 database_url을 쓴다. alembic.ini에는 주소를 적지 않는다.
통합 테스트는 컨테이너의 주소를 직접 넘기며(tests/support/postgres.py의 alembic_config),
그때에는 설정 클래스를 읽지 않는다.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection

from app.core.config import get_settings
from app.core.database import create_engine

config = context.config

if config.config_file_name is not None:
    # 이미 만들어진 로거를 끄지 않는다.
    # 테스트 안에서 마이그레이션을 돌려도 다른 로거가 살아 있어야 한다.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# 기능 테이블의 모델이 아직 없으므로 비워 둔다. 모델이 생기면 그 MetaData를 넣는다.
target_metadata = None


def database_url() -> str:
    return config.get_main_option("sqlalchemy.url") or get_settings().database_url


def run_migrations_offline() -> None:
    """데이터베이스에 접속하지 않고 SQL만 출력한다(`alembic upgrade head --sql`)."""
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    engine = create_engine(database_url())
    try:
        async with engine.connect() as connection:
            await connection.run_sync(do_run_migrations)
    finally:
        await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
