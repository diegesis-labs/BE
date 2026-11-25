"""로그인 결과 처리 경로와 실제 repository를 이은 통합 테스트.

docs/backlog/epic-1/testcase.md의 S1.3 가운데 데이터베이스의 변화를 경로로 다시 확인한다(TC-1.3.1,
TC-1.3.2, TC-1.3.7, TC-1.3.10, TC-1.3.14, TC-1.3.16). 그리고 커밋이 실패하면 로그인 상태의 쿠키가
나가지 않는 것을 확인한다.

- 앱은 create_app()으로 만들고, 신원만 app.dependency_overrides[get_identity_provider]로
  FakeIdentityProvider를 끼운다. 저장소와 트랜잭션은 실제의 것(get_auth_repository, DbSession)이다.
- 준비와 확인은 앱과 다른 엔진으로, SQL 문장 하나마다 트랜잭션 하나로 한다. 만료 시각은
  데이터베이스의 now()를 기준으로 정한다.
- 쿠키의 속성은 Set-Cookie 헤더를 직접 읽어서 확인한다. 요청의 쿠키는 Cookie 헤더로 직접 붙이고,
  결과 처리를 부르기 전에 TestClient의 쿠키 저장소를 비운다.
"""

import asyncio
import hashlib
import logging
import re
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.router import get_identity_provider
from app.core.database import create_engine
from app.core.ports import Identity
from app.main import create_app
from tests.auth.fakes import READER_IDENTITY, FakeIdentityProvider
from tests.support.settings import TEST_FRONTEND_URL

pytestmark = pytest.mark.integration

CALLBACK_PATH = "/api/auth/google/callback"
OAUTH_STATE_COOKIE = "diegesis_oauth_state"
SESSION_COOKIE = "diegesis_session"

SUCCESS_LOCATION = f"{TEST_FRONTEND_URL}/"
NOT_ALLOWED_LOCATION = f"{TEST_FRONTEND_URL}/login?error=NOT_ALLOWED"
LOGIN_FAILED_LOCATION = f"{TEST_FRONTEND_URL}/login?error=LOGIN_FAILED"

STATE = "routerState7f1c"
NONCE = "routerNonce2b8d"
CODE_VERIFIER = "routerVerifier9e4a"
CODE = "routerGoogleCode5c3f"
STATE_COOKIE = f"{STATE}.{NONCE}.{CODE_VERIFIER}"

SESSION_TTL = timedelta(hours=336)
HOUR = timedelta(hours=1)
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{43}")

READER = "reader@example.com"
OTHER = "other@example.com"


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


# --- SQL ----------------------------------------------------------------------


def execute(url: str, statement: str, **params: Any) -> list[dict[str, Any]]:
    """SQL 문장 하나를 한 트랜잭션에서 실행하고 커밋한다. 행을 돌려주는 문장이면 그 행들을 준다."""

    async def run() -> list[dict[str, Any]]:
        engine = create_engine(url)
        try:
            async with engine.begin() as connection:
                result = await connection.execute(text(statement), params)
                if not result.returns_rows:
                    return []
                return [dict(row) for row in result.mappings()]
        finally:
            await engine.dispose()

    return asyncio.run(run())


def allow(url: str, email: str) -> None:
    execute(url, "INSERT INTO allowed_emails (email, role) VALUES (:email, 'user')", email=email)


def add_user(url: str, email: str, google_sub: str, display_name: str | None = None) -> uuid.UUID:
    [row] = execute(
        url,
        "INSERT INTO users (email, google_sub, display_name) "
        "VALUES (:email, :google_sub, :display_name) RETURNING id",
        email=email,
        google_sub=google_sub,
        display_name=display_name,
    )
    return row["id"]


def add_login_session(url: str, token_hash: str, user_id: uuid.UUID, expires_in: timedelta) -> None:
    """만료 시각이 데이터베이스의 now()에 expires_in을 더한 로그인 상태. 음수면 이미 만료됐다."""
    execute(
        url,
        "INSERT INTO login_sessions (token_hash, user_id, expires_at) "
        "VALUES (:token_hash, :user_id, now() + :expires_in)",
        token_hash=token_hash,
        user_id=user_id,
        expires_in=expires_in,
    )


def user_rows(url: str) -> list[dict[str, Any]]:
    """users의 모든 행과 모든 컬럼."""
    return execute(url, "SELECT * FROM users ORDER BY email")


def login_session_rows(url: str) -> list[dict[str, Any]]:
    """login_sessions의 모든 행과 모든 컬럼."""
    return execute(url, "SELECT * FROM login_sessions ORDER BY token_hash")


def login_session_hashes(url: str) -> set[str]:
    return {row["token_hash"] for row in login_session_rows(url)}


# --- HTTP ---------------------------------------------------------------------


def session_cookies(response: httpx.Response) -> list[tuple[str, list[str]]]:
    """응답의 Set-Cookie 가운데 로그인 상태의 쿠키. (값, 받은 표기 그대로의 속성 목록)이다."""
    found: list[tuple[str, list[str]]] = []
    for header in response.headers.get_list("set-cookie"):
        pair, *attributes = header.split(";")
        name, _, value = pair.partition("=")
        if name.strip() == SESSION_COOKIE:
            found.append((value.strip(), [attribute.strip() for attribute in attributes]))
    return found


def callback(client: TestClient, *, session_cookie: str | None = None) -> httpx.Response:
    """state 쿠키, state, code가 모두 맞는 결과 처리. 결과는 가짜 신원이 정한다."""
    client.cookies.clear()
    cookie = f"{OAUTH_STATE_COOKIE}={STATE_COOKIE}"
    if session_cookie is not None:
        cookie += f"; {SESSION_COOKIE}={session_cookie}"
    return client.get(
        CALLBACK_PATH, params={"code": CODE, "state": STATE}, headers={"Cookie": cookie}
    )


def assert_redirect(response: httpx.Response, location: str) -> None:
    assert response.status_code == 302, response.text
    assert response.headers["location"] == location


def logged_in_token(response: httpx.Response) -> str:
    """로그인에 성공한 응답이 심은 로그인 상태의 쿠키 값."""
    assert_redirect(response, SUCCESS_LOCATION)
    [(token, _)] = session_cookies(response)
    return token


@pytest.fixture
def provider() -> FakeIdentityProvider:
    return FakeIdentityProvider()


def make_app(provider: FakeIdentityProvider) -> FastAPI:
    app = create_app()
    app.dependency_overrides[get_identity_provider] = lambda: provider
    return app


@pytest.fixture
def client(clean_db: str, provider: FakeIdentityProvider) -> Iterator[TestClient]:
    with TestClient(make_app(provider), follow_redirects=False) as test_client:
        yield test_client


# --- TC-1.3.1 ---------------------------------------------------------------


def test_success_sets_session_cookie_and_stores_only_its_hash(
    clean_db: str, client: TestClient
) -> None:
    """TC-1.3.1."""
    allow(clean_db, READER)

    response = callback(client)
    now = datetime.now(UTC)

    assert_redirect(response, SUCCESS_LOCATION)
    [(token, attributes)] = session_cookies(response)
    assert sorted(attributes) == sorted(["HttpOnly", "SameSite=Lax", "Path=/", "Max-Age=1209600"])
    assert TOKEN_PATTERN.fullmatch(token)
    [user] = user_rows(clean_db)
    assert (user["email"], user["google_sub"], user["display_name"]) == (
        READER,
        "1234567890",
        "독자",
    )
    [session] = login_session_rows(clean_db)
    assert session["token_hash"] != token
    assert session["token_hash"] == sha256(token)
    assert session["user_id"] == user["id"]
    assert abs(session["expires_at"] - (now + SESSION_TTL)) < timedelta(minutes=1)


# --- TC-1.3.2 ---------------------------------------------------------------


def test_not_allowed_sets_no_cookie_and_writes_nothing(clean_db: str, client: TestClient) -> None:
    """TC-1.3.2."""
    allow(clean_db, OTHER)

    response = callback(client)

    assert_redirect(response, NOT_ALLOWED_LOCATION)
    assert session_cookies(response) == []
    assert user_rows(clean_db) == []
    assert login_session_rows(clean_db) == []


# --- TC-1.3.7 ---------------------------------------------------------------


def test_email_is_lowercased(
    clean_db: str, client: TestClient, provider: FakeIdentityProvider
) -> None:
    """TC-1.3.7."""
    allow(clean_db, READER)
    provider.identity = Identity("1234567890", "Reader@Example.com", True, "독자")

    token = logged_in_token(callback(client))

    assert [row["email"] for row in user_rows(clean_db)] == [READER]
    assert login_session_hashes(clean_db) == {sha256(token)}


# --- TC-1.3.10 --------------------------------------------------------------


def test_relogin_from_other_device_updates_name_and_keeps_both_login_sessions(
    clean_db: str, client: TestClient, provider: FakeIdentityProvider
) -> None:
    """TC-1.3.10. 이름을 바꾼 뒤 옛 쿠키 없이 다시 로그인한다."""
    allow(clean_db, READER)
    provider.identity = Identity("1234567890", READER, True, "옛 이름")
    first = logged_in_token(callback(client))
    [before] = user_rows(clean_db)

    provider.identity = Identity("1234567890", READER, True, "새 이름")
    second = logged_in_token(callback(client))

    assert first != second
    [after] = user_rows(clean_db)
    assert after == {**before, "display_name": "새 이름"}
    rows = login_session_rows(clean_db)
    assert {row["token_hash"] for row in rows} == {sha256(first), sha256(second)}
    assert {row["user_id"] for row in rows} == {before["id"]}


# --- TC-1.3.14 --------------------------------------------------------------


@pytest.mark.parametrize(
    ("identity", "cause"),
    [
        pytest.param(
            Identity("sub-B", READER, True, "다른 계정"), "google_sub가 다른", id="same-email"
        ),
        pytest.param(Identity("sub-A", OTHER, True, "다른 계정"), "이메일이 다른", id="same-sub"),
    ],
)
def test_rejects_when_only_email_or_only_sub_matches(
    caplog: pytest.LogCaptureFixture,
    clean_db: str,
    client: TestClient,
    provider: FakeIdentityProvider,
    identity: Identity,
    cause: str,
) -> None:
    """TC-1.3.14. 고유 제약 위반의 500이 아니라 302 LOGIN_FAILED다.

    처음의 행은 값까지 그대로다.
    """
    allow(clean_db, READER)
    allow(clean_db, OTHER)
    add_user(clean_db, READER, "sub-A", "원래 이름")
    users_before = user_rows(clean_db)
    provider.identity = identity
    caplog.set_level(logging.DEBUG)

    response = callback(client)

    assert_redirect(response, LOGIN_FAILED_LOCATION)
    assert session_cookies(response) == []
    assert user_rows(clean_db) == users_before
    assert login_session_rows(clean_db) == []
    assert any(
        cause in record.getMessage()
        for record in caplog.records
        if record.name == "app.auth.service"
    )


# --- TC-1.3.16 --------------------------------------------------------------


def test_success_deletes_only_own_expired_login_sessions(clean_db: str, client: TestClient) -> None:
    """TC-1.3.16. P의 만료된 행 둘만 지우고, P의 유효한 행과 새 행, Q의 만료된 행은 남긴다."""
    allow(clean_db, READER)
    allow(clean_db, OTHER)
    p_id = add_user(clean_db, READER, "1234567890", "독자")
    q_id = add_user(clean_db, OTHER, "sub-Q")
    add_login_session(clean_db, "p-expired-1", p_id, -HOUR)
    add_login_session(clean_db, "p-expired-2", p_id, -2 * HOUR)
    add_login_session(clean_db, "p-valid", p_id, HOUR)
    add_login_session(clean_db, "q-expired", q_id, -HOUR)

    token = logged_in_token(callback(client))

    assert login_session_hashes(clean_db) == {"p-valid", "q-expired", sha256(token)}


# --- 커밋이 실패하면 쿠키가 나가지 않는다 -----------------------------------------


def test_commit_failure_sends_no_session_cookie(
    monkeypatch: pytest.MonkeyPatch, clean_db: str, provider: FakeIdentityProvider
) -> None:
    """커밋이 실패하면 302와 로그인 상태의 쿠키 대신 500이 나간다.

    저장되지 않은 로그인 상태의 쿠키를 받으면, 사용자는 로그인한 줄 알지만 다음 요청에서 401을
    받는다. 그래서 커밋은 응답을 보내기 전에 끝나야 한다.
    """
    allow(clean_db, READER)

    async def failing_commit(self: AsyncSession) -> None:
        raise RuntimeError("커밋 실패를 흉내 냄")

    monkeypatch.setattr(AsyncSession, "commit", failing_commit)

    with TestClient(
        make_app(provider), follow_redirects=False, raise_server_exceptions=False
    ) as client:
        response = callback(client)

    assert response.status_code == 500
    assert session_cookies(response) == []
    assert user_rows(clean_db) == []
    assert login_session_rows(clean_db) == []
    # 비교 대상: 신원은 허용 목록에 있으므로, 커밋이 되었다면 로그인에 성공했을 것이다.
    assert provider.identity == READER_IDENTITY
    assert len(provider.exchange_code_calls) == 1
