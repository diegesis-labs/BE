"""서버의 로그 설정을 조립한다(docs/CONFIGURATION.md 3.1절의 LOG_LEVEL).

진입점(`app/__main__.py`)이 이 설정을 uvicorn에 넘긴다.

uvicorn의 접근 로그는 쿼리를 포함한 경로를 남긴다. 로그인 결과 처리의 쿼리에는 Google의 code와
state가 있으므로, 접근 로그에서 쿼리를 뗀다(E1 "못 박을 것").
"""

import copy
import logging
from typing import Any

from uvicorn.config import LOGGING_CONFIG

# uvicorn이 접근 로그를 남길 때 쓰는 서식. 인자는 (클라이언트, 메서드, 쿼리를 포함한 경로,
# HTTP 버전, 상태 코드)다.
_ACCESS_LOG_FORMAT = '%s - "%s %s HTTP/%s" %d'
_ACCESS_LOG_PATH_INDEX = 2
_ACCESS_LOG_QUERY_FILTER = "access_log_query"


class AccessLogQueryFilter(logging.Filter):
    """uvicorn 접근 로그의 경로에서 `?`부터 끝까지를 뗀다. 기록 자체는 버리지 않는다.

    접근 로그의 서식과 인자 모양이 아닌 기록은 고치지 않는다. uvicorn이 서식을 바꾸면 쿼리가 다시
    남을 수 있으므로, 실제 uvicorn의 출력은 tests/test___main__.py가 본다.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if record.msg == _ACCESS_LOG_FORMAT and isinstance(args, tuple) and len(args) == 5:
            path = args[_ACCESS_LOG_PATH_INDEX]
            if isinstance(path, str):
                stripped = path.partition("?")[0]
                record.args = (
                    *args[:_ACCESS_LOG_PATH_INDEX],
                    stripped,
                    *args[_ACCESS_LOG_PATH_INDEX + 1 :],
                )
        return True


def log_config(level: str) -> dict[str, Any]:
    """uvicorn의 기본 로그 설정에 앱의 로거(`app`과 `app.*`)와 접근 로그의 쿼리 필터를 더한다.

    uvicorn의 log_level은 uvicorn의 로거에만 걸린다. 앱의 로거에도 LOG_LEVEL을 걸고, uvicorn과 같은
    처리기와 서식으로 내보낸다. uvicorn의 기본 설정은 복사해서 쓰고 고치지 않는다.
    """
    config = copy.deepcopy(LOGGING_CONFIG)
    config["loggers"]["app"] = {"handlers": ["default"], "level": level, "propagate": False}
    config["filters"] = {_ACCESS_LOG_QUERY_FILTER: {"()": AccessLogQueryFilter}}
    config["loggers"]["uvicorn.access"]["filters"] = [_ACCESS_LOG_QUERY_FILTER]
    return config
