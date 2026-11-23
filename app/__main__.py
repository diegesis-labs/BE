"""`python -m app`으로 서버를 띄운다. 설정을 읽어 uvicorn을 실행하는 일만 한다.

로그 설정은 app/core/log_config.py가 조립한다.
"""

import uvicorn

from app.core.config import get_settings
from app.core.log_config import log_config

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
