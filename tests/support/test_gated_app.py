"""관문을 건 경로를 붙인 앱(tests/support/gated_app.py)의 테스트 (1차 리뷰 ARC-5).

관문의 테스트는 이 앱의 두 경로가 각각 사용자 관문과 관리자 관문을 건다고 믿는다. 관문을 바꿔
걸거나 빠뜨리면 관문의 테스트가 엉뚱한 것을 판정한다. 그리고 두 경로는 테스트에만 있어야 한다.
"""

from collections.abc import Iterator
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.gate import CurrentUser, require_user
from app.main import create_app
from tests.support.gated_app import ADMIN_ROUTE, USER_ROUTE, create_gated_app

USER = CurrentUser(
    id=UUID("00000000-0000-4000-8000-000000000001"),
    email="reader@example.com",
    display_name="독자",
    role="user",
)
ADMIN = CurrentUser(
    id=UUID("00000000-0000-4000-8000-000000000002"),
    email="admin@example.com",
    display_name=None,
    role="admin",
)


def body_of(user: CurrentUser) -> dict[str, str | None]:
    return {
        "id": str(user.id),
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
    }


@pytest.fixture
def app(app_env: None) -> FastAPI:
    return create_gated_app()


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def test_user_route_passes_whoever_the_user_gate_returns(app: FastAPI, client: TestClient) -> None:
    app.dependency_overrides[require_user] = lambda: USER

    response = client.get(USER_ROUTE)

    assert response.status_code == 200, response.text
    assert response.json() == body_of(USER)


def test_admin_route_goes_through_the_admin_gate(app: FastAPI, client: TestClient) -> None:
    # 관리자 관문은 사용자 관문을 먼저 거치므로, 사용자 관문을 바꾸면 관리자 관문의 판정이 드러난다.
    app.dependency_overrides[require_user] = lambda: USER
    rejected = client.get(ADMIN_ROUTE)
    app.dependency_overrides[require_user] = lambda: ADMIN
    passed = client.get(ADMIN_ROUTE)

    assert rejected.status_code == 403, rejected.text
    assert rejected.json()["code"] == "ADMIN_ONLY"
    assert passed.status_code == 200, passed.text
    assert passed.json() == body_of(ADMIN)


@pytest.mark.parametrize("path", [USER_ROUTE, ADMIN_ROUTE])
def test_routes_reject_request_without_cookie(client: TestClient, path: str) -> None:
    # 관문을 바꾸지 않으면 쿠키가 없는 요청은 데이터베이스에 닿기 전에 401이다.
    response = client.get(path)

    assert response.status_code == 401, response.text
    assert response.json()["code"] == "NOT_AUTHENTICATED"


def test_gated_app_is_the_real_app_plus_two_routes_that_the_real_app_lacks(
    app_env: None,
) -> None:
    real_paths = {getattr(route, "path", None) for route in create_app().routes}
    gated_paths = {getattr(route, "path", None) for route in create_gated_app().routes}

    assert USER_ROUTE not in real_paths
    assert ADMIN_ROUTE not in real_paths
    assert gated_paths - real_paths == {USER_ROUTE, ADMIN_ROUTE}
