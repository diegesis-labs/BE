"""앱 조립의 테스트 (TC-0.1.5).

`import app.main`과 `create_app()`은 설정을 읽지 않아야 한다. 테스트는 DATABASE_URL을 지우고
작업 경로를 빈 임시 폴더로 옮겨서, 설정을 읽으려 하면 검증 오류가 나는 상태를 만든다.
개발자의 `.env`에 DATABASE_URL이 있더라도 그것이 보이지 않게 하기 위해서다.
"""

import importlib
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import get_settings


@pytest.fixture(autouse=True)
def no_settings_available(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("database_url", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_settings_are_unreadable_in_this_state() -> None:
    """전제: 이 상태에서는 설정을 읽으려 하면 실패한다.

    그래야 아래 테스트들이 "설정을 읽지 않는다"를 확인하는 의미를 가진다.
    """
    with pytest.raises(ValidationError):
        get_settings()


def test_import_app_main_does_not_read_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """DATABASE_URL이 없어도 app.main을 import할 수 있다."""
    # 다른 테스트가 먼저 import했더라도 지금 상태에서 모듈을 다시 실행하게 한다.
    monkeypatch.delitem(sys.modules, "app.main", raising=False)

    module = importlib.import_module("app.main")

    assert module.app is not None


@pytest.fixture
def client() -> Iterator[TestClient]:
    from app.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client


def test_openapi_document_is_served_under_api(client: TestClient) -> None:
    response = client.get("/api/openapi.json")

    assert response.status_code == 200
    document = response.json()
    assert document["openapi"].startswith("3.")
    assert "info" in document
    assert "paths" in document


def test_docs_page_is_served_under_api(client: TestClient) -> None:
    response = client.get("/api/docs")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    # 문서 화면이 /api 아래의 OpenAPI 문서를 불러온다.
    assert "/api/openapi.json" in response.text


@pytest.mark.parametrize("path", ["/openapi.json", "/docs", "/redoc"])
def test_default_documentation_paths_are_closed(client: TestClient, path: str) -> None:
    response = client.get(path)

    assert response.status_code == 404
