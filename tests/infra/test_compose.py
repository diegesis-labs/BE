"""`compose.yaml`의 테스트 (TC-0.5.4).

데이터베이스 서비스(`db`)의 이미지는 tests/support/test_postgres.py와 통합 테스트가 다룬다.
이 파일은 마이그레이션 서비스(`migrate`)와 서버 서비스(`api`)를 본다.
"""

import shlex
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = REPO_ROOT / "compose.yaml"

SERVER_SERVICES = ["migrate", "api"]


def compose() -> dict[str, Any]:
    return yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))


def services() -> dict[str, dict[str, Any]]:
    return compose()["services"]


def service(name: str) -> dict[str, Any]:
    found = services().get(name)
    assert isinstance(found, dict), f"compose.yaml에 {name} 서비스가 없다"
    return found


def environment(name: str) -> dict[str, str]:
    """서비스의 environment. 사전 형식과 `KEY=VALUE` 목록 형식을 모두 읽는다."""
    raw = service(name).get("environment") or {}
    if isinstance(raw, list):
        result: dict[str, str] = {}
        for item in raw:
            key, _, value = str(item).partition("=")
            result[key] = value
        return result
    return {str(key): str(value) for key, value in raw.items()}


def depends_on_condition(name: str, dependency: str) -> str | None:
    raw = service(name).get("depends_on") or {}
    # 목록 형식(`- db`)은 조건이 없으므로 컨테이너가 뜨기만 하면 시작한다.
    if isinstance(raw, list):
        return None
    entry = raw.get(dependency)
    return entry.get("condition") if isinstance(entry, dict) else None


def command_words(name: str) -> list[str]:
    command = service(name).get("command")
    if isinstance(command, str):
        return command.split()
    return [str(word) for word in command or []]


# --- TC-0.5.4: platform과 env_file ------------------------------------------


def test_no_service_has_platform_or_env_file() -> None:
    # 각 컴퓨터는 자기 CPU 아키텍처로 빌드한다.
    # 그리고 개발자의 `.env`가 컨테이너 안의 주소를 덮어쓰면 안 된다.
    for name, definition in services().items():
        assert "platform" not in definition, f"{name}에 platform이 있다"
        assert "env_file" not in definition, f"{name}에 env_file이 있다"


# --- TC-0.5.4: DATABASE_URL -------------------------------------------------


@pytest.mark.parametrize("name", SERVER_SERVICES)
def test_database_url_points_to_db_service(name: str) -> None:
    url = environment(name).get("DATABASE_URL")
    assert url, f"{name}의 environment에 DATABASE_URL이 없다"
    # 컨테이너 안의 localhost는 그 컨테이너 자신이다. db 서비스의 이름으로 닿아야 한다.
    parts = urlsplit(url)
    assert parts.hostname == "db", f"{name}의 DATABASE_URL의 호스트가 db가 아니다: {url}"
    assert parts.port == 5432
    assert parts.scheme == "postgresql+asyncpg"


def test_api_and_migrate_share_the_same_database_url() -> None:
    # 서버는 시작할 때 데이터베이스에 접속하지 않고, /api/health도 데이터베이스를 보지 않는다.
    # 서버와 데이터베이스의 연결은 스모크가 서버 이미지로 실행한 migrate의 성공으로 확인한다
    # (docs/DECISIONS.md의 D-39). 그 확인은 두 서비스의 주소가 같을 때에만 api에도 성립한다.
    # api의 주소만 틀리면 스모크는 초록이므로, 여기서 걸러야 한다.
    assert environment("api").get("DATABASE_URL") == environment("migrate").get("DATABASE_URL")


# --- TC-0.5.4: 시작 순서 ----------------------------------------------------


def test_migrate_starts_after_db_is_healthy() -> None:
    assert depends_on_condition("migrate", "db") == "service_healthy"
    # service_healthy는 db에 healthcheck가 있어야 뜻이 있다.
    assert service("db").get("healthcheck"), "db에 healthcheck가 없다"


def test_db_healthcheck_checks_tcp_connection() -> None:
    # 첫 초기화 중에 이미지의 entrypoint가 띄우는 임시 서버는 유닉스 소켓만 열고 TCP는 열지 않는다.
    # 소켓만 보면 그때 healthy가 되고, TCP로 붙는 migrate가 거부당해 실패할 수 있다.
    healthcheck = service("db").get("healthcheck") or {}
    test = healthcheck.get("test")
    assert isinstance(test, list) and test[:1] == ["CMD-SHELL"], f"healthcheck의 형식: {test!r}"
    words = shlex.split(" ".join(str(word) for word in test[1:]))
    assert words[:1] == ["pg_isready"], words
    pairs = zip(words, words[1:], strict=False)
    hosts = [value for flag, value in pairs if flag in {"-h", "--host"}]
    hosts += [word.split("=", 1)[1] for word in words if word.startswith("--host=")]
    assert hosts, f"pg_isready가 호스트를 받지 않아 유닉스 소켓만 본다: {words}"
    # 경로(/로 시작)를 주면 여전히 유닉스 소켓이다.
    assert all(host in {"127.0.0.1", "localhost", "::1"} for host in hosts), hosts


def test_api_starts_after_migrate_completed_successfully() -> None:
    assert depends_on_condition("api", "migrate") == "service_completed_successfully"


# --- 그 밖의 서비스 정의 (step 4의 지시) --------------------------------------


@pytest.mark.parametrize("name", SERVER_SERVICES)
def test_server_services_are_built_from_repo(name: str) -> None:
    # 이미지를 레지스트리에서 받지 않고 레포에서 빌드한다(docs/DECISIONS.md의 D-37).
    definition = service(name)
    build = definition.get("build")
    context = build.get("context") if isinstance(build, dict) else build
    assert context in {".", "./"}, f"{name}이 레포에서 빌드하지 않는다: build={build!r}"
    assert "image" not in definition, f"{name}이 레지스트리의 이미지를 가리킨다"


def test_migrate_runs_alembic_upgrade_head_once() -> None:
    assert command_words("migrate") == ["alembic", "upgrade", "head"]
    # 끝나면 멈춰야 한다. 다시 띄우면 service_completed_successfully가 성립하지 않는다.
    assert service("migrate").get("restart", "no") == "no"


def test_api_uses_image_default_command() -> None:
    # 서버의 시작 명령은 Dockerfile의 CMD(python -m app) 한 곳에만 둔다.
    assert "command" not in service("api")


def test_api_publishes_port_8080_through_api_port_on_loopback_only() -> None:
    # 호스트 주소 없이 열면 같은 네트워크의 다른 기기에도 열린다.
    # 로컬 개발용이므로 이 컴퓨터에만 연다.
    assert service("api").get("ports") == ["127.0.0.1:${API_PORT:-8080}:8080"]


def test_db_publishes_port_5432_through_db_port_on_loopback_only() -> None:
    # db에는 compose.yaml에 적힌 고정 계정(diegesis/diegesis)으로 누구나 접속할 수 있다.
    # 뒤 Epic에서 책을 적재하면 본문이 들어가므로, 같은 네트워크의 다른 기기에 열지 않는다.
    assert service("db").get("ports") == ["127.0.0.1:${DB_PORT:-5432}:5432"]


def test_api_healthcheck_calls_health_endpoint() -> None:
    healthcheck = service("api").get("healthcheck")
    assert healthcheck, "api에 healthcheck가 없어서 `up --wait`가 서버의 응답을 기다리지 않는다"
    test = healthcheck["test"]
    text = test if isinstance(test, str) else " ".join(str(word) for word in test)
    assert "/api/health" in text
    assert ":8080/" in text
