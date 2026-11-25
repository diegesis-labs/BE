"""설정 클래스의 테스트 (TC-0.1.1 ~ TC-0.1.4, TC-1.2.9, 그리고 로그인 설정값).

설정 클래스는 작업 경로의 `.env`를 읽는다. 테스트는 작업 경로를 임시 폴더로 옮겨서
그 안의 `.env`만 보이게 하고, 관련 환경변수를 지운 상태에서 확인한다.
개발자의 실제 `.env`가 있든 없든 결과가 같아야 한다.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings
from tests.support.settings import (
    SETTING_ENV_NAMES,
    TEST_FRONTEND_URL,
    TEST_GOOGLE_CLIENT_ID,
    TEST_GOOGLE_CLIENT_SECRET,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

# 설정 클래스가 들고 있는 값의 이름. 클래스에 없는 값이 속성으로 남지 않았는지 볼 때 쓴다.
SETTING_FIELDS = {
    "port",
    "log_level",
    "database_url",
    "frontend_url",
    "google_client_id",
    "google_client_secret",
    "login_session_ttl_hours",
    "login_cookie_name",
}

# DATABASE_URL 말고 기본값이 없는 값. `.env`에 이 줄들을 함께 적으면 DATABASE_URL 하나만 빠진다.
OTHER_REQUIRED_DOTENV = (
    f"FRONTEND_URL={TEST_FRONTEND_URL}\n"
    f"GOOGLE_CLIENT_ID={TEST_GOOGLE_CLIENT_ID}\n"
    f"GOOGLE_CLIENT_SECRET={TEST_GOOGLE_CLIENT_SECRET}\n"
)


@pytest.fixture(autouse=True)
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """작업 경로를 빈 임시 폴더로 옮기고, 설정값의 환경변수와 get_settings()의 캐시를 비운다."""
    monkeypatch.chdir(tmp_path)
    for name in SETTING_ENV_NAMES:
        # pydantic-settings는 이름의 대소문자를 가리지 않고 읽는다.
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name.lower(), raising=False)
    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


def write_dotenv(folder: Path, content: str) -> None:
    (folder / ".env").write_text(content, encoding="utf-8")


def set_required_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """기본값이 없는 값을 모두 환경변수에 넣는다. 다른 값을 확인하는 테스트의 준비다."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/x")
    monkeypatch.setenv("FRONTEND_URL", TEST_FRONTEND_URL)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", TEST_GOOGLE_CLIENT_ID)
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", TEST_GOOGLE_CLIENT_SECRET)


def error_locations(error: ValidationError) -> list[tuple[int | str, ...]]:
    return [e["loc"] for e in error.errors()]


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
    write_dotenv(isolated_env, "PORT=9000\nLOG_LEVEL=DEBUG\n" + OTHER_REQUIRED_DOTENV)

    with pytest.raises(ValidationError) as excinfo:
        get_settings()

    assert error_locations(excinfo.value) == [("database_url",)]


# --- TC-0.1.2 ---------------------------------------------------------------


def test_dotenv_with_values_not_in_class_is_read(isolated_env: Path) -> None:
    """.env에 설정 클래스에 없는 값이 있어도 거부하지 않고 무시한다."""
    write_dotenv(
        isolated_env,
        "APP_ENV=local\n"
        "FRONTEND_URL=http://localhost:5173\n"
        "DATABASE_URL=postgresql+asyncpg://from:dotenv@localhost:5432/diegesis\n"
        "GOOGLE_CLIENT_ID=1234567890-abc.apps.googleusercontent.com\n"
        "GOOGLE_CLIENT_SECRET=dotenv-secret\n"
        "BOOTSTRAP_ADMIN_EMAILS=admin@example.com\n"
        "RECOMMENDATION_TOP_K=10\n"
        "STORAGE_BACKEND=local\n",
    )

    settings = get_settings()

    assert settings.database_url == "postgresql+asyncpg://from:dotenv@localhost:5432/diegesis"
    # 클래스에 없는 값은 속성으로도 남지 않는다. APP_ENV와 BOOTSTRAP_ADMIN_EMAILS는
    # ADR-027과 ADR-024가 없앤 값이므로 클래스에 다시 생기면 안 된다.
    assert set(settings.model_dump()) == SETTING_FIELDS


def test_copy_of_env_example_is_read(isolated_env: Path) -> None:
    """`cp .env.example .env`를 한 직후의 상태로도 설정을 읽을 수 있다."""
    example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    write_dotenv(isolated_env, example)

    settings = get_settings()

    assert settings.database_url == (
        "postgresql+asyncpg://diegesis:diegesis@localhost:5432/diegesis"
    )
    assert set(settings.model_dump()) == SETTING_FIELDS
    # 견본의 Google 값은 비어 있다. 빈 값으로도 서버는 뜨고, Google 로그인만 실패한다.
    assert settings.google_client_id == ""
    assert settings.google_client_secret.get_secret_value() == ""


# --- TC-0.1.3 ---------------------------------------------------------------


def test_environment_variable_wins_over_dotenv(
    isolated_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """같은 이름의 값이 환경변수와 .env에 모두 있으면 환경변수의 값을 쓴다."""
    write_dotenv(
        isolated_env,
        "DATABASE_URL=postgresql+asyncpg://from:dotenv@localhost:5432/diegesis\n"
        "PORT=9000\n"
        "LOG_LEVEL=DEBUG\n" + OTHER_REQUIRED_DOTENV,
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
        "LOG_LEVEL=WARNING\n" + OTHER_REQUIRED_DOTENV,
    )

    settings = get_settings()

    assert settings.database_url == "postgresql+asyncpg://from:dotenv@localhost:5432/diegesis"
    assert settings.port == 9000
    assert settings.log_level == "WARNING"


# --- TC-0.1.4 ---------------------------------------------------------------


def test_port_and_log_level_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """PORT와 LOG_LEVEL을 주지 않으면 8080과 INFO다."""
    set_required_env(monkeypatch)

    settings = get_settings()

    assert settings.port == 8080
    assert settings.log_level == "INFO"


@pytest.mark.parametrize("level", ["DEBUG", "INFO", "WARNING", "ERROR"])
def test_allowed_log_levels_are_accepted(monkeypatch: pytest.MonkeyPatch, level: str) -> None:
    set_required_env(monkeypatch)
    monkeypatch.setenv("LOG_LEVEL", level)

    assert get_settings().log_level == level


@pytest.mark.parametrize("level", ["VERBOSE", "TRACE", "CRITICAL", ""])
def test_unknown_log_level_fails_validation(monkeypatch: pytest.MonkeyPatch, level: str) -> None:
    """LOG_LEVEL에 정해지지 않은 값을 주면 검증 오류가 난다."""
    set_required_env(monkeypatch)
    monkeypatch.setenv("LOG_LEVEL", level)

    with pytest.raises(ValidationError) as excinfo:
        get_settings()

    assert error_locations(excinfo.value) == [("log_level",)]


def test_port_is_read_as_integer(monkeypatch: pytest.MonkeyPatch) -> None:
    set_required_env(monkeypatch)
    monkeypatch.setenv("PORT", "9000")

    assert get_settings().port == 9000


def test_non_integer_port_fails_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    set_required_env(monkeypatch)
    monkeypatch.setenv("PORT", "eighty")

    with pytest.raises(ValidationError) as excinfo:
        get_settings()

    assert error_locations(excinfo.value) == [("port",)]


# --- get_settings() ---------------------------------------------------------


def test_get_settings_reuses_one_instance(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_settings()는 한 번 만든 인스턴스를 재사용한다."""
    set_required_env(monkeypatch)

    first = get_settings()
    second = get_settings()

    assert isinstance(first, Settings)
    assert first is second


# --- 로그인 설정값의 필수 여부 (docs/CONFIGURATION.md 3.1절, 3.3절) -------------


@pytest.mark.parametrize(
    ("name", "field"),
    [
        ("FRONTEND_URL", "frontend_url"),
        ("GOOGLE_CLIENT_ID", "google_client_id"),
        ("GOOGLE_CLIENT_SECRET", "google_client_secret"),
    ],
)
def test_login_value_without_default_is_required(
    monkeypatch: pytest.MonkeyPatch, name: str, field: str
) -> None:
    """기본값이 없는 로그인 설정값이 빠지면, 그 값 하나만 빠졌다는 검증 오류가 난다."""
    set_required_env(monkeypatch)
    monkeypatch.delenv(name)

    with pytest.raises(ValidationError) as excinfo:
        get_settings()

    assert [(e["loc"], e["type"]) for e in excinfo.value.errors()] == [((field,), "missing")]


def test_google_values_accept_empty_strings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Google의 두 값은 빈 문자열을 받아들인다.

    CI의 compose 스모크는 Google의 값 없이 서버와 마이그레이션을 띄운다. 빈 값으로 뜬 서버는
    Google 로그인만 실패한다(E1 S1.7).
    """
    set_required_env(monkeypatch)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "")

    settings = get_settings()

    assert settings.google_client_id == ""
    assert settings.google_client_secret.get_secret_value() == ""


def test_google_values_are_read(monkeypatch: pytest.MonkeyPatch) -> None:
    set_required_env(monkeypatch)

    settings = get_settings()

    assert settings.google_client_id == TEST_GOOGLE_CLIENT_ID
    assert settings.google_client_secret.get_secret_value() == TEST_GOOGLE_CLIENT_SECRET


def test_google_client_secret_is_hidden_when_settings_are_printed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """설정 객체가 로그나 예외 메시지에 찍혀도 클라이언트 비밀값은 드러나지 않는다."""
    set_required_env(monkeypatch)

    settings = get_settings()

    assert TEST_GOOGLE_CLIENT_SECRET not in repr(settings)
    assert TEST_GOOGLE_CLIENT_SECRET not in str(settings)
    assert TEST_GOOGLE_CLIENT_SECRET not in str(settings.model_dump())


def test_login_session_values_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """LOGIN_SESSION_TTL_HOURS와 LOGIN_COOKIE_NAME을 주지 않으면 336과 diegesis_session이다."""
    set_required_env(monkeypatch)

    settings = get_settings()

    assert settings.login_session_ttl_hours == 336
    assert settings.login_cookie_name == "diegesis_session"


def test_login_session_values_are_read(monkeypatch: pytest.MonkeyPatch) -> None:
    set_required_env(monkeypatch)
    monkeypatch.setenv("LOGIN_SESSION_TTL_HOURS", "720")
    monkeypatch.setenv("LOGIN_COOKIE_NAME", "other_session")

    settings = get_settings()

    assert settings.login_session_ttl_hours == 720
    assert settings.login_cookie_name == "other_session"


@pytest.mark.parametrize("hours", ["0", "-1", "twelve"])
def test_login_session_ttl_hours_must_be_positive_integer(
    monkeypatch: pytest.MonkeyPatch, hours: str
) -> None:
    """로그인 상태의 수명이 0 이하이면 로그인하자마자 만료되므로 서버가 뜨지 않아야 한다."""
    set_required_env(monkeypatch)
    monkeypatch.setenv("LOGIN_SESSION_TTL_HOURS", hours)

    with pytest.raises(ValidationError) as excinfo:
        get_settings()

    assert error_locations(excinfo.value) == [("login_session_ttl_hours",)]


# --- TC-1.2.9: FRONTEND_URL의 조건 (docs/CONFIGURATION.md 3.1절, ADR-027) ----


ACCEPTED_FRONTEND_URLS = [
    # TC-1.2.9의 받아들일 값
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://diegesis.example",
    # 포트는 있어도 되고 없어도 된다. http는 호스트만 보고 포트는 가리지 않는다.
    "http://localhost",
    "https://diegesis.example:8443",
    "https://localhost:5173",
]

REJECTED_FRONTEND_URLS = [
    # TC-1.2.9의 거부할 값
    "http://diegesis.example",  # localhost가 아닌 http
    "https://diegesis.example/",  # 끝의 /
    "https://diegesis.example/app",  # 경로. 끝이 /인지만 보는 구현은 이것을 놓친다.
    "ftp://diegesis.example",  # http와 https가 아닌 스킴
    # localhost처럼 보이지만 localhost가 아닌 호스트
    "http://localhost.evil.example:5173",
    "http://127.0.0.1.evil.example",
    "http://0.0.0.0:5173",
    # 쿼리, 프래그먼트, 사용자 정보. 비어 있어도 거부한다.
    "https://diegesis.example?next=1",
    "https://diegesis.example?",
    "https://diegesis.example#top",
    "https://diegesis.example#",
    "https://user@diegesis.example",
    "https://user:pw@diegesis.example",
    "http://evil.example@localhost:5173",
    # 호스트가 없거나 스킴이 없다.
    "https://",
    "https://:443",
    "diegesis.example",
    "//diegesis.example",
    "",
    # 포트가 숫자가 아니거나 비어 있다.
    "http://localhost:abc",
    "http://localhost:",
    # 출처 확인은 브라우저가 보낸 Origin과 이 값을 글자 그대로 비교한다(API.md 2.4절). 브라우저는
    # 스킴과 호스트를 소문자로, 기본 포트를 빼고 보내므로, 그렇게 적지 않은 값은 모든 요청을 막는다.
    "HTTPS://diegesis.example",
    "https://Diegesis.example",
    "https://diegesis.example:443",
    "http://localhost:80",
    # 앞뒤의 공백
    " https://diegesis.example",
    "https://diegesis.example ",
]


@pytest.mark.parametrize("url", ACCEPTED_FRONTEND_URLS)
def test_frontend_url_is_accepted(monkeypatch: pytest.MonkeyPatch, url: str) -> None:
    set_required_env(monkeypatch)
    monkeypatch.setenv("FRONTEND_URL", url)

    assert get_settings().frontend_url == url


@pytest.mark.parametrize("url", REJECTED_FRONTEND_URLS)
def test_frontend_url_is_rejected(monkeypatch: pytest.MonkeyPatch, url: str) -> None:
    """조건에 맞지 않는 FRONTEND_URL로는 설정을 만들 때 검증 오류가 나서 서버가 뜨지 않는다."""
    set_required_env(monkeypatch)
    monkeypatch.setenv("FRONTEND_URL", url)

    with pytest.raises(ValidationError) as excinfo:
        get_settings()

    assert error_locations(excinfo.value) == [("frontend_url",)]


# --- cookie_secure (ADR-027의 "Secure와 FRONTEND_URL") -----------------------


@pytest.mark.parametrize(
    ("url", "secure"),
    [
        ("https://diegesis.example", True),
        ("https://localhost:5173", True),
        ("http://localhost:5173", False),
        ("http://127.0.0.1:5173", False),
    ],
)
def test_cookie_secure_follows_frontend_url_scheme(
    monkeypatch: pytest.MonkeyPatch, url: str, secure: bool
) -> None:
    """쿠키에 Secure를 붙일지는 FRONTEND_URL의 스킴 하나로만 정한다."""
    set_required_env(monkeypatch)
    monkeypatch.setenv("FRONTEND_URL", url)

    assert get_settings().cookie_secure is secure


def test_cookie_secure_ignores_app_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """APP_ENV는 ADR-027이 없앤 값이다. 있어도 Secure를 바꾸지 않는다."""
    set_required_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")

    settings = get_settings()

    assert settings.frontend_url == TEST_FRONTEND_URL
    assert settings.cookie_secure is False
