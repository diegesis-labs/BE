"""서버의 로그 설정을 조립하는 함수의 테스트 (docs/CONFIGURATION.md 3.1절의 LOG_LEVEL).

진입점(`python -m app`)이 이 설정을 uvicorn에 넘겨 실제로 무엇이 나오는지는 tests/test___main__.py가
본다. 이 파일은 조립된 설정의 내용을 본다. 설정을 이 프로세스의 logging에 적용하지 않는다.
"""

import copy

import pytest
from uvicorn.config import LOGGING_CONFIG

from app.core.log_config import log_config

UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")


@pytest.mark.parametrize("level", ["DEBUG", "WARNING"])
def test_app_logger_gets_level_and_uvicorn_handler(level: str) -> None:
    config = log_config(level)

    # `app` 로거의 설정은 그 아래의 `app.*` 로거가 모두 물려받는다.
    app_logger = config["loggers"]["app"]
    assert app_logger["level"] == level
    assert app_logger["handlers"] == ["default"]
    # 루트 로거로 다시 올라가면 같은 줄이 두 번 나올 수 있다.
    assert app_logger["propagate"] is False
    assert "default" in config["handlers"]


def test_uvicorn_logging_config_is_kept() -> None:
    config = log_config("INFO")

    assert config["version"] == 1
    # 설정을 적용하기 전에 만들어진 로거(import될 때 만든 app.core.errors 등)를 끄지 않는다.
    assert config["disable_existing_loggers"] is False
    assert config["formatters"] == LOGGING_CONFIG["formatters"]
    assert config["handlers"] == LOGGING_CONFIG["handlers"]
    for name in UVICORN_LOGGERS:
        assert config["loggers"][name] == LOGGING_CONFIG["loggers"][name], name


def test_uvicorn_default_is_not_modified() -> None:
    before = copy.deepcopy(LOGGING_CONFIG)

    config = log_config("DEBUG")
    config["loggers"]["uvicorn"]["level"] = "CRITICAL"
    config["handlers"]["default"]["stream"] = "ext://sys.stdout"

    assert before == LOGGING_CONFIG
