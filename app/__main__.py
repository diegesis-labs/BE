"""`python -m app`으로 서버를 띄운다. 로그 설정을 조립해 uvicorn을 실행하는 일만 한다."""

import copy
from typing import Any

import uvicorn
from uvicorn.config import LOGGING_CONFIG

from app.core.config import get_settings


def log_config(level: str) -> dict[str, Any]:
    """uvicorn의 기본 로그 설정에 앱의 로거(`app`과 그 아래 `app.*`)를 더한다.

    uvicorn의 log_level은 uvicorn의 로거에만 걸린다. 앱의 로거에도 LOG_LEVEL을 걸고, uvicorn과 같은
    처리기와 서식으로 내보낸다(docs/CONFIGURATION.md 3.1절).
    """
    config = copy.deepcopy(LOGGING_CONFIG)
    config["loggers"]["app"] = {"handlers": ["default"], "level": level, "propagate": False}
    return config


if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        # 컨테이너 안에서 바깥의 요청을 받아야 하므로 모든 주소에서 듣는다.
        host="0.0.0.0",
        port=settings.port,
        # uvicorn은 로그 레벨의 이름을 소문자로 받는다.
        log_level=settings.log_level.lower(),
        log_config=log_config(settings.log_level),
    )
