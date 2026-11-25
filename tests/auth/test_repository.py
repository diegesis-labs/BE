"""허용 목록, 사용자, 로그인 상태를 읽고 쓰는 repository의 통합 테스트.

TC-1.1.6과 메서드마다의 동작을 확인한다. 스키마와 로그인 상태의 수명은 docs/ARCHITECTURE.md 6절에
있다. 테스트의 준비와 확인은 repository를 거치지 않고 SQL로 한다. repository가 틀려도 준비와 확인이
함께 틀리지 않게 하기 위해서다.

repository는 커밋하지 않는다. 그래서 repository가 쓴 것을 확인하는 테스트는 그 세션을 직접 커밋한
뒤에 다른 연결로 읽는다. 시각은 데이터베이스의 now()를 기준으로 한 시간씩 앞뒤로 둔다. 컨테이너와
이 컴퓨터의 시계가 조금 어긋나도 결과가 바뀌지 않게 하기 위해서다.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.auth.repository import ActiveLogin, AllowedEmail, AuthRepository, UserRecord

pytestmark = pytest.mark.integration

HOUR = timedelta(hours=1)


async def insert_allowed_email(engine: AsyncEngine, email: str, role: str) -> datetime:
    """허용 목록에 한 줄을 넣고, 데이터베이스가 정한 created_at을 돌려준다.

    README의 SQL처럼 created_at을 적지 않는다. 한 줄마다 트랜잭션이 따로라서 created_at도 저마다
    다르다.
    """
    async with engine.begin() as connection:
        created_at = await connection.scalar(
            text(
                "INSERT INTO allowed_emails (email, role) VALUES (:email, :role) "
                "RETURNING created_at"
            ),
            {"email": email, "role": role},
        )
    assert isinstance(created_at, datetime)
    return created_at


async def insert_user(
    engine: AsyncEngine, email: str, google_sub: str, display_name: str | None = None
) -> UserRecord:
    async with engine.begin() as connection:
        user_id = await connection.scalar(
            text(
                "INSERT INTO users (email, google_sub, display_name) "
                "VALUES (:email, :google_sub, :display_name) RETURNING id"
            ),
            {"email": email, "google_sub": google_sub, "display_name": display_name},
        )
    assert isinstance(user_id, uuid.UUID)
    return UserRecord(id=user_id, email=email, google_sub=google_sub, display_name=display_name)


async def insert_login_session(
    engine: AsyncEngine, token_hash: str, user_id: uuid.UUID, expires_in: timedelta
) -> datetime:
    """로그인 상태를 넣고 created_at을 돌려준다.

    만료 시각은 데이터베이스의 now()에 expires_in을 더한 시각이다. expires_in이 음수이면 이미 만료된
    로그인 상태다.
    """
    async with engine.begin() as connection:
        created_at = await connection.scalar(
            text(
                "INSERT INTO login_sessions (token_hash, user_id, expires_at) "
                "VALUES (:token_hash, :user_id, now() + CAST(:expires_in AS interval)) "
                "RETURNING created_at"
            ),
            {"token_hash": token_hash, "user_id": user_id, "expires_in": expires_in},
        )
    assert isinstance(created_at, datetime)
    return created_at


async def login_session_rows(engine: AsyncEngine) -> set[tuple[object, ...]]:
    """login_sessions의 모든 행과 모든 컬럼."""
    async with engine.connect() as connection:
        rows = await connection.execute(
            text("SELECT token_hash, user_id, expires_at, created_at FROM login_sessions")
        )
        return {tuple(row) for row in rows}


async def login_session_hashes(engine: AsyncEngine) -> set[str]:
    async with engine.connect() as connection:
        rows = await connection.execute(text("SELECT token_hash FROM login_sessions"))
        return set(rows.scalars())


async def user_rows(engine: AsyncEngine) -> set[tuple[object, ...]]:
    """users의 모든 행과 모든 컬럼."""
    async with engine.connect() as connection:
        rows = await connection.execute(
            text("SELECT id, email, google_sub, display_name, created_at FROM users")
        )
        return {tuple(row) for row in rows}


# --- TC-1.1.6 ---------------------------------------------------------------


async def test_find_active_login_skips_expired_login_session(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await insert_allowed_email(db_engine, "reader@example.com", "user")
    reader = await insert_user(db_engine, "reader@example.com", "sub-reader")
    await insert_login_session(db_engine, "expired-hash", reader.id, -HOUR)
    await insert_login_session(db_engine, "valid-hash", reader.id, HOUR)

    async with db_session_factory() as session:
        repository = AuthRepository(session)
        expired = await repository.find_active_login("expired-hash")
        valid = await repository.find_active_login("valid-hash")
        unknown = await repository.find_active_login("unknown-hash")

    # 만료된 행은 지워지지 않고 남아 있지만, 조회 결과에는 나오지 않는다.
    assert await login_session_hashes(db_engine) == {"expired-hash", "valid-hash"}
    assert expired is None
    assert unknown is None
    assert valid is not None
    assert valid.user == reader


# --- find_active_login ------------------------------------------------------


async def test_find_active_login_returns_user_and_their_allowed_email_row(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """로그인 상태의 사용자와, 그 사용자의 이메일로 찾은 허용 목록 행을 함께 돌려준다.

    허용 목록의 행은 사람마다 역할과 created_at이 다르게 넣는다. 다른 사람의 행을 돌려주거나 역할을
    지어내는 구현을 걸러 내기 위해서다. 허용 목록에서 가장 먼저 넣은 행은 로그인 상태가 없는 사람의
    것이다.
    """
    await insert_allowed_email(db_engine, "pending@example.com", "admin")
    reader_allowed_at = await insert_allowed_email(db_engine, "reader@example.com", "user")
    admin_allowed_at = await insert_allowed_email(db_engine, "admin@example.com", "admin")
    reader = await insert_user(db_engine, "reader@example.com", "sub-reader", "읽는 사람")
    admin = await insert_user(db_engine, "admin@example.com", "sub-admin")
    # 허용 목록에 없는 사람. 로그인한 뒤에 허용 목록에서 빠진 경우다.
    removed = await insert_user(db_engine, "removed@example.com", "sub-removed", "빠진 사람")
    reader_logged_in_at = await insert_login_session(db_engine, "reader-hash", reader.id, HOUR)
    admin_logged_in_at = await insert_login_session(db_engine, "admin-hash", admin.id, HOUR)
    removed_logged_in_at = await insert_login_session(db_engine, "removed-hash", removed.id, HOUR)

    async with db_session_factory() as session:
        repository = AuthRepository(session)
        found_reader = await repository.find_active_login("reader-hash")
        found_admin = await repository.find_active_login("admin-hash")
        found_removed = await repository.find_active_login("removed-hash")

    assert found_reader == ActiveLogin(
        user=reader,
        session_created_at=reader_logged_in_at,
        allowed=AllowedEmail(email="reader@example.com", role="user", created_at=reader_allowed_at),
    )
    assert found_admin == ActiveLogin(
        user=admin,
        session_created_at=admin_logged_in_at,
        allowed=AllowedEmail(email="admin@example.com", role="admin", created_at=admin_allowed_at),
    )
    assert found_removed == ActiveLogin(
        user=removed, session_created_at=removed_logged_in_at, allowed=None
    )


async def test_find_active_login_does_not_change_login_sessions(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """조회한 뒤에 커밋해도 login_sessions의 모든 값이 그대로다.

    로그인 상태의 만료 시각은 늘리지 않는다(ADR-027).
    """
    await insert_allowed_email(db_engine, "reader@example.com", "user")
    reader = await insert_user(db_engine, "reader@example.com", "sub-reader")
    await insert_login_session(db_engine, "valid-hash", reader.id, HOUR)
    await insert_login_session(db_engine, "expired-hash", reader.id, -HOUR)
    before = await login_session_rows(db_engine)

    async with db_session_factory() as session:
        repository = AuthRepository(session)
        assert await repository.find_active_login("valid-hash") is not None
        assert await repository.find_active_login("expired-hash") is None
        # 요청이 정상으로 끝나면 get_db_session이 커밋하는 것처럼 커밋한다.
        await session.commit()

    assert await login_session_rows(db_engine) == before


# --- get_allowed_email ------------------------------------------------------


async def test_get_allowed_email_returns_the_row_for_exactly_that_email(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    reader_allowed_at = await insert_allowed_email(db_engine, "reader@example.com", "user")
    admin_allowed_at = await insert_allowed_email(db_engine, "admin@example.com", "admin")

    async with db_session_factory() as session:
        repository = AuthRepository(session)
        reader = await repository.get_allowed_email("reader@example.com")
        admin = await repository.get_allowed_email("admin@example.com")
        unknown = await repository.get_allowed_email("nobody@example.com")
        # 소문자로 바꾸는 것은 service의 일이다. repository가 몰래 바꾸면 service가 바꾸지 않는
        # 결함을 테스트가 놓친다.
        mixed_case = await repository.get_allowed_email("Reader@Example.com")

    assert reader == AllowedEmail(
        email="reader@example.com", role="user", created_at=reader_allowed_at
    )
    assert admin == AllowedEmail(
        email="admin@example.com", role="admin", created_at=admin_allowed_at
    )
    assert unknown is None
    assert mixed_case is None


# --- find_users_by_email_or_sub ---------------------------------------------


async def test_find_users_by_email_or_sub_returns_every_row_matching_either(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """이메일이 같거나 google_sub가 같은 행을 모두 돌려준다(ADR-027)."""
    first = await insert_user(db_engine, "first@example.com", "sub-first", "첫째")
    second = await insert_user(db_engine, "second@example.com", "sub-second")
    # 어느 질의에도 걸리지 않는 행. 이 행이 나오면 조건을 보지 않은 것이다.
    await insert_user(db_engine, "third@example.com", "sub-third")

    async with db_session_factory() as session:
        repository = AuthRepository(session)

        async def found(email: str, google_sub: str) -> set[UserRecord]:
            records = await repository.find_users_by_email_or_sub(
                email=email, google_sub=google_sub
            )
            assert isinstance(records, list)
            # 같은 행을 두 번 돌려주지 않는다.
            assert len(records) == len(set(records))
            return set(records)

        both_match_one_row = await found("first@example.com", "sub-first")
        email_only = await found("first@example.com", "sub-unknown")
        sub_only = await found("unknown@example.com", "sub-first")
        email_and_sub_on_different_rows = await found("first@example.com", "sub-second")
        neither = await found("unknown@example.com", "sub-unknown")
        # 이메일은 받은 그대로 비교한다.
        mixed_case_email = await found("First@Example.com", "sub-unknown")

    assert both_match_one_row == {first}
    assert email_only == {first}
    assert sub_only == {first}
    assert email_and_sub_on_different_rows == {first, second}
    assert neither == set()
    assert mixed_case_email == set()


# --- create_user, update_display_name ---------------------------------------


async def test_create_user_inserts_a_row_and_returns_it(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with db_session_factory() as session:
        repository = AuthRepository(session)
        named = await repository.create_user(
            email="reader@example.com", google_sub="sub-reader", display_name="읽는 사람"
        )
        unnamed = await repository.create_user(
            email="quiet@example.com", google_sub="sub-quiet", display_name=None
        )
        await session.commit()

    assert named.email == "reader@example.com"
    assert named.google_sub == "sub-reader"
    assert named.display_name == "읽는 사람"
    assert unnamed.display_name is None
    assert named.id != unnamed.id
    # 돌려준 값이 데이터베이스의 행과 같다. id는 데이터베이스가 정한 것이다.
    stored = {row[:4] for row in await user_rows(db_engine)}
    assert stored == {
        (named.id, "reader@example.com", "sub-reader", "읽는 사람"),
        (unnamed.id, "quiet@example.com", "sub-quiet", None),
    }


async def test_update_display_name_changes_only_that_user(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    reader = await insert_user(db_engine, "reader@example.com", "sub-reader", "옛 이름")
    other = await insert_user(db_engine, "other@example.com", "sub-other", "다른 사람")

    async with db_session_factory() as session:
        await AuthRepository(session).update_display_name(reader.id, "새 이름")
        await session.commit()
    after_rename = {row[:4] for row in await user_rows(db_engine)}

    async with db_session_factory() as session:
        await AuthRepository(session).update_display_name(reader.id, None)
        await session.commit()
    after_clear = {row[:4] for row in await user_rows(db_engine)}

    assert after_rename == {
        (reader.id, "reader@example.com", "sub-reader", "새 이름"),
        (other.id, "other@example.com", "sub-other", "다른 사람"),
    }
    assert after_clear == {
        (reader.id, "reader@example.com", "sub-reader", None),
        (other.id, "other@example.com", "sub-other", "다른 사람"),
    }


# --- add_login_session ------------------------------------------------------


async def test_add_login_session_stores_given_values_and_database_created_at(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """created_at은 데이터베이스의 now()다.

    관문이 이 값을 allowed_emails.created_at과 비교하므로 같은 시계에서 나와야 한다.

    PostgreSQL의 now()는 트랜잭션이 시작한 시각이므로, 같은 트랜잭션에서 읽은 now()와 같아야 한다.
    파이썬의 시각을 넘기면 이 값과 어긋난다.
    """
    reader = await insert_user(db_engine, "reader@example.com", "sub-reader")
    expires_at = datetime(2030, 1, 2, 3, 4, 5, 678901, tzinfo=UTC)

    async with db_session_factory() as session:
        database_now = await session.scalar(select(func.now()))
        await AuthRepository(session).add_login_session(
            token_hash="new-hash", user_id=reader.id, expires_at=expires_at
        )
        await session.commit()

    assert await login_session_rows(db_engine) == {
        ("new-hash", reader.id, expires_at, database_now)
    }


# --- delete_login_session ---------------------------------------------------


async def test_delete_login_session_deletes_only_that_row(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    reader = await insert_user(db_engine, "reader@example.com", "sub-reader")
    other = await insert_user(db_engine, "other@example.com", "sub-other")
    await insert_login_session(db_engine, "reader-phone", reader.id, HOUR)
    await insert_login_session(db_engine, "reader-laptop", reader.id, HOUR)
    await insert_login_session(db_engine, "other-phone", other.id, HOUR)

    async with db_session_factory() as session:
        await AuthRepository(session).delete_login_session("reader-phone")
        await session.commit()

    # 같은 사람이 다른 기기에서 만든 로그인 상태는 남는다.
    assert await login_session_hashes(db_engine) == {"reader-laptop", "other-phone"}


async def test_delete_login_session_ignores_unknown_hash(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    reader = await insert_user(db_engine, "reader@example.com", "sub-reader")
    await insert_login_session(db_engine, "reader-phone", reader.id, HOUR)
    before = await login_session_rows(db_engine)

    async with db_session_factory() as session:
        # 예외를 내지 않는다.
        await AuthRepository(session).delete_login_session("unknown-hash")
        await session.commit()

    assert await login_session_rows(db_engine) == before


# --- delete_expired_login_sessions ------------------------------------------


async def test_delete_expired_login_sessions_deletes_only_that_users_expired_rows(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    reader = await insert_user(db_engine, "reader@example.com", "sub-reader")
    other = await insert_user(db_engine, "other@example.com", "sub-other")
    await insert_login_session(db_engine, "reader-expired-1", reader.id, -HOUR)
    await insert_login_session(db_engine, "reader-expired-2", reader.id, -2 * HOUR)
    await insert_login_session(db_engine, "reader-valid", reader.id, HOUR)
    await insert_login_session(db_engine, "other-expired", other.id, -HOUR)
    await insert_login_session(db_engine, "other-valid", other.id, HOUR)

    async with db_session_factory() as session:
        await AuthRepository(session).delete_expired_login_sessions(reader.id)
        await session.commit()

    # 그 사용자의 만료되지 않은 행, 다른 사용자의 행은 만료 여부와 관계없이 남는다.
    assert await login_session_hashes(db_engine) == {
        "reader-valid",
        "other-expired",
        "other-valid",
    }


# --- 트랜잭션의 경계 --------------------------------------------------------


async def test_repository_does_not_commit_on_its_own(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """쓰는 메서드를 모두 부른 뒤 커밋하지 않고 되돌리면 데이터베이스는 부르기 전과 같다.

    트랜잭션의 경계는 get_db_session이 정한다. 로그인에 성공했을 때의 쓰기가 한 트랜잭션이어야 하기
    때문이다(E1 S1.3). 메서드가 안에서 커밋하면 중간에 실패했을 때 반쯤 쓴 상태가 남는다.
    """
    reader = await insert_user(db_engine, "reader@example.com", "sub-reader", "옛 이름")
    await insert_login_session(db_engine, "reader-expired", reader.id, -HOUR)
    await insert_login_session(db_engine, "reader-valid", reader.id, HOUR)
    users_before = await user_rows(db_engine)
    sessions_before = await login_session_rows(db_engine)

    async with db_session_factory() as session:
        repository = AuthRepository(session)
        newcomer = await repository.create_user(
            email="newcomer@example.com", google_sub="sub-newcomer", display_name=None
        )
        await repository.add_login_session(
            token_hash="newcomer-hash",
            user_id=newcomer.id,
            expires_at=datetime.now(UTC) + 336 * HOUR,
        )
        await repository.update_display_name(reader.id, "새 이름")
        await repository.delete_login_session("reader-valid")
        await repository.delete_expired_login_sessions(reader.id)
        await session.rollback()

    assert await user_rows(db_engine) == users_before
    assert await login_session_rows(db_engine) == sessions_before
