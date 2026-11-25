"""로그인, 로그아웃, 내 정보 경로(app/auth/router.py)의 단위 테스트.

docs/backlog/epic-1/testcase.md의 S1.3 가운데 HTTP로 드러나는 것(상태 코드, Location, 쿠키의 속성)과
TC-1.5.1, TC-1.2.1의 Host 부분, TC-1.3.12, TC-1.5.3을 확인한다. 동작 순서는 docs/API.md 4.2절과
4.3절이다.

- 앱은 create_app()으로 만든다. 경로를 따로 만든 앱에만 붙여서 확인하면, create_app()이 경로를
  등록하지 않거나 어댑터를 잇지 않아도 초록이 되기 때문이다.
- 신원은 app.dependency_overrides[get_identity_provider]로 FakeIdentityProvider를, 저장소는
  app.dependency_overrides[get_auth_repository]로 FakeAuthStore를 끼운다. 실제 Google 어댑터로
  확인하는 TC-1.5.1과 TC-1.2.1만 아무것도 덮어쓰지 않는다. 그 어댑터는 로그인 시작에서 네트워크를
  쓰지 않고, 데이터베이스의 세션은 첫 질의 전에는 접속하지 않으므로 닿지 않는 DATABASE_URL로도
  돈다.
- 쿠키의 속성은 Set-Cookie 헤더를 직접 읽어서 확인한다. TestClient의 쿠키 저장소는 HttpOnly,
  Secure, Max-Age를 보여 주지 않는다. 속성은 API.md 4.2절의 예시와 같은 표기로 비교한다.
- 리디렉션을 따라가지 않는다. Location은 FRONTEND_URL을 붙인 전체 주소로 비교한다.
- 요청의 쿠키는 Cookie 헤더로 직접 붙인다. 앞선 응답의 쿠키가 TestClient의 저장소에 남아 다음
  요청에 저절로 붙지 않도록, 결과 처리와 로그아웃과 내 정보를 부르기 전에 저장소를 비운다.
- 로그아웃은 상태를 바꾸는 요청이므로 Origin: TEST_FRONTEND_URL을 붙인다(API.md 2.4절).
"""

import ast
import base64
import hashlib
import logging
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.repository import get_auth_repository
from app.auth.router import get_identity_provider
from app.core import security
from app.core.config import get_settings
from app.core.ports import LoginFailedError
from app.main import create_app
from tests.auth.fakes import (
    READER_IDENTITY,
    AuthorizationUrlCall,
    ExchangeCodeCall,
    FakeAuthStore,
    FakeIdentityProvider,
    StoreWrite,
    fake_authorization_url,
)
from tests.support.settings import (
    TEST_FRONTEND_URL,
    TEST_GOOGLE_CLIENT_ID,
    TEST_GOOGLE_CLIENT_SECRET,
)

pytestmark = pytest.mark.usefixtures("app_env")

REPO_ROOT = Path(__file__).resolve().parents[2]
ROUTER_PATH = REPO_ROOT / "app" / "auth" / "router.py"

LOGIN_PATH = "/api/auth/google/login"
CALLBACK_PATH = "/api/auth/google/callback"
LOGOUT_PATH = "/api/auth/logout"
ME_PATH = "/api/me"
GOOGLE_AUTHORIZATION_PREFIX = "https://accounts.google.com/o/oauth2/v2/auth?"

OAUTH_STATE_COOKIE = "diegesis_oauth_state"
SESSION_COOKIE = "diegesis_session"
STATE_COOKIE_PATH = "/api/auth/google"
# LOGIN_SESSION_TTL_HOURS의 기본값(336시간)을 초로 바꾼 값.
DEFAULT_SESSION_MAX_AGE = 336 * 3600

SUCCESS_LOCATION = f"{TEST_FRONTEND_URL}/"
NOT_ALLOWED_LOCATION = f"{TEST_FRONTEND_URL}/login?error=NOT_ALLOWED"
LOGIN_FAILED_LOCATION = f"{TEST_FRONTEND_URL}/login?error=LOGIN_FAILED"

# state, nonce, code_verifier, code, 쿠키 값은 서로 다르고 로그의 문장과 겹치지 않는 문자열로 둔다.
# 자리가 바뀌거나 로그에 새면 드러나게 하기 위해서다.
STATE = "routerState7f1c"
NONCE = "routerNonce2b8d"
CODE_VERIFIER = "routerVerifier9e4a"
CODE = "routerGoogleCode5c3f"
STATE_COOKIE = f"{STATE}.{NONCE}.{CODE_VERIFIER}"
OTHER_STATE = "routerOtherState3d9a"
OLD_SESSION_TOKEN = "routerOldSessionToken1a6b"
# 저장소에 없는 로그인 상태의 쿠키 값.
UNKNOWN_SESSION_TOKEN = "routerUnknownSessionToken8c2e"
OTHER_DEVICE_TOKEN = "routerOtherDeviceToken4f7d"
MATCHING_QUERY = {"code": CODE, "state": STATE}

EXCHANGE_FAILURE_MESSAGE = "ID 토큰의 aud가 다름"

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{43}")


# --- Set-Cookie 읽기 ----------------------------------------------------------


@dataclass(frozen=True)
class SetCookie:
    """Set-Cookie 헤더 하나. attributes는 `;`로 나눈 속성을 받은 표기 그대로 담는다."""

    name: str
    value: str
    attributes: tuple[str, ...]


def parse_set_cookie(header: str) -> SetCookie:
    pair, *attributes = header.split(";")
    name, separator, value = pair.partition("=")
    assert separator, header
    return SetCookie(
        name=name.strip(),
        value=value.strip(),
        attributes=tuple(attribute.strip() for attribute in attributes),
    )


def set_cookies(response: httpx.Response, name: str) -> list[SetCookie]:
    """응답의 Set-Cookie 가운데 이름이 name인 것."""
    return [
        cookie
        for cookie in map(parse_set_cookie, response.headers.get_list("set-cookie"))
        if cookie.name == name
    ]


def state_cookie_attributes(*, secure: bool) -> list[str]:
    """diegesis_oauth_state를 심을 때의 속성(API.md 4.2절의 예시). 순서와 상관없이 비교한다."""
    return sorted(
        [
            "HttpOnly",
            "SameSite=Lax",
            f"Path={STATE_COOKIE_PATH}",
            "Max-Age=600",
            *(["Secure"] if secure else []),
        ]
    )


def session_cookie_attributes(*, secure: bool, max_age: int = DEFAULT_SESSION_MAX_AGE) -> list[str]:
    """로그인 상태의 쿠키를 심을 때의 속성(API.md 4.2절의 예시). 순서와 상관없이 비교한다."""
    return sorted(
        [
            "HttpOnly",
            "SameSite=Lax",
            "Path=/",
            f"Max-Age={max_age}",
            *(["Secure"] if secure else []),
        ]
    )


def assert_redirect(response: httpx.Response, location: str) -> None:
    """302이며 Location이 location과 글자 그대로 같다. RedirectResponse의 기본값은 307이다."""
    assert response.status_code == 302, response.text
    assert response.headers["location"] == location


def assert_state_cookie_deleted(response: httpx.Response) -> None:
    """diegesis_oauth_state를 지우는 Set-Cookie가 하나 있다.

    브라우저는 이름과 경로가 모두 같은 쿠키만 지우므로, 심을 때와 같은 Path가 붙어야 한다.
    """
    [cookie] = set_cookies(response, OAUTH_STATE_COOKIE)
    assert cookie.value == ""
    assert "Max-Age=0" in cookie.attributes
    assert f"Path={STATE_COOKIE_PATH}" in cookie.attributes


def code_challenge(code_verifier: str) -> str:
    """PKCE의 S256(RFC 7636 4.2절)."""
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


# --- 앱과 요청 ----------------------------------------------------------------


def make_app(store: FakeAuthStore, provider: FakeIdentityProvider) -> FastAPI:
    app = create_app()
    app.dependency_overrides[get_identity_provider] = lambda: provider
    app.dependency_overrides[get_auth_repository] = lambda: store
    return app


@pytest.fixture
def store() -> FakeAuthStore:
    """reader@example.com이 허용 목록에 있는 빈 저장소."""
    fake = FakeAuthStore()
    fake.allow("reader@example.com")
    return fake


@pytest.fixture
def provider() -> FakeIdentityProvider:
    """READER_IDENTITY(reader@example.com, 이메일 확인됨)를 돌려주는 가짜 신원."""
    return FakeIdentityProvider()


@pytest.fixture
def client(store: FakeAuthStore, provider: FakeIdentityProvider) -> Iterator[TestClient]:
    with TestClient(make_app(store, provider), follow_redirects=False) as test_client:
        yield test_client


def callback(
    client: TestClient,
    *,
    state_cookie: str | None = STATE_COOKIE,
    session_cookie: str | None = None,
    session_cookie_name: str = SESSION_COOKIE,
    query: dict[str, str] | None = None,
) -> httpx.Response:
    """로그인 결과 처리 경로를 부른다.

    쿼리를 주지 않으면 state 쿠키와 맞는 code와 state를 붙인다.
    """
    client.cookies.clear()
    cookies: list[str] = []
    if state_cookie is not None:
        cookies.append(f"{OAUTH_STATE_COOKIE}={state_cookie}")
    if session_cookie is not None:
        cookies.append(f"{session_cookie_name}={session_cookie}")
    headers = {"Cookie": "; ".join(cookies)} if cookies else {}
    return client.get(
        CALLBACK_PATH,
        params=MATCHING_QUERY if query is None else query,
        headers=headers,
    )


def start_login(client: TestClient) -> tuple[httpx.Response, SetCookie]:
    """로그인 시작을 부르고, 응답과 그 응답이 심은 diegesis_oauth_state를 돌려준다."""
    response = client.get(LOGIN_PATH)
    [cookie] = set_cookies(response, OAUTH_STATE_COOKIE)
    return response, cookie


# --- TC-1.5.1, TC-1.2.1: 실제 Google 어댑터로 로그인 시작 ------------------------


def test_login_start_with_real_google_adapter() -> None:
    """TC-1.5.1. 아무것도 덮어쓰지 않은 앱에서 쿠키의 세 값과 인가 주소의 값이 서로 맞는다."""
    with TestClient(create_app(), follow_redirects=False) as client:
        response, cookie = start_login(client)

    assert response.status_code == 302
    location = response.headers["location"]
    assert location.startswith(GOOGLE_AUTHORIZATION_PREFIX)
    assert sorted(cookie.attributes) == state_cookie_attributes(secure=False)
    parts = cookie.value.split(".")
    assert len(parts) == 3
    for part in parts:
        assert TOKEN_PATTERN.fullmatch(part)
    assert len(set(parts)) == 3
    state, nonce, code_verifier = parts
    query = parse_qs(urlsplit(location).query, keep_blank_values=True, strict_parsing=True)
    assert query["client_id"] == [TEST_GOOGLE_CLIENT_ID]
    assert query["state"] == [state]
    assert query["nonce"] == [nonce]
    assert query["code_challenge"] == [code_challenge(code_verifier)]
    assert query["code_challenge_method"] == ["S256"]
    assert code_verifier not in location
    # 로그인 시작은 로그인 상태의 쿠키를 심지 않는다.
    assert set_cookies(response, SESSION_COOKIE) == []


def test_redirect_uri_is_built_from_frontend_url_not_request_host() -> None:
    """TC-1.2.1의 Host 부분. 요청의 Host가 백엔드의 주소여도 돌아올 주소는 FRONTEND_URL을 따른다.

    프론트엔드의 개발 서버는 /api 요청을 넘길 때 Host를 localhost:8080으로 바꾼다(ADR-025).
    """
    with TestClient(
        create_app(), base_url="http://localhost:8080", follow_redirects=False
    ) as client:
        response = client.get(LOGIN_PATH)

    assert response.status_code == 302
    assert response.request.headers["host"] == "localhost:8080"
    query = parse_qs(urlsplit(response.headers["location"]).query, strict_parsing=True)
    assert query["redirect_uri"] == [f"{TEST_FRONTEND_URL}/api/auth/google/callback"]


# --- 로그인 시작 --------------------------------------------------------------


def test_login_start_uses_injected_identity_provider(
    client: TestClient, provider: FakeIdentityProvider
) -> None:
    """가짜 신원을 끼우면 그 신원의 인가 주소로 보낸다.

    쿠키에는 그 신원에 넘긴 세 값을 심는다.
    """
    response, cookie = start_login(client)

    state, nonce, code_verifier = cookie.value.split(".")
    assert_redirect(response, fake_authorization_url(state=state, nonce=nonce))
    assert provider.authorization_url_calls == [
        AuthorizationUrlCall(state=state, nonce=nonce, code_verifier=code_verifier)
    ]
    assert sorted(cookie.attributes) == state_cookie_attributes(secure=False)


# --- 로그인 결과 처리: 실패 ----------------------------------------------------


@pytest.mark.parametrize(
    ("state_cookie", "query"),
    [
        # TC-1.3.3의 네 경우
        pytest.param(None, MATCHING_QUERY, id="TC-1.3.3-no-state-cookie"),
        pytest.param(
            STATE_COOKIE, {"code": CODE, "state": OTHER_STATE}, id="TC-1.3.3-state-mismatch"
        ),
        pytest.param(
            f".{NONCE}.{CODE_VERIFIER}", {"code": CODE, "state": ""}, id="TC-1.3.3-both-empty"
        ),
        pytest.param(STATE, MATCHING_QUERY, id="TC-1.3.3-state-cookie-has-only-state"),
        # TC-1.3.4: 나머지가 모두 맞아도 error 쿼리가 있으면 실패다.
        pytest.param(
            STATE_COOKIE,
            {"error": "access_denied", "state": STATE, "code": CODE},
            id="TC-1.3.4-error-query",
        ),
        # Google이 취소를 알릴 때의 모양(API.md 4.2절). code가 없다.
        pytest.param(
            STATE_COOKIE, {"error": "access_denied", "state": STATE}, id="error-query-without-code"
        ),
        # 쿼리가 빠져도 400 VALIDATION_ERROR가 아니라 LOGIN_FAILED로 돌려보낸다.
        pytest.param(STATE_COOKIE, {"state": STATE}, id="no-code-query"),
        pytest.param(STATE_COOKIE, {}, id="no-code-and-no-state-query"),
        pytest.param(None, {}, id="no-query-and-no-cookie"),
    ],
)
def test_rejects_without_exchanging_code(
    client: TestClient,
    store: FakeAuthStore,
    provider: FakeIdentityProvider,
    state_cookie: str | None,
    query: dict[str, str],
) -> None:
    response = callback(
        client, state_cookie=state_cookie, session_cookie=OLD_SESSION_TOKEN, query=query
    )

    assert_redirect(response, LOGIN_FAILED_LOCATION)
    assert set_cookies(response, SESSION_COOKIE) == []
    assert provider.exchange_code_calls == []
    assert store.writes == []


def test_rejects_unverified_email(
    client: TestClient, store: FakeAuthStore, provider: FakeIdentityProvider
) -> None:
    """TC-1.3.5. 이메일은 허용 목록에 있지만 Google이 확인하지 않은 계정이다."""
    provider.identity = replace(READER_IDENTITY, email_verified=False)

    response = callback(client)

    assert_redirect(response, LOGIN_FAILED_LOCATION)
    assert set_cookies(response, SESSION_COOKIE) == []
    assert store.writes == []


def test_code_exchange_failure_redirects_instead_of_500(
    client: TestClient, store: FakeAuthStore, provider: FakeIdentityProvider
) -> None:
    """TC-1.3.6."""
    provider.error = LoginFailedError(EXCHANGE_FAILURE_MESSAGE)

    response = callback(client)

    assert_redirect(response, LOGIN_FAILED_LOCATION)
    assert set_cookies(response, SESSION_COOKIE) == []
    assert store.writes == []


def test_not_allowed_redirects_without_session_cookie(
    client: TestClient, store: FakeAuthStore, provider: FakeIdentityProvider
) -> None:
    provider.identity = replace(READER_IDENTITY, email="stranger@example.com")

    response = callback(client)

    assert_redirect(response, NOT_ALLOWED_LOCATION)
    assert set_cookies(response, SESSION_COOKIE) == []
    assert store.writes == []


# --- 로그인 결과 처리: 성공 ----------------------------------------------------


def test_success_sets_session_cookie_and_redirects_to_first_screen(
    client: TestClient, store: FakeAuthStore
) -> None:
    response = callback(client)

    assert_redirect(response, SUCCESS_LOCATION)
    [cookie] = set_cookies(response, SESSION_COOKIE)
    assert sorted(cookie.attributes) == session_cookie_attributes(secure=False)
    assert TOKEN_PATTERN.fullmatch(cookie.value)
    # 저장소에는 쿠키 값이 아니라 그 해시가 들어간다.
    assert set(store.login_sessions) == {security.hash_token(cookie.value)}


def test_success_ignores_redirect_parameters(client: TestClient) -> None:
    """로그인 뒤에는 언제나 첫 화면으로 돌아간다(ADR-025). 열린 리디렉션의 구멍이 되면 안 된다."""
    response = callback(
        client,
        query={**MATCHING_QUERY, "next": "https://evil.example/", "redirect": "/books/1"},
    )

    assert_redirect(response, SUCCESS_LOCATION)


def test_exchange_code_receives_query_code_and_cookie_verifier_and_nonce(
    client: TestClient, provider: FakeIdentityProvider
) -> None:
    """TC-1.3.18. 쿠키의 둘째가 nonce, 셋째가 code_verifier다."""
    response = callback(
        client,
        state_cookie="sPart4e1a.nPart7c2b.vPart9d3c",
        query={"code": CODE, "state": "sPart4e1a"},
    )

    assert provider.exchange_code_calls == [
        ExchangeCodeCall(code=CODE, code_verifier="vPart9d3c", expected_nonce="nPart7c2b")
    ]
    assert_redirect(response, SUCCESS_LOCATION)


@pytest.mark.parametrize("cookie_name", [SESSION_COOKIE, "custom_login_cookie"])
def test_session_cookie_name_follows_settings_and_attached_cookie_is_passed(
    monkeypatch: pytest.MonkeyPatch,
    store: FakeAuthStore,
    provider: FakeIdentityProvider,
    cookie_name: str,
) -> None:
    """심는 쿠키와 읽는 쿠키의 이름은 LOGIN_COOKIE_NAME을 따른다.

    요청에 붙어 온 로그인 상태의 쿠키는 service에 넘어가서, 그 쿠키의 행 하나가 지워진다(ADR-027).
    """
    monkeypatch.setenv("LOGIN_COOKIE_NAME", cookie_name)
    get_settings.cache_clear()

    with TestClient(make_app(store, provider), follow_redirects=False) as client:
        response = callback(
            client, session_cookie=OLD_SESSION_TOKEN, session_cookie_name=cookie_name
        )

    assert_redirect(response, SUCCESS_LOCATION)
    [cookie] = set_cookies(response, cookie_name)
    assert sorted(cookie.attributes) == session_cookie_attributes(secure=False)
    assert (
        StoreWrite("delete_login_session", {"token_hash": security.hash_token(OLD_SESSION_TOKEN)})
        in store.writes
    )


def test_session_cookie_max_age_and_expiry_follow_ttl_setting(
    monkeypatch: pytest.MonkeyPatch, store: FakeAuthStore, provider: FakeIdentityProvider
) -> None:
    """Max-Age는 LOGIN_SESSION_TTL_HOURS × 3600이고, 저장하는 만료 시각도 같은 TTL을 쓴다."""
    monkeypatch.setenv("LOGIN_SESSION_TTL_HOURS", "720")
    get_settings.cache_clear()

    with TestClient(make_app(store, provider), follow_redirects=False) as client:
        response = callback(client)
    now = datetime.now(UTC)

    [cookie] = set_cookies(response, SESSION_COOKIE)
    assert sorted(cookie.attributes) == session_cookie_attributes(secure=False, max_age=720 * 3600)
    [session] = store.login_sessions.values()
    assert abs(session.expires_at - (now + timedelta(hours=720))) < timedelta(minutes=1)


# --- TC-1.3.8: 어느 경우든 diegesis_oauth_state를 지운다 -------------------------


def _succeeds(provider: FakeIdentityProvider) -> None:
    pass


def _not_allowed(provider: FakeIdentityProvider) -> None:
    provider.identity = replace(READER_IDENTITY, email="stranger@example.com")


def _exchange_fails(provider: FakeIdentityProvider) -> None:
    provider.error = LoginFailedError(EXCHANGE_FAILURE_MESSAGE)


@pytest.mark.parametrize(
    ("arrange", "state_cookie", "query", "location"),
    [
        pytest.param(_succeeds, STATE_COOKIE, MATCHING_QUERY, SUCCESS_LOCATION, id="success"),
        pytest.param(
            _not_allowed, STATE_COOKIE, MATCHING_QUERY, NOT_ALLOWED_LOCATION, id="not-allowed"
        ),
        pytest.param(
            _succeeds,
            STATE_COOKIE,
            {"code": CODE, "state": OTHER_STATE},
            LOGIN_FAILED_LOCATION,
            id="failed-state-mismatch",
        ),
        pytest.param(
            _exchange_fails,
            STATE_COOKIE,
            MATCHING_QUERY,
            LOGIN_FAILED_LOCATION,
            id="failed-exchange",
        ),
        pytest.param(_succeeds, None, {}, LOGIN_FAILED_LOCATION, id="failed-no-cookie-no-query"),
    ],
)
def test_state_cookie_is_deleted_in_every_case(
    client: TestClient,
    provider: FakeIdentityProvider,
    arrange: Callable[[FakeIdentityProvider], None],
    state_cookie: str | None,
    query: dict[str, str],
    location: str,
) -> None:
    """TC-1.3.8."""
    arrange(provider)

    response = callback(client, state_cookie=state_cookie, query=query)

    assert_redirect(response, location)
    assert_state_cookie_deleted(response)


# --- TC-1.3.9: Secure는 FRONTEND_URL의 스킴을 따른다 ----------------------------


@pytest.mark.parametrize(
    ("frontend_url", "secure"),
    [
        pytest.param("https://diegesis.example", True, id="https"),
        pytest.param(TEST_FRONTEND_URL, False, id="http-localhost"),
    ],
)
def test_secure_attribute_follows_frontend_url_scheme(
    monkeypatch: pytest.MonkeyPatch,
    store: FakeAuthStore,
    provider: FakeIdentityProvider,
    frontend_url: str,
    secure: bool,
) -> None:
    """TC-1.3.9."""
    monkeypatch.setenv("FRONTEND_URL", frontend_url)
    get_settings.cache_clear()

    with TestClient(make_app(store, provider), follow_redirects=False) as client:
        _, state_cookie = start_login(client)
        state, _, _ = state_cookie.value.split(".")
        response = callback(
            client, state_cookie=state_cookie.value, query={"code": CODE, "state": state}
        )

    assert sorted(state_cookie.attributes) == state_cookie_attributes(secure=secure)
    assert_redirect(response, f"{frontend_url}/")
    [session_cookie] = set_cookies(response, SESSION_COOKIE)
    assert sorted(session_cookie.attributes) == session_cookie_attributes(secure=secure)


# --- TC-1.3.17의 뒷부분: 쿠키의 값은 모두 security.new_token()이 만든다 -----------


def test_cookie_values_come_from_security_new_token(
    monkeypatch: pytest.MonkeyPatch, client: TestClient, provider: FakeIdentityProvider
) -> None:
    """TC-1.3.17의 뒷부분."""
    values = iter(["tok-1", "tok-2", "tok-3", "tok-4"])
    monkeypatch.setattr(security, "new_token", lambda: next(values))

    start, state_cookie = start_login(client)
    response = callback(
        client, state_cookie=state_cookie.value, query={"code": CODE, "state": "tok-1"}
    )

    assert state_cookie.value == "tok-1.tok-2.tok-3"
    assert_redirect(start, fake_authorization_url(state="tok-1", nonce="tok-2"))
    assert provider.exchange_code_calls == [
        ExchangeCodeCall(code=CODE, code_verifier="tok-3", expected_nonce="tok-2")
    ]
    [session_cookie] = set_cookies(response, SESSION_COOKIE)
    assert session_cookie.value == "tok-4"


# --- TC-1.3.13: 로그 ----------------------------------------------------------


def capture_server_logs(caplog: pytest.LogCaptureFixture) -> None:
    """모든 로거를 DEBUG부터 모은다.

    httpx 로거만 WARNING으로 올린다. TestClient는 httpx의 클라이언트라서 요청한 주소(code와 state가
    든 쿼리 포함)를 INFO로 남기는데, 그것은 서버가 아니라 이 테스트의 클라이언트가 남긴 로그다.

    caplog.set_level은 로거와 함께 caplog의 처리기의 레벨도 바꾸므로, httpx를 먼저 올리고 전체를
    나중에 DEBUG로 둔다. 순서가 바뀌면 처리기가 WARNING이 되어 서버의 INFO와 DEBUG 기록이 버려지고,
    그 기록에 비밀값이 있어도 이 검사가 초록이 된다.
    """
    caplog.set_level(logging.WARNING, logger="httpx")
    caplog.set_level(logging.DEBUG)
    assert caplog.handler.level == logging.DEBUG
    assert logging.getLogger("app").getEffectiveLevel() == logging.DEBUG


def app_log_messages(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        record.getMessage()
        for record in caplog.records
        if record.name == "app" or record.name.startswith("app.")
    ]


def assert_no_secrets_logged(caplog: pytest.LogCaptureFixture, *secrets: str) -> None:
    """모든 로거의 기록에 비밀값이 없다. 서식을 거친 문장과 예외의 추적까지 본다."""
    texts = [caplog.text, *(record.getMessage() for record in caplog.records)]
    for secret in (
        *secrets,
        CODE,
        OTHER_STATE,
        OLD_SESSION_TOKEN,
        security.hash_token(OLD_SESSION_TOKEN),
        TEST_GOOGLE_CLIENT_SECRET,
    ):
        for text in texts:
            assert secret not in text


@pytest.mark.parametrize(
    ("case", "location", "cause"),
    [
        pytest.param("error-query", LOGIN_FAILED_LOCATION, "error 쿼리", id="error-query"),
        pytest.param("no-state-cookie", LOGIN_FAILED_LOCATION, "state 쿠키가 없", id="no-cookie"),
        pytest.param("not-three-parts", LOGIN_FAILED_LOCATION, "세 부분", id="not-three-parts"),
        pytest.param("state-mismatch", LOGIN_FAILED_LOCATION, "state가 맞지 않", id="mismatch"),
        pytest.param("no-code", LOGIN_FAILED_LOCATION, "code가 없", id="no-code"),
        pytest.param(
            "exchange-failed", LOGIN_FAILED_LOCATION, EXCHANGE_FAILURE_MESSAGE, id="exchange"
        ),
        pytest.param("unverified", LOGIN_FAILED_LOCATION, "email_verified", id="unverified"),
        pytest.param("not-allowed", NOT_ALLOWED_LOCATION, "허용 목록", id="not-allowed"),
    ],
)
def test_failure_logs_cause_without_secrets(
    caplog: pytest.LogCaptureFixture,
    client: TestClient,
    provider: FakeIdentityProvider,
    case: str,
    location: str,
    cause: str,
) -> None:
    """TC-1.3.13. 로그인 시작부터 실패한 결과 처리까지, 원인은 남고 비밀값은 남지 않는다."""
    capture_server_logs(caplog)
    _, state_cookie = start_login(client)
    state, nonce, code_verifier = state_cookie.value.split(".")
    cookie: str | None = state_cookie.value
    query = {"code": CODE, "state": state}
    if case == "error-query":
        query["error"] = "access_denied"
    elif case == "no-state-cookie":
        cookie = None
    elif case == "not-three-parts":
        cookie = state
    elif case == "state-mismatch":
        query["state"] = OTHER_STATE
    elif case == "no-code":
        del query["code"]
    elif case == "exchange-failed":
        provider.error = LoginFailedError(EXCHANGE_FAILURE_MESSAGE)
    elif case == "unverified":
        provider.identity = replace(READER_IDENTITY, email_verified=False)
    else:
        assert case == "not-allowed"
        provider.identity = replace(READER_IDENTITY, email="stranger@example.com")

    response = callback(client, state_cookie=cookie, session_cookie=OLD_SESSION_TOKEN, query=query)

    assert_redirect(response, location)
    assert any(cause in message for message in app_log_messages(caplog))
    assert_no_secrets_logged(caplog, state, nonce, code_verifier, state_cookie.value)


def test_success_logs_no_secrets(caplog: pytest.LogCaptureFixture, client: TestClient) -> None:
    """TC-1.3.13. 로그인 시작과 성공을 거치는 동안 새 쿠키 값과 그 해시도 남지 않는다."""
    capture_server_logs(caplog)
    _, state_cookie = start_login(client)
    state, nonce, code_verifier = state_cookie.value.split(".")

    response = callback(
        client,
        state_cookie=state_cookie.value,
        session_cookie=OLD_SESSION_TOKEN,
        query={"code": CODE, "state": state},
    )

    assert_redirect(response, SUCCESS_LOCATION)
    [session_cookie] = set_cookies(response, SESSION_COOKIE)
    assert_no_secrets_logged(
        caplog,
        state,
        nonce,
        code_verifier,
        state_cookie.value,
        session_cookie.value,
        security.hash_token(session_cookie.value),
    )


# --- 로그아웃 ------------------------------------------------------------------


def logout(
    client: TestClient,
    *,
    session_cookie: str | None = None,
    session_cookie_name: str = SESSION_COOKIE,
    origin: str = TEST_FRONTEND_URL,
) -> httpx.Response:
    """로그아웃을 부른다. 출처 확인을 통과하도록 Origin을 붙인다."""
    client.cookies.clear()
    headers = {"Origin": origin}
    if session_cookie is not None:
        headers["Cookie"] = f"{session_cookie_name}={session_cookie}"
    return client.post(LOGOUT_PATH, headers=headers)


def deleted_session_cookie_attributes(*, secure: bool) -> list[str]:
    """로그인 상태의 쿠키를 지울 때의 속성. 심을 때와 같은 Path, HttpOnly, SameSite, Secure다.

    브라우저는 이름과 경로가 모두 같은 쿠키만 지우므로 Path=/가 빠지면 쿠키가 남는다.
    """
    return sorted(
        ["HttpOnly", "SameSite=Lax", "Path=/", "Max-Age=0", *(["Secure"] if secure else [])]
    )


def assert_logged_out(
    response: httpx.Response, *, secure: bool = False, cookie_name: str = SESSION_COOKIE
) -> None:
    """204이고 본문이 없으며, 로그인 상태의 쿠키를 지우는 Set-Cookie가 하나 있다."""
    assert response.status_code == 204, response.text
    assert response.content == b""
    [cookie] = set_cookies(response, cookie_name)
    assert cookie.value == ""
    assert sorted(cookie.attributes) == deleted_session_cookie_attributes(secure=secure)


def far_future() -> datetime:
    return datetime.now(UTC) + timedelta(days=1)


@pytest.mark.parametrize(
    "session_cookie",
    [
        pytest.param(None, id="no-cookie"),
        pytest.param(UNKNOWN_SESSION_TOKEN, id="unknown-cookie"),
    ],
)
def test_logout_without_valid_login_returns_204_and_deletes_cookie(
    client: TestClient, store: FakeAuthStore, session_cookie: str | None
) -> None:
    """TC-1.3.12. 로그아웃은 관문을 거치지 않으므로 로그인 상태를 조회하지 않는다."""
    response = logout(client, session_cookie=session_cookie)

    assert_logged_out(response)
    assert store.lookups == []
    if session_cookie is None:
        assert store.writes == []
    else:
        assert store.writes == [
            StoreWrite("delete_login_session", {"token_hash": security.hash_token(session_cookie)})
        ]


def test_logout_deletes_only_the_attached_login_session(
    client: TestClient, store: FakeAuthStore
) -> None:
    """요청에 붙은 쿠키의 행 하나만 지운다. 같은 사람의 다른 기기 행은 그대로 둔다."""
    user = store.put_user("reader@example.com", READER_IDENTITY.sub)
    store.put_login_session(security.hash_token(OLD_SESSION_TOKEN), user.id, far_future())
    store.put_login_session(security.hash_token(OTHER_DEVICE_TOKEN), user.id, far_future())

    response = logout(client, session_cookie=OLD_SESSION_TOKEN)

    assert_logged_out(response)
    assert set(store.login_sessions) == {security.hash_token(OTHER_DEVICE_TOKEN)}


def test_logout_of_person_removed_from_allowlist_returns_204(
    client: TestClient, store: FakeAuthStore
) -> None:
    """허용 목록에서 빠진 사람도 로그아웃할 수 있다(API.md 4.2절, ADR-025)."""
    user = store.put_user("stranger@example.com", "sub-stranger")
    store.put_login_session(security.hash_token(OLD_SESSION_TOKEN), user.id, far_future())

    response = logout(client, session_cookie=OLD_SESSION_TOKEN)

    assert_logged_out(response)
    assert store.login_sessions == {}


def test_logout_cookie_name_and_secure_follow_settings(
    monkeypatch: pytest.MonkeyPatch, store: FakeAuthStore, provider: FakeIdentityProvider
) -> None:
    """읽고 지우는 쿠키의 이름은 LOGIN_COOKIE_NAME을, Secure는 FRONTEND_URL의 스킴을 따른다."""
    frontend_url = "https://diegesis.example"
    monkeypatch.setenv("LOGIN_COOKIE_NAME", "custom_login_cookie")
    monkeypatch.setenv("FRONTEND_URL", frontend_url)
    get_settings.cache_clear()

    with TestClient(make_app(store, provider), follow_redirects=False) as client:
        response = logout(
            client,
            session_cookie=UNKNOWN_SESSION_TOKEN,
            session_cookie_name="custom_login_cookie",
            origin=frontend_url,
        )

    assert_logged_out(response, secure=True, cookie_name="custom_login_cookie")
    assert set_cookies(response, SESSION_COOKIE) == []
    assert store.writes == [
        StoreWrite(
            "delete_login_session", {"token_hash": security.hash_token(UNKNOWN_SESSION_TOKEN)}
        )
    ]


def test_logout_is_not_served_by_get(client: TestClient, store: FakeAuthStore) -> None:
    """상태를 바꾸는 경로는 GET으로 받지 않는다(ADR-027). GET은 출처 확인을 거치지 않는다."""
    client.cookies.clear()
    response = client.get(LOGOUT_PATH, headers={"Cookie": f"{SESSION_COOKIE}={OLD_SESSION_TOKEN}"})

    assert response.status_code == 405
    assert response.json()["code"] == "METHOD_NOT_ALLOWED"
    assert set_cookies(response, SESSION_COOKIE) == []
    assert store.writes == []


# --- 내 정보 ------------------------------------------------------------------


def test_me_returns_the_user_and_role_from_allowlist(
    client: TestClient, store: FakeAuthStore
) -> None:
    """관문이 돌려준 사용자를 그대로 응답한다. 역할은 허용 목록의 값이고, 이름이 없으면 null이다."""
    store.allow("admin@example.com", "admin")
    user = store.put_user("admin@example.com", "sub-admin", display_name=None)
    store.put_login_session(security.hash_token(OLD_SESSION_TOKEN), user.id, far_future())

    client.cookies.clear()
    response = client.get(ME_PATH, headers={"Cookie": f"{SESSION_COOKIE}={OLD_SESSION_TOKEN}"})

    assert response.status_code == 200, response.text
    assert response.json() == {
        "id": str(user.id),
        "email": "admin@example.com",
        "display_name": None,
        "role": "admin",
    }
    assert store.writes == []


# --- TC-1.5.3: OpenAPI 문서 -----------------------------------------------------


def test_openapi_lists_this_epics_routes_and_no_allowlist_api(client: TestClient) -> None:
    """TC-1.5.3. 허용 목록은 SQL로만 다루므로 그것을 조회하거나 바꾸는 경로가 없다(ADR-024)."""
    document = client.get("/api/openapi.json").json()
    paths = document["paths"]

    assert {LOGIN_PATH, CALLBACK_PATH, LOGOUT_PATH, ME_PATH} <= set(paths)
    assert set(paths[LOGOUT_PATH]) == {"post"}
    assert set(paths[ME_PATH]) == {"get"}
    assert [path for path in paths if path.startswith("/api/admin/allowed-emails")] == []
    # 프론트엔드는 이 문서로 타입을 만든다(docs/DEVELOPMENT.md 6.4절). 내 정보의 네 필드가 있다.
    me_schema = document["components"]["schemas"]["MeResponse"]
    assert set(me_schema["properties"]) == {"id", "email", "display_name", "role"}
    assert me_schema["properties"]["role"]["enum"] == ["user", "admin"]


# --- 의존 방향 --------------------------------------------------------------

# 어댑터를 아는 곳은 app/main.py뿐이다. 라우터는 IdentityProvider 포트만 안다
# (docs/ARCHITECTURE.md 8절: 어댑터는 서버가 시작될 때 주입된다).
ADAPTERS_PACKAGE = "app.adapters"
ROUTER_PACKAGE = "app.auth"


def imported_modules(source: str, package: str = ROUTER_PACKAGE) -> set[str]:
    """import 구문이 가져오는 것의 전체 이름. `from a.b import c`는 `a.b.c`로 센다.

    상대 경로의 import는 package를 기준으로 절대 이름으로 바꾼다. 함수 안의 import도 센다.
    """
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                package_parts = package.split(".")
                base = package_parts[: len(package_parts) - (node.level - 1)]
                module = ".".join([*base, *([node.module] if node.module else [])])
            else:
                module = node.module or ""
            found.update(f"{module}.{alias.name}" for alias in node.names)
    return found


def adapter_imports(source: str) -> set[str]:
    return {
        name
        for name in imported_modules(source)
        if name == ADAPTERS_PACKAGE or name.startswith(f"{ADAPTERS_PACKAGE}.")
    }


@pytest.mark.parametrize(
    ("source", "found"),
    [
        (
            "from app.adapters.google import GoogleIdentityProvider",
            {"app.adapters.google.GoogleIdentityProvider"},
        ),
        ("import app.adapters.google", {"app.adapters.google"}),
        ("from app import adapters", {"app.adapters"}),
        ("from ..adapters import google", {"app.adapters.google"}),
        (
            "def f():\n    from app.adapters import google\n    return google",
            {"app.adapters.google"},
        ),
        ("from app.core.ports import IdentityProvider", set()),
        ("from app.adaptersx import thing", set()),
    ],
)
def test_adapter_import_detector(source: str, found: set[str]) -> None:
    # 아래 검사가 import를 놓치면 라우터가 어댑터를 가져와도 초록이 된다.
    assert adapter_imports(source) == found


def test_router_does_not_import_adapters() -> None:
    assert adapter_imports(ROUTER_PATH.read_text(encoding="utf-8")) == set()
