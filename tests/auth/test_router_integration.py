"""로그인, 로그아웃, 내 정보 경로와 실제 repository를 이은 통합 테스트.

docs/backlog/epic-1/testcase.md의 S1.3 가운데 데이터베이스의 변화를 경로로 다시 확인한다(TC-1.3.1,
TC-1.3.2, TC-1.3.7, TC-1.3.10, TC-1.3.11, TC-1.3.14 ~ TC-1.3.16). 그리고 커밋이 실패하면 로그인
상태의 쿠키가 나가지 않는 것을 확인한다. 로그아웃과 내 정보는 S1.4의 TC-1.4.3(마지막 부분),
TC-1.4.6, TC-1.4.8을 실제 로그인으로 확인한다.

- 로그인 상태는 테이블에 직접 넣지 않고, 가짜 신원과 올바른 diegesis_oauth_state를 붙여 로그인 결과
  처리 경로를 실제로 불러서 만든다.
- SQL로 허용 목록이나 역할을 바꾸는 테스트는 앱과 TestClient를 다시 만들지 않는다. 앱이 허용
  목록이나 역할을 메모리에 담아 두면 드러나야 하기 때문이다(ADR-024).

- 앱은 create_app()으로 만들고, 신원만 app.dependency_overrides[get_identity_provider]로
  FakeIdentityProvider를 끼운다. 저장소와 트랜잭션은 실제의 것(get_auth_repository, DbSession)이다.
- 준비와 확인은 앱과 다른 엔진으로, SQL 문장 하나마다 트랜잭션 하나로 한다. 만료 시각은
  데이터베이스의 now()를 기준으로 정한다.
- 쿠키의 속성은 Set-Cookie 헤더를 직접 읽어서 확인한다. 요청의 쿠키는 Cookie 헤더로 직접 붙이고,
  요청을 보내기 전에 TestClient의 쿠키 저장소를 비운다.
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
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.auth.repository import AuthRepository, UserRecord, get_auth_repository
from app.auth.router import get_identity_provider
from app.core.database import DbSession, create_engine
from app.core.ports import Identity
from app.main import create_app
from tests.auth.fakes import READER_IDENTITY, FakeIdentityProvider
from tests.support.settings import TEST_FRONTEND_URL

pytestmark = pytest.mark.integration

CALLBACK_PATH = "/api/auth/google/callback"
LOGOUT_PATH = "/api/auth/logout"
ME_PATH = "/api/me"
EVIL_ORIGIN = "https://evil.example"
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


def allow(url: str, email: str, role: str = "user") -> None:
    execute(
        url,
        "INSERT INTO allowed_emails (email, role) VALUES (:email, :role)",
        email=email,
        role=role,
    )


def disallow(url: str, email: str) -> None:
    """그 사람의 allowed_emails 행만 지운다. 로그인 상태는 남긴다."""
    execute(url, "DELETE FROM allowed_emails WHERE email = :email", email=email)


def set_role(url: str, email: str, role: str) -> None:
    execute(
        url, "UPDATE allowed_emails SET role = :role WHERE email = :email", email=email, role=role
    )


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


def login(client: TestClient, *, session_cookie: str | None = None) -> str:
    """로그인 결과 처리 경로를 불러 로그인하고, 새 로그인 상태의 쿠키 값을 돌려준다."""
    return logged_in_token(callback(client, session_cookie=session_cookie))


def me(client: TestClient, token: str) -> httpx.Response:
    client.cookies.clear()
    return client.get(ME_PATH, headers={"Cookie": f"{SESSION_COOKIE}={token}"})


def logout(client: TestClient, token: str, *, origin: str = TEST_FRONTEND_URL) -> httpx.Response:
    client.cookies.clear()
    return client.post(
        LOGOUT_PATH, headers={"Cookie": f"{SESSION_COOKIE}={token}", "Origin": origin}
    )


def assert_error(response: httpx.Response, status_code: int, code: str) -> None:
    """API.md 2.3절의 형식({code, message})이며 code가 기대한 값이다."""
    assert response.status_code == status_code, response.text
    body = response.json()
    assert set(body) == {"code", "message"}
    assert body["code"] == code


def assert_logged_out(response: httpx.Response) -> None:
    """204이고 본문이 없으며, 로그인 상태의 쿠키를 지우는 Set-Cookie가 있다."""
    assert response.status_code == 204, response.text
    assert response.content == b""
    [(value, attributes)] = session_cookies(response)
    assert value == ""
    assert sorted(attributes) == sorted(["HttpOnly", "SameSite=Lax", "Path=/", "Max-Age=0"])


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


# --- TC-1.3.11 --------------------------------------------------------------


def test_logout_deletes_only_the_attached_login_session(clean_db: str, client: TestClient) -> None:
    """TC-1.3.11. 같은 사람이 두 기기에서 로그인한 뒤 한 기기에서 로그아웃한다."""
    allow(clean_db, READER)
    first = login(client)
    second = login(client)

    response = logout(client, first)

    assert_logged_out(response)
    assert_error(me(client, first), 401, "NOT_AUTHENTICATED")
    assert me(client, second).status_code == 200
    assert login_session_hashes(clean_db) == {sha256(second)}


# --- TC-1.3.15 --------------------------------------------------------------


def test_relogin_with_old_cookie_replaces_only_that_login_session(
    clean_db: str, client: TestClient
) -> None:
    """TC-1.3.15. 쿠키 X를 붙인 채 다시 로그인하면 X의 행만 지워지고 다른 기기의 Z는 남는다."""
    allow(clean_db, READER)
    x = login(client)
    z = login(client)

    y = login(client, session_cookie=x)

    assert_error(me(client, x), 401, "NOT_AUTHENTICATED")
    assert me(client, y).status_code == 200
    assert me(client, z).status_code == 200
    assert login_session_hashes(clean_db) == {sha256(y), sha256(z)}


# --- TC-1.4.3의 마지막 부분 -----------------------------------------------------


def test_relogin_after_being_allowed_again_passes(clean_db: str, client: TestClient) -> None:
    """TC-1.4.3. 허용 목록에서 뺐다가 다시 넣으면 옛 쿠키는 401이고, 다시 로그인한 쿠키는 200이다.

    다시 넣은 뒤의 로그인은 옛 쿠키를 붙인 채 한다. 브라우저에 옛 쿠키가 남아 있기 때문이다.
    """
    allow(clean_db, READER)
    old = login(client)
    assert me(client, old).status_code == 200

    disallow(clean_db, READER)
    assert_error(me(client, old), 403, "NOT_ALLOWED")

    allow(clean_db, READER)
    assert_error(me(client, old), 401, "NOT_AUTHENTICATED")

    new = login(client, session_cookie=old)
    assert me(client, new).status_code == 200
    assert_error(me(client, old), 401, "NOT_AUTHENTICATED")


# --- TC-1.4.6 ---------------------------------------------------------------


def test_me_returns_user_and_role_from_allowlist(clean_db: str, client: TestClient) -> None:
    """TC-1.4.6. 역할은 요청마다 허용 목록에서 읽으므로 SQL로 바꾸면 다음 요청부터 바뀐다."""
    allow(clean_db, READER, "admin")
    token = login(client)
    [user] = user_rows(clean_db)

    response = me(client, token)

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"id", "email", "display_name", "role"}
    assert body == {
        "id": str(user["id"]),
        "email": user["email"],
        "display_name": "독자",
        "role": "admin",
    }

    set_role(clean_db, READER, "user")
    assert me(client, token).json()["role"] == "user"


# --- TC-1.4.9, TC-1.4.2를 GET /api/me로 (1차 리뷰 TST-3) --------------------
#
# tests/core/test_gate_integration.py는 관문을 테스트 전용 경로에 걸어 확인한다. 여기서는 TC가 정한
# 대로 실제로 로그인한 뒤 GET /api/me를 부른다. /api/me가 관문 말고 다른 것을 거쳐 행을 고치거나
# 만료를 보지 않으면 드러난다.


def allowed_email_rows(url: str) -> list[dict[str, Any]]:
    return execute(url, "SELECT * FROM allowed_emails ORDER BY email")


def test_me_three_times_changes_no_row(clean_db: str, client: TestClient) -> None:
    """TC-1.4.9. 로그인한 뒤 GET /api/me를 세 번 불러도 세 테이블의 모든 값이 그대로다."""
    allow(clean_db, READER)
    token = login(client)
    before = (allowed_email_rows(clean_db), user_rows(clean_db), login_session_rows(clean_db))
    assert [row["token_hash"] for row in before[2]] == [sha256(token)]

    for _ in range(3):
        response = me(client, token)
        assert response.status_code == 200, response.text

    assert (allowed_email_rows(clean_db), user_rows(clean_db), login_session_rows(clean_db)) == (
        before
    )


def test_me_with_expired_login_session_is_not_authenticated(
    clean_db: str, client: TestClient
) -> None:
    """TC-1.4.2. 실제로 로그인해 만든 로그인 상태의 만료 시각이 지나면 GET /api/me는 401이다."""
    allow(clean_db, READER)
    token = login(client)
    assert me(client, token).status_code == 200
    execute(
        clean_db,
        "UPDATE login_sessions SET expires_at = now() - interval '1 minute' "
        "WHERE token_hash = :token_hash",
        token_hash=sha256(token),
    )

    assert_error(me(client, token), 401, "NOT_AUTHENTICATED")


# --- 실제 repository를 거치는 경로의 로그 (1차 리뷰 TST-4, TC-1.3.13) --------


def test_login_relogin_me_and_logout_log_no_secret(
    caplog: pytest.LogCaptureFixture, clean_db: str, client: TestClient
) -> None:
    """실제 repository와 트랜잭션을 거치는 동안 앱의 로그에 비밀값과 token_hash가 없다.

    서버에서 LOG_LEVEL이 걸리는 것은 `app` 로거와 그 아래이므로(app/core/log_config.py), 그 로거를
    DEBUG로 모은다. 테스트 클라이언트(httpx)의 로그는 요청 주소의 쿼리를 담으므로 모으지 않는다.
    """
    caplog.set_level(logging.DEBUG, logger="app")
    # 이 캡처가 repository의 로거에서 DEBUG를 받는지 먼저 확인한다.
    logging.getLogger("app.auth.repository").debug("canary-repository-debug")
    assert "canary-repository-debug" in caplog.text
    allow(clean_db, READER)

    first = login(client)
    second = login(client, session_cookie=first)
    assert me(client, second).status_code == 200
    assert me(client, first).status_code == 401
    assert_logged_out(logout(client, second))

    texts = [caplog.text, *(record.getMessage() for record in caplog.records)]
    secrets = (first, sha256(first), second, sha256(second), CODE, STATE, NONCE, CODE_VERIFIER)
    for secret in secrets:
        for log_text in texts:
            assert secret not in log_text, (secret, log_text)


# --- TC-1.4.8 ---------------------------------------------------------------


def test_logout_from_other_origin_is_rejected(clean_db: str, client: TestClient) -> None:
    """TC-1.4.8. 공개 경로인 로그아웃도 출처 확인을 거친다."""
    allow(clean_db, READER)
    token = login(client)
    before = login_session_rows(clean_db)

    rejected = logout(client, token, origin=EVIL_ORIGIN)

    assert_error(rejected, 403, "ORIGIN_MISMATCH")
    assert session_cookies(rejected) == []
    assert login_session_rows(clean_db) == before
    assert me(client, token).status_code == 200

    accepted = logout(client, token)

    assert_logged_out(accepted)
    assert login_session_rows(clean_db) == []


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


# --- 같은 사람의 첫 로그인이 겹칠 때 (1차 리뷰 COR-1) ----------------------


class FindTogetherRepository(AuthRepository):
    """처음의 쌍 확인을 겹친 요청 두 개가 모두 마칠 때까지 기다리는 repository.

    두 요청이 모두 "행이 없다"를 본 뒤에야 등록으로 넘어가므로, 한쪽의 INSERT가 반드시 다른 쪽이
    먼저 만든 행과 부딪힌다. 기다리는 것은 요청마다 처음의 조회 한 번뿐이다.
    """

    def __init__(self, session: AsyncSession, barrier: asyncio.Barrier) -> None:
        super().__init__(session)
        self._barrier = barrier
        self._waited = False

    async def find_users_by_email_or_sub(self, *, email: str, google_sub: str) -> list[UserRecord]:
        users = await super().find_users_by_email_or_sub(email=email, google_sub=google_sub)
        if not self._waited:
            self._waited = True
            await self._barrier.wait()
        return users


async def concurrent_callbacks(app: FastAPI, count: int) -> list[httpx.Response]:
    """같은 신원의 결과 처리를 count개 함께 보낸다. 실제 서버처럼 예외는 500 응답으로 받는다."""
    barrier = asyncio.Barrier(count)

    def find_together_repository(session: DbSession) -> AuthRepository:
        return FindTogetherRepository(session, barrier)

    app.dependency_overrides[get_auth_repository] = find_together_repository
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            # 기다림이 풀리지 않으면 테스트가 멈추지 않고 실패하게 한다.
            async with asyncio.timeout(30):
                return await asyncio.gather(
                    *(
                        client.get(
                            CALLBACK_PATH,
                            params={"code": CODE, "state": STATE},
                            headers={"Cookie": f"{OAUTH_STATE_COOKIE}={STATE_COOKIE}"},
                        )
                        for _ in range(count)
                    )
                )
    finally:
        # ASGITransport는 앱의 수명 주기를 돌리지 않으므로, 앱이 만든 엔진을 직접 닫는다.
        engine: AsyncEngine | None = getattr(app.state, "db_engine", None)
        if engine is not None:
            await engine.dispose()


def test_concurrent_first_logins_of_same_person_both_succeed(
    clean_db: str, provider: FakeIdentityProvider
) -> None:
    """E1 S1.3: 결과 처리는 어떤 경우에도 500으로 끝나지 않는다.

    같은 사람의 첫 로그인 결과 처리 두 개가 겹치면, 늦게 등록하는 쪽은 먼저 만든 행으로 쌍을 다시
    확인해 로그인한다. users의 행은 하나이고, 로그인 상태는 요청마다 하나씩 생긴다.
    """
    allow(clean_db, READER)

    responses = asyncio.run(concurrent_callbacks(make_app(provider), 2))

    tokens = [logged_in_token(response) for response in responses]
    [user] = user_rows(clean_db)
    assert (user["email"], user["google_sub"]) == (READER, READER_IDENTITY.sub)
    assert login_session_hashes(clean_db) == {sha256(token) for token in tokens}
    assert {row["user_id"] for row in login_session_rows(clean_db)} == {user["id"]}
    assert len(provider.exchange_code_calls) == 2
