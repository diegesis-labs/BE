"""관문의 단위 테스트 (TC-1.4.1, 그리고 판정의 경우).

docs/backlog/epic-1/testcase.md의 S1.4 가운데 데이터베이스 없이 확인할 수 있는 것을 확인한다.
데이터베이스의 변화(만료, SQL로 바꾼 허용 목록과 역할, 행을 바꾸지 않음)는
tests/core/test_gate_integration.py가 확인한다.

저장소는 app.dependency_overrides[get_auth_repository]로 FakeAuthStore(tests/auth/fakes.py)를
끼운다. FakeAuthStore는 받은 해시를 lookups에, 쓰기를 writes에 남긴다.
"""

import logging
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from app.auth.repository import UserRecord, get_auth_repository
from app.core.config import get_settings
from app.core.security import hash_token
from tests.auth.fakes import FakeAuthStore
from tests.core.gated_app import ADMIN_ROUTE, USER_ROUTE, create_gated_app

pytestmark = pytest.mark.usefixtures("app_env")

COOKIE_NAME = "diegesis_session"
# 로그에 남았는지 찾을 때 다른 문자열과 헷갈리지 않도록 고유한 값을 쓴다.
TOKEN = "gate-cookie-value-3c9e1f"
UNKNOWN_TOKEN = "gate-unknown-cookie-value-8a4d"

EMAIL = "reader@example.com"
GOOGLE_SUB = "1234567890"
DISPLAY_NAME = "독자"

# 허용 목록에 들어간 시각. 로그인 상태를 만든 시각은 이 값을 기준으로 정한다.
ALLOWED_AT = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)
MICROSECOND = timedelta(microseconds=1)


@pytest.fixture
def store() -> FakeAuthStore:
    return FakeAuthStore()


@pytest.fixture
def client(store: FakeAuthStore) -> Iterator[TestClient]:
    app = create_gated_app()
    app.dependency_overrides[get_auth_repository] = lambda: store
    with TestClient(app) as test_client:
        yield test_client


def sign_in(
    store: FakeAuthStore,
    *,
    role: str | None = "user",
    session_created_at: datetime = ALLOWED_AT,
    token: str = TOKEN,
) -> UserRecord:
    """독자의 사용자 행과 로그인 상태를 만든다. role이 None이면 허용 목록에 넣지 않는다.

    로그인 상태는 만료되지 않았다. 허용 목록에 들어간 시각은 ALLOWED_AT이다.
    """
    if role is not None:
        store.allow(EMAIL, role, created_at=ALLOWED_AT)
    user = store.put_user(EMAIL, GOOGLE_SUB, DISPLAY_NAME)
    store.put_login_session(
        hash_token(token),
        user.id,
        datetime.now(UTC) + timedelta(hours=1),
        created_at=session_created_at,
    )
    return user


def with_cookie(token: str, name: str = COOKIE_NAME) -> dict[str, str]:
    return {"Cookie": f"{name}={token}"}


def assert_error(response: httpx.Response, status_code: int, code: str) -> None:
    """API.md 2.3절의 형식({code, message})이며 code가 기대한 값이다."""
    assert response.status_code == status_code, response.text
    body = response.json()
    assert set(body) == {"code", "message"}
    assert body["code"] == code
    assert isinstance(body["message"], str) and body["message"]


def described(user: UserRecord, role: str) -> dict[str, str | None]:
    """관문을 통과했을 때 테스트 경로가 돌려주는 본문."""
    return {
        "id": str(user.id),
        "email": user.email,
        "display_name": user.display_name,
        "role": role,
    }


# --- TC-1.4.1 ---------------------------------------------------------------


def test_request_without_cookie_is_not_authenticated(
    client: TestClient, store: FakeAuthStore
) -> None:
    sign_in(store)

    response = client.get(USER_ROUTE)

    assert_error(response, 401, "NOT_AUTHENTICATED")
    # 쿠키가 없으면 로그인 상태를 조회하지 않는다(API.md 2.2절의 동작 순서).
    assert store.lookups == []


def test_request_with_empty_cookie_is_not_authenticated(
    client: TestClient, store: FakeAuthStore
) -> None:
    sign_in(store)

    response = client.get(USER_ROUTE, headers=with_cookie(""))

    assert_error(response, 401, "NOT_AUTHENTICATED")
    assert store.lookups == []


def test_request_with_unknown_cookie_is_not_authenticated(
    client: TestClient, store: FakeAuthStore
) -> None:
    # 저장소에는 다른 쿠키 값의 로그인 상태가 있다.
    sign_in(store)

    response = client.get(USER_ROUTE, headers=with_cookie(UNKNOWN_TOKEN))

    assert_error(response, 401, "NOT_AUTHENTICATED")
    # 쿠키 값이 아니라 그 해시로 조회한다(docs/ARCHITECTURE.md 6절).
    assert store.lookups == [hash_token(UNKNOWN_TOKEN)]


# --- 쿠키가 없을 때 데이터베이스에 닿지 않음 --------------------------------


def test_database_is_unreachable_in_this_state() -> None:
    """전제: 저장소를 바꾸지 않은 앱이 로그인 상태를 조회하면 500이 난다.

    `app_env`의 DATABASE_URL은 닿지 않는 주소다. 그래서 아래 테스트의 401은 데이터베이스에 닿지
    않았다는 뜻이 된다.
    """
    with TestClient(create_gated_app(), raise_server_exceptions=False) as client:
        response = client.get(USER_ROUTE, headers=with_cookie(TOKEN))

    assert_error(response, 500, "INTERNAL_ERROR")


@pytest.mark.parametrize("headers", [{}, with_cookie("")], ids=["no-cookie", "empty-cookie"])
def test_request_without_cookie_does_not_touch_database(headers: dict[str, str]) -> None:
    with TestClient(create_gated_app(), raise_server_exceptions=False) as client:
        response = client.get(USER_ROUTE, headers=headers)

    assert_error(response, 401, "NOT_AUTHENTICATED")


# --- 판정의 경우 -------------------------------------------------------------


def test_login_not_in_allowed_emails_is_not_allowed(
    client: TestClient, store: FakeAuthStore
) -> None:
    sign_in(store, role=None)

    response = client.get(USER_ROUTE, headers=with_cookie(TOKEN))

    assert_error(response, 403, "NOT_ALLOWED")


def test_login_created_before_allowed_is_not_authenticated(
    client: TestClient, store: FakeAuthStore
) -> None:
    # 허용 목록에서 뺐다가 다시 넣은 사람의 옛 로그인 상태다(ADR-027).
    sign_in(store, session_created_at=ALLOWED_AT - MICROSECOND)

    response = client.get(USER_ROUTE, headers=with_cookie(TOKEN))

    assert_error(response, 401, "NOT_AUTHENTICATED")


@pytest.mark.parametrize(
    "session_created_at",
    [ALLOWED_AT, ALLOWED_AT + MICROSECOND],
    ids=["same-time", "later"],
)
def test_login_created_at_or_after_allowed_passes(
    client: TestClient, store: FakeAuthStore, session_created_at: datetime
) -> None:
    user = sign_in(store, session_created_at=session_created_at)

    response = client.get(USER_ROUTE, headers=with_cookie(TOKEN))

    assert response.status_code == 200, response.text
    assert response.json() == described(user, "user")
    assert store.lookups == [hash_token(TOKEN)]
    # 관문은 행을 바꾸지 않는다.
    assert store.writes == []


def test_role_comes_from_allowed_emails(client: TestClient, store: FakeAuthStore) -> None:
    user = sign_in(store, role="admin")

    response = client.get(USER_ROUTE, headers=with_cookie(TOKEN))

    assert response.status_code == 200, response.text
    assert response.json() == described(user, "admin")


def test_user_role_on_admin_route_is_admin_only(client: TestClient, store: FakeAuthStore) -> None:
    sign_in(store, role="user")

    response = client.get(ADMIN_ROUTE, headers=with_cookie(TOKEN))

    assert_error(response, 403, "ADMIN_ONLY")


def test_admin_role_on_admin_route_passes(client: TestClient, store: FakeAuthStore) -> None:
    user = sign_in(store, role="admin")

    response = client.get(ADMIN_ROUTE, headers=with_cookie(TOKEN))

    assert response.status_code == 200, response.text
    assert response.json() == described(user, "admin")
    assert store.writes == []


def test_login_not_in_allowed_emails_on_admin_route_is_not_allowed(
    client: TestClient, store: FakeAuthStore
) -> None:
    # 관리자 관문이 사용자 관문을 먼저 거친다. 역할부터 보면 ADMIN_ONLY가 나온다(E1 S1.4).
    sign_in(store, role=None)

    response = client.get(ADMIN_ROUTE, headers=with_cookie(TOKEN))

    assert_error(response, 403, "NOT_ALLOWED")


@pytest.mark.parametrize("headers", [{}, with_cookie(UNKNOWN_TOKEN)], ids=["no-cookie", "unknown"])
def test_admin_route_without_login_is_not_authenticated(
    client: TestClient, store: FakeAuthStore, headers: dict[str, str]
) -> None:
    sign_in(store, role="admin")

    response = client.get(ADMIN_ROUTE, headers=headers)

    assert_error(response, 401, "NOT_AUTHENTICATED")


def test_old_login_on_admin_route_is_not_authenticated(
    client: TestClient, store: FakeAuthStore
) -> None:
    sign_in(store, role="admin", session_created_at=ALLOWED_AT - MICROSECOND)

    response = client.get(ADMIN_ROUTE, headers=with_cookie(TOKEN))

    assert_error(response, 401, "NOT_AUTHENTICATED")


# --- 쿠키의 이름과 로그 -------------------------------------------------------


def test_cookie_name_comes_from_settings(
    client: TestClient, store: FakeAuthStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOGIN_COOKIE_NAME", "custom_session")
    get_settings.cache_clear()
    user = sign_in(store)

    default_name = client.get(USER_ROUTE, headers=with_cookie(TOKEN, COOKIE_NAME))
    custom_name = client.get(USER_ROUTE, headers=with_cookie(TOKEN, "custom_session"))

    assert_error(default_name, 401, "NOT_AUTHENTICATED")
    assert custom_name.status_code == 200, custom_name.text
    assert custom_name.json() == described(user, "user")


def test_cookie_value_is_not_logged(
    client: TestClient, store: FakeAuthStore, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    sign_in(store, role="user")

    statuses = [
        client.get(USER_ROUTE, headers=with_cookie(TOKEN)).status_code,
        client.get(ADMIN_ROUTE, headers=with_cookie(TOKEN)).status_code,
        client.get(USER_ROUTE, headers=with_cookie(UNKNOWN_TOKEN)).status_code,
    ]
    del store.allowed_emails[EMAIL]
    statuses.append(client.get(USER_ROUTE, headers=with_cookie(TOKEN)).status_code)

    assert statuses == [200, 403, 401, 403]
    assert TOKEN not in caplog.text
    assert UNKNOWN_TOKEN not in caplog.text
