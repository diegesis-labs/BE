"""앱의 모든 경로가 관문과 출처 확인을 거치는지 확인한다(E1 T1.5.2, TC-1.5.2, TC-1.5.4).

경로는 손으로 나열하지 않고 create_app()이 만든 앱의 app.routes에서 메서드마다 뽑는다. 그래서 이후
Epic이 경로를 더하면 이 테스트가 그 경로를 저절로 검사한다.

- 공개 경로의 목록은 이 파일의 PUBLIC_ROUTES 하나뿐이다(E1 S1.5 "못 박을 것").
- 검사는 함수(unauthenticated_failures, origin_check_failures)로 두고, 그 함수가 틀린 경로를 실제로
  보고하는지도 확인한다. 경로를 하나도 뽑지 못하는 검사도 "모두 401"을 통과하기 때문이다.
- 앱은 닿지 않는 DATABASE_URL(app_env)로 돈다. 관문은 쿠키가 없으면 데이터베이스에 닿지 않으므로,
  관문을 걸지 않은 경로가 데이터베이스에 닿으면 401이 아니라 500으로 드러난다.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated

import httpx
import pytest
from fastapi import Depends, FastAPI
from fastapi.routing import iter_route_contexts
from fastapi.testclient import TestClient

from app.core.gate import CurrentUser, require_user
from app.core.origin import OriginCheckMiddleware
from app.main import create_app
from tests.support.settings import TEST_FRONTEND_URL

pytestmark = pytest.mark.usefixtures("app_env")

# 쿠키 없이 부를 수 있는 공개 경로의 (메서드, 경로). 공개 경로는 이 목록에만 적는다.
# 이후 Epic이 공개 경로를 더하려면 이 목록을 고치고, 그 이유를 그 Epic 문서에 적는다
# (E1 S1.5 "못 박을 것"). 이 목록 밖에 공개 경로를 따로 적거나 검사에서 빼는 예외를 두지 않는다.
PUBLIC_ROUTES = frozenset(
    {
        ("GET", "/api/health"),
        ("GET", "/api/auth/google/login"),
        ("GET", "/api/auth/google/callback"),
        ("POST", "/api/auth/logout"),
        ("GET", "/api/openapi.json"),
        ("GET", "/api/docs"),
    }
)

# 뽑지 않는 메서드. HEAD는 GET 경로에 저절로 붙고, OPTIONS로는 경로를 만들지 않는다.
SKIPPED_METHODS = frozenset({"HEAD", "OPTIONS"})
STATE_CHANGING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# 경로 매개변수에 채우는 값. 경로의 변환기가 이 값을 받지 않아 경로에 닿지 못하면 404가 나므로,
# 검사가 조용히 통과하지 않고 그 경로를 보고한다.
PATH_PARAMETER_VALUE = "1"

EVIL_ORIGIN = "https://evil.example"

# 이 Epic의 네 경로와 헬스체크. 경로를 뽑는 함수가 적어도 이것들은 뽑아야 한다.
EXPECTED_ROUTES = frozenset(
    {
        ("GET", "/api/health"),
        ("GET", "/api/auth/google/login"),
        ("GET", "/api/auth/google/callback"),
        ("POST", "/api/auth/logout"),
        ("GET", "/api/me"),
    }
)


@dataclass(frozen=True)
class Endpoint:
    method: str
    path: str  # 앱에 등록된 모양 그대로다. 예: /api/books/{book_id}
    url: str  # 경로 매개변수를 채운 주소

    @property
    def key(self) -> tuple[str, str]:
        return (self.method, self.path)


@dataclass(frozen=True)
class Failure:
    """기대와 다르게 응답한 경로."""

    method: str
    path: str
    status_code: int
    code: str | None

    @property
    def key(self) -> tuple[str, str]:
        return (self.method, self.path)


def endpoints(app: FastAPI) -> list[Endpoint]:
    """앱에 등록된 모든 경로를 메서드마다 하나씩 뽑는다. HEAD와 OPTIONS는 뺀다.

    app.routes에는 include_router로 넣은 라우터가 펼쳐지지 않은 채 들어 있다. 그래서 FastAPI가
    OpenAPI 문서를 만들 때 쓰는 iter_route_contexts로 펼친다. 라우터의 접두사도 이때 경로에 붙는다.

    메서드나 경로가 정해지지 않은 것(Mount, WebSocketRoute 등)을 만나면 건너뛰지 않고 예외를 낸다.
    이 검사가 그 안을 보지 못하므로, 조용히 건너뛰면 그 경로가 검사에서 빠진다.
    """
    found: list[Endpoint] = []
    for route in iter_route_contexts(app.routes):
        path, methods, name = route.path, route.methods, route.name
        if path is None or methods is None or name is None:
            raise TypeError(f"이 검사가 메서드와 경로를 뽑지 못하는 경로: {route!r}")
        parameters = dict.fromkeys(route.param_convertors, PATH_PARAMETER_VALUE)
        url = str(route.url_path_for(name, **parameters))
        for method in sorted(methods - SKIPPED_METHODS):
            found.append(Endpoint(method=method, path=path, url=url))
    return found


def error_code(response: httpx.Response) -> str | None:
    """API.md 2.3절 형식의 본문이면 그 code, 아니면 None."""
    try:
        body = response.json()
    except ValueError:
        return None
    code = body.get("code") if isinstance(body, dict) else None
    return code if isinstance(code, str) else None


def failures(
    app: FastAPI, targets: Callable[[Endpoint], bool], *, origin: str, expected: tuple[int, str]
) -> list[Failure]:
    """targets가 고른 경로를 쿠키 없이 Origin을 붙여 부르고, (상태, code)가 expected가 아닌 것.

    처리되지 않은 예외는 500 응답으로 받아서 보고한다. 리디렉션은 따라가지 않는다.
    """
    found: list[Failure] = []
    with TestClient(app, follow_redirects=False, raise_server_exceptions=False) as client:
        for endpoint in filter(targets, endpoints(app)):
            # 앞선 응답이 심은 쿠키가 다음 요청에 붙지 않게 한다.
            client.cookies.clear()
            response = client.request(endpoint.method, endpoint.url, headers={"Origin": origin})
            got = (response.status_code, error_code(response))
            if got != expected:
                found.append(Failure(endpoint.method, endpoint.path, *got))
    return found


def unauthenticated_failures(app: FastAPI) -> list[Failure]:
    """공개 경로를 뺀 모든 (메서드, 경로) 가운데, 쿠키 없이 부르면 401 NOT_AUTHENTICATED가 아닌 것.

    상태를 바꾸는 메서드가 출처 확인에서 먼저 거절되지 않도록 Origin: TEST_FRONTEND_URL을 붙인다.
    """
    return failures(
        app,
        lambda endpoint: endpoint.key not in PUBLIC_ROUTES,
        origin=TEST_FRONTEND_URL,
        expected=(401, "NOT_AUTHENTICATED"),
    )


def origin_check_failures(app: FastAPI) -> list[Failure]:
    """상태를 바꾸는 메서드의 모든 (메서드, 경로) 가운데, 403 ORIGIN_MISMATCH가 아닌 것.

    공개 경로까지 모두 쿠키 없이 Origin: EVIL_ORIGIN으로 부른다.
    """
    return failures(
        app,
        lambda endpoint: endpoint.method in STATE_CHANGING_METHODS,
        origin=EVIL_ORIGIN,
        expected=(403, "ORIGIN_MISMATCH"),
    )


def without_origin_check(app: FastAPI) -> FastAPI:
    """출처 확인 미들웨어를 뺀 앱. 미들웨어는 첫 요청 때 쌓이므로 그 전에 빼면 걸리지 않는다."""
    middleware = [entry for entry in app.user_middleware if entry.cls is not OriginCheckMiddleware]
    assert len(middleware) == len(app.user_middleware) - 1
    app.user_middleware = middleware
    return app


# --- 경로를 뽑는 함수 ----------------------------------------------------------


def test_endpoints_are_extracted_from_app_routes() -> None:
    found = [endpoint.key for endpoint in endpoints(create_app())]

    assert len(found) > 0
    assert len(found) == len(set(found))
    assert set(found) >= EXPECTED_ROUTES
    # 공개 경로의 목록에 앱에 없는 경로가 있으면, 그 목록이 잘못 적혔거나 낡은 것이다.
    assert set(found) >= PUBLIC_ROUTES
    assert not any(method in SKIPPED_METHODS for method, _ in found)


# --- TC-1.5.2 -----------------------------------------------------------------


def test_every_non_public_route_requires_login() -> None:
    """TC-1.5.2."""
    app = create_app()
    protected = [endpoint.key for endpoint in endpoints(app) if endpoint.key not in PUBLIC_ROUTES]

    # 검사할 경로가 하나도 없으면 아래의 빈 목록은 아무것도 확인하지 않은 것이다.
    assert ("GET", "/api/me") in protected
    assert unauthenticated_failures(app) == []


def test_login_check_reports_route_without_gate() -> None:
    """관문을 걸지 않은 경로를 하나 더 등록하면 검사가 그 경로를 보고한다.

    경로 매개변수를 채운 주소로 부르므로 그 경로에 실제로 닿는다(404가 아니라 200). 관문을 건 경로는
    경로 매개변수가 있어도 보고하지 않는다.
    """
    app = create_app()

    @app.get("/api/_test/unguarded/{item_id}")
    async def unguarded(item_id: str) -> dict[str, str]:
        return {"item_id": item_id}

    @app.post("/api/_test/unguarded")
    async def unguarded_post() -> dict[str, str]:
        return {}

    @app.get("/api/_test/guarded/{item_no}")
    async def guarded(
        item_no: int, user: Annotated[CurrentUser, Depends(require_user)]
    ) -> dict[str, int]:
        return {"item_no": item_no}

    reported = unauthenticated_failures(app)

    assert sorted(reported, key=lambda failure: failure.key) == [
        Failure("GET", "/api/_test/unguarded/{item_id}", 200, None),
        Failure("POST", "/api/_test/unguarded", 200, None),
    ]


# --- TC-1.5.4 -----------------------------------------------------------------


def add_state_changing_routes(app: FastAPI) -> set[tuple[str, str]]:
    """관문 없이 POST, PUT, PATCH, DELETE를 받는 경로를 붙이고, 그 (메서드, 경로)를 돌려준다."""
    path = "/api/_test/state/{item_id}"

    @app.api_route(path, methods=sorted(STATE_CHANGING_METHODS))
    async def change_state(item_id: str) -> dict[str, str]:
        return {"item_id": item_id}

    return {(method, path) for method in STATE_CHANGING_METHODS}


def test_every_state_changing_route_checks_origin() -> None:
    """TC-1.5.4. 공개 경로인 로그아웃도 거절된다."""
    app = create_app()
    state_changing = [
        endpoint.key for endpoint in endpoints(app) if endpoint.method in STATE_CHANGING_METHODS
    ]

    assert ("POST", "/api/auth/logout") in state_changing
    assert origin_check_failures(app) == []


def test_origin_check_covers_routes_added_later() -> None:
    """나중에 더한 경로도 메서드마다 출처 확인에 걸린다. 경로마다 따로 걸지 않기 때문이다."""
    app = create_app()
    added = add_state_changing_routes(app)

    assert added <= {endpoint.key for endpoint in endpoints(app)}
    assert origin_check_failures(app) == []


def test_origin_check_detector_reports_routes_without_origin_check() -> None:
    """출처 확인을 거치지 않는 앱에서는 검사가 상태를 바꾸는 경로를 메서드마다 모두 보고한다."""
    app = create_app()
    added = add_state_changing_routes(app)
    without_origin_check(app)

    reported = origin_check_failures(app)

    assert {failure.key for failure in reported} == {("POST", "/api/auth/logout"), *added}
    # 쿠키 없는 로그아웃은 관문을 거치지 않으므로 204가, 붙인 경로는 200이 된다.
    assert all(failure.status_code in {200, 204} for failure in reported)
