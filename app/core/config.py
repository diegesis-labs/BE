"""설정 클래스. 설정값의 이름, 뜻, 기본값은 docs/CONFIGURATION.md에 있다.

나머지 코드는 환경변수를 직접 읽지 않고 get_settings()를 통해서만 설정값을 가져온다.
"""

from functools import cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # `.env`는 작업 경로에서 찾는다. `python -m app`, alembic, compose는 모두 프로젝트 최상위에서
    # 실행하므로 프로젝트 최상위의 `.env`가 읽힌다. 같은 이름이 있으면 환경변수가 우선한다.
    # `.env.example`에는 다른 Epic이 쓸 값도 들어 있으므로,
    # 클래스에 없는 값은 거부하지 않고 무시한다.
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    port: int = 8080
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    database_url: str  # 기본값을 두지 않는다. 값이 없으면 설정을 읽는 순간 실패해야 한다.


@cache
def get_settings() -> Settings:
    """설정을 처음 부를 때 읽고, 그 뒤로는 같은 인스턴스를 돌려준다."""
    # `Settings()`라고 쓰면 pyright는 database_url 인자가 빠졌다고 본다. 그 값은 인자가 아니라
    # 환경변수와 `.env`에서 오므로, 빈 입력을 검증하게 해서 같은 읽기 과정을 거치게 한다.
    # model_validate도 BaseSettings의 __init__을 거쳐 환경변수와 `.env`를 읽는다.
    return Settings.model_validate({})
