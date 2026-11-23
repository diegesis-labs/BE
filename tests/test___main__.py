"""서버 진입점(`python -m app`)의 로그 설정 테스트 (docs/CONFIGURATION.md 3.1절의 LOG_LEVEL).

LOG_LEVEL은 uvicorn의 로그만이 아니라 앱의 로그(`app.*`)에도 걸려야 한다. 그리고 앱의 로그는
서식을 갖춘 처리기로 나가야 한다. 처리기가 없으면 파이썬은 WARNING 이상만 서식 없이 내보낸다.

진입점은 uvicorn을 띄우므로 새 파이썬 프로세스에서 uvicorn.run을 가짜로 바꿔 돌린다. 그리고
진입점이 uvicorn에 넘긴 로그 설정을 uvicorn과 같은 방식으로 적용한 뒤, 앱의 로거로 로그를 남겨
무엇이 나오는지 본다. 이 테스트 프로세스의 로그 설정은 건드리지 않는다.
"""

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

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


def run_entrypoint(log_level: str, tmp_path: Path) -> str:
    env = {key: value for key, value in os.environ.items() if key.upper() != "LOG_LEVEL"}
    env["LOG_LEVEL"] = log_level
    env["DATABASE_URL"] = "postgresql+asyncpg://u:p@127.0.0.1:1/x"
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(REPO_ROOT), env.get("PYTHONPATH")]))
    # 빈 작업 경로에서 돌려 개발자의 `.env`를 읽지 않는다.
    result = subprocess.run(
        [sys.executable, "-c", PROBE],
        cwd=tmp_path,
        env=env,
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
