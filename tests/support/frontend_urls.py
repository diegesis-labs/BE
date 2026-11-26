"""FRONTEND_URL로 받아들일 값과 거부할 값의 목록 (TC-1.2.9, docs/CONFIGURATION.md 3.1절, ADR-027).

판정 함수의 테스트(tests/core/test_frontend_url.py)와 설정 클래스의 테스트
(tests/core/test_config.py)가 같은 값들로 확인한다. 두 테스트가 함께 쓰므로 여기에 둔다
(docs/DEVELOPMENT.md 4.2절, 2차 리뷰 ARC-3).
"""

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
