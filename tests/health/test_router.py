"""헬스체크의 테스트 (TC-0.4.1 ~ TC-0.4.3).

모든 테스트는 `create_app()`으로 만든 앱을 쓴다. 라우터만 따로 붙인 앱으로 확인하면,
`create_app()`이 이 라우터를 등록하지 않아도 초록이 되기 때문이다.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app

# 닿을 수 없는 데이터베이스 주소. 포트 1에는 PostgreSQL이 없으므로 접속하면 곧바로 실패한다.
UNREACHABLE_DATABASE_URL = "postgresql+asyncpg://u:p@127.0.0.1:1/x"


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


@pytest.fixture
def unreachable_database(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """설정의 DATABASE_URL이 닿을 수 없는 주소를 가리키게 한다.

    환경변수는 `.env`보다 우선하므로, 개발자의 `.env`에 다른 주소가 있어도 이 주소가 쓰인다.
    """
    monkeypatch.setenv("DATABASE_URL", UNREACHABLE_DATABASE_URL)
    monkeypatch.delenv("database_url", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_health_does_not_touch_the_database(unreachable_database: None) -> None:
    # 전제: 앱이 설정을 읽는다면 닿을 수 없는 주소를 읽게 된다.
    assert get_settings().database_url == UNREACHABLE_DATABASE_URL

    # 데이터베이스에 질의하는 구현이면 접속 오류가 500으로 나가서 실패해야 한다.
    # 예외를 테스트로 다시 던지지 않고, 서버가 보낸 응답을 그대로 받아서 비교한다.
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


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
