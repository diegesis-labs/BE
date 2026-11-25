"""FRONTEND_URL의 모양을 판정하는 함수의 테스트 (TC-1.2.9, docs/CONFIGURATION.md 3.1절, ADR-027).

설정 클래스(app/core/config.py)는 선언만 하므로 판정을 app/core/frontend_url.py에 둔다
(docs/DEVELOPMENT.md 4.2절, 1차 리뷰 ARC-3). 설정 클래스가 이 판정을 거치는지는
tests/core/test_config.py가 같은 값들로 본다.
"""

import pytest

from app.core.frontend_url import check_frontend_url, uses_https

ACCEPTED_FRONTEND_URLS = [
    # TC-1.2.9의 받아들일 값
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://diegesis.example",
    # 포트는 있어도 되고 없어도 된다. http는 호스트만 보고 포트는 가리지 않는다.
    "http://localhost",
    "https://diegesis.example:8443",
    "https://localhost:5173",
]

REJECTED_FRONTEND_URLS = [
    # TC-1.2.9의 거부할 값
    "http://diegesis.example",  # localhost가 아닌 http
    "https://diegesis.example/",  # 끝의 /
    "https://diegesis.example/app",  # 경로. 끝이 /인지만 보는 구현은 이것을 놓친다.
    "ftp://diegesis.example",  # http와 https가 아닌 스킴
    # localhost처럼 보이지만 localhost가 아닌 호스트
    "http://localhost.evil.example:5173",
    "http://127.0.0.1.evil.example",
    "http://0.0.0.0:5173",
    # 쿼리, 프래그먼트, 사용자 정보. 비어 있어도 거부한다.
    "https://diegesis.example?next=1",
    "https://diegesis.example?",
    "https://diegesis.example#top",
    "https://diegesis.example#",
    "https://user@diegesis.example",
    "https://user:pw@diegesis.example",
    "http://evil.example@localhost:5173",
    # 호스트가 없거나 스킴이 없다.
    "https://",
    "https://:443",
    "diegesis.example",
    "//diegesis.example",
    "",
    # 포트가 숫자가 아니거나 비어 있다.
    "http://localhost:abc",
    "http://localhost:",
    # 출처 확인은 브라우저가 보낸 Origin과 이 값을 글자 그대로 비교한다(API.md 2.4절). 브라우저는
    # 스킴과 호스트를 소문자로, 기본 포트를 빼고 보내므로, 그렇게 적지 않은 값은 모든 요청을 막는다.
    "HTTPS://diegesis.example",
    "https://Diegesis.example",
    "https://diegesis.example:443",
    "http://localhost:80",
    # 공백. urlsplit은 호스트 안의 공백을 그대로 두므로 다시 만든 주소와 비교해서는 걸러지지 않는다.
    " https://diegesis.example",
    "https://diegesis.example ",
    "https://diegesis .example",
    "https://diegesis.example\t",
]


@pytest.mark.parametrize("url", ACCEPTED_FRONTEND_URLS)
def test_accepted_frontend_url_is_returned_unchanged(url: str) -> None:
    assert check_frontend_url(url) == url


@pytest.mark.parametrize("url", REJECTED_FRONTEND_URLS)
def test_rejected_frontend_url_raises_value_error_naming_the_setting(url: str) -> None:
    # 설정 클래스의 검증은 ValueError를 검증 오류로 바꾼다. 문장에는 어느 설정값인지가 있어야 한다.
    with pytest.raises(ValueError, match="FRONTEND_URL"):
        check_frontend_url(url)


@pytest.mark.parametrize(
    ("url", "https"),
    [
        ("https://diegesis.example", True),
        ("https://localhost:5173", True),
        ("http://localhost:5173", False),
        ("http://127.0.0.1:5173", False),
    ],
)
def test_uses_https_follows_only_the_scheme(url: str, https: bool) -> None:
    """쿠키에 Secure를 붙일지는 FRONTEND_URL의 스킴 하나로만 정한다(ADR-027)."""
    assert uses_https(url) is https
