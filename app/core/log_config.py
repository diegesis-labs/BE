"""서버의 로그 설정을 조립한다(docs/CONFIGURATION.md 3.1절의 LOG_LEVEL)."""

from typing import Any


def log_config(level: str) -> dict[str, Any]:
    raise NotImplementedError
