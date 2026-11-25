"""로그인 service와 실제 repository를 이은 통합 테스트.

docs/backlog/epic-1/testcase.md의 S1.3 가운데 데이터베이스의 변화를 확인한다. 리디렉션 주소와 쿠키의
속성은 라우터의 테스트가 확인한다.

테스트마다 요청 하나처럼 한 트랜잭션 안에서 service를 부르고 커밋한 뒤, 다른 연결로 테이블을 읽는다.
get_db_session(app/core/database.py)은 결과가 실패여도 경로가 정상으로 끝나면 커밋하므로, 실패한
경우에도 커밋한다. 그래야 허용 목록을 확인하기 전에 쓴 것이 드러난다. 준비와 확인은 repository를
거치지 않고 SQL로 한다.
"""

import hashlib
import logging
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.auth.repository import AuthRepository
from app.auth.service import AuthService, LoginRejected, LoginResult, LoginSucceeded
from app.core.ports import Identity
from tests.auth.fakes import READER_IDENTITY, FakeIdentityProvider

pytestmark = pytest.mark.integration

SESSION_TTL = timedelta(hours=336)
HOUR = timedelta(hours=1)

STATE = "stateValue7f1c"
NONCE = "nonceValue2b8d"
CODE_VERIFIER = "verifierValue9e4a"
STATE_COOKIE = f"{STATE}.{NONCE}.{CODE_VERIFIER}"
CODE = "googleCode5c3f"

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{43}")
LOGIN_FAILED = LoginRejected(error="LOGIN_FAILED")


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


async def login(
    session_factory: async_sessionmaker[AsyncSession],
    identity: Identity,
    *,
    current_session_token: str | None = None,
) -> LoginResult:
    """가짜 신원이 identity를 돌려줄 때, 맞는 state 쿠키와 code로 결과 처리를 하고 커밋한다."""
    provider = FakeIdentityProvider(identity)
    async with session_factory() as session:
        service = AuthService(AuthRepository(session), provider, session_ttl=SESSION_TTL)
        result = await service.complete_login(
            state_cookie=STATE_COOKIE,
            state=STATE,
            code=CODE,
            error=None,
            current_session_token=current_session_token,
        )
        await session.commit()
    return result


async def insert_allowed_email(engine: AsyncEngine, email: str, role: str = "user") -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text("INSERT INTO allowed_emails (email, role) VALUES (:email, :role)"),
            {"email": email, "role": role},
        )


async def insert_user(
    engine: AsyncEngine, email: str, google_sub: str, display_name: str | None = None
) -> uuid.UUID:
    async with engine.begin() as connection:
        user_id = await connection.scalar(
            text(
                "INSERT INTO users (email, google_sub, display_name) "
                "VALUES (:email, :google_sub, :display_name) RETURNING id"
            ),
            {"email": email, "google_sub": google_sub, "display_name": display_name},
        )
    assert isinstance(user_id, uuid.UUID)
    return user_id


async def insert_login_session(
    engine: AsyncEngine, token_hash: str, user_id: uuid.UUID, expires_in: timedelta
) -> None:
    """만료 시각이 데이터베이스의 now()에 expires_in을 더한 로그인 상태. 음수면 이미 만료됐다."""
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO login_sessions (token_hash, user_id, expires_at) "
                "VALUES (:token_hash, :user_id, now() + CAST(:expires_in AS interval))"
            ),
            {"token_hash": token_hash, "user_id": user_id, "expires_in": expires_in},
        )


async def user_rows(engine: AsyncEngine) -> set[tuple[Any, ...]]:
    """users의 모든 행과 모든 컬럼."""
    async with engine.connect() as connection:
        rows = await connection.execute(
            text("SELECT id, email, google_sub, display_name, created_at FROM users")
        )
        return {tuple(row) for row in rows}


async def login_session_rows(engine: AsyncEngine) -> list[tuple[Any, ...]]:
    """login_sessions의 (token_hash, user_id, expires_at)."""
    async with engine.connect() as connection:
        rows = await connection.execute(
            text("SELECT token_hash, user_id, expires_at FROM login_sessions")
        )
        return [tuple(row) for row in rows]


async def login_session_hashes(engine: AsyncEngine) -> set[str]:
    return {row[0] for row in await login_session_rows(engine)}


# --- TC-1.3.1 ---------------------------------------------------------------


async def test_success_creates_user_and_login_session_with_hash_of_cookie(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """TC-1.3.1. 쿠키 값은 저장하지 않고 그 SHA-256만 저장한다."""
    await insert_allowed_email(db_engine, "reader@example.com")

    result = await login(db_session_factory, READER_IDENTITY)
    now = datetime.now(UTC)

    assert isinstance(result, LoginSucceeded)
    assert TOKEN_PATTERN.fullmatch(result.session_token)
    users = await user_rows(db_engine)
    assert len(users) == 1
    [(user_id, email, google_sub, display_name, _)] = users
    assert (email, google_sub, display_name) == ("reader@example.com", "1234567890", "독자")
    [(token_hash, session_user_id, expires_at)] = await login_session_rows(db_engine)
    assert token_hash != result.session_token
    assert token_hash == sha256(result.session_token)
    assert session_user_id == user_id
    assert abs(expires_at - (now + SESSION_TTL)) < timedelta(minutes=1)


# --- TC-1.3.2 ---------------------------------------------------------------


async def test_not_allowed_creates_no_user_and_no_login_session(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """TC-1.3.2. 허용 목록을 확인하기 전에 users에 쓰면 커밋한 뒤에 드러난다."""
    await insert_allowed_email(db_engine, "other@example.com")

    result = await login(db_session_factory, READER_IDENTITY)

    assert result == LoginRejected(error="NOT_ALLOWED")
    assert await user_rows(db_engine) == set()
    assert await login_session_rows(db_engine) == []


# --- TC-1.3.7 ---------------------------------------------------------------


async def test_email_is_lowercased_before_allowlist_check_and_storage(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """TC-1.3.7."""
    await insert_allowed_email(db_engine, "reader@example.com")

    result = await login(
        db_session_factory, Identity("1234567890", "Reader@Example.com", True, "독자")
    )

    assert isinstance(result, LoginSucceeded)
    assert [row[1] for row in await user_rows(db_engine)] == ["reader@example.com"]
    assert await login_session_hashes(db_engine) == {sha256(result.session_token)}


# --- TC-1.3.10 --------------------------------------------------------------


async def test_relogin_from_other_device_updates_name_and_keeps_both_login_sessions(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """TC-1.3.10. 이름을 바꾼 뒤 옛 쿠키 없이 다시 로그인한다."""
    await insert_allowed_email(db_engine, "reader@example.com")
    first = await login(
        db_session_factory, Identity("1234567890", "reader@example.com", True, "옛 이름")
    )
    [(user_id, *_)] = await user_rows(db_engine)

    second = await login(
        db_session_factory, Identity("1234567890", "reader@example.com", True, "새 이름")
    )

    assert isinstance(first, LoginSucceeded)
    assert isinstance(second, LoginSucceeded)
    assert first.session_token != second.session_token
    assert {row[:4] for row in await user_rows(db_engine)} == {
        (user_id, "reader@example.com", "1234567890", "새 이름")
    }
    rows = await login_session_rows(db_engine)
    assert {row[0] for row in rows} == {sha256(first.session_token), sha256(second.session_token)}
    assert {row[1] for row in rows} == {user_id}


# --- TC-1.3.14 --------------------------------------------------------------


@pytest.mark.parametrize(
    ("identity", "cause"),
    [
        pytest.param(
            Identity("sub-B", "reader@example.com", True, "다른 계정"),
            "google_sub가 다른",
            id="same-email-other-sub",
        ),
        pytest.param(
            Identity("sub-A", "other@example.com", True, "다른 계정"),
            "이메일이 다른",
            id="same-sub-other-email",
        ),
    ],
)
async def test_rejects_when_only_email_or_only_sub_matches(
    caplog: pytest.LogCaptureFixture,
    db_engine: AsyncEngine,
    db_session_factory: async_sessionmaker[AsyncSession],
    identity: Identity,
    cause: str,
) -> None:
    """TC-1.3.14. 고유 제약 위반으로 끝나지 않고 LOGIN_FAILED이며, 처음의 행은 값까지 그대로다."""
    await insert_allowed_email(db_engine, "reader@example.com")
    await insert_allowed_email(db_engine, "other@example.com")
    await insert_user(db_engine, "reader@example.com", "sub-A", "원래 이름")
    users_before = await user_rows(db_engine)
    caplog.set_level(logging.DEBUG)

    result = await login(db_session_factory, identity)

    assert result == LOGIN_FAILED
    assert await user_rows(db_engine) == users_before
    assert await login_session_rows(db_engine) == []
    assert any(
        cause in record.getMessage()
        for record in caplog.records
        if record.name == "app.auth.service"
    )


# --- TC-1.3.15 --------------------------------------------------------------


async def test_relogin_with_old_cookie_deletes_only_that_login_session(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """TC-1.3.15의 저장소 부분. 쿠키 X의 행만 지우고, 다른 기기의 Z와 새 Y가 남는다."""
    await insert_allowed_email(db_engine, "reader@example.com")
    user_id = await insert_user(db_engine, "reader@example.com", "1234567890", "독자")
    cookie_x = "cookieXValue4d2e"
    await insert_login_session(db_engine, sha256(cookie_x), user_id, HOUR)
    await insert_login_session(db_engine, sha256("cookieZValue8a1f"), user_id, HOUR)

    result = await login(db_session_factory, READER_IDENTITY, current_session_token=cookie_x)

    assert isinstance(result, LoginSucceeded)
    assert await login_session_hashes(db_engine) == {
        sha256("cookieZValue8a1f"),
        sha256(result.session_token),
    }


# --- TC-1.3.16 --------------------------------------------------------------


async def test_success_deletes_only_own_expired_login_sessions(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """TC-1.3.16. P의 만료된 행 둘만 지우고, P의 유효한 행과 새 행, Q의 만료된 행은 남긴다."""
    await insert_allowed_email(db_engine, "reader@example.com")
    await insert_allowed_email(db_engine, "other@example.com")
    p_id = await insert_user(db_engine, "reader@example.com", "1234567890", "독자")
    q_id = await insert_user(db_engine, "other@example.com", "sub-Q")
    await insert_login_session(db_engine, "p-expired-1", p_id, -HOUR)
    await insert_login_session(db_engine, "p-expired-2", p_id, -2 * HOUR)
    await insert_login_session(db_engine, "p-valid", p_id, HOUR)
    await insert_login_session(db_engine, "q-expired", q_id, -HOUR)

    result = await login(db_session_factory, READER_IDENTITY)

    assert isinstance(result, LoginSucceeded)
    assert await login_session_hashes(db_engine) == {
        "p-valid",
        "q-expired",
        sha256(result.session_token),
    }
