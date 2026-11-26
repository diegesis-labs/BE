"""허용 목록, 사용자, 로그인 상태의 테이블 제약과 마이그레이션 (TC-1.1.1 ~ TC-1.1.5).

스키마는 docs/ARCHITECTURE.md 6절에 있다. TC-1.1.1 ~ TC-1.1.4는 마이그레이션을 끝까지 적용한
데이터베이스(`clean_db`)에 SQL로 넣어 본다. README의 허용 목록 SQL처럼, 데이터베이스가 기본값을 주는
컬럼(`id`, `created_at`)은 적지 않는다.

거부될 때에는 예외가 났다는 것만 보지 않고, 데이터베이스가 알려 준 위반의 종류와 제약의 이름
(NOT NULL은 컬럼의 이름)까지 확인한다. 그러지 않으면 다른 이유로 거부된 것도 통과한다.
"""

import asyncio
import uuid
from typing import NamedTuple

import asyncpg
import pytest
from alembic import command
from asyncpg.exceptions import CheckViolationError, NotNullViolationError, UniqueViolationError
from sqlalchemy import make_url, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine
from testcontainers.community.postgres import PostgresContainer

from app.core.database import create_engine
from tests.support.postgres import alembic_config

pytestmark = pytest.mark.integration

INSERT_ALLOWED_EMAIL = "INSERT INTO allowed_emails (email, role) VALUES (:email, :role)"
INSERT_USER = "INSERT INTO users (email, google_sub) VALUES (:email, :google_sub)"

# 이 Epic의 마이그레이션 바로 앞의 리비전(vector 확장을 켜는 리비전).
VECTOR_REVISION = "d98e11845e03"
AUTH_TABLES = frozenset({"allowed_emails", "users", "login_sessions"})


async def execute(engine: AsyncEngine, statement: str, **params: object) -> None:
    """문장 하나를 한 트랜잭션으로 실행하고 커밋한다."""
    async with engine.begin() as connection:
        await connection.execute(text(statement), params)


class Violation(NamedTuple):
    """데이터베이스가 알려 준 제약 위반. kind는 위반의 종류에 대응하는 asyncpg의 예외 클래스다."""

    kind: type[asyncpg.PostgresError]
    table: str | None
    constraint: str | None
    column: str | None


async def rejection(engine: AsyncEngine, statement: str, **params: object) -> Violation:
    """문장이 무결성 제약 위반으로 거부되는지 보고, 데이터베이스가 알려 준 위반을 돌려준다."""
    with pytest.raises(IntegrityError) as caught:
        await execute(engine, statement, **params)
    # SQLAlchemy는 asyncpg의 예외를 DBAPI의 예외로 감싸고, 원래의 예외를 __cause__에 둔다.
    assert caught.value.orig is not None
    cause = caught.value.orig.__cause__
    assert isinstance(cause, asyncpg.PostgresError)
    # 위반한 테이블, 제약, 컬럼은 서버가 보낸 필드로만 온다. asyncpg는 이 값을 속성으로도 두지만
    # 타입 선언이 없으므로 as_dict()로 읽는다.
    fields = cause.as_dict()
    return Violation(
        kind=type(cause),
        table=fields.get("table_name"),
        constraint=fields.get("constraint_name"),
        column=fields.get("column_name"),
    )


# --- TC-1.1.1 ---------------------------------------------------------------


async def test_allowed_emails_rejects_email_with_uppercase(db_engine: AsyncEngine) -> None:
    violation = await rejection(
        db_engine, INSERT_ALLOWED_EMAIL, email="Reader@Example.com", role="user"
    )

    assert violation.kind is CheckViolationError
    assert violation.constraint == "ck_allowed_emails_email_lowercase"
    # 소문자로 적은 같은 이메일은 들어간다.
    await execute(db_engine, INSERT_ALLOWED_EMAIL, email="reader@example.com", role="user")


async def test_users_rejects_email_with_uppercase(db_engine: AsyncEngine) -> None:
    violation = await rejection(
        db_engine, INSERT_USER, email="Reader@Example.com", google_sub="sub-A"
    )

    assert violation.kind is CheckViolationError
    assert violation.constraint == "ck_users_email_lowercase"
    # 소문자로 적은 같은 이메일은 들어간다.
    await execute(db_engine, INSERT_USER, email="reader@example.com", google_sub="sub-A")


# --- TC-1.1.2 ---------------------------------------------------------------


async def test_allowed_emails_rejects_unknown_role(db_engine: AsyncEngine) -> None:
    violation = await rejection(
        db_engine, INSERT_ALLOWED_EMAIL, email="reader@example.com", role="owner"
    )

    assert violation.kind is CheckViolationError
    assert violation.constraint == "ck_allowed_emails_role"


async def test_allowed_emails_accepts_user_and_admin_roles(db_engine: AsyncEngine) -> None:
    await execute(db_engine, INSERT_ALLOWED_EMAIL, email="reader@example.com", role="user")
    await execute(db_engine, INSERT_ALLOWED_EMAIL, email="admin@example.com", role="admin")

    async with db_engine.connect() as connection:
        rows = (
            await connection.execute(text("SELECT email, role FROM allowed_emails ORDER BY email"))
        ).all()

    assert [tuple(row) for row in rows] == [
        ("admin@example.com", "admin"),
        ("reader@example.com", "user"),
    ]


# --- TC-1.1.3 ---------------------------------------------------------------


async def test_users_rejects_duplicate_email(db_engine: AsyncEngine) -> None:
    await execute(db_engine, INSERT_USER, email="reader@example.com", google_sub="sub-A")

    violation = await rejection(
        db_engine, INSERT_USER, email="reader@example.com", google_sub="sub-B"
    )

    assert violation.kind is UniqueViolationError
    assert violation.constraint == "uq_users_email"


async def test_users_rejects_duplicate_google_sub(db_engine: AsyncEngine) -> None:
    await execute(db_engine, INSERT_USER, email="reader@example.com", google_sub="sub-A")

    violation = await rejection(
        db_engine, INSERT_USER, email="other@example.com", google_sub="sub-A"
    )

    assert violation.kind is UniqueViolationError
    assert violation.constraint == "uq_users_google_sub"


async def test_users_rejects_missing_google_sub(db_engine: AsyncEngine) -> None:
    violation = await rejection(
        db_engine, "INSERT INTO users (email) VALUES (:email)", email="reader@example.com"
    )

    assert violation.kind is NotNullViolationError
    assert violation.table == "users"
    assert violation.column == "google_sub"


# --- TC-1.1.4 ---------------------------------------------------------------


async def test_deleting_user_deletes_all_their_login_sessions(db_engine: AsyncEngine) -> None:
    insert_session = (
        "INSERT INTO login_sessions (token_hash, user_id, expires_at) "
        "VALUES (:token_hash, :user_id, now() + interval '1 day')"
    )
    async with db_engine.begin() as connection:
        reader_id = await connection.scalar(
            text(f"{INSERT_USER} RETURNING id"),
            {"email": "reader@example.com", "google_sub": "sub-A"},
        )
        other_id = await connection.scalar(
            text(f"{INSERT_USER} RETURNING id"),
            {"email": "other@example.com", "google_sub": "sub-B"},
        )
        await connection.execute(
            text(insert_session),
            [
                {"token_hash": "reader-phone", "user_id": reader_id},
                {"token_hash": "reader-laptop", "user_id": reader_id},
                {"token_hash": "other-phone", "user_id": other_id},
            ],
        )

    async with db_engine.begin() as connection:
        await connection.execute(text("DELETE FROM users WHERE id = :id"), {"id": reader_id})

    async with db_engine.connect() as connection:
        remaining = (
            await connection.execute(text("SELECT token_hash FROM login_sessions"))
        ).scalars()
        remaining = set(remaining)

    # 지운 사용자의 로그인 상태는 둘 다 지워지고, 다른 사용자의 로그인 상태는 남는다.
    assert remaining == {"other-phone"}


# --- TC-1.1.5 ---------------------------------------------------------------


class SchemaState(NamedTuple):
    auth_tables: frozenset[str]
    has_vector: bool


async def schema_state(url: str) -> SchemaState:
    """세 테이블 가운데 있는 것과 vector 확장이 있는지."""
    engine = create_engine(url)
    try:
        async with engine.connect() as connection:
            tables = (
                await connection.execute(
                    text(
                        "SELECT tablename FROM pg_tables "
                        "WHERE schemaname = 'public' AND tablename = ANY(:names)"
                    ),
                    {"names": sorted(AUTH_TABLES)},
                )
            ).scalars()
            has_vector = await connection.scalar(
                text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')")
            )
            return SchemaState(frozenset(tables), bool(has_vector))
    finally:
        await engine.dispose()


async def execute_autocommit(url: str, statement: str) -> None:
    """트랜잭션 밖에서 실행해야 하는 문장(CREATE DATABASE, DROP DATABASE)을 실행한다."""
    engine = create_engine(url)
    try:
        async with engine.connect() as connection:
            connection = await connection.execution_options(isolation_level="AUTOCOMMIT")
            await connection.execute(text(statement))
    finally:
        await engine.dispose()


def test_downgrade_removes_auth_tables_keeping_vector_and_upgrade_restores_them(
    postgres_container: PostgresContainer,
) -> None:
    """이 Epic의 마이그레이션을 되돌렸다가 다시 올린다.

    다른 테스트가 함께 쓰는 데이터베이스(`database_url`)가 아니라, 같은 컨테이너에 새로 만든
    데이터베이스에서 한다. 되돌리는 도중에 실패하면 함께 쓰는 데이터베이스에 테이블이 없는 채로 남아
    뒤의 통합 테스트가 엉뚱한 이유로 깨지기 때문이다.

    동기 테스트로 둔다. migrations/env.py가 asyncio.run()을 부르므로, 이벤트 루프가 도는 비동기
    테스트 안에서는 Alembic 명령을 부를 수 없다.
    """
    admin_url = postgres_container.get_connection_url()
    database = f"migration_roundtrip_{uuid.uuid4().hex}"
    url = make_url(admin_url).set(database=database).render_as_string(hide_password=False)
    config = alembic_config(url)

    create_database = f'CREATE DATABASE "{database}"'
    # 테스트가 끝나면 지운다. 남은 연결이 있어도 지울 수 있게 FORCE를 붙인다.
    remove_database = f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)'

    asyncio.run(execute_autocommit(admin_url, create_database))
    try:
        command.upgrade(config, "head")
        after_first_upgrade = asyncio.run(schema_state(url))
        command.downgrade(config, VECTOR_REVISION)
        after_downgrade = asyncio.run(schema_state(url))
        command.upgrade(config, "head")
        after_upgrade = asyncio.run(schema_state(url))
    finally:
        asyncio.run(execute_autocommit(admin_url, remove_database))

    assert after_first_upgrade == SchemaState(AUTH_TABLES, has_vector=True)
    assert after_downgrade == SchemaState(frozenset(), has_vector=True)
    assert after_upgrade == SchemaState(AUTH_TABLES, has_vector=True)
