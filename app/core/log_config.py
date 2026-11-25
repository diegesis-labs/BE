"""서버의 로그 설정을 조립한다(docs/CONFIGURATION.md 3.1절의 LOG_LEVEL).

진입점(`app/__main__.py`)이 이 설정을 uvicorn에 넘긴다.
"""

import copy
import logging
from typing import Any

from uvicorn.config import LOGGING_CONFIG


class AccessLogQueryFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return True


def log_config(level: str) -> dict[str, Any]:
    """uvicorn의 기본 로그 설정에 앱의 로거(`app`과 그 아래 `app.*`)를 더한다.

    uvicorn의 log_level은 uvicorn의 로거에만 걸린다. 앱의 로거에도 LOG_LEVEL을 걸고, uvicorn과 같은
    처리기와 서식으로 내보낸다. uvicorn의 기본 설정은 복사해서 쓰고 고치지 않는다.
    """
    config = copy.deepcopy(LOGGING_CONFIG)
    config["loggers"]["app"] = {"handlers": ["default"], "level": level, "propagate": False}
    return config
