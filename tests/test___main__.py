"""서버 진입점(`python -m app`)의 로그 설정 테스트 (docs/CONFIGURATION.md 3.1절의 LOG_LEVEL).

LOG_LEVEL은 uvicorn의 로그만이 아니라 앱의 로그(`app.*`)에도 걸려야 한다. 그리고 앱의 로그는
서식을 갖춘 처리기로 나가야 한다. 처리기가 없으면 파이썬은 WARNING 이상만 서식 없이 내보낸다.

진입점은 uvicorn을 띄우므로 새 파이썬 프로세스에서 uvicorn.run을 가짜로 바꿔 돌린다. 그리고
진입점이 uvicorn에 넘긴 로그 설정을 uvicorn과 같은 방식으로 적용한 뒤, 앱의 로거로 로그를 남겨
무엇이 나오는지 본다. 이 테스트 프로세스의 로그 설정은 건드리지 않는다.
"""

import ast
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from tests.support.settings import (
    SETTING_ENV_NAMES,
    TEST_FRONTEND_URL,
    TEST_GOOGLE_CLIENT_ID,
    TEST_GOOGLE_CLIENT_SECRET,
    UNREACHABLE_DATABASE_URL,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = REPO_ROOT / "app" / "__main__.py"

# 진입점을 돌린 뒤, 넘겨받은 로그 설정을 적용하고 앱의 로거로 로그를 남긴다.
# 진입점이 로그 설정을 넘기지 않으면 uvicorn이 쓰는 기본 설정을 적용한다(uvicorn.run의 기본값).
PROBE = """
import logging
import logging.config
import runpy

import uvicorn
from uvicorn.config import LOGGING_CONFIG

captured = {}
uvicorn.run = lambda *args, **kwargs: captured.update(kwargs)
runpy.run_module("app", run_name="__main__")
logging.config.dictConfig(captured.get("log_config") or LOGGING_CONFIG)

logger = logging.getLogger("app.core.errors")
logger.debug("probe-debug-message")
logger.info("probe-info-message")
try:
    raise RuntimeError("probe-exception")
except RuntimeError:
    logger.exception("probe-error-message")

# uvicorn 자신의 로그와 접근 로그. 앱의 로거를 더하면서 uvicorn의 설정을 버리면 사라진다.
logging.getLogger("uvicorn.error").info("probe-uvicorn-info-message")
logging.getLogger("uvicorn.access").info(
    '%s - "%s %s HTTP/%s" %d', "127.0.0.1:50000", "GET", "/probe-access-path", "1.1", 200
)
"""


def entrypoint_env(log_level: str) -> dict[str, str]:
    """진입점을 돌릴 프로세스의 환경변수.

    개발자의 셸에 있는 설정값이 결과를 바꾸지 않도록, 설정 클래스가 읽는 이름을 모두 빼고 필요한
    값만 넣는다.
    """
    env = {key: value for key, value in os.environ.items() if key.upper() not in SETTING_ENV_NAMES}
    env["LOG_LEVEL"] = log_level
    env["DATABASE_URL"] = UNREACHABLE_DATABASE_URL
    env["FRONTEND_URL"] = TEST_FRONTEND_URL
    env["GOOGLE_CLIENT_ID"] = TEST_GOOGLE_CLIENT_ID
    env["GOOGLE_CLIENT_SECRET"] = TEST_GOOGLE_CLIENT_SECRET
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(REPO_ROOT), env.get("PYTHONPATH")]))
    return env


def run_entrypoint(log_level: str, tmp_path: Path) -> str:
    # 빈 작업 경로에서 돌려 개발자의 `.env`를 읽지 않는다.
    result = subprocess.run(
        [sys.executable, "-c", PROBE],
        cwd=tmp_path,
        env=entrypoint_env(log_level),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout + result.stderr


def test_log_level_applies_to_app_loggers(tmp_path: Path) -> None:
    output = run_entrypoint("DEBUG", tmp_path)

    assert "probe-debug-message" in output, output
    assert "probe-info-message" in output, output


@pytest.mark.parametrize("log_level", ["WARNING", "ERROR"])
def test_log_level_hides_lower_app_logs(tmp_path: Path, log_level: str) -> None:
    output = run_entrypoint(log_level, tmp_path)

    assert "probe-debug-message" not in output, output
    assert "probe-info-message" not in output, output
    assert "probe-error-message" in output, output


def test_app_error_log_has_level_and_stack(tmp_path: Path) -> None:
    # 500을 낸 예외는 레벨이 붙은 서식으로, 스택과 함께 남는다.
    output = run_entrypoint("INFO", tmp_path)

    error_lines = [line for line in output.splitlines() if "probe-error-message" in line]
    assert error_lines, output
    assert error_lines[0].startswith("ERROR:"), f"레벨이 붙지 않았다: {error_lines[0]!r}"
    assert "Traceback" in output and "RuntimeError: probe-exception" in output, output


def test_uvicorn_logs_are_kept(tmp_path: Path) -> None:
    # 앱의 로거를 더한 설정에도 uvicorn의 기본 설정(서버 로그와 접근 로그)이 남아 있어야 한다.
    output = run_entrypoint("INFO", tmp_path)

    assert "probe-uvicorn-info-message" in output, output
    access_lines = [line for line in output.splitlines() if "/probe-access-path" in line]
    assert access_lines, output
    assert "200" in access_lines[0], access_lines


# --- 실제 uvicorn의 접근 로그 (1차 리뷰 SEC-1) ------------------------------
#
# 위의 PROBE는 uvicorn.run을 가짜로 바꾸므로 요청을 받지 않는다. 아래는 진입점이 넘긴 설정 그대로
# uvicorn을 실제로 띄워 요청을 보내고, 서버가 내보낸 출력 전체를 본다. 진입점은 모든 주소에서 듣지만
# 테스트에서는 이 컴퓨터 안에서만 듣게 한다.
SERVER_PROBE = """
import runpy

import uvicorn

run = uvicorn.run


def run_on_loopback(*args, **kwargs):
    kwargs["host"] = "127.0.0.1"
    run(*args, **kwargs)


uvicorn.run = run_on_loopback
runpy.run_module("app", run_name="__main__")
"""

# 로그인 결과 처리 요청의 쿼리. URL 인코딩으로 모양이 바뀌지 않도록 영문자와 숫자만 쓴다. 모양이
# 바뀌면 로그에 남아도 아래의 확인이 찾지 못한다.
CALLBACK_QUERY = {"state": "STATESECRETVALUE4f2a", "code": "CODESECRETVALUE9c1e"}


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_until_up(url: str, process: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if process.poll() is not None:
            pytest.fail("서버가 뜨기 전에 끝났다")
        try:
            if httpx.get(url, timeout=1).status_code == 200:
                return
        except httpx.TransportError:
            pass
        time.sleep(0.1)
    pytest.fail(f"서버가 30초 안에 응답하지 않았다: {url}")


def test_access_log_does_not_keep_login_callback_query(tmp_path: Path) -> None:
    """E1 "못 박을 것", TC-1.3.13. 기본값(INFO)의 접근 로그에 Google의 code와 state가 남지 않는다.

    접근 로그 자체는 남는다. 접근 로그를 꺼서 통과하면 서버의 요청 기록이 사라진다.
    """
    port = free_port()
    env = entrypoint_env("INFO")
    env["PORT"] = str(port)
    process = subprocess.Popen(
        [sys.executable, "-c", SERVER_PROBE],
        cwd=tmp_path,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        base_url = f"http://127.0.0.1:{port}"
        wait_until_up(f"{base_url}/api/health", process)
        response = httpx.get(f"{base_url}/api/auth/google/callback", params=CALLBACK_QUERY)
    finally:
        process.terminate()
        output, _ = process.communicate(timeout=30)

    # state 쿠키가 없으므로 데이터베이스에 닿기 전에 LOGIN_FAILED로 끝난다.
    assert response.status_code == 302, output
    access_lines = [line for line in output.splitlines() if "/api/auth/google/callback" in line]
    assert len(access_lines) == 1, output
    assert '"GET /api/auth/google/callback HTTP/1.1" 302' in access_lines[0], access_lines
    for name, value in CALLBACK_QUERY.items():
        assert value not in output, f"{name}가 서버의 출력에 남았다:\n{output}"


def test_entrypoint_only_runs_uvicorn() -> None:
    # app/__main__.py는 TDD 가드의 개별 예외라서 테스트를 먼저 요구받지 않는다. 그래서
    # uvicorn을 실행하는 것 밖의 로직을 두지 않는다(docs/DEVELOPMENT.md 4.2절). 로그 설정은
    # app/core/log_config.py가 조립하고, 진입점은 그것을 부르기만 한다.
    tree = ast.parse(ENTRYPOINT.read_text(encoding="utf-8"))
    definitions = [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
    ]
    assert definitions == [], f"진입점에 정의가 있다: {definitions}"
