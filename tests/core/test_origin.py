"""상태를 바꾸는 요청의 출처 확인 테스트 (TC-1.4.7, 그리고 앱 전체에 걸리는지).

docs/backlog/epic-1/testcase.md의 "출처 확인의 경우" 표를 그대로 확인한다(docs/API.md 2.4절).
앱은 create_app()으로 만든다. 출처 확인을 따로 만든 앱에만 걸어서 확인하면, create_app()이 그것을
걸지 않아도 초록이 되기 때문이다. 관문을 걸지 않은 테스트 전용 경로는 이 파일 안에서만 붙인다.
"""

import logging
import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import get_settings
from app.main import create_app
from tests.support.settings import SETTING_ENV_NAMES, TEST_FRONTEND_URL

TEST_ROUTE = "/api/_test/origin"
UNKNOWN_ROUTE = "/api/_test/no-such-route"
# 테스트 전용 경로가 받는 메서드. HEAD와 OPTIONS도 받게 해서, 그 둘이 확인 없이 경로까지 가는지를
# 경로가 불렸는지로 확인한다.
ROUTE_METHODS = ["GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"]

EVIL_ORIGIN = "https://evil.example"
# 로그에 남았는지 찾을 때 다른 문자열과 헷갈리지 않도록 고유한 값을 쓴다.
COOKIE_MARKER = "cookie-marker-1234"

HANGUL = re.compile(r"[가-힣]")

# testcase.md "출처 확인의 경우" 표(FRONTEND_URL은 http://localhost:5173).
# None은 헤더가 없다는 뜻이다. 표의 "PUT, PATCH, DELETE" 줄은 메서드마다 한 줄로 펼친다.
PASS = "pass"
REJECT = "reject"
ORIGIN_CASES = [
    pytest.param("POST", TEST_FRONTEND_URL, None, PASS, id="post-origin-frontend"),
    # Origin이 있으면 Origin만 본다. Referer가 달라도 통과다.
    pytest.param(
        "POST", TEST_FRONTEND_URL, "https://evil.example/", PASS, id="post-origin-wins-over-referer"
    ),
    pytest.param("POST", EVIL_ORIGIN, None, REJECT, id="post-origin-evil"),
    # 문자열의 앞부분만 비교하면 통과해 버린다.
    pytest.param(
        "POST", "http://localhost:5173.evil.example", None, REJECT, id="post-origin-prefix"
    ),
    # 백엔드 자신의 주소도 프론트엔드가 아니다.
    pytest.param("POST", "http://localhost:8080", None, REJECT, id="post-origin-backend"),
    # 스킴이 다르다.
    pytest.param("POST", "https://localhost:5173", None, REJECT, id="post-origin-other-scheme"),
    pytest.param("POST", "null", None, REJECT, id="post-origin-null"),
    pytest.param("POST", None, "http://localhost:5173/books/1", PASS, id="post-referer-frontend"),
    pytest.param("POST", None, "https://evil.example/page", REJECT, id="post-referer-evil"),
    pytest.param("POST", None, None, REJECT, id="post-no-origin-no-referer"),
    pytest.param("PUT", EVIL_ORIGIN, None, REJECT, id="put-origin-evil"),
    pytest.param("PATCH", EVIL_ORIGIN, None, REJECT, id="patch-origin-evil"),
    pytest.param("DELETE", EVIL_ORIGIN, None, REJECT, id="delete-origin-evil"),
    # GET은 확인하지 않는다.
    pytest.param("GET", EVIL_ORIGIN, None, PASS, id="get-origin-evil"),
]


def build_app(calls: list[str]) -> FastAPI:
    """create_app()으로 만든 앱에 관문을 걸지 않은 테스트 전용 경로를 붙인다.

    경로는 불릴 때마다 그 메서드를 calls에 남긴다.
    """
    app = create_app()

    @app.api_route(TEST_ROUTE, methods=ROUTE_METHODS)
    async def route(request: Request) -> dict[str, str]:
        calls.append(request.method)
        return {"route": "origin-test", "method": request.method}

    return app


@pytest.fixture
def calls() -> list[str]:
    return []


@pytest.fixture
def client(app_env: None, calls: list[str]) -> Iterator[TestClient]:
    # 이 클라이언트에는 기본 Origin을 두지 않는다. 출처 확인을 시험하는 케이스는 헤더를 직접 정한다.
    with TestClient(build_app(calls)) as test_client:
        yield test_client


def headers_of(
    origin: str | None, referer: str | None, cookie: str | None = None
) -> dict[str, str]:
    headers: dict[str, str] = {}
    if origin is not None:
        headers["Origin"] = origin
    if referer is not None:
        headers["Referer"] = referer
    if cookie is not None:
        headers["Cookie"] = cookie
    return headers


def assert_origin_mismatch(response_status: int, body: object) -> None:
    """거절 응답이 403이고 본문이 API.md 2.3절의 형식이며 code가 ORIGIN_MISMATCH인지."""
    assert response_status == 403, body
    assert isinstance(body, dict)
    assert set(body) == {"code", "message"}, body
    assert body["code"] == "ORIGIN_MISMATCH"
    assert isinstance(body["message"], str) and HANGUL.search(body["message"]), body


# --- TC-1.4.7 ---------------------------------------------------------------


@pytest.mark.parametrize(("method", "origin", "referer", "expected"), ORIGIN_CASES)
def test_origin_check_follows_the_case_table(
    client: TestClient,
    calls: list[str],
    method: str,
    origin: str | None,
    referer: str | None,
    expected: str,
) -> None:
    response = client.request(method, TEST_ROUTE, headers=headers_of(origin, referer))

    if expected == PASS:
        assert response.status_code == 200, response.text
        assert response.json() == {"route": "origin-test", "method": method}
        assert calls == [method]
    else:
        assert_origin_mismatch(response.status_code, response.json())
        # 거절한 요청은 경로의 처리로 넘어가지 않는다.
        assert calls == []


@pytest.mark.parametrize(
    "origin",
    [
        # Origin이 있으면 Origin만 본다. null이나 빈 값을 없는 것으로 보고 Referer로 넘어가면
        # 프론트엔드의 Referer가 붙은 요청이 통과해 버린다.
        pytest.param("null", id="null"),
        pytest.param("", id="empty"),
    ],
)
def test_present_origin_does_not_fall_back_to_referer(
    client: TestClient, calls: list[str], origin: str
) -> None:
    response = client.post(TEST_ROUTE, headers=headers_of(origin, "http://localhost:5173/books/1"))

    assert_origin_mismatch(response.status_code, response.json())
    assert calls == []


@pytest.mark.parametrize(
    "referer",
    [
        # Referer의 출처도 앞부분이나 포함 여부가 아니라 정확히 비교한다.
        pytest.param("http://localhost:5173.evil.example/page", id="prefix-host"),
        pytest.param("http://localhost:51730/page", id="prefix-port"),
        pytest.param("https://evil.example/?next=http://localhost:5173", id="contains"),
        # 주소로 읽히지 않는 Referer도 500이 아니라 거절이다.
        pytest.param("http://[::1/page", id="unparsable"),
        pytest.param("", id="empty"),
    ],
)
def test_referer_origin_is_compared_exactly(
    client: TestClient, calls: list[str], referer: str
) -> None:
    response = client.post(TEST_ROUTE, headers=headers_of(None, referer))

    assert_origin_mismatch(response.status_code, response.json())
    assert calls == []


# --- 앱 전체에 걸린다 ---------------------------------------------------------


def test_unknown_path_post_from_other_origin_is_rejected_not_404(client: TestClient) -> None:
    # 출처 확인을 경로의 의존성으로 걸면 등록되지 않은 경로는 확인 없이 404로 나간다.
    response = client.post(UNKNOWN_ROUTE, headers=headers_of(EVIL_ORIGIN, None))

    assert_origin_mismatch(response.status_code, response.json())


def test_unknown_path_post_from_frontend_reaches_routing(client: TestClient) -> None:
    # 출처가 맞으면 확인을 지나 경로를 찾고, 없는 경로이므로 404다.
    response = client.post(UNKNOWN_ROUTE, headers=headers_of(TEST_FRONTEND_URL, None))

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


@pytest.mark.parametrize("method", ["HEAD", "OPTIONS"])
def test_head_and_options_are_not_checked(
    client: TestClient, calls: list[str], method: str
) -> None:
    response = client.request(method, TEST_ROUTE, headers=headers_of(EVIL_ORIGIN, None))

    assert response.status_code == 200
    assert calls == [method]


# --- 설정이 없을 때 -----------------------------------------------------------


@pytest.fixture
def no_settings_available(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """설정을 읽으려 하면 검증 오류가 나는 상태. 개발자의 `.env`와 셸의 값이 보이지 않게 한다."""
    monkeypatch.chdir(tmp_path)
    for name in SETTING_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name.lower(), raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_health_works_without_settings(no_settings_available: None) -> None:
    # 전제: 이 상태에서는 설정을 읽으려 하면 실패한다.
    with pytest.raises(ValidationError):
        get_settings()
    get_settings.cache_clear()

    with TestClient(create_app()) as client:
        response = client.get("/api/health", headers=headers_of(EVIL_ORIGIN, None))

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS"])
def test_safe_methods_do_not_read_settings(
    no_settings_available: None, calls: list[str], method: str
) -> None:
    # 설정을 읽고 그 오류를 삼키는 구현도 걸러 내도록, 응답과 함께 설정을 읽으려 한 횟수를 본다.
    with TestClient(build_app(calls)) as client:
        get_settings.cache_clear()
        response = client.request(method, TEST_ROUTE, headers=headers_of(EVIL_ORIGIN, None))

    assert response.status_code == 200
    assert calls == [method]
    cache = get_settings.cache_info()
    assert cache.hits == 0 and cache.misses == 0, f"{method}에서 설정을 읽었다"


# --- 로그 -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("origin", "referer", "received"),
    [
        pytest.param(EVIL_ORIGIN, None, EVIL_ORIGIN, id="origin"),
        pytest.param(None, "https://evil.example/page", "https://evil.example/page", id="referer"),
    ],
)
def test_rejection_is_logged_without_the_cookie(
    client: TestClient,
    caplog: pytest.LogCaptureFixture,
    origin: str | None,
    referer: str | None,
    received: str,
) -> None:
    cookie = f"diegesis_session={COOKIE_MARKER}"
    with caplog.at_level(logging.DEBUG):
        response = client.post(TEST_ROUTE, headers=headers_of(origin, referer, cookie))

    assert response.status_code == 403
    records = [record for record in caplog.records if record.name == "app.core.origin"]
    assert len(records) == 1, records
    message = records[0].getMessage()
    assert "POST" in message, message
    assert TEST_ROUTE in message, message
    assert received in message, message
    # 쿠키는 어느 로그에도 남지 않는다(E1 S1.4).
    assert COOKIE_MARKER not in caplog.text
    for record in caplog.records:
        assert COOKIE_MARKER not in record.getMessage()
        assert COOKIE_MARKER not in repr(record.args)
