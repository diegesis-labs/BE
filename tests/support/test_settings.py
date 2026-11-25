"""tests/conftest.py의 `app_env` fixture와 tests/support/settings.py의 테스트.

`app_env`를 쓴 테스트에서는 get_settings()가 테스트용 상수를 돌려주어야 하고, 개발자의 셸이나
작업 경로의 `.env`에 있던 값이 보이면 안 된다.
"""

from pathlib import Path

import pytest

from app.core.config import get_settings
from tests.support.settings import (
    SETTING_ENV_NAMES,
    TEST_FRONTEND_URL,
    TEST_GOOGLE_CLIENT_ID,
    TEST_GOOGLE_CLIENT_SECRET,
    UNREACHABLE_DATABASE_URL,
)

# 개발자의 `.env`를 흉내 낸다. 모든 값이 기본값이나 테스트용 상수와 다르다.
DEVELOPER_DOTENV = (
    "PORT=9999\n"
    "LOG_LEVEL=DEBUG\n"
    "DATABASE_URL=postgresql+asyncpg://developer:secret@localhost:5432/developer\n"
    "FRONTEND_URL=https://developer.example\n"
    "GOOGLE_CLIENT_ID=developer-client-id\n"
    "GOOGLE_CLIENT_SECRET=developer-client-secret\n"
    "LOGIN_SESSION_TTL_HOURS=1\n"
    "LOGIN_COOKIE_NAME=developer_session\n"
)


@pytest.fixture
def developer_checkout(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """`app_env`보다 먼저, 개발자의 `.env`가 있는 폴더를 작업 경로로 두고 셸에 설정값을 넣는다.

    그리고 그 상태에서 get_settings()를 한 번 불러 개발자의 값이 캐시에 남게 한다. `app_env`가
    작업 경로를 옮기지 않거나, 환경변수를 지우지 않거나, 캐시를 비우지 않으면 그 값이 보인다.
    """
    folder = tmp_path_factory.mktemp("developer-checkout")
    (folder / ".env").write_text(DEVELOPER_DOTENV, encoding="utf-8")
    monkeypatch.chdir(folder)
    for name in SETTING_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name.lower(), raising=False)
    get_settings.cache_clear()

    # 전제: 이 상태에서는 개발자의 `.env`가 읽힌다.
    cached = get_settings()
    assert cached.port == 9999
    assert cached.frontend_url == "https://developer.example"

    # 개발자의 셸에만 있는 값. 소문자 이름도 pydantic-settings가 읽는다.
    monkeypatch.setenv("LOGIN_COOKIE_NAME", "shell_session")
    monkeypatch.setenv("log_level", "ERROR")
    return folder


# 인자의 순서대로 fixture가 준비되므로, developer_checkout이 app_env보다 먼저 돈다.
def test_app_env_hides_developer_dotenv_shell_and_cache(
    developer_checkout: Path, app_env: None
) -> None:
    assert Path.cwd().resolve() != developer_checkout.resolve()

    settings = get_settings()

    # app_env가 넣지 않는 값은 개발자의 `.env`나 셸이 아니라 기본값으로 읽힌다.
    assert settings.port == 8080
    assert settings.log_level == "INFO"
    assert settings.login_session_ttl_hours == 336
    assert settings.login_cookie_name == "diegesis_session"


def test_app_env_provides_test_constants(app_env: None) -> None:
    settings = get_settings()

    assert settings.database_url == UNREACHABLE_DATABASE_URL
    assert settings.frontend_url == TEST_FRONTEND_URL
    assert settings.google_client_id == TEST_GOOGLE_CLIENT_ID
    assert settings.google_client_secret.get_secret_value() == TEST_GOOGLE_CLIENT_SECRET
    # 테스트의 FRONTEND_URL은 http이므로 쿠키에 Secure를 붙이지 않는다.
    assert settings.cookie_secure is False


def test_app_env_working_directory_is_empty(app_env: None, tmp_path: Path) -> None:
    # 테스트가 tmp_path에 만든 `.env`도 보이지 않도록 작업 경로는 tmp_path와 다른 빈 폴더다.
    (tmp_path / ".env").write_text("PORT=9999\n", encoding="utf-8")

    assert Path.cwd().resolve() != tmp_path.resolve()
    assert list(Path.cwd().iterdir()) == []
    assert get_settings().port == 8080


def test_setting_env_names_include_login_settings() -> None:
    # 테스트가 지우는 이름에 이 Epic의 설정값이 들어 있어야 개발자의 셸이 결과를 바꾸지 못한다.
    assert {
        "DATABASE_URL",
        "FRONTEND_URL",
        "GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET",
        "LOGIN_SESSION_TTL_HOURS",
        "LOGIN_COOKIE_NAME",
    } <= set(SETTING_ENV_NAMES)
