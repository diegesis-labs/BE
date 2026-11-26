"""서버의 로그 설정을 조립하는 함수의 테스트 (docs/CONFIGURATION.md 3.1절의 LOG_LEVEL).

진입점(`python -m app`)이 이 설정을 uvicorn에 넘겨 실제로 무엇이 나오는지는 tests/test___main__.py가
본다. 이 파일은 조립된 설정의 내용을 본다. 설정을 이 프로세스의 logging에 적용하지 않는다.
"""

import copy
import logging

import pytest
from uvicorn.config import LOGGING_CONFIG

from app.core.log_config import AccessLogQueryFilter, log_config

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
        # 접근 로그의 로거에 더한 필터는 아래 테스트가 본다. 그 밖의 설정은 uvicorn의 것 그대로다.
        logger = {key: value for key, value in config["loggers"][name].items() if key != "filters"}
        assert logger == LOGGING_CONFIG["loggers"][name], name


def test_uvicorn_default_is_not_modified() -> None:
    before = copy.deepcopy(LOGGING_CONFIG)

    config = log_config("DEBUG")
    config["loggers"]["uvicorn"]["level"] = "CRITICAL"
    config["handlers"]["default"]["stream"] = "ext://sys.stdout"

    assert before == LOGGING_CONFIG


# --- 접근 로그에서 쿼리를 떼는 필터 (1차 리뷰 SEC-1) ------------------------
#
# uvicorn은 접근 로그를 '%s - "%s %s HTTP/%s" %d' 서식과 (클라이언트, 메서드, 쿼리를 포함한 경로,
# HTTP 버전, 상태 코드)의 인자로 남긴다. 로그인 결과 처리의 쿼리에는 Google의 code와 state가 있다
# (E1 "못 박을 것"). 실제 uvicorn으로 띄운 서버의 출력은 tests/test___main__.py가 본다.

ACCESS_FORMAT = '%s - "%s %s HTTP/%s" %d'


def access_record(path: str) -> logging.LogRecord:
    return logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        0,
        ACCESS_FORMAT,
        ("127.0.0.1:50000", "GET", path, "1.1", 302),
        None,
    )


def test_access_logger_has_only_the_query_filter() -> None:
    config = log_config("INFO")

    assert config["loggers"]["uvicorn.access"]["filters"] == ["access_log_query"]
    assert config["filters"] == {"access_log_query": {"()": AccessLogQueryFilter}}
    # 다른 로거에는 걸지 않는다.
    for name in ("uvicorn", "uvicorn.error", "app"):
        assert "filters" not in config["loggers"][name], name


@pytest.mark.parametrize(
    ("path", "logged_path"),
    [
        pytest.param(
            "/api/auth/google/callback?state=s3cr3tState&code=s3cr3tCode",
            "/api/auth/google/callback",
            id="query",
        ),
        pytest.param("/api/auth/google/callback?", "/api/auth/google/callback", id="empty-query"),
        pytest.param("/api/health", "/api/health", id="no-query"),
    ],
)
def test_access_log_filter_drops_query_and_keeps_the_rest(path: str, logged_path: str) -> None:
    record = access_record(path)

    # 기록을 버리지 않는다. 접근 로그는 쿼리만 빼고 그대로 남는다.
    assert AccessLogQueryFilter().filter(record) is True
    assert record.getMessage() == f'127.0.0.1:50000 - "GET {logged_path} HTTP/1.1" 302'


def test_access_log_filter_leaves_other_records_alone() -> None:
    # 접근 로그의 모양이 아닌 기록은 고치지 않는다. 서식을 깨뜨려 로그 자체를 잃지 않기 위해서다.
    record = logging.LogRecord(
        "uvicorn.access", logging.INFO, __file__, 0, "%s?%s", ("a", "b"), None
    )

    assert AccessLogQueryFilter().filter(record) is True
    assert record.getMessage() == "a?b"
