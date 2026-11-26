"""설정 클래스. 설정값의 이름, 뜻, 기본값은 docs/CONFIGURATION.md에 있다.

나머지 코드는 환경변수를 직접 읽지 않고 get_settings()를 통해서만 설정값을 가져온다.
"""

from functools import cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.frontend_url import check_frontend_url, uses_https


class Settings(BaseSettings):
    # `.env`는 작업 경로에서 찾는다. `python -m app`, alembic, compose는 모두 프로젝트 최상위에서
    # 실행하므로 프로젝트 최상위의 `.env`가 읽힌다. 같은 이름이 있으면 환경변수가 우선한다.
    # `.env.example`에는 다른 Epic이 쓸 값도 들어 있으므로,
    # 클래스에 없는 값은 거부하지 않고 무시한다.
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    port: int = 8080
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    # 기본값이 없는 값(database_url, frontend_url, google_client_id, google_client_secret)은
    # 값이 없으면 설정을 읽는 순간 실패해야 한다.
    # DATABASE_URL은 빈 값도 거부한다. 빈 값으로 뜬 서버는 헬스체크만 통과하고 데이터베이스를 쓰는
    # 요청은 모두 500이 되므로, 시작하는 순간 알아야 한다(docs/CONFIGURATION.md 1절, 3.2절).
    database_url: str = Field(min_length=1)

    frontend_url: str
    # Google의 두 값은 빈 문자열을 받아들인다. CI의 compose 스모크는 이 값 없이 서버를 띄우며,
    # 빈 값으로 뜬 서버는 Google 로그인만 실패한다(E1 S1.7).
    google_client_id: str
    # 설정 객체가 로그나 예외 메시지에 찍혀도 비밀값이 드러나지 않게 SecretStr로 둔다.
    google_client_secret: SecretStr
    login_session_ttl_hours: int = Field(default=336, gt=0)
    login_cookie_name: str = "diegesis_session"

    @field_validator("frontend_url")
    @classmethod
    def check_frontend_url(cls, value: str) -> str:
        """FRONTEND_URL의 모양을 확인한다. 판정은 app/core/frontend_url.py가 한다."""
        return check_frontend_url(value)

    @property
    def cookie_secure(self) -> bool:
        """로그인과 관련된 쿠키에 Secure를 붙이는지.

        FRONTEND_URL의 스킴 하나로만 정한다(ADR-027). 다른 값으로 정하지 않는다.
        """
        return uses_https(self.frontend_url)


@cache
def get_settings() -> Settings:
    """설정을 처음 부를 때 읽고, 그 뒤로는 같은 인스턴스를 돌려준다."""
    # `Settings()`라고 쓰면 pyright는 기본값이 없는 값의 인자가 빠졌다고 본다. 그 값들은 인자가
    # 아니라 환경변수와 `.env`에서 오므로, 빈 입력을 검증하게 해서 같은 읽기 과정을 거치게 한다.
    # model_validate도 BaseSettings의 __init__을 거쳐 환경변수와 `.env`를 읽는다.
    return Settings.model_validate({})
