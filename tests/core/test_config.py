"""설정 클래스의 테스트 (TC-0.1.1 ~ TC-0.1.4).

설정 클래스는 작업 경로의 `.env`를 읽는다. 테스트는 작업 경로를 임시 폴더로 옮겨서
그 안의 `.env`만 보이게 하고, 관련 환경변수를 지운 상태에서 확인한다.
개발자의 실제 `.env`가 있든 없든 결과가 같아야 한다.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings

SETTING_NAMES = ("PORT", "LOG_LEVEL", "DATABASE_URL")
REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """작업 경로를 빈 임시 폴더로 옮기고, 설정값의 환경변수와 get_settings()의 캐시를 비운다."""
    monkeypatch.chdir(tmp_path)
    for name in SETTING_NAMES:
        # pydantic-settings는 이름의 대소문자를 가리지 않고 읽는다.
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name.lower(), raising=False)
    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


def write_dotenv(folder: Path, content: str) -> None:
    (folder / ".env").write_text(content, encoding="utf-8")


# --- TC-0.1.1 ---------------------------------------------------------------


def test_database_url_missing_everywhere_fails_validation() -> None:
    """DATABASE_URL이 환경변수에도 .env에도 없으면 설정을 읽는 순간 검증 오류가 난다."""
    with pytest.raises(ValidationError) as excinfo:
        get_settings()

    missing = [e for e in excinfo.value.errors() if e["loc"] == ("database_url",)]
    assert len(missing) == 1
    assert missing[0]["type"] == "missing"


def test_database_url_missing_with_other_values_in_dotenv_still_fails(
    isolated_env: Path,
) -> None:
    """.env에 다른 값만 있고 DATABASE_URL이 없어도 검증 오류가 난다."""
    write_dotenv(isolated_env, "PORT=9000\nLOG_LEVEL=DEBUG\n")

    with pytest.raises(ValidationError) as excinfo:
        get_settings()

    assert [e["loc"] for e in excinfo.value.errors()] == [("database_url",)]


# --- TC-0.1.2 ---------------------------------------------------------------


def test_dotenv_with_values_not_in_class_is_read(isolated_env: Path) -> None:
    """.env에 설정 클래스에 없는 값이 있어도 거부하지 않고 무시한다."""
    write_dotenv(
        isolated_env,
        "APP_ENV=local\n"
        "FRONTEND_URL=http://localhost:5173\n"
        "DATABASE_URL=postgresql+asyncpg://from:dotenv@localhost:5432/diegesis\n"
        "GOOGLE_CLIENT_ID=1234567890-abc.apps.googleusercontent.com\n"
        "BOOTSTRAP_ADMIN_EMAILS=admin@example.com\n"
        "RECOMMENDATION_TOP_K=10\n"
        "STORAGE_BACKEND=local\n",
    )

    settings = get_settings()

    assert settings.database_url == "postgresql+asyncpg://from:dotenv@localhost:5432/diegesis"
    # 클래스에 없는 값은 속성으로도 남지 않는다.
    assert set(settings.model_dump()) == {"port", "log_level", "database_url"}


def test_copy_of_env_example_is_read(isolated_env: Path) -> None:
    """`cp .env.example .env`를 한 직후의 상태로도 설정을 읽을 수 있다."""
    example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    write_dotenv(isolated_env, example)

    settings = get_settings()

    assert settings.database_url == (
        "postgresql+asyncpg://diegesis:diegesis@localhost:5432/diegesis"
    )
    assert set(settings.model_dump()) == {"port", "log_level", "database_url"}


# --- TC-0.1.3 ---------------------------------------------------------------


def test_environment_variable_wins_over_dotenv(
    isolated_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """같은 이름의 값이 환경변수와 .env에 모두 있으면 환경변수의 값을 쓴다."""
    write_dotenv(
        isolated_env,
        "DATABASE_URL=postgresql+asyncpg://from:dotenv@localhost:5432/diegesis\n"
        "PORT=9000\n"
        "LOG_LEVEL=DEBUG\n",
    )
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://from:env@db:5432/diegesis")
    monkeypatch.setenv("PORT", "9100")
    monkeypatch.setenv("LOG_LEVEL", "ERROR")

    settings = get_settings()

    assert settings.database_url == "postgresql+asyncpg://from:env@db:5432/diegesis"
    assert settings.port == 9100
    assert settings.log_level == "ERROR"


def test_dotenv_value_is_used_when_environment_variable_is_absent(isolated_env: Path) -> None:
    """환경변수가 없으면 .env의 값을 쓴다."""
    write_dotenv(
        isolated_env,
        "DATABASE_URL=postgresql+asyncpg://from:dotenv@localhost:5432/diegesis\n"
        "PORT=9000\n"
        "LOG_LEVEL=WARNING\n",
    )

    settings = get_settings()

    assert settings.database_url == "postgresql+asyncpg://from:dotenv@localhost:5432/diegesis"
    assert settings.port == 9000
    assert settings.log_level == "WARNING"


# --- TC-0.1.4 ---------------------------------------------------------------


def test_port_and_log_level_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """PORT와 LOG_LEVEL을 주지 않으면 8080과 INFO다."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/x")

    settings = get_settings()

    assert settings.port == 8080
    assert settings.log_level == "INFO"


@pytest.mark.parametrize("level", ["DEBUG", "INFO", "WARNING", "ERROR"])
def test_allowed_log_levels_are_accepted(monkeypatch: pytest.MonkeyPatch, level: str) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/x")
    monkeypatch.setenv("LOG_LEVEL", level)

    assert get_settings().log_level == level


@pytest.mark.parametrize("level", ["VERBOSE", "TRACE", "CRITICAL", ""])
def test_unknown_log_level_fails_validation(monkeypatch: pytest.MonkeyPatch, level: str) -> None:
    """LOG_LEVEL에 정해지지 않은 값을 주면 검증 오류가 난다."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/x")
    monkeypatch.setenv("LOG_LEVEL", level)

    with pytest.raises(ValidationError) as excinfo:
        get_settings()

    assert [e["loc"] for e in excinfo.value.errors()] == [("log_level",)]


def test_port_is_read_as_integer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/x")
    monkeypatch.setenv("PORT", "9000")

    assert get_settings().port == 9000


def test_non_integer_port_fails_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/x")
    monkeypatch.setenv("PORT", "eighty")

    with pytest.raises(ValidationError) as excinfo:
        get_settings()

    assert [e["loc"] for e in excinfo.value.errors()] == [("port",)]


# --- get_settings() ---------------------------------------------------------


def test_get_settings_reuses_one_instance(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_settings()는 한 번 만든 인스턴스를 재사용한다."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/x")

    first = get_settings()
    second = get_settings()

    assert isinstance(first, Settings)
    assert first is second
