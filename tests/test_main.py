"""앱 조립의 테스트 (TC-0.1.5).

`import app.main`과 `create_app()`은 설정을 읽지 않아야 한다. 테스트는 DATABASE_URL을 지우고
작업 경로를 빈 임시 폴더로 옮겨서, 설정을 읽으려 하면 검증 오류가 나는 상태를 만든다.
개발자의 `.env`에 DATABASE_URL이 있더라도 그것이 보이지 않게 하기 위해서다.
"""

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import get_settings

REPO_ROOT = Path(__file__).resolve().parents[1]


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


def run_python_without_settings(code: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    """DATABASE_URL이 없는 환경변수와 빈 작업 경로로, 새 파이썬 프로세스에서 코드를 돌린다.

    이 프로세스에서 `app`의 어느 모듈도 미리 import되어 있지 않으므로, `app.main`이 끌어오는
    모든 하위 모듈이 처음부터 실행된다.
    """
    env = {key: value for key, value in os.environ.items() if key.upper() != "DATABASE_URL"}
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(REPO_ROOT), env.get("PYTHONPATH")]))
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_import_app_main_does_not_read_settings(tmp_path: Path) -> None:
    """DATABASE_URL이 없어도 app.main을 import할 수 있다. app.main이 끌어오는 모듈도 마찬가지다."""
    # 전제: 그 프로세스에서는 설정을 읽으려 하면 실패한다.
    precondition = run_python_without_settings(
        "from app.core.config import get_settings; get_settings()", tmp_path
    )
    assert precondition.returncode != 0
    assert "database_url" in precondition.stderr

    result = run_python_without_settings(
        "import app.main; assert app.main.app is not None", tmp_path
    )

    assert result.returncode == 0, result.stderr


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
