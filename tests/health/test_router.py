"""헬스체크의 테스트 (TC-0.4.1 ~ TC-0.4.3).

모든 테스트는 `create_app()`으로 만든 앱을 쓴다. 라우터만 따로 붙인 앱으로 확인하면,
`create_app()`이 이 라우터를 등록하지 않아도 초록이 되기 때문이다.
"""

import socket
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import get_settings
from app.main import create_app
from tests.support.settings import UNREACHABLE_DATABASE_URL


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as test_client:
        yield test_client


# --- TC-0.4.1 ---------------------------------------------------------------


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    # 키가 있는지만 보지 않고 본문 전체를 비교한다. {"status": "ok", "db": "ok"}이면 실패해야 한다.
    assert response.json() == {"status": "ok"}


def test_health_is_not_served_without_api_prefix(client: TestClient) -> None:
    # 모든 경로에는 /api 접두사가 붙는다(docs/API.md 1절).
    response = client.get("/health")

    assert response.status_code == 404


# --- TC-0.4.2 ---------------------------------------------------------------


def record_database_access(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """데이터베이스에 닿으려는 시도를 기록한다. 시도는 막지 않고 그대로 진행시킨다.

    헬스체크가 예외를 삼키면 응답만으로는 질의했는지 알 수 없다. 그래서 어떤 방식으로 import해서
    부르든 거쳐야 하는 자리에 기록을 건다. 소켓의 연결(asyncpg와 그 밖의 드라이버), 그리고
    SQLAlchemy 엔진의 연결(드라이버가 소켓을 열기 전에 실패하는 경우)이다.
    """
    calls: list[str] = []

    def recording(owner: object, name: str) -> None:
        original = getattr(owner, name)

        def record(*args: object, **kwargs: object) -> object:
            calls.append(f"{getattr(owner, '__name__', owner)}.{name}{args[1:]!r}")
            return original(*args, **kwargs)

        monkeypatch.setattr(owner, name, record)

    recording(socket.socket, "connect")
    recording(socket.socket, "connect_ex")
    recording(Engine, "connect")
    recording(AsyncEngine, "connect")
    return calls


def test_health_does_not_touch_the_database(app_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    # 전제: 앱이 설정을 읽는다면 닿을 수 없는 주소를 읽게 된다. app_env는 작업 경로를 빈 임시 폴더로
    # 옮기고 DATABASE_URL을 닿을 수 없는 주소로 둔다(tests/conftest.py).
    assert get_settings().database_url == UNREACHABLE_DATABASE_URL

    # 예외를 테스트로 다시 던지지 않고, 서버가 보낸 응답을 그대로 받아서 비교한다.
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        # 요청을 보내기 직전에 건다.
        # 테스트 클라이언트가 이벤트 루프를 준비하며 여는 소켓은 세지 않는다.
        get_settings.cache_clear()
        database_access = record_database_access(monkeypatch)
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    # 데이터베이스에 질의하고 그 오류를 삼키는 구현이면 여기서 실패해야 한다.
    assert database_access == [], f"헬스체크가 데이터베이스에 닿으려 했다: {database_access}"
    # 헬스체크는 설정에도 접근하지 않는다(docs/DECISIONS.md의 D-39, app/health/router.py).
    # 데이터베이스 주소를 읽는 것이 질의의 첫걸음이다.
    cache = get_settings.cache_info()
    assert cache.hits == 0 and cache.misses == 0, "헬스체크가 설정을 읽었다"


# --- TC-0.4.3 ---------------------------------------------------------------


def test_health_is_documented_in_openapi(client: TestClient) -> None:
    document = client.get("/api/openapi.json").json()

    operation = document["paths"]["/api/health"]["get"]

    # 응답의 형식이 문서에 드러난다. status 필드 하나이며 값은 "ok"뿐이다.
    schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    ref = schema["$ref"]
    assert ref.startswith("#/components/schemas/")
    model = document["components"]["schemas"][ref.removeprefix("#/components/schemas/")]
    assert set(model["properties"]) == {"status"}
    assert model["required"] == ["status"]
    status = model["properties"]["status"]
    allowed = status.get("enum", [status["const"]] if "const" in status else None)
    assert allowed == ["ok"]


def test_post_to_health_returns_method_not_allowed(client: TestClient) -> None:
    response = client.post("/api/health")

    assert response.status_code == 405
    body = response.json()
    # FastAPI의 기본 형식({"detail": "Method Not Allowed"})이 그대로 나가면 실패해야 한다.
    assert set(body) == {"code", "message"}
    assert body["code"] == "METHOD_NOT_ALLOWED"
    assert response.headers["allow"] == "GET"
