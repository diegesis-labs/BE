"""FRONTEND_URL의 모양을 판정한다(docs/CONFIGURATION.md 3.1절, ADR-027).

설정 클래스(app/core/config.py)는 선언만 하고 판정하는 로직을 두지 않는다(docs/DEVELOPMENT.md
4.2절). 그래서 설정 클래스의 검증과 속성은 이 모듈의 함수를 부르기만 한다.
"""

from urllib.parse import urlsplit

# http는 이 컴퓨터 안에서만 쓴다. 그 밖의 주소에 http를 쓰면 쿠키가 Secure 없이 나간다(ADR-027).
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1"})
# 브라우저는 Origin에 기본 포트를 적지 않는다.
DEFAULT_PORTS = {"http": 80, "https": 443}


def check_frontend_url(value: str) -> str:
    """스킴, 호스트, 포트만 담은 주소인지 확인하고, 맞으면 받은 값을 그대로 돌려준다.

    출처 확인은 브라우저가 보낸 Origin과 이 값을 글자 그대로 비교한다(docs/API.md 2.4절).
    그래서 브라우저가 Origin을 적는 모양(소문자 스킴과 호스트, 기본 포트는 생략)과 다르게 적은
    값도 거부한다. 그런 값으로 서버가 뜨면 상태를 바꾸는 요청이 모두 거절된다. 맞지 않으면
    ValueError를 낸다.
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


def uses_https(frontend_url: str) -> bool:
    """FRONTEND_URL이 https인지. 로그인과 관련된 쿠키에 Secure를 붙일지를 이것 하나로 정한다."""
    return urlsplit(frontend_url).scheme == "https"
