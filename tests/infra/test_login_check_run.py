"""`scripts/login_check.py`의 점검을 진행하는 층(`run_checks`)의 테스트 (ADR-031).

판정 함수는 test_login_check_judge.py가, 대역 서버를 지난 것으로 브라우저를 따라가는 부분은
test_login_check_observe.py가, `main`이 종료 코드를 고르는 것은 test_login_check_main.py가 확인한다.
이 파일은 그 사이의 이음새(`run_checks`, `_check_allowed`, `_check_denied`)를 확인한다.

- 사람에게 다음에 할 일을 안내하고, 그 일이 만든 요청이 대역 서버를 지나간 뒤에 데이터베이스를
  읽어 시점의 스냅숏을 찍는다. 너무 일찍 읽으면 그 시점의 변화가 보이지 않고, 너무 늦게 읽으면
  다음 시점의 변화가 섞인다.
- 시점마다 표가 기준으로 삼는 바로 앞 시점의 스냅숏과 함께 그 시점의 판정에 넘긴다.
- 판정이 돌려준 어긋난 것과 쿠키의 대조에서 나온 어긋난 것에 시점의 제목을 붙여, 두 점검에 걸쳐
  빠짐없이 모은다.
- 점검을 끝내지 못하면(데이터베이스, 기다리는 시간, 대역 서버) CheckAbortedError로 바꾸고,
  `main`은 4로 끝난다. 대역 서버는 어떻게 끝나든 닫는다.

대역 서버, 데이터베이스 읽기(`read_state`), 사람에게 하는 안내(`_ask`)는 가짜(FakeWorld)로 바꾼다.
가짜는 안내를 받은 사람이 게스트 창에서 그대로 따라 하고, 브라우저와 서버가 testcase.md의 "로컬
로그인 점검의 테이블 상태"대로 움직이는 것을 흉내 낸다. 그래서 고장을 넣지 않으면 어긋난 것이 하나도
없고, 고장을 하나 넣으면 그 고장이 드러나는 시점의 칸 하나만 보고되어야 한다. 데이터베이스에
연결하는 가장 아래의 함수(`connect_read_only`)는 불리면 테스트가 실패하게 바꾼다.
"""

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

import asyncpg
import pytest

from scripts import login_check
from scripts.login_check import (
    CALLBACK_PATH,
    LOGIN_PATH,
    LOGIN_SESSION_TTL,
    LOGOUT_PATH,
    ME_PATH,
    NOT_ALLOWED_PATH,
    SESSION_COOKIE,
    STATE_COOKIE,
    STEP_LOG_IN,
    STEP_LOG_OUT,
    STEP_ME,
    STEP_OPEN,
    STEP_REOPEN,
    AllowedRow,
    Args,
    CheckAbortedError,
    CheckSettings,
    CookieMismatch,
    DbState,
    Exchange,
    SentCookie,
    SessionRow,
    UserRow,
    cookie_path_matches,
    main,
    parse_set_cookie,
    request_target,
    run_checks,
    sha256_hex,
)

A = "reader-a@example.com"
B = "outsider-b@example.com"
ARGS = Args(allowed_email=A, denied_email=B)
ARGV = ["--allowed-email", A, "--denied-email", B]

# compose의 기본값과 다른 값을 써서, 설정의 값이 대역 서버와 데이터베이스 읽기에 그대로 쓰이는지
# 본다.
FRONTEND = "http://localhost:5199"
API_PORT = 18080
DB_PORT = 15432
SETTINGS = CheckSettings(frontend_url=FRONTEND, api_port=API_PORT, db_port=DB_PORT)

# 대역 서버가 요청을 기록한 시각. 지금과 멀리 떨어진 고정된 시각이다. 층이 로그인 결과 처리를 기록한
# 시각이 아닌 다른 시각을 판정에 넘기면 created_at과 expires_at의 칸이 어긋난다.
LOGIN_AT = datetime(2026, 1, 5, 9, 30, tzinfo=UTC)
ALLOWED_AT = datetime(2026, 1, 1, tzinfo=UTC)
# 두 계정 말고 다른 사람의 로그인 상태의 수. 점검 2는 login_sessions의 전체 행의 수만 본다.
OTHER_SESSIONS = 3
SESSION_TOKEN = "sessionTokenOfReaderA7c2e"
STATE_VALUE = "stateCookieOfThisLogin.n.v"
LEFTOVER_TOKEN = "leftoverTokenFromAnotherWindow"

STATE_SET = (
    f"{STATE_COOKIE}={STATE_VALUE}; HttpOnly; SameSite=Lax; Path=/api/auth/google; Max-Age=600"
)
STATE_DELETE = f"{STATE_COOKIE}=; Max-Age=0; Path=/api/auth/google"
SESSION_DELETE = f"{SESSION_COOKIE}=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0"


def session_set(*, secure: bool) -> str:
    max_age = int(LOGIN_SESSION_TTL.total_seconds())
    header = f"{SESSION_COOKIE}={SESSION_TOKEN}; HttpOnly; SameSite=Lax; Path=/; Max-Age={max_age}"
    return header + ("; Secure" if secure else "")


TITLES = [
    "점검 1 · 로그인 전",
    "점검 1 · 로그인 후",
    "점검 1 · 로그아웃 전",
    "점검 1 · 로그아웃 후",
    "점검 2 · 로그인 전",
    "점검 2 · 로그인 시도 후",
]

# 사람에게 한 안내와 데이터베이스 읽기의 순서. 점검 2의 로그인 시도 뒤에는 GET /api/me의 401을
# 보려고 내 정보 확인을 한 번 더 안내한 다음에 읽는다.
EXPECTED_LOG = [
    f"ask:{STEP_OPEN}",
    "read",  # 점검 1 · 로그인 전
    f"ask:{STEP_LOG_IN}",
    "read",  # 점검 1 · 로그인 후
    f"ask:{STEP_ME}",
    "read",  # 점검 1 · 로그아웃 전
    f"ask:{STEP_LOG_OUT}",
    "read",  # 점검 1 · 로그아웃 후
    f"ask:{STEP_REOPEN}",
    "read",  # 점검 2 · 로그인 전
    f"ask:{STEP_LOG_IN}",
    f"ask:{STEP_ME}",
    "read",  # 점검 2 · 로그인 시도 후
]

# 가짜 서버에 넣을 수 있는 고장과, 그 고장이 있을 때 보고되어야 하는 어긋난 것 하나(의 앞부분).
# 각 고장은 한 시점에서만 표와 달라지게 만든다. 판정에 넘기는 기준 스냅숏이 바뀌면 보고되지 않는다.
FAULTS = {
    # A가 로그인하면 A의 allowed_emails 행이 다시 들어간다(created_at이 바뀐다). 기준: 로그인 전.
    "login_reinserts_allowed_row": (
        "[점검 1 · 로그인 후] allowed_emails: 로그인 전 시점과 같아야 하는데 다르다."
    ),
    # 로그인 결과 처리가 http의 FRONTEND_URL에서도 Secure를 붙인다.
    "session_cookie_secure": (
        "[점검 1 · 로그인 후] 브라우저: diegesis_session 쿠키에 Secure가 붙었다."
    ),
    # GET /api/me가 로그인 상태의 만료 시각을 늘린다. 기준: 로그인 후.
    "me_extends_session": (
        "[점검 1 · 로그아웃 전] login_sessions: 로그인 후 시점과 같아야 하는데 다르다."
    ),
    # 로그아웃이 users의 display_name을 바꾼다. 기준: 로그아웃 전.
    "logout_renames_user": "[점검 1 · 로그아웃 후] users: 로그아웃 전 시점과 같아야 하는데 다르다.",
    # 로그아웃이 쿠키만 지우고 login_sessions의 행을 남긴다.
    "logout_keeps_session": (
        "[점검 1 · 로그아웃 후] login_sessions: A의 행이 1개 남아 있다. 없어야 한다."
    ),
    # 로그아웃이 login_sessions의 행만 지우고 쿠키를 지우는 Set-Cookie를 보내지 않는다.
    "logout_keeps_cookie": (
        "[점검 1 · 로그아웃 후] 브라우저: diegesis_session 쿠키가 있다. 없어야 한다."
    ),
    # B의 로그인 시도가 다른 사람의 login_sessions 행을 하나 만든다. 기준: 점검 2의 로그인 전.
    "denied_adds_session": (
        "[점검 2 · 로그인 시도 후] login_sessions: 전체 행의 수가 로그인 전과 다르다"
        f"(로그인 전: {OTHER_SESSIONS}, 지금: {OTHER_SESSIONS + 1})."
    ),
}


def _raw_cookie(header: str) -> tuple[str, str, str, bool]:
    """가짜 브라우저가 Set-Cookie를 읽는다. (이름, 값, 경로, 지우는가)."""
    pair, *attributes = header.split(";")
    name, _, value = pair.partition("=")
    found = {
        key.strip().lower(): val.strip() for key, _, val in (a.partition("=") for a in attributes)
    }
    return name.strip(), value.strip(), found.get("path", "/"), found.get("max-age") == "0"


class FakeGuestWindow:
    """사람이 연 게스트 창. 실제 브라우저처럼 쿠키를 이름과 경로로 쌓고, 경로가 맞는 것을 붙인다."""

    def __init__(self, *, drops_session: bool) -> None:
        self.jar: dict[tuple[str, str], str] = {}
        self.drops_session = drops_session

    def cookies_for(self, path: str) -> dict[str, str]:
        return {
            name: value
            for (name, cookie_path), value in self.jar.items()
            if cookie_path_matches(path, cookie_path)
        }

    def receive(self, headers: list[str]) -> None:
        for header in headers:
            name, value, path, deleting = _raw_cookie(header)
            if deleting:
                self.jar.pop((name, path), None)
            elif not (self.drops_session and name == SESSION_COOKIE):
                self.jar[(name, path)] = value


class FakeStandIn:
    def __init__(self, world: FakeWorld, *, observe: Callable[[Exchange], None], **kwargs: object):
        self.world = world
        world.stand_in_kwargs.append(kwargs)
        world.observe = observe

    def start(self) -> None:
        self.world.stand_in_events.append("start")
        if self.world.stand_in_error is not None:
            raise self.world.stand_in_error

    def stop(self) -> None:
        self.world.stand_in_events.append("stop")


@dataclass(frozen=True)
class Response:
    status: int
    set_cookies: tuple[str, ...] = ()
    body: dict[str, object] | None = None
    location: str | None = None


class FakeWorld:
    """안내대로 따라 하는 사람과, 표대로 움직이는 브라우저, 서버, 데이터베이스.

    faults에 FAULTS의 이름을 넣으면 그 자리에서만 표와 다르게 움직인다. idle_step에 안내의 이름을
    넣으면 사람이 그 안내를 따르지 않는다. *_error에 예외를 넣으면 그 자리에서 낸다.
    """

    def __init__(self) -> None:
        self.faults: set[str] = set()
        self.idle_step: str | None = None
        self.read_error: Exception | None = None
        self.read_error_at = 0  # 몇 번째(0부터) 데이터베이스 읽기에서 read_error를 낼지
        self.stand_in_error: Exception | None = None

        self.allowed: dict[str, AllowedRow] = {A: AllowedRow(A, "user", ALLOWED_AT)}
        self.users: dict[str, UserRow] = {}
        self.sessions: dict[str, SessionRow] = {}
        self.other_sessions = OTHER_SESSIONS

        self.observe: Callable[[Exchange], None] | None = None
        self.window = FakeGuestWindow(drops_session=False)
        self.account = A
        self.log: list[str] = []
        self.messages: list[str] = []
        self.reads: list[tuple[str, tuple[str, ...]]] = []
        self.stand_in_kwargs: list[dict[str, object]] = []
        self.stand_in_events: list[str] = []

    # --- 데이터베이스 -------------------------------------------------------------------------

    async def read_state(self, database_url: str, *, emails: tuple[str, ...]) -> DbState:
        index = len(self.reads)
        self.reads.append((database_url, tuple(emails)))
        self.log.append("read")
        if self.read_error is not None and index == self.read_error_at:
            raise self.read_error
        wanted = {email.lower() for email in emails}
        return DbState(
            allowed=tuple(row for email, row in sorted(self.allowed.items()) if email in wanted),
            users=tuple(row for email, row in sorted(self.users.items()) if email in wanted),
            sessions=tuple(row for row in self.sessions.values() if row.user_email in wanted),
            session_total=len(self.sessions) + self.other_sessions,
        )

    # --- 사람 ---------------------------------------------------------------------------------

    def ask(self, step: str, message: str) -> None:
        self.log.append(f"ask:{step}")
        self.messages.append(message)
        if step == self.idle_step:
            return
        if step in (STEP_OPEN, STEP_REOPEN):
            # 점검 1에서는 계정 A를, 점검 2에서는 계정 B를 고르라는 안내를 받는다.
            self.account = A if step == STEP_OPEN else B
            self.window = FakeGuestWindow(drops_session="browser_drops_session" in self.faults)
            if step == STEP_OPEN and "stale_cookie_in_browser" in self.faults:
                self.window.jar[(SESSION_COOKIE, "/")] = LEFTOVER_TOKEN
            self._navigate("/")
            self._request("GET", ME_PATH, navigation=False)
        elif step == STEP_LOG_IN:
            self._navigate(LOGIN_PATH)
            # 사람이 Google 화면에서 계정을 고르면, Google이 브라우저를 결과 처리로 보낸다.
            self._navigate(f"{CALLBACK_PATH}?code=CODESECRET1&state=STATESECRET2")
        elif step == STEP_ME:
            self._request("GET", ME_PATH, navigation=False)
        elif step == STEP_LOG_OUT:
            self._request("POST", LOGOUT_PATH, navigation=False)
            self._request("GET", ME_PATH, navigation=False)
        else:
            raise AssertionError(f"모르는 안내: {step}")

    # --- 브라우저 -----------------------------------------------------------------------------

    def _navigate(self, target: str) -> None:
        response = self._request("GET", target, navigation=True)
        if response.location is not None and response.location.startswith(FRONTEND + "/"):
            self._navigate(response.location.removeprefix(FRONTEND))

    def _request(self, method: str, target: str, *, navigation: bool) -> Response:
        path = urlsplit(target).path
        cookies = self.window.cookies_for(path)
        response = self._serve(method, path, cookies) if path.startswith("/api/") else Response(200)
        self.window.receive(list(response.set_cookies))
        assert self.observe is not None, "대역 서버가 뜨기 전에 요청했다"
        self.observe(
            Exchange(
                at=LOGIN_AT,
                method=method,
                target=request_target(target),
                navigation=navigation,
                sent=tuple(SentCookie(name, sha256_hex(value)) for name, value in cookies.items()),
                status=response.status,
                set_cookies=tuple(parse_set_cookie(header) for header in response.set_cookies),
                body=response.body,
            )
        )
        return response

    # --- 서버 ---------------------------------------------------------------------------------

    def _serve(self, method: str, path: str, cookies: dict[str, str]) -> Response:
        token = cookies.get(SESSION_COOKIE)
        session = self.sessions.get(sha256_hex(token)) if token is not None else None
        if (method, path) == ("GET", LOGIN_PATH):
            return Response(302, (STATE_SET,), location="https://accounts.google.com/o/oauth2")
        if (method, path) == ("GET", CALLBACK_PATH):
            assert cookies.get(STATE_COOKIE) == STATE_VALUE, "결과 처리가 state 쿠키를 받지 못했다"
            return self._finish_login()
        if (method, path) == ("GET", ME_PATH):
            if session is None:
                return Response(401, body={"code": "NOT_AUTHENTICATED"})
            if "me_extends_session" in self.faults:
                self.sessions[session.token_hash] = replace(
                    session, expires_at=session.expires_at + timedelta(hours=1)
                )
            user = self.users[session.user_email]
            role = self.allowed[user.email].role
            body = {"id": str(user.id), "email": user.email, "display_name": user.display_name}
            return Response(200, body={**body, "role": role})
        if (method, path) == ("POST", LOGOUT_PATH):
            if session is not None and "logout_keeps_session" not in self.faults:
                del self.sessions[session.token_hash]
            if session is not None and "logout_renames_user" in self.faults:
                user = self.users[session.user_email]
                self.users[session.user_email] = replace(user, display_name="바뀐 이름")
            deleting = () if "logout_keeps_cookie" in self.faults else (SESSION_DELETE,)
            return Response(204, deleting)
        raise AssertionError(f"모르는 요청: {method} {path}")

    def _finish_login(self) -> Response:
        email = self.account
        if email not in self.allowed:
            if "denied_adds_session" in self.faults:
                self.other_sessions += 1
            return Response(302, (STATE_DELETE,), location=FRONTEND + NOT_ALLOWED_PATH)
        if "login_reinserts_allowed_row" in self.faults:
            self.allowed[email] = replace(self.allowed[email], created_at=LOGIN_AT)
        user = UserRow(uuid.uuid4(), email, "google-sub-a", "독자 A", LOGIN_AT)
        self.users[email] = user
        token_hash = sha256_hex(SESSION_TOKEN)
        self.sessions[token_hash] = SessionRow(
            token_hash, user.id, email, LOGIN_AT + LOGIN_SESSION_TTL, LOGIN_AT
        )
        secure = "session_cookie_secure" in self.faults
        return Response(302, (session_set(secure=secure), STATE_DELETE), location=FRONTEND + "/")


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> FakeWorld:
    world = FakeWorld()

    async def no_database(database_url: str) -> asyncpg.Connection:
        raise AssertionError(f"가짜를 거치지 않고 데이터베이스({database_url})에 연결하려 했다")

    monkeypatch.setattr(
        login_check, "FrontendStandIn", lambda **kwargs: FakeStandIn(world, **kwargs)
    )
    monkeypatch.setattr(login_check, "read_state", world.read_state)
    monkeypatch.setattr(login_check, "_ask", world.ask)
    monkeypatch.setattr(login_check, "connect_read_only", no_database)
    return world


def headings(output: str) -> list[str]:
    return [line.removeprefix("=== ") for line in output.splitlines() if line.startswith("=== ")]


class TestStepsOfChecks:
    """표대로 움직이면 어긋난 것이 없다. 층은 정해진 순서로 안내하고, 대역 서버를 지난 것을 기다려
    데이터베이스를 읽는다."""

    async def test_all_match_reports_nothing_and_closes_the_stand_in(
        self, world: FakeWorld, capsys: pytest.CaptureFixture[str]
    ) -> None:
        mismatches = await run_checks(SETTINGS, ARGS)

        assert mismatches == []
        # 대역 서버는 FRONTEND_URL의 호스트와 포트에서 받고, 백엔드로 넘긴다.
        assert world.stand_in_kwargs == [
            {
                "listen_host": "localhost",
                "listen_port": 5199,
                "backend_url": f"http://localhost:{API_PORT}",
            }
        ]
        assert world.stand_in_events == ["start", "stop"]
        assert world.log == EXPECTED_LOG
        # 여섯 시점마다 두 계정의 상태를 설정의 데이터베이스에서 한 번씩 읽는다.
        assert world.reads == [(SETTINGS.database_url, (A, B))] * 6
        # 사람이 표와 대조할 수 있게 시점마다 상태를 순서대로 출력한다.
        assert headings(capsys.readouterr().out) == TITLES

    async def test_messages_tell_where_to_go_and_which_account(self, world: FakeWorld) -> None:
        await run_checks(SETTINGS, ARGS)

        steps = [entry.removeprefix("ask:") for entry in world.log if entry.startswith("ask:")]
        by_step = list(zip(steps, world.messages, strict=True))
        open_message = by_step[0][1]
        reopen_message = next(message for step, message in by_step if step == STEP_REOPEN)
        # 점검마다 새 게스트 창에서 FRONTEND_URL을 연다.
        for message in (open_message, reopen_message):
            assert f"{FRONTEND}/" in message
            assert "게스트 창" in message
        log_ins = [message for step, message in by_step if step == STEP_LOG_IN]
        assert A in log_ins[0] and B not in log_ins[0]
        assert B in log_ins[1] and A not in log_ins[1]

    async def test_exchange_that_arrives_after_the_checks_is_ignored(
        self, world: FakeWorld
    ) -> None:
        await run_checks(SETTINGS, ARGS)

        assert world.observe is not None
        # 사람이 점검이 끝난 뒤에 버튼을 눌러도 대역 서버의 스레드에서 예외가 나지 않는다.
        world.observe(Exchange(LOGIN_AT, "GET", ME_PATH, False, (), 401, (), None))


class TestMismatchesOfEachStep:
    """고장 하나는 그 고장이 드러나는 시점의 칸 하나로, 그 시점의 제목을 붙여 보고된다."""

    @pytest.mark.parametrize("fault", list(FAULTS))
    async def test_one_fault_is_reported_once_under_its_step(
        self, world: FakeWorld, fault: str
    ) -> None:
        world.faults = {fault}

        mismatches = await run_checks(SETTINGS, ARGS)

        assert len(mismatches) == 1, mismatches
        assert mismatches[0].startswith(FAULTS[fault]), mismatches[0]

    async def test_faults_in_both_checks_are_all_collected_in_order(self, world: FakeWorld) -> None:
        faults = ["me_extends_session", "logout_renames_user", "denied_adds_session"]
        world.faults = set(faults)

        mismatches = await run_checks(SETTINGS, ARGS)

        assert len(mismatches) == len(faults), mismatches
        for mismatch, fault in zip(mismatches, faults, strict=True):
            assert mismatch.startswith(FAULTS[fault]), mismatch

    async def test_browser_that_did_not_keep_the_session_cookie_is_reported(
        self, world: FakeWorld
    ) -> None:
        # Set-Cookie만 보면 로그인 후가 표와 같다. 브라우저가 다음 요청에 붙인 Cookie로 대조해야
        # 드러난다.
        world.faults = {"browser_drops_session"}

        mismatches = await run_checks(SETTINGS, ARGS)

        expected = CookieMismatch("missing", SESSION_COOKIE, "GET /").text()
        assert f"[점검 1 · 로그인 후] {expected}" in mismatches

    async def test_cookie_left_from_another_window_is_reported_before_login(
        self, world: FakeWorld
    ) -> None:
        world.faults = {"stale_cookie_in_browser"}

        mismatches = await run_checks(SETTINGS, ARGS)

        expected = CookieMismatch("unexpected", SESSION_COOKIE, "GET /").text()
        assert mismatches[0] == f"[점검 1 · 로그인 전] {expected}"
        assert LEFTOVER_TOKEN not in json.dumps(mismatches, ensure_ascii=False)


@dataclass(frozen=True)
class Abort:
    """점검을 끝내지 못하게 하는 데이터베이스의 고장과, 그때 CheckAbortedError가 보여 줄 안내."""

    error: Exception
    message: str


# 세 번째 읽기(점검 1 · 로그아웃 전)에서 실패하게 해서, 점검 도중에도 대역 서버를 닫는지 본다.
ABORTS = {
    "database_refused": Abort(
        ConnectionRefusedError(61, "Connection refused"),
        "점검 중에 개발용 데이터베이스를 읽지 못했다: ConnectionRefusedError",
    ),
    "database_error": Abort(
        asyncpg.exceptions.UndefinedTableError('relation "users" does not exist'),
        "점검 중에 개발용 데이터베이스를 읽지 못했다: UndefinedTableError",
    ),
    # DB_PORT의 서버가 asyncpg가 지원하지 않는 인증이나 프로토콜을 쓸 때(2차 리뷰 COR-1).
    "database_auth_unsupported": Abort(
        asyncpg.InterfaceError("unsupported authentication method requested by the server: 99"),
        "점검 중에 개발용 데이터베이스를 읽지 못했다: InterfaceError",
    ),
    "database_protocol_broken": Abort(
        asyncpg.exceptions.InternalClientError("unexpected message length"),
        "점검 중에 개발용 데이터베이스를 읽지 못했다: InternalClientError",
    ),
}


class TestAbortedChecks:
    """점검을 끝내지 못하면 CheckAbortedError로 바꾸고, 대역 서버를 닫는다."""

    @pytest.mark.parametrize("name", list(ABORTS))
    async def test_database_failure_during_checks_is_aborted_and_closes_the_stand_in(
        self, world: FakeWorld, name: str
    ) -> None:
        abort = ABORTS[name]
        world.read_error = abort.error
        world.read_error_at = 2

        with pytest.raises(CheckAbortedError) as raised:
            await run_checks(SETTINGS, ARGS)

        assert str(raised.value) == abort.message
        assert world.log.count("read") == 3
        assert world.stand_in_events == ["start", "stop"]

    async def test_person_who_does_not_follow_the_step_times_out(
        self, world: FakeWorld, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Google이 로그인을 막거나 사람이 계정을 고르지 않으면 결과 처리가 지나가지 않는다.
        monkeypatch.setattr(login_check, "LOGIN_WAIT_SECONDS", 0.05)
        world.idle_step = STEP_LOG_IN

        with pytest.raises(CheckAbortedError) as raised:
            await run_checks(SETTINGS, ARGS)

        assert f"로그인 결과 처리(GET {CALLBACK_PATH})" in str(raised.value)
        assert world.log == [f"ask:{STEP_OPEN}", "read", f"ask:{STEP_LOG_IN}"]
        assert world.stand_in_events == ["start", "stop"]

    async def test_stand_in_port_failure_is_aborted_before_asking(self, world: FakeWorld) -> None:
        world.stand_in_error = OSError(48, "Address already in use")

        with pytest.raises(CheckAbortedError) as raised:
            await run_checks(SETTINGS, ARGS)

        assert str(raised.value).startswith(f"대역 서버를 {FRONTEND}에 띄우지 못했다: OSError.")
        assert world.log == []


class TestExitCodeWithRealLayer:
    """`main`이 진짜 `run_checks`의 결과로 종료 코드를 고른다.

    점검을 시작하기 전의 확인(preflight)은 통과시킨다.
    """

    @pytest.fixture(autouse=True)
    def checks_pass_preflight(
        self, world: FakeWorld, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        dotenv = tmp_path / ".env"
        dotenv.write_text(
            f"FRONTEND_URL={FRONTEND}\nAPI_PORT={API_PORT}\nDB_PORT={DB_PORT}\n", encoding="utf-8"
        )
        monkeypatch.setattr(login_check, "DOTENV_PATH", dotenv)
        for name in ("FRONTEND_URL", "API_PORT", "DB_PORT"):
            monkeypatch.delenv(name, raising=False)

        async def no_problems(settings: CheckSettings, args: Args) -> list[object]:
            assert (settings, args) == (SETTINGS, ARGS)
            return []

        monkeypatch.setattr(login_check, "preflight", no_problems)

    def test_all_match_exits_0(self, world: FakeWorld, capsys: pytest.CaptureFixture[str]) -> None:
        code = main(ARGV)

        out, err = capsys.readouterr()
        assert code == 0, err
        assert "=== 결과\n모든 시점의 상태가 testcase.md의 표와 같다." in out

    def test_mismatch_exits_1_and_reports_it(
        self, world: FakeWorld, capsys: pytest.CaptureFixture[str]
    ) -> None:
        world.faults = {"logout_renames_user"}

        code = main(ARGV)

        out, _ = capsys.readouterr()
        assert code == 1
        assert "=== 결과\ntestcase.md의 표와 다른 것이 1개 있다." in out
        assert f"- {FAULTS['logout_renames_user']}" in out

    def test_database_failure_during_checks_exits_4(
        self, world: FakeWorld, capsys: pytest.CaptureFixture[str]
    ) -> None:
        world.read_error = ConnectionRefusedError(61, "Connection refused")
        world.read_error_at = 3

        code = main(ARGV)

        out, err = capsys.readouterr()
        assert code == 4
        assert (
            "점검을 끝내지 못했다. 점검 중에 개발용 데이터베이스를 읽지 못했다: "
            "ConnectionRefusedError"
        ) in err
        assert "=== 결과" not in out
