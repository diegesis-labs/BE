"""로그인 시작, 로그인 결과 처리, 로그아웃의 규칙(app/auth/service.py)의 단위 테스트.

docs/backlog/epic-1/testcase.md의 S1.3 가운데 service가 정하는 부분(분기, 저장소의 변화, 가짜 신원이
받은 값, 로그)을 service를 직접 불러 확인한다. 리디렉션 주소와 쿠키의 속성은 라우터의 테스트가
HTTP로 확인한다. 결과 처리의 순서는 docs/API.md 4.2절의 동작 순서다.

가짜 신원(FakeIdentityProvider)과 메모리 저장소(FakeAuthStore)를 끼운다. 데이터베이스에 닿는 확인은
tests/auth/test_service_integration.py에 있다.

state, nonce, code_verifier, code, 쿠키 값은 서로 다르고 로그의 문장과 겹치지 않는 문자열로 둔다.
자리가 바뀌거나 로그에 새면 드러나게 하기 위해서다.
"""

import ast
import logging
import re
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from app.auth.repository import UserRecord
from app.auth.service import AuthService, LoginRejected, LoginResult, LoginSucceeded
from app.core import security
from app.core.ports import LoginFailedError
from tests.support.auth_fakes import (
    READER_IDENTITY,
    AuthorizationUrlCall,
    ExchangeCodeCall,
    FakeAuthStore,
    FakeIdentityProvider,
    fake_authorization_url,
)
from tests.support.settings import TEST_GOOGLE_CLIENT_SECRET

REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE_PATH = REPO_ROOT / "app" / "auth" / "service.py"

SESSION_TTL = timedelta(hours=336)

STATE = "stateValue7f1c"
NONCE = "nonceValue2b8d"
CODE_VERIFIER = "verifierValue9e4a"
CODE = "googleCode5c3f"
STATE_COOKIE = f"{STATE}.{NONCE}.{CODE_VERIFIER}"
OTHER_STATE = "otherState3d9a"
OLD_SESSION_TOKEN = "oldSessionToken1a6b"

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{43}")

LOGIN_FAILED = LoginRejected(error="LOGIN_FAILED")
NOT_ALLOWED = LoginRejected(error="NOT_ALLOWED")

# 로그에 나오면 안 되는 값. 쿠키 값(state 쿠키, 로그인 상태의 쿠키)과 그 해시, code, state, nonce,
# code_verifier, 클라이언트 비밀값이다(E1 "못 박을 것", TC-1.3.13).
SECRET_VALUES = (
    STATE,
    NONCE,
    CODE_VERIFIER,
    CODE,
    OTHER_STATE,
    OLD_SESSION_TOKEN,
    security.hash_token(OLD_SESSION_TOKEN),
    TEST_GOOGLE_CLIENT_SECRET,
)


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
def service(store: FakeAuthStore, provider: FakeIdentityProvider) -> AuthService:
    return AuthService(store, provider, session_ttl=SESSION_TTL)


async def complete(service: AuthService, **overrides: Any) -> LoginResult:
    """state 쿠키, state, code가 모두 맞는 결과 처리. 덮어쓴 인자만 바꾼다."""
    arguments: dict[str, Any] = {
        "state_cookie": STATE_COOKIE,
        "state": STATE,
        "code": CODE,
        "error": None,
        "current_session_token": None,
    }
    arguments.update(overrides)
    return await service.complete_login(**arguments)


def service_log_messages(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [record.getMessage() for record in caplog.records if record.name == "app.auth.service"]


def assert_no_secrets_logged(caplog: pytest.LogCaptureFixture, *extra: str) -> None:
    """모든 로거의 기록에 비밀값이 없다. 서식을 거친 문장과 예외의 추적까지 본다."""
    texts = [caplog.text, *(record.getMessage() for record in caplog.records)]
    for secret in (*SECRET_VALUES, *extra):
        for text in texts:
            assert secret not in text


# --- start_login ------------------------------------------------------------


def test_start_login_makes_three_distinct_tokens_and_passes_them_to_provider(
    service: AuthService, provider: FakeIdentityProvider
) -> None:
    start = service.start_login()

    parts = start.state_cookie.split(".")
    assert len(parts) == 3
    state, nonce, code_verifier = parts
    assert len(set(parts)) == 3
    for part in parts:
        assert TOKEN_PATTERN.fullmatch(part)
    assert provider.authorization_url_calls == [
        AuthorizationUrlCall(state=state, nonce=nonce, code_verifier=code_verifier)
    ]
    assert start.authorization_url == fake_authorization_url(state=state, nonce=nonce)


def test_start_login_makes_new_tokens_every_time(service: AuthService) -> None:
    first = service.start_login()
    second = service.start_login()

    assert set(first.state_cookie.split(".")).isdisjoint(second.state_cookie.split("."))


async def test_tokens_come_from_security_new_token(
    monkeypatch: pytest.MonkeyPatch, service: AuthService, provider: FakeIdentityProvider
) -> None:
    """state, nonce, code_verifier, 로그인 상태의 쿠키 값을 모두 security.new_token()으로 만든다.

    TC-1.3.17의 service 부분. 이름을 가져와 부르면 모듈의 함수를 바꿔도 반영되지 않는다.
    """
    values = iter(["tok-1", "tok-2", "tok-3", "tok-4"])
    monkeypatch.setattr(security, "new_token", lambda: next(values))

    start = service.start_login()
    result = await complete(service, state_cookie=start.state_cookie, state="tok-1")

    assert start.state_cookie == "tok-1.tok-2.tok-3"
    assert provider.authorization_url_calls == [
        AuthorizationUrlCall(state="tok-1", nonce="tok-2", code_verifier="tok-3")
    ]
    assert provider.exchange_code_calls == [
        ExchangeCodeCall(code=CODE, code_verifier="tok-3", expected_nonce="tok-2")
    ]
    assert result == LoginSucceeded(session_token="tok-4")


# --- TC-1.3.3, TC-1.3.4, code가 없음: code를 교환하지 않는다 --------------------


@pytest.mark.parametrize(
    "overrides",
    [
        # TC-1.3.3의 네 경우
        pytest.param({"state_cookie": None}, id="TC-1.3.3-no-state-cookie"),
        pytest.param({"state": OTHER_STATE}, id="TC-1.3.3-state-mismatch"),
        pytest.param(
            {"state_cookie": f".{NONCE}.{CODE_VERIFIER}", "state": ""},
            id="TC-1.3.3-both-states-empty",
        ),
        pytest.param({"state_cookie": STATE}, id="TC-1.3.3-state-cookie-has-only-state"),
        # 그 밖의 state 확인
        pytest.param({"state": None}, id="no-state-query"),
        pytest.param({"state": ""}, id="empty-state-query"),
        pytest.param({"state_cookie": f".{NONCE}.{CODE_VERIFIER}"}, id="empty-cookie-state"),
        pytest.param({"state_cookie": f"{STATE_COOKIE}.extra"}, id="state-cookie-has-four-parts"),
        pytest.param({"state_cookie": f"{STATE}.{NONCE}"}, id="state-cookie-has-two-parts"),
        pytest.param({"state_cookie": ""}, id="empty-state-cookie"),
        # TC-1.3.4: 나머지가 모두 맞아도 error 쿼리가 있으면 실패다.
        pytest.param({"error": "access_denied"}, id="TC-1.3.4-error-query"),
        pytest.param({"error": ""}, id="empty-error-query"),
        # code가 없음
        pytest.param({"code": None}, id="no-code"),
        pytest.param({"code": ""}, id="empty-code"),
    ],
)
async def test_rejects_without_exchanging_code(
    service: AuthService,
    store: FakeAuthStore,
    provider: FakeIdentityProvider,
    overrides: dict[str, Any],
) -> None:
    result = await complete(service, current_session_token=OLD_SESSION_TOKEN, **overrides)

    assert result == LOGIN_FAILED
    assert provider.exchange_code_calls == []
    assert store.writes == []


# --- TC-1.3.5, TC-1.3.6 -----------------------------------------------------


async def test_rejects_identity_whose_email_is_not_verified(
    store: FakeAuthStore, provider: FakeIdentityProvider, service: AuthService
) -> None:
    """TC-1.3.5. 이메일은 허용 목록에 있지만 Google이 확인하지 않았다."""
    provider.identity = replace(READER_IDENTITY, email_verified=False)

    result = await complete(service, current_session_token=OLD_SESSION_TOKEN)

    assert result == LOGIN_FAILED
    assert len(provider.exchange_code_calls) == 1
    assert store.writes == []
    assert store.users == {}


async def test_rejects_when_code_exchange_fails(
    store: FakeAuthStore, provider: FakeIdentityProvider, service: AuthService
) -> None:
    """TC-1.3.6. 어댑터의 LoginFailedError를 밖으로 내보내지 않고 LOGIN_FAILED로 바꾼다."""
    provider.error = LoginFailedError("토큰 교환이 400으로 실패")

    result = await complete(service, current_session_token=OLD_SESSION_TOKEN)

    assert result == LOGIN_FAILED
    assert store.writes == []


# --- TC-1.3.18 --------------------------------------------------------------


async def test_exchange_code_receives_query_code_and_cookie_verifier_and_nonce(
    service: AuthService, provider: FakeIdentityProvider
) -> None:
    """TC-1.3.18. 쿠키 {s}.{n}.{v}의 셋째가 code_verifier, 둘째가 기대하는 nonce다."""
    result = await complete(service)

    assert isinstance(result, LoginSucceeded)
    assert provider.exchange_code_calls == [
        ExchangeCodeCall(code=CODE, code_verifier=CODE_VERIFIER, expected_nonce=NONCE)
    ]


# --- 허용 목록, 이메일과 google_sub의 쌍 ------------------------------------------


async def test_not_allowed_does_not_touch_store(
    store: FakeAuthStore, provider: FakeIdentityProvider, service: AuthService
) -> None:
    """TC-1.3.2의 service 부분. 허용 목록 밖이면 users와 login_sessions를 바꾸지 않는다."""
    provider.identity = replace(READER_IDENTITY, email="stranger@example.com")

    result = await complete(service, current_session_token=OLD_SESSION_TOKEN)

    assert result == NOT_ALLOWED
    assert store.writes == []


async def test_allowlist_is_checked_with_lowercased_email(
    store: FakeAuthStore, provider: FakeIdentityProvider, service: AuthService
) -> None:
    """TC-1.3.7의 service 부분. 이후의 조회와 저장도 소문자로 바꾼 이메일로 한다."""
    provider.identity = replace(READER_IDENTITY, email="Reader@Example.COM")

    result = await complete(service)

    assert isinstance(result, LoginSucceeded)
    assert [user.email for user in store.users.values()] == ["reader@example.com"]


@pytest.mark.parametrize(
    ("email", "google_sub"),
    [
        pytest.param("reader@example.com", "sub-B", id="same-email-other-sub"),
        pytest.param("other@example.com", "sub-A", id="same-sub-other-email"),
    ],
)
async def test_rejects_when_only_email_or_only_sub_matches(
    store: FakeAuthStore,
    provider: FakeIdentityProvider,
    service: AuthService,
    email: str,
    google_sub: str,
) -> None:
    """TC-1.3.14의 service 부분. 기존 행을 고치거나 새 행을 만들지 않는다."""
    store.allow("other@example.com")
    existing = store.put_user("reader@example.com", "sub-A", "원래 이름")
    provider.identity = replace(READER_IDENTITY, email=email, sub=google_sub)

    result = await complete(service, current_session_token=OLD_SESSION_TOKEN)

    assert result == LOGIN_FAILED
    assert store.writes == []
    assert store.users == {existing.id: existing}


# --- 같은 사람의 첫 로그인이 겹칠 때 (1차 리뷰 COR-1) ----------------------
#
# 결과 처리 두 개가 함께 쌍을 확인해 행이 없다고 본 뒤, 한쪽이 먼저 사용자를 등록하는 경우다.
# store.before_create_user로 "다른 요청이 쌍 확인과 등록 사이에 행을 만들었다"를 흉내 낸다.
# 어떤 경우에도 고유 제약 위반이 밖으로 나가지 않는다(E1 S1.3).


async def test_first_login_racing_with_same_person_uses_the_row_made_by_other_request(
    store: FakeAuthStore, service: AuthService
) -> None:
    made_by_other: list[UserRecord] = []
    store.before_create_user = lambda: made_by_other.append(
        store.put_user("reader@example.com", "1234567890", "독자")
    )

    result = await complete(service)

    assert isinstance(result, LoginSucceeded)
    [other_user] = made_by_other
    assert store.users == {other_user.id: other_user}
    token_hash = security.hash_token(result.session_token)
    assert set(store.login_sessions) == {token_hash}
    assert store.login_sessions[token_hash].user_id == other_user.id


@pytest.mark.parametrize(
    ("email", "google_sub"),
    [
        pytest.param("reader@example.com", "sub-B", id="same-email-other-sub"),
        pytest.param("other@example.com", "1234567890", id="same-sub-other-email"),
    ],
)
async def test_first_login_racing_with_other_account_is_login_failed(
    store: FakeAuthStore, service: AuthService, email: str, google_sub: str
) -> None:
    """겹친 요청이 만든 행이 이메일만 같거나 google_sub만 같으면 처음부터 있던 행처럼 거부한다."""
    made_by_other: list[UserRecord] = []
    store.before_create_user = lambda: made_by_other.append(store.put_user(email, google_sub))

    result = await complete(service, current_session_token=OLD_SESSION_TOKEN)

    assert result == LOGIN_FAILED
    [other_user] = made_by_other
    assert store.users == {other_user.id: other_user}
    assert store.login_sessions == {}
    # 등록을 시도한 것 말고는 쓰지 않는다. 옛 쿠키의 행도 지우지 않는다.
    assert [write.method for write in store.writes] == ["create_user"]


# --- 성공 -------------------------------------------------------------------


async def test_success_creates_user_and_stores_only_hash_of_new_token(
    store: FakeAuthStore, service: AuthService
) -> None:
    before = datetime.now(UTC)
    result = await complete(service)
    after = datetime.now(UTC)

    assert isinstance(result, LoginSucceeded)
    assert TOKEN_PATTERN.fullmatch(result.session_token)
    [user] = store.users.values()
    assert (user.email, user.google_sub, user.display_name) == (
        "reader@example.com",
        "1234567890",
        "독자",
    )
    token_hash = security.hash_token(result.session_token)
    assert set(store.login_sessions) == {token_hash}
    login_session = store.login_sessions[token_hash]
    assert login_session.user_id == user.id
    assert before + SESSION_TTL <= login_session.expires_at <= after + SESSION_TTL


async def test_success_for_known_pair_updates_display_name_without_creating_user(
    store: FakeAuthStore, service: AuthService
) -> None:
    existing = store.put_user("reader@example.com", "1234567890", "옛 이름")

    result = await complete(service)

    assert isinstance(result, LoginSucceeded)
    assert store.users == {existing.id: replace(existing, display_name="독자")}
    assert "create_user" not in [write.method for write in store.writes]
    assert store.login_sessions[security.hash_token(result.session_token)].user_id == existing.id


async def test_success_deletes_attached_cookie_and_own_expired_sessions_only(
    store: FakeAuthStore, service: AuthService
) -> None:
    """요청에 붙은 쿠키의 행과 그 사용자의 만료된 행만 지운다.

    TC-1.3.15, TC-1.3.16의 service 부분.
    """
    now = datetime.now(UTC)
    reader = store.put_user("reader@example.com", "1234567890")
    other = store.put_user("other@example.com", "sub-other")
    store.put_login_session(security.hash_token(OLD_SESSION_TOKEN), reader.id, now + SESSION_TTL)
    store.put_login_session("reader-other-device", reader.id, now + SESSION_TTL)
    store.put_login_session("reader-expired", reader.id, now - timedelta(hours=1))
    store.put_login_session("other-expired", other.id, now - timedelta(hours=1))

    result = await complete(service, current_session_token=OLD_SESSION_TOKEN)

    assert isinstance(result, LoginSucceeded)
    assert set(store.login_sessions) == {
        "reader-other-device",
        "other-expired",
        security.hash_token(result.session_token),
    }


# --- 로그아웃 ---------------------------------------------------------------


@pytest.mark.parametrize("session_token", [None, ""])
async def test_logout_without_cookie_does_nothing(
    store: FakeAuthStore, service: AuthService, session_token: str | None
) -> None:
    """TC-1.3.12의 service 부분. 쿠키가 없으면 예외 없이 끝나고 저장소에 쓰지 않는다."""
    await service.logout(session_token)

    assert store.writes == []


async def test_logout_with_unknown_cookie_ends_without_error(
    store: FakeAuthStore, service: AuthService
) -> None:
    """TC-1.3.12의 service 부분. 백엔드가 모르는 값이어도 예외 없이 끝난다."""
    reader = store.put_user("reader@example.com", "1234567890")
    store.put_login_session("reader-phone", reader.id, datetime.now(UTC) + SESSION_TTL)

    await service.logout("unknown-cookie-value")

    assert set(store.login_sessions) == {"reader-phone"}


async def test_logout_deletes_only_login_session_of_that_cookie(
    store: FakeAuthStore, service: AuthService
) -> None:
    reader = store.put_user("reader@example.com", "1234567890")
    expires_at = datetime.now(UTC) + SESSION_TTL
    store.put_login_session(security.hash_token(OLD_SESSION_TOKEN), reader.id, expires_at)
    store.put_login_session("reader-other-device", reader.id, expires_at)

    await service.logout(OLD_SESSION_TOKEN)

    assert set(store.login_sessions) == {"reader-other-device"}


# --- TC-1.3.13: 로그 -------------------------------------------------------


def _unverified(provider: FakeIdentityProvider) -> None:
    provider.identity = replace(READER_IDENTITY, email_verified=False)


def _exchange_fails(provider: FakeIdentityProvider) -> None:
    provider.error = LoginFailedError("ID 토큰의 aud가 다름")


def _not_allowed(provider: FakeIdentityProvider) -> None:
    provider.identity = replace(READER_IDENTITY, email="stranger@example.com")


def _no_change(provider: FakeIdentityProvider) -> None:
    pass


@pytest.mark.parametrize(
    ("overrides", "arrange", "expected", "cause"),
    [
        pytest.param({"error": "access_denied"}, _no_change, LOGIN_FAILED, "error", id="error"),
        pytest.param(
            {"state_cookie": None}, _no_change, LOGIN_FAILED, "state 쿠키가 없", id="no-cookie"
        ),
        pytest.param(
            {"state_cookie": STATE}, _no_change, LOGIN_FAILED, "세 부분", id="not-three-parts"
        ),
        pytest.param(
            {"state": OTHER_STATE}, _no_change, LOGIN_FAILED, "state가 맞지 않", id="mismatch"
        ),
        pytest.param({"code": None}, _no_change, LOGIN_FAILED, "code가 없", id="no-code"),
        pytest.param(
            {}, _exchange_fails, LOGIN_FAILED, "ID 토큰의 aud가 다름", id="exchange-failed"
        ),
        pytest.param({}, _unverified, LOGIN_FAILED, "email_verified", id="unverified"),
        pytest.param({}, _not_allowed, NOT_ALLOWED, "허용 목록", id="not-allowed"),
    ],
)
async def test_failure_logs_cause_without_secrets(
    caplog: pytest.LogCaptureFixture,
    store: FakeAuthStore,
    provider: FakeIdentityProvider,
    service: AuthService,
    overrides: dict[str, Any],
    arrange: Callable[[FakeIdentityProvider], None],
    expected: LoginRejected,
    cause: str,
) -> None:
    """TC-1.3.13의 service 부분. 실패와 거부마다 원인이 로그에 남고, 비밀값은 남지 않는다."""
    arrange(provider)
    caplog.set_level(logging.DEBUG)

    result = await complete(service, current_session_token=OLD_SESSION_TOKEN, **overrides)

    assert result == expected
    assert any(cause in message for message in service_log_messages(caplog))
    assert_no_secrets_logged(caplog)


@pytest.mark.parametrize(
    ("email", "google_sub", "cause"),
    [
        pytest.param("reader@example.com", "sub-B", "google_sub가 다른", id="same-email"),
        pytest.param("other@example.com", "sub-A", "이메일이 다른", id="same-sub"),
    ],
)
async def test_pair_mismatch_logs_cause_without_secrets(
    caplog: pytest.LogCaptureFixture,
    store: FakeAuthStore,
    provider: FakeIdentityProvider,
    service: AuthService,
    email: str,
    google_sub: str,
    cause: str,
) -> None:
    """TC-1.3.13, TC-1.3.14의 service 부분. 어느 방향으로 어긋났는지 로그에 남긴다."""
    store.allow("other@example.com")
    store.put_user("reader@example.com", "sub-A")
    provider.identity = replace(READER_IDENTITY, email=email, sub=google_sub)
    caplog.set_level(logging.DEBUG)

    result = await complete(service, current_session_token=OLD_SESSION_TOKEN)

    assert result == LOGIN_FAILED
    assert any(cause in message for message in service_log_messages(caplog))
    assert_no_secrets_logged(caplog)


async def test_success_does_not_log_tokens(
    caplog: pytest.LogCaptureFixture, store: FakeAuthStore, service: AuthService
) -> None:
    """TC-1.3.13의 service 부분. 새 쿠키 값과 그 해시, 옛 쿠키 값이 로그에 없다."""
    caplog.set_level(logging.DEBUG)

    start = service.start_login()
    start_state, _, _ = start.state_cookie.split(".")
    result = await complete(
        service,
        state_cookie=start.state_cookie,
        state=start_state,
        current_session_token=OLD_SESSION_TOKEN,
    )

    assert isinstance(result, LoginSucceeded)
    assert_no_secrets_logged(
        caplog,
        *start.state_cookie.split("."),
        result.session_token,
        security.hash_token(result.session_token),
    )


# --- 의존 방향 --------------------------------------------------------------

# service는 특정 기술의 이름을 알지 못한다. Google은 IdentityProvider 포트를 거친다
# (docs/ARCHITECTURE.md 8절, E1 "못 박을 것").
FORBIDDEN_MODULES = ("fastapi", "sqlalchemy", "httpx", "app.adapters")
SERVICE_PACKAGE = "app.auth"
# service가 app/에서 가져와도 되는 것. repository에서는 레코드 타입만 가져온다. AuthRepository를
# 가져오면 SQLAlchemy에 기대게 된다.
REPOSITORY_RECORDS = frozenset({"AllowedEmail", "UserRecord", "ActiveLogin"})


def imported_names(source: str, package: str = SERVICE_PACKAGE) -> set[str]:
    """import 구문이 가져오는 것의 전체 이름. `from a.b import c`는 `a.b.c`로 센다.

    상대 경로의 import는 package를 기준으로 절대 이름으로 바꾼다.
    """
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base_parts = package.split(".")[: len(package.split(".")) - (node.level - 1)]
                module = ".".join([*base_parts, *([node.module] if node.module else [])])
            else:
                module = node.module or ""
            found.update(f"{module}.{alias.name}" for alias in node.names)
    return found


def is_forbidden(name: str) -> bool:
    return any(name == module or name.startswith(f"{module}.") for module in FORBIDDEN_MODULES)


def is_allowed_app_import(name: str) -> bool:
    if name in {"app.core.security", "app.core.ports"} or name.startswith("app.core.ports."):
        return True
    module, _, attribute = name.rpartition(".")
    return module == "app.auth.repository" and attribute in REPOSITORY_RECORDS


@pytest.mark.parametrize(
    ("source", "forbidden"),
    [
        ("import fastapi", {"fastapi"}),
        ("from fastapi import Depends", {"fastapi.Depends"}),
        (
            "from sqlalchemy.ext.asyncio import AsyncSession",
            {"sqlalchemy.ext.asyncio.AsyncSession"},
        ),
        ("import httpx", {"httpx"}),
        ("def f():\n    import httpx\n    return httpx", {"httpx"}),
        (
            "from app.adapters.google import GoogleIdentityProvider",
            {"app.adapters.google.GoogleIdentityProvider"},
        ),
        ("from app import adapters", {"app.adapters"}),
        ("from ..adapters import google", {"app.adapters.google"}),
        ("from app.core import security", set()),
        ("import httpx_mock, fastapiish", set()),
        ("from app.adaptersx import thing", set()),
    ],
)
def test_forbidden_import_detector(source: str, forbidden: set[str]) -> None:
    # 아래 검사가 import를 놓치면 service가 특정 기술을 가져와도 초록이 된다.
    assert {name for name in imported_names(source) if is_forbidden(name)} == forbidden


@pytest.mark.parametrize(
    ("name", "allowed"),
    [
        ("app.core.security", True),
        ("app.core.ports.IdentityProvider", True),
        ("app.auth.repository.UserRecord", True),
        ("app.auth.repository.AuthRepository", False),
        ("app.auth.repository", False),
        ("app.core.database.DbSession", False),
        ("app.core.config.get_settings", False),
    ],
)
def test_allowed_app_import_rule(name: str, allowed: bool) -> None:
    assert is_allowed_app_import(name) is allowed


def test_service_imports_no_framework_database_http_or_adapter() -> None:
    names = imported_names(SERVICE_PATH.read_text(encoding="utf-8"))

    assert {name for name in names if is_forbidden(name)} == set()
    assert {
        name for name in names if name.startswith("app.") and not is_allowed_app_import(name)
    } == set()
