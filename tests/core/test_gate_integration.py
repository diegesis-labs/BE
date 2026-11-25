"""관문과 실제 repository를 이은 통합 테스트 (TC-1.4.2 ~ TC-1.4.5, TC-1.4.9).

로그인 경로는 아직 없으므로 로그인 상태는 테스트가 직접 만든다. security.new_token()으로 쿠키 값을
만들고, 그 hash_token으로 users, allowed_emails, login_sessions에 행을 넣는다. 다시 로그인하는
것은 새 트랜잭션에서 새 로그인 상태를 만드는 것으로 흉내 낸다. 로그인 경로로 하는 확인은 뒤의
step이 한다.

준비와 바꿈과 확인은 앱과 다른 엔진으로, SQL 문장 하나마다 트랜잭션 하나로 한다. 그래서 각 행의
created_at(데이터베이스의 now())은 그 문장을 실행한 순서대로 늘어난다. 만료 시각도 데이터베이스의
now()를 기준으로 정한다. 이 컴퓨터와 컨테이너의 시계가 어긋나도 결과가 같게 하기 위해서다.

SQL로 허용 목록과 역할을 바꾸는 테스트는 앱과 TestClient를 다시 만들지 않는다. 앱이 허용 목록이나
역할을 메모리에 담아 두면 드러나야 하기 때문이다(ADR-024).
"""

import asyncio
import uuid
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core import security
from app.core.database import create_engine
from tests.core.gated_app import ADMIN_ROUTE, USER_ROUTE, create_gated_app

pytestmark = pytest.mark.integration

SESSION_TTL = timedelta(hours=336)

READER = "reader@example.com"
OTHER = "other@example.com"


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


def add_login(url: str, user_id: uuid.UUID, expires_in: timedelta = SESSION_TTL) -> str:
    """새 트랜잭션에서 로그인 상태를 만들고 그 쿠키 값을 돌려준다.

    만료 시각은 데이터베이스의 now()에 expires_in을 더한 시각이다. 음수면 이미 만료된 것이다.
    """
    token = security.new_token()
    execute(
        url,
        "INSERT INTO login_sessions (token_hash, user_id, expires_at) "
        "VALUES (:token_hash, :user_id, now() + :expires_in)",
        token_hash=security.hash_token(token),
        user_id=user_id,
        expires_in=expires_in,
    )
    return token


def snapshot(url: str) -> dict[str, list[dict[str, Any]]]:
    """관문이 닿는 세 테이블의 모든 행과 모든 컬럼."""
    return {
        "allowed_emails": execute(url, "SELECT * FROM allowed_emails ORDER BY email"),
        "users": execute(url, "SELECT * FROM users ORDER BY email"),
        "login_sessions": execute(url, "SELECT * FROM login_sessions ORDER BY token_hash"),
    }


def with_cookie(token: str) -> dict[str, str]:
    return {"Cookie": f"diegesis_session={token}"}


def assert_error(response: httpx.Response, status_code: int, code: str) -> None:
    """API.md 2.3절의 형식({code, message})이며 code가 기대한 값이다."""
    assert response.status_code == status_code, response.text
    body = response.json()
    assert set(body) == {"code", "message"}
    assert body["code"] == code
    assert isinstance(body["message"], str) and body["message"]


def assert_passes(response: httpx.Response, user_id: uuid.UUID, email: str, role: str) -> None:
    assert response.status_code == 200, response.text
    assert response.json()["id"] == str(user_id)
    assert response.json()["email"] == email
    assert response.json()["role"] == role


@pytest.fixture
def client(clean_db: str) -> Iterator[TestClient]:
    with TestClient(create_gated_app()) as test_client:
        yield test_client


# --- TC-1.4.2 ---------------------------------------------------------------


def test_expired_login_is_not_authenticated(clean_db: str, client: TestClient) -> None:
    allow(clean_db, READER)
    reader = add_user(clean_db, READER, "sub-reader", "독자")
    expired = add_login(clean_db, reader, expires_in=-timedelta(hours=1))
    # 비교 대상: 같은 사람의 만료되지 않은 로그인 상태는 통과한다.
    live = add_login(clean_db, reader)

    assert_error(client.get(USER_ROUTE, headers=with_cookie(expired)), 401, "NOT_AUTHENTICATED")
    passed = client.get(USER_ROUTE, headers=with_cookie(live))
    assert_passes(passed, reader, READER, "user")
    assert passed.json()["display_name"] == "독자"


# --- TC-1.4.3 ---------------------------------------------------------------


def test_allowed_emails_is_checked_on_every_request(clean_db: str) -> None:
    allow(clean_db, READER)
    reader = add_user(clean_db, READER, "sub-reader")
    old = add_login(clean_db, reader)

    # 앱과 TestClient는 처음 한 번만 만든다.
    with TestClient(create_gated_app()) as client:
        # 허용 목록에 있을 때 한 번 통과시켜 둔다. 앱이 이때 읽은 것을 담아 두면 아래에서 드러난다.
        assert_passes(client.get(USER_ROUTE, headers=with_cookie(old)), reader, READER, "user")

        disallow(clean_db, READER)
        assert_error(client.get(USER_ROUTE, headers=with_cookie(old)), 403, "NOT_ALLOWED")

        # 다시 넣으면 allowed_emails.created_at이 새로 정해진다. 그 전에 만든 로그인 상태는
        # 받아들이지 않는다(ADR-027).
        allow(clean_db, READER)
        assert_error(client.get(USER_ROUTE, headers=with_cookie(old)), 401, "NOT_AUTHENTICATED")

        # 다시 넣은 뒤에 새 트랜잭션에서 만든 로그인 상태는 통과한다(다시 로그인한 것).
        new = add_login(clean_db, reader)
        assert_passes(client.get(USER_ROUTE, headers=with_cookie(new)), reader, READER, "user")
        assert_error(client.get(USER_ROUTE, headers=with_cookie(old)), 401, "NOT_AUTHENTICATED")


# --- TC-1.4.4 ---------------------------------------------------------------


def test_role_is_read_on_every_request(clean_db: str) -> None:
    allow(clean_db, READER, "user")
    reader = add_user(clean_db, READER, "sub-reader")
    token = add_login(clean_db, reader)

    with TestClient(create_gated_app()) as client:
        assert_error(client.get(ADMIN_ROUTE, headers=with_cookie(token)), 403, "ADMIN_ONLY")
        assert_passes(client.get(USER_ROUTE, headers=with_cookie(token)), reader, READER, "user")

        set_role(clean_db, READER, "admin")
        assert_passes(client.get(ADMIN_ROUTE, headers=with_cookie(token)), reader, READER, "admin")
        assert_passes(client.get(USER_ROUTE, headers=with_cookie(token)), reader, READER, "admin")

        # 한 번 관리자로 통과한 것을 기억해 두어도 드러난다.
        set_role(clean_db, READER, "user")
        assert_error(client.get(ADMIN_ROUTE, headers=with_cookie(token)), 403, "ADMIN_ONLY")


# --- TC-1.4.5 ---------------------------------------------------------------


def test_admin_removed_from_allowed_emails_is_not_allowed_on_admin_route(clean_db: str) -> None:
    allow(clean_db, READER, "admin")
    reader = add_user(clean_db, READER, "sub-reader")
    token = add_login(clean_db, reader)

    with TestClient(create_gated_app()) as client:
        assert_passes(client.get(ADMIN_ROUTE, headers=with_cookie(token)), reader, READER, "admin")

        disallow(clean_db, READER)
        # 관리자 관문이 역할부터 보면 ADMIN_ONLY가 나온다(E1 S1.4).
        assert_error(client.get(ADMIN_ROUTE, headers=with_cookie(token)), 403, "NOT_ALLOWED")


# --- TC-1.4.9 ---------------------------------------------------------------


def test_gate_does_not_change_rows(clean_db: str, client: TestClient) -> None:
    allow(clean_db, READER, "user")
    allow(clean_db, OTHER, "user")
    reader = add_user(clean_db, READER, "sub-reader", "독자")
    other = add_user(clean_db, OTHER, "sub-other")
    token = add_login(clean_db, reader)
    add_login(clean_db, other)
    before = snapshot(clean_db)

    for _ in range(3):
        assert_passes(client.get(USER_ROUTE, headers=with_cookie(token)), reader, READER, "user")
    # 거절하는 경우에도 바꾸지 않는다.
    assert_error(client.get(ADMIN_ROUTE, headers=with_cookie(token)), 403, "ADMIN_ONLY")

    after = snapshot(clean_db)
    # 전제: 비교할 행이 있다.
    assert len(before["login_sessions"]) == 2
    assert after == before
