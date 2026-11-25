"""설정 클래스. 설정값의 이름, 뜻, 기본값은 docs/CONFIGURATION.md에 있다.

나머지 코드는 환경변수를 직접 읽지 않고 get_settings()를 통해서만 설정값을 가져온다.
"""

from functools import cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# http는 이 컴퓨터 안에서만 쓴다. 그 밖의 주소에 http를 쓰면 쿠키가 Secure 없이 나간다(ADR-027).
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1"})
# 브라우저는 Origin에 기본 포트를 적지 않는다.
DEFAULT_PORTS = {"http": 80, "https": 443}


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
    database_url: str

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
        """스킴, 호스트, 포트만 담은 주소인지 확인한다(docs/CONFIGURATION.md 3.1절, ADR-027).

        출처 확인은 브라우저가 보낸 Origin과 이 값을 글자 그대로 비교한다(docs/API.md 2.4절).
        그래서 브라우저가 Origin을 적는 모양(소문자 스킴과 호스트, 기본 포트는 생략)과 다르게 적은
        값도 거부한다. 그런 값으로 서버가 뜨면 상태를 바꾸는 요청이 모두 거절된다.
        """
        # urlsplit은 호스트 안의 공백을 그대로 두므로, 아래에서 다시 만든 주소로는 걸러지지 않는다.
        if any(character.isspace() for character in value):
            raise ValueError("FRONTEND_URL에 공백이 있다")
        parts = urlsplit(value)
        if parts.scheme not in DEFAULT_PORTS:
            raise ValueError("FRONTEND_URL의 스킴은 http나 https여야 한다")
        if not parts.hostname:
            raise ValueError("FRONTEND_URL에 호스트가 없다")
        try:
            port = parts.port
        except ValueError as error:
            raise ValueError("FRONTEND_URL의 포트가 숫자가 아니다") from error
        if port == DEFAULT_PORTS[parts.scheme]:
            raise ValueError("FRONTEND_URL에 기본 포트를 적지 않는다")
        # 경로(끝의 / 포함), 쿼리, 프래그먼트, 사용자 정보, 대문자, 공백이 있으면 다시 만든 주소와
        # 글자가 달라진다. 빈 쿼리(`?`)와 빈 프래그먼트(`#`)도 여기서 걸린다.
        origin = f"{parts.scheme}://{parts.hostname}" + ("" if port is None else f":{port}")
        if value != origin:
            raise ValueError(
                "FRONTEND_URL은 스킴, 호스트, 포트만 소문자로 담아야 하며 끝에 /를 붙이지 않는다"
            )
        if parts.scheme == "http" and parts.hostname not in LOCAL_HOSTS:
            raise ValueError("FRONTEND_URL에 http는 호스트가 localhost나 127.0.0.1일 때만 쓴다")
        return value

    @property
    def cookie_secure(self) -> bool:
        """로그인과 관련된 쿠키에 Secure를 붙이는지.

        FRONTEND_URL의 스킴 하나로만 정한다(ADR-027). 다른 값으로 정하지 않는다.
        """
        return urlsplit(self.frontend_url).scheme == "https"


@cache
def get_settings() -> Settings:
    """설정을 처음 부를 때 읽고, 그 뒤로는 같은 인스턴스를 돌려준다."""
    # `Settings()`라고 쓰면 pyright는 기본값이 없는 값의 인자가 빠졌다고 본다. 그 값들은 인자가
    # 아니라 환경변수와 `.env`에서 오므로, 빈 입력을 검증하게 해서 같은 읽기 과정을 거치게 한다.
    # model_validate도 BaseSettings의 __init__을 거쳐 환경변수와 `.env`를 읽는다.
    return Settings.model_validate({})
