"""`scripts/login_check.py`의 표 대조, 출력, 점검 전 확인의 테스트.

점검 스크립트의 `main`은 실제 Google 계정과 사람이 필요하므로 검사에서 돌리지 않는다(ADR-026).
그래서 판정과 출력은 대역 서버와 데이터베이스에서 떼어 낸 순수 함수로 두었고, 이 파일은 그 함수들을
testcase.md의 "로컬 로그인 점검의 테이블 상태"의 두 표에 견준다.

- 표와 같은 상태(점검 1의 네 시점, 점검 2의 두 시점)를 만들어 판정하면 다른 칸이 없다.
- 표와 한 칸만 다른 상태를 만들어 판정하면 그 칸 하나만 보고된다. 그 칸이 아닌 다른 칸이 함께
  보고되거나 아무것도 보고되지 않으면 판정이 틀린 것이다(step 11의 반증 조건).
- 쿠키의 값과 token_hash의 값은 출력에도, 판정의 문장에도 나오지 않는다.
"""

import ast
import hashlib
import socket
import subprocess
import sys
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from scripts.login_check import (
    DEFAULT_FRONTEND_URL,
    STATE_COOKIE,
    AllowedRow,
    BrowserState,
    CheckSettings,
    CookieState,
    DbState,
    FetchResult,
    PrecheckProblem,
    SessionRow,
    Snapshot,
    UserRow,
    frontend_port_problems,
    health_problems,
    judge_allowed_after_login,
    judge_allowed_after_logout,
    judge_allowed_before_login,
    judge_allowed_before_logout,
    judge_denied_after_attempt,
    judge_denied_before_login,
    login_redirect_problems,
    parse_args,
    parse_dotenv,
    port_in_use,
    precheck_problems,
    render_preflight,
    render_report,
    render_snapshot,
    resolve_settings,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "login_check.py"

FRONTEND = "http://localhost:5173"
A = "reader-a@example.com"
B = "outsider-b@example.com"
COOKIE_VALUE = "cookie-secret-marker"
COOKIE_SHA256 = hashlib.sha256(COOKIE_VALUE.encode()).hexdigest()
OTHER_SHA256 = hashlib.sha256(b"some-other-cookie").hexdigest()

LOGIN_AT = datetime(2026, 11, 25, 7, 0, 0, tzinfo=UTC)
# 서버가 결과 처리에서 행을 만든 시각. 브라우저가 돌아오기 조금 전이다.
CREATED_AT = LOGIN_AT - timedelta(seconds=2)
ALLOWED_AT = LOGIN_AT - timedelta(days=1)
USER_ID = uuid.UUID("0b9f6c1e-2c8a-4f5e-9a51-3d0c7b1e2f44")
TTL = timedelta(hours=336)

ME_401 = FetchResult(401, {"code": "NOT_AUTHENTICATED", "message": "로그인이 필요합니다."})
ME_200 = FetchResult(
    200, {"id": str(USER_ID), "email": A, "display_name": "독자 A", "role": "user"}
)


def session_cookie(**changes: object) -> CookieState:
    cookie = CookieState(
        name="diegesis_session",
        path="/",
        http_only=True,
        secure=False,
        same_site="Lax",
        value_sha256=COOKIE_SHA256,
    )
    return replace(cookie, **changes)


ALLOWED_A = AllowedRow(email=A, role="user", created_at=ALLOWED_AT)
USER_A = UserRow(
    id=USER_ID, email=A, google_sub="109876543210", display_name="독자 A", created_at=CREATED_AT
)
SESSION_A = SessionRow(
    token_hash=COOKIE_SHA256,
    user_id=USER_ID,
    user_email=A,
    expires_at=CREATED_AT + TTL,
    created_at=CREATED_AT,
)

# 점검 1: 허용된 계정 A의 로그인과 로그아웃 (표 그대로)
BEFORE_LOGIN = Snapshot(
    db=DbState(allowed=(ALLOWED_A,), users=(), sessions=(), session_total=0),
    browser=BrowserState(url=f"{FRONTEND}/", cookies=(), me=ME_401),
)
AFTER_LOGIN = Snapshot(
    db=DbState(allowed=(ALLOWED_A,), users=(USER_A,), sessions=(SESSION_A,), session_total=1),
    browser=BrowserState(url=f"{FRONTEND}/", cookies=(session_cookie(),)),
)
BEFORE_LOGOUT = Snapshot(
    db=AFTER_LOGIN.db,
    browser=BrowserState(url=f"{FRONTEND}/", cookies=(session_cookie(),), me=ME_200),
)
AFTER_LOGOUT = Snapshot(
    db=DbState(allowed=(ALLOWED_A,), users=(USER_A,), sessions=(), session_total=0),
    browser=BrowserState(url=f"{FRONTEND}/", cookies=(), me=ME_401, logout_status=204),
)

# 점검 2: 허용 목록 밖 계정 B의 로그인 시도 (표 그대로). 다른 사람의 로그인 상태가 3개 있다.
DENIED_BEFORE = Snapshot(
    db=DbState(allowed=(ALLOWED_A,), users=(USER_A,), sessions=(), session_total=3),
    browser=BrowserState(url=f"{FRONTEND}/", cookies=()),
)
DENIED_AFTER = Snapshot(
    db=DENIED_BEFORE.db,
    browser=BrowserState(url=f"{FRONTEND}/login?error=NOT_ALLOWED", cookies=(), me=ME_401),
)


def with_db(snapshot: Snapshot, **changes: object) -> Snapshot:
    return replace(snapshot, db=replace(snapshot.db, **changes))


def with_browser(snapshot: Snapshot, **changes: object) -> Snapshot:
    return replace(snapshot, browser=replace(snapshot.browser, **changes))


def after_login(now: Snapshot) -> list[str]:
    return judge_allowed_after_login(
        now, before=BEFORE_LOGIN, email=A, login_at=LOGIN_AT, frontend_url=FRONTEND
    )


def before_logout(now: Snapshot) -> list[str]:
    return judge_allowed_before_logout(now, after_login=AFTER_LOGIN, email=A)


def after_logout(now: Snapshot) -> list[str]:
    return judge_allowed_after_logout(now, before_logout=BEFORE_LOGOUT, email=A)


def denied_after(now: Snapshot) -> list[str]:
    return judge_denied_after_attempt(now, before=DENIED_BEFORE, email=B, frontend_url=FRONTEND)


def assert_one(mismatches: list[str], column: str, *words: str) -> None:
    """정확히 한 칸만 보고됐고, 그 칸이 column이며 그 문장에 words가 모두 들어 있다."""
    assert len(mismatches) == 1, mismatches
    assert mismatches[0].startswith(column), mismatches
    for word in words:
        assert word in mismatches[0], mismatches


class TestTableAsWritten:
    """표와 같은 상태는 다른 칸이 없다."""

    def test_allowed_before_login(self) -> None:
        assert judge_allowed_before_login(BEFORE_LOGIN, email=A) == []

    def test_allowed_after_login(self) -> None:
        assert after_login(AFTER_LOGIN) == []

    def test_allowed_before_logout(self) -> None:
        assert before_logout(BEFORE_LOGOUT) == []

    def test_allowed_after_logout(self) -> None:
        assert after_logout(AFTER_LOGOUT) == []

    def test_denied_before_login(self) -> None:
        assert judge_denied_before_login(DENIED_BEFORE, email=B) == []

    def test_denied_after_attempt(self) -> None:
        assert denied_after(DENIED_AFTER) == []

    def test_time_tolerance_is_inclusive_one_minute(self) -> None:
        # "1분 안에서 같다": 정확히 1분 다른 것은 같다고 본다.
        session = replace(SESSION_A, expires_at=LOGIN_AT + TTL + timedelta(minutes=1))
        user = replace(USER_A, created_at=LOGIN_AT - timedelta(minutes=1))
        assert after_login(with_db(AFTER_LOGIN, sessions=(session,), users=(user,))) == []


class TestAllowedBeforeLogin:
    def test_a_not_in_allowlist(self) -> None:
        assert_one(
            judge_allowed_before_login(with_db(BEFORE_LOGIN, allowed=()), email=A),
            "allowed_emails",
        )

    def test_a_is_admin(self) -> None:
        now = with_db(BEFORE_LOGIN, allowed=(replace(ALLOWED_A, role="admin"),))
        assert_one(judge_allowed_before_login(now, email=A), "allowed_emails", "admin")

    def test_a_has_user_row(self) -> None:
        now = with_db(BEFORE_LOGIN, users=(USER_A,))
        assert_one(judge_allowed_before_login(now, email=A), "users")

    def test_a_has_session_row(self) -> None:
        now = with_db(BEFORE_LOGIN, sessions=(SESSION_A,))
        assert_one(judge_allowed_before_login(now, email=A), "login_sessions")

    def test_cookie_present(self) -> None:
        now = with_browser(BEFORE_LOGIN, cookies=(session_cookie(),))
        assert_one(judge_allowed_before_login(now, email=A), "브라우저", "diegesis_session")

    def test_me_not_401(self) -> None:
        now = with_browser(BEFORE_LOGIN, me=ME_200)
        assert_one(judge_allowed_before_login(now, email=A), "브라우저", "/api/me", "200")


class TestAllowedAfterLogin:
    def test_token_hash_is_not_cookie_sha256(self) -> None:
        # 쿠키 값을 그대로 저장한 서버.
        now = with_db(AFTER_LOGIN, sessions=(replace(SESSION_A, token_hash=COOKIE_VALUE),))
        assert_one(after_login(now), "login_sessions", "token_hash")

    def test_token_hash_of_another_cookie(self) -> None:
        now = with_db(AFTER_LOGIN, sessions=(replace(SESSION_A, token_hash=OTHER_SHA256),))
        assert_one(after_login(now), "login_sessions", "token_hash")

    @pytest.mark.parametrize("offset", [timedelta(minutes=2), -timedelta(minutes=2)])
    def test_expires_at_two_minutes_off(self, offset: timedelta) -> None:
        session = replace(SESSION_A, expires_at=LOGIN_AT + TTL + offset)
        assert_one(after_login(with_db(AFTER_LOGIN, sessions=(session,))), "login_sessions")

    def test_no_session_row(self) -> None:
        now = with_db(AFTER_LOGIN, sessions=())
        assert_one(after_login(now), "login_sessions")

    def test_two_session_rows(self) -> None:
        extra = replace(SESSION_A, token_hash=OTHER_SHA256)
        assert_one(after_login(with_db(AFTER_LOGIN, sessions=(SESSION_A, extra))), "login_sessions")

    def test_no_user_row(self) -> None:
        assert_one(after_login(with_db(AFTER_LOGIN, users=())), "users")

    def test_user_email_not_lowercase(self) -> None:
        user = replace(USER_A, email=A.upper())
        assert_one(after_login(with_db(AFTER_LOGIN, users=(user,))), "users", "email")

    def test_google_sub_empty(self) -> None:
        user = replace(USER_A, google_sub="")
        assert_one(after_login(with_db(AFTER_LOGIN, users=(user,))), "users", "google_sub")

    @pytest.mark.parametrize("name", [None, ""])
    def test_display_name_empty(self, name: str | None) -> None:
        user = replace(USER_A, display_name=name)
        assert_one(after_login(with_db(AFTER_LOGIN, users=(user,))), "users", "display_name")

    def test_user_created_long_ago(self) -> None:
        user = replace(USER_A, created_at=LOGIN_AT - timedelta(minutes=2))
        assert_one(after_login(with_db(AFTER_LOGIN, users=(user,))), "users", "created_at")

    def test_allowed_row_changed(self) -> None:
        now = with_db(AFTER_LOGIN, allowed=(replace(ALLOWED_A, created_at=LOGIN_AT),))
        assert_one(after_login(now), "allowed_emails")

    def test_cookie_secure(self) -> None:
        now = with_browser(AFTER_LOGIN, cookies=(session_cookie(secure=True),))
        assert_one(after_login(now), "브라우저", "Secure")

    def test_cookie_not_http_only(self) -> None:
        now = with_browser(AFTER_LOGIN, cookies=(session_cookie(http_only=False),))
        assert_one(after_login(now), "브라우저", "HttpOnly")

    @pytest.mark.parametrize("same_site", ["Strict", "None", ""])
    def test_cookie_same_site_not_lax(self, same_site: str) -> None:
        now = with_browser(AFTER_LOGIN, cookies=(session_cookie(same_site=same_site),))
        assert_one(after_login(now), "브라우저", "SameSite")

    def test_cookie_path_not_root(self) -> None:
        now = with_browser(AFTER_LOGIN, cookies=(session_cookie(path="/api"),))
        assert_one(after_login(now), "브라우저", "Path")

    def test_oauth_state_cookie_remains(self) -> None:
        state = session_cookie(
            name=STATE_COOKIE, path="/api/auth/google", value_sha256=OTHER_SHA256
        )
        now = with_browser(AFTER_LOGIN, cookies=(session_cookie(), state))
        assert_one(after_login(now), "브라우저", STATE_COOKIE)

    def test_url_not_frontend_root(self) -> None:
        now = with_browser(AFTER_LOGIN, url=f"{FRONTEND}/login?error=NOT_ALLOWED")
        assert_one(after_login(now), "브라우저", "주소")

    def test_no_session_cookie(self) -> None:
        # 쿠키가 없으면 브라우저 칸과 함께, token_hash를 대조할 수 없다는 것도 보고된다.
        mismatches = after_login(with_browser(AFTER_LOGIN, cookies=()))
        assert any(m.startswith("브라우저") and "diegesis_session" in m for m in mismatches)
        assert any(m.startswith("login_sessions") and "token_hash" in m for m in mismatches)


class TestAllowedBeforeLogout:
    def test_expires_at_extended_by_me(self) -> None:
        # GET /api/me가 행을 고친 서버.
        session = replace(SESSION_A, expires_at=SESSION_A.expires_at + timedelta(minutes=5))
        assert_one(
            before_logout(with_db(BEFORE_LOGOUT, sessions=(session,))),
            "login_sessions",
            "expires_at",
        )

    def test_session_row_added(self) -> None:
        extra = replace(SESSION_A, token_hash=OTHER_SHA256)
        now = with_db(BEFORE_LOGOUT, sessions=(SESSION_A, extra), session_total=2)
        assert_one(before_logout(now), "login_sessions")

    def test_token_hash_changed(self) -> None:
        now = with_db(BEFORE_LOGOUT, sessions=(replace(SESSION_A, token_hash=OTHER_SHA256),))
        assert_one(before_logout(now), "login_sessions", "token_hash")

    def test_user_row_changed(self) -> None:
        now = with_db(BEFORE_LOGOUT, users=(replace(USER_A, display_name="바뀐 이름"),))
        # users가 바뀌면 /api/me의 display_name과도 어긋나므로, users 칸이 반드시 보고된다.
        mismatches = before_logout(now)
        assert any(m.startswith("users") for m in mismatches), mismatches

    def test_allowed_row_changed(self) -> None:
        now = with_db(BEFORE_LOGOUT, allowed=(replace(ALLOWED_A, created_at=LOGIN_AT),))
        assert_one(before_logout(now), "allowed_emails")

    def test_me_not_200(self) -> None:
        assert_one(before_logout(with_browser(BEFORE_LOGOUT, me=ME_401)), "브라우저", "401")

    def test_me_email_differs(self) -> None:
        me = FetchResult(200, {**(ME_200.body or {}), "email": B})
        assert_one(before_logout(with_browser(BEFORE_LOGOUT, me=me)), "브라우저", "email")

    def test_me_role_admin(self) -> None:
        me = FetchResult(200, {**(ME_200.body or {}), "role": "admin"})
        assert_one(before_logout(with_browser(BEFORE_LOGOUT, me=me)), "브라우저", "role")

    def test_me_display_name_differs_from_users(self) -> None:
        me = FetchResult(200, {**(ME_200.body or {}), "display_name": "다른 이름"})
        assert_one(before_logout(with_browser(BEFORE_LOGOUT, me=me)), "브라우저", "display_name")

    def test_me_not_called(self) -> None:
        assert_one(before_logout(with_browser(BEFORE_LOGOUT, me=None)), "브라우저", "/api/me")


class TestAllowedAfterLogout:
    def test_session_row_remains(self) -> None:
        now = with_db(AFTER_LOGOUT, sessions=(SESSION_A,), session_total=1)
        assert_one(after_logout(now), "login_sessions")

    def test_user_row_deleted(self) -> None:
        assert_one(after_logout(with_db(AFTER_LOGOUT, users=())), "users")

    def test_allowed_row_deleted(self) -> None:
        assert_one(after_logout(with_db(AFTER_LOGOUT, allowed=())), "allowed_emails")

    @pytest.mark.parametrize("status", [403, 200, None])
    def test_logout_not_204(self, status: int | None) -> None:
        now = with_browser(AFTER_LOGOUT, logout_status=status)
        assert_one(after_logout(now), "브라우저", "로그아웃")

    def test_session_cookie_remains(self) -> None:
        now = with_browser(AFTER_LOGOUT, cookies=(session_cookie(),))
        assert_one(after_logout(now), "브라우저", "diegesis_session")

    def test_me_still_200(self) -> None:
        assert_one(after_logout(with_browser(AFTER_LOGOUT, me=ME_200)), "브라우저", "/api/me")


class TestDeniedBeforeLogin:
    def test_b_in_allowlist(self) -> None:
        now = with_db(DENIED_BEFORE, allowed=(ALLOWED_A, replace(ALLOWED_A, email=B)))
        assert_one(judge_denied_before_login(now, email=B), "allowed_emails")

    def test_b_has_user_row(self) -> None:
        user_b = replace(USER_A, id=uuid.uuid4(), email=B, google_sub="222")
        now = with_db(DENIED_BEFORE, users=(USER_A, user_b))
        assert_one(judge_denied_before_login(now, email=B), "users")

    def test_cookie_present(self) -> None:
        now = with_browser(DENIED_BEFORE, cookies=(session_cookie(),))
        assert_one(judge_denied_before_login(now, email=B), "브라우저")


class TestDeniedAfterAttempt:
    def test_b_user_row_created(self) -> None:
        user_b = replace(USER_A, id=uuid.uuid4(), email=B, google_sub="222")
        now = with_db(DENIED_AFTER, users=(USER_A, user_b))
        assert_one(denied_after(now), "users")

    def test_b_added_to_allowlist(self) -> None:
        now = with_db(DENIED_AFTER, allowed=(ALLOWED_A, replace(ALLOWED_A, email=B)))
        assert_one(denied_after(now), "allowed_emails")

    def test_session_total_increased(self) -> None:
        now = with_db(DENIED_AFTER, session_total=DENIED_BEFORE.db.session_total + 1)
        assert_one(denied_after(now), "login_sessions", "전체")

    def test_url_login_failed(self) -> None:
        now = with_browser(DENIED_AFTER, url=f"{FRONTEND}/login?error=LOGIN_FAILED")
        assert_one(denied_after(now), "브라우저", "주소", "NOT_ALLOWED")

    @pytest.mark.parametrize("name", ["diegesis_session", STATE_COOKIE])
    def test_cookie_present(self, name: str) -> None:
        now = with_browser(DENIED_AFTER, cookies=(session_cookie(name=name),))
        assert_one(denied_after(now), "브라우저", name)

    def test_me_not_401(self) -> None:
        assert_one(denied_after(with_browser(DENIED_AFTER, me=ME_200)), "브라우저", "/api/me")


# --- 출력에 쿠키의 값과 token_hash의 값이 없다 ------------------------------------------------

TOKEN_MISMATCH = with_db(
    AFTER_LOGIN, sessions=(replace(SESSION_A, token_hash=OTHER_SHA256),)
)  # 쿠키 해시와 다른 token_hash. 둘 다 출력에 없어야 한다.

ALL_SNAPSHOTS = {
    "before_login": BEFORE_LOGIN,
    "after_login": AFTER_LOGIN,
    "before_logout": BEFORE_LOGOUT,
    "after_logout": AFTER_LOGOUT,
    "denied_before": DENIED_BEFORE,
    "denied_after": DENIED_AFTER,
    "token_mismatch": TOKEN_MISMATCH,
}
SECRETS = (COOKIE_VALUE, COOKIE_SHA256, OTHER_SHA256)


class TestNoSecretsInOutput:
    @pytest.mark.parametrize("name", list(ALL_SNAPSHOTS))
    def test_render_snapshot_has_no_cookie_value_or_hash(self, name: str) -> None:
        output = render_snapshot(name, ALL_SNAPSHOTS[name], allowed_email=A, denied_email=B)
        for secret in SECRETS:
            assert secret not in output

    def test_render_snapshot_shows_tables_and_browser(self) -> None:
        output = render_snapshot("로그인 후", AFTER_LOGIN, allowed_email=A, denied_email=B)
        for expected in ("allowed_emails", "users", "login_sessions", A, B, "109876543210"):
            assert expected in output
        # token_hash는 쿠키 값의 SHA-256과 같은지만 보여 준다.
        assert "SHA-256과 같다" in output

    def test_render_snapshot_says_when_token_hash_differs(self) -> None:
        output = render_snapshot("로그인 후", TOKEN_MISMATCH, allowed_email=A, denied_email=B)
        assert "SHA-256과 다르다" in output

    def test_judge_messages_have_no_cookie_value_or_hash(self) -> None:
        mismatches = [
            *after_login(TOKEN_MISMATCH),
            *after_login(
                with_db(AFTER_LOGIN, sessions=(replace(SESSION_A, token_hash=COOKIE_VALUE),))
            ),
            *before_logout(
                with_db(BEFORE_LOGOUT, sessions=(replace(SESSION_A, token_hash=OTHER_SHA256),))
            ),
            *after_logout(with_db(AFTER_LOGOUT, sessions=(SESSION_A,))),
        ]
        assert mismatches
        report = render_report(mismatches)
        for secret in SECRETS:
            assert secret not in report

    def test_dataclass_reprs_hide_hashes(self) -> None:
        for value in (SESSION_A, session_cookie(), AFTER_LOGIN):
            text = repr(value)
            assert COOKIE_SHA256 not in text

    def test_render_report(self) -> None:
        assert "같다" in render_report([])
        report = render_report(
            ["[점검 1 · 로그인 후] 브라우저: 하나", "[점검 2 · 로그인 시도 후] users: 둘"]
        )
        assert "하나" in report and "둘" in report


# --- 점검을 시작하기 전의 확인 ---------------------------------------------------------------


def location(**params: str) -> str:
    query = {
        "client_id": "test-client.apps.googleusercontent.com",
        "redirect_uri": f"{FRONTEND}/api/auth/google/callback",
        "response_type": "code",
        "scope": "openid email profile",
        "state": "s",
        "nonce": "n",
        "code_challenge": "c",
        "code_challenge_method": "S256",
        **params,
    }
    from urllib.parse import urlencode

    return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(query)


class TestPreflight:
    def test_login_redirect_matches(self) -> None:
        assert login_redirect_problems(302, location(), frontend_url=FRONTEND) == []

    def test_redirect_uri_is_backend(self) -> None:
        problems = login_redirect_problems(
            302,
            location(redirect_uri="http://localhost:8080/api/auth/google/callback"),
            frontend_url=FRONTEND,
        )
        assert len(problems) == 1
        assert "redirect_uri" in problems[0].problem
        assert "FRONTEND_URL" in problems[0].fix

    def test_client_id_empty(self) -> None:
        problems = login_redirect_problems(302, location(client_id=""), frontend_url=FRONTEND)
        assert len(problems) == 1
        assert "client_id" in problems[0].problem
        assert "GOOGLE_CLIENT_ID" in problems[0].fix

    def test_client_id_missing(self) -> None:
        url = location().replace("client_id=test-client.apps.googleusercontent.com&", "")
        problems = login_redirect_problems(302, url, frontend_url=FRONTEND)
        assert len(problems) == 1
        assert "client_id" in problems[0].problem

    @pytest.mark.parametrize(("status", "loc"), [(None, None), (500, None), (200, None)])
    def test_login_not_redirecting(self, status: int | None, loc: str | None) -> None:
        assert len(login_redirect_problems(status, loc, frontend_url=FRONTEND)) == 1

    def test_health(self) -> None:
        assert health_problems(200, backend_url="http://localhost:8080") == []
        for status in (None, 500):
            problems = health_problems(status, backend_url="http://localhost:8080")
            assert len(problems) == 1
            assert "compose" in problems[0].fix

    def test_frontend_port(self) -> None:
        assert frontend_port_problems(FRONTEND, in_use=False) == []
        problems = frontend_port_problems(FRONTEND, in_use=True)
        assert len(problems) == 1
        assert "개발 서버" in problems[0].fix

    def test_port_in_use(self) -> None:
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            port = listener.getsockname()[1]
            assert port_in_use("127.0.0.1", port)
        assert not port_in_use("127.0.0.1", port)

    def test_render_preflight_shows_problem_and_fix(self) -> None:
        from scripts.login_check import PreflightProblem

        output = render_preflight([PreflightProblem("문제 하나", "SELECT 1;")])
        assert "문제 하나" in output and "SELECT 1;" in output


class TestPrecheckProblems:
    """점검 전 상태의 판정. 데이터베이스와 함께 도는 확인은 test_login_check_precheck.py에 있다."""

    def test_all_good(self) -> None:
        assert precheck_problems(BEFORE_LOGIN.db, allowed_email=A, denied_email=B) == []

    def test_fix_sql_escapes_quote(self) -> None:
        email = "o'neil@example.com"
        problems = precheck_problems(
            DbState(allowed=(), users=(), sessions=(), session_total=0),
            allowed_email=email,
            denied_email=B,
        )
        assert problems == [problems[0]]
        assert isinstance(problems[0], PrecheckProblem)
        assert "lower('o''neil@example.com')" in problems[0].fix_sql


# --- 설정과 인자 -----------------------------------------------------------------------------


class TestSettings:
    def test_parse_dotenv(self) -> None:
        text = (
            "# 주석\n"
            "\n"
            "FRONTEND_URL=http://localhost:3000\n"
            "API_PORT = 8081\n"
            'export DB_PORT="5433"\n'
            "GOOGLE_CLIENT_ID=abc # 줄 끝 주석\n"
            "EMPTY=\n"
            "NOT_A_PAIR\n"
        )
        assert parse_dotenv(text) == {
            "FRONTEND_URL": "http://localhost:3000",
            "API_PORT": "8081",
            "DB_PORT": "5433",
            "GOOGLE_CLIENT_ID": "abc",
            "EMPTY": "",
        }

    def test_defaults_are_compose_defaults(self) -> None:
        settings = resolve_settings({}, {})
        assert settings == CheckSettings(
            frontend_url=DEFAULT_FRONTEND_URL, api_port=8080, db_port=5432
        )
        assert settings.backend_url == "http://localhost:8080"
        assert settings.database_url == "postgresql://diegesis:diegesis@localhost:5432/diegesis"
        assert (settings.frontend_host, settings.frontend_port) == ("localhost", 5173)

    def test_dotenv_when_no_environment(self) -> None:
        dotenv = {"FRONTEND_URL": "http://127.0.0.1:3000", "API_PORT": "8081", "DB_PORT": "5433"}
        assert resolve_settings({}, dotenv) == CheckSettings("http://127.0.0.1:3000", 8081, 5433)

    def test_environment_wins_over_dotenv(self) -> None:
        environ = {"API_PORT": "9000"}
        dotenv = {"API_PORT": "8081", "DB_PORT": "5433"}
        settings = resolve_settings(environ, dotenv)
        assert (settings.api_port, settings.db_port) == (9000, 5433)

    def test_empty_value_falls_back_to_default(self) -> None:
        # compose의 `${이름:-기본값}`은 비어 있는 값도 기본값으로 바꾼다.
        settings = resolve_settings({"API_PORT": ""}, {"API_PORT": "8081", "FRONTEND_URL": ""})
        assert (settings.api_port, settings.frontend_url) == (8080, DEFAULT_FRONTEND_URL)

    @pytest.mark.parametrize(
        "environ",
        [
            {"API_PORT": "eighty"},
            {"DB_PORT": "0"},
            {"FRONTEND_URL": "https://diegesis.example"},
            {"FRONTEND_URL": "http://192.168.0.10:5173"},
            {"FRONTEND_URL": "http://localhost:5173/app"},
        ],
    )
    def test_invalid_values(self, environ: dict[str, str]) -> None:
        with pytest.raises(ValueError):
            resolve_settings(environ, {})

    def test_parse_args_lowercases_emails(self) -> None:
        args = parse_args(["--allowed-email", "Reader-A@Example.com", "--denied-email", B.upper()])
        assert (args.allowed_email, args.denied_email) == (A, B)

    @pytest.mark.parametrize(
        "argv",
        [
            ["--allowed-email", A],
            ["--denied-email", B],
            ["--allowed-email", A, "--denied-email", A.upper()],
        ],
    )
    def test_parse_args_rejects(self, argv: list[str]) -> None:
        with pytest.raises(SystemExit) as exc:
            parse_args(argv)
        assert exc.value.code == 2

    def test_help_exits_zero_without_browser(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert "--allowed-email" in result.stdout
        assert "--denied-email" in result.stdout


# --- 스크립트가 쓰지 않는 것 -----------------------------------------------------------------

# 스크립트는 브라우저를 열거나 조종하지 않는다(ADR-031). 사람이 연 브라우저에 연결하지도 않고,
# 자동화 탐지를 피하는 옵션도 쓰지 않는다. Google 계정의 비밀번호는 사람만 다룬다(E1 S1.7의
# "못 박을 것").
BROWSER_MODULES = ("playwright", "selenium", "pyppeteer", "undetected_chromedriver", "webbrowser")
FORBIDDEN = ("AutomationControlled", "stealth", "remote-debugging", "connect_over_cdp")


def imported_modules(source: str) -> set[str]:
    """소스가 import하는 모듈의 전체 이름. `from a.b import c`는 `a.b`로 센다."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


def forbidden_in(source: str) -> list[str]:
    modules = imported_modules(source)
    found = [
        module
        for module in BROWSER_MODULES
        if any(name == module or name.startswith(module + ".") for name in modules)
    ]
    found += [token for token in FORBIDDEN if token in source]
    if "password" in source.lower():
        found.append("password")
    return found


class TestScriptSource:
    @pytest.mark.parametrize(
        ("source", "expected"),
        [
            ("from playwright.async_api import async_playwright", ["playwright"]),
            ("def f():\n    import selenium.webdriver\n", ["selenium"]),
            ("import webbrowser\nwebbrowser.open('http://localhost:5173/')", ["webbrowser"]),
            ("args=['--disable-blink-features=AutomationControlled']", ["AutomationControlled"]),
            ("browser = await chromium.connect_over_cdp(url)", ["connect_over_cdp"]),
            ("parser.add_argument('--password')", ["password"]),
            ("import playwrightish", []),
            ("from scripts import login_check", []),
        ],
    )
    def test_detector(self, source: str, expected: list[str]) -> None:
        assert forbidden_in(source) == expected

    def test_script_does_not_drive_a_browser(self) -> None:
        assert forbidden_in(SCRIPT.read_text(encoding="utf-8")) == []

    def test_script_has_main(self) -> None:
        tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
        names = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
        assert "main" in names
