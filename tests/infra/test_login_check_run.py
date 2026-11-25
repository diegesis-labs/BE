"""`scripts/login_check.py`의 브라우저를 모는 층(`run_checks`)의 테스트 (2차 리뷰 TST-1).

판정 함수는 test_login_check_judge.py가, `main`이 종료 코드를 고르는 것은 test_login_check_main.py가
확인한다. 이 파일은 그 사이의 이음새(`run_checks`, `_check_allowed`, `_check_denied`)를 확인한다.

- 시점마다 스냅숏을 하나씩 찍고, 표가 기준으로 삼는 바로 앞 시점의 스냅숏과 함께 그 시점의 판정에
  넘긴다. 기준을 다른 시점으로 바꾸면 그 시점에서만 생긴 변화가 보이지 않는다.
- 판정이 돌려준 어긋난 것에 시점의 제목을 붙여, 두 점검에 걸쳐 빠짐없이 모은다.
- 점검을 끝내지 못하면(데이터베이스, 브라우저, 대역 서버) CheckAbortedError로 바꾸고, `main`은 4로
  끝난다. 컨텍스트, 브라우저, 대역 서버는 어떻게 끝나든 닫는다.

대역 서버, Playwright, 데이터베이스 읽기(`read_state`), 사람이 Google 화면에서 하는 로그인
(`_log_in`)은 가짜(FakeWorld)로 바꾼다. 가짜는 testcase.md의 "로컬 로그인 점검의 테이블 상태"대로
움직이는 서버와 데이터베이스를 흉내 낸다. 그래서 고장을 넣지 않으면 어긋난 것이 하나도 없고, 고장을
하나 넣으면 그 고장이 드러나는 시점의 칸 하나만 보고되어야 한다. 데이터베이스에 연결하는 가장 아래의
함수(`connect_read_only`)는 불리면 테스트가 실패하게 바꾼다. 가짜를 거치지 않고 개발용
데이터베이스에 닿는 길이 생기면 바로 드러나게 하기 위해서다.
"""

import hashlib
import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import asyncpg
import playwright.async_api
import pytest
from playwright.async_api import Error as PlaywrightError

from scripts import login_check
from scripts.login_check import (
    FETCH_SCRIPT,
    LOGIN_SESSION_TTL,
    LOGOUT_PATH,
    ME_PATH,
    NOT_ALLOWED_PATH,
    SESSION_COOKIE,
    AllowedRow,
    Args,
    CheckAbortedError,
    CheckSettings,
    DbState,
    SessionRow,
    UserRow,
    main,
    run_checks,
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

# 로그인한 시각. 지금과 멀리 떨어진 고정된 시각이다. 층이 `_log_in`이 돌려준 시각이 아닌 다른 시각을
# 판정에 넘기면 created_at과 expires_at의 칸이 어긋난다.
LOGIN_AT = datetime(2026, 1, 5, 9, 30, tzinfo=UTC)
ALLOWED_AT = datetime(2026, 1, 1, tzinfo=UTC)
# 두 계정 말고 다른 사람의 로그인 상태의 수. 점검 2는 login_sessions의 전체 행의 수만 본다.
OTHER_SESSIONS = 3
SESSION_TOKEN = "sessionTokenOfReaderA7c2e"

TITLES = [
    "점검 1 · 로그인 전",
    "점검 1 · 로그인 후",
    "점검 1 · 로그아웃 전",
    "점검 1 · 로그아웃 후",
    "점검 2 · 로그인 전",
    "점검 2 · 로그인 시도 후",
]

# 가짜 서버에 넣을 수 있는 고장과, 그 고장이 있을 때 보고되어야 하는 어긋난 것 하나(의 앞부분).
# 각 고장은 한 시점에서만 표와 달라지게 만든다. 판정에 넘기는 기준 스냅숏이 바뀌면 보고되지 않는다.
FAULTS = {
    # A가 로그인하면 A의 allowed_emails 행이 다시 들어간다(created_at이 바뀐다). 기준: 로그인 전.
    "login_reinserts_allowed_row": (
        "[점검 1 · 로그인 후] allowed_emails: 로그인 전 시점과 같아야 하는데 다르다."
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
    # B의 로그인 시도가 다른 사람의 login_sessions 행을 하나 만든다. 기준: 점검 2의 로그인 전.
    "denied_adds_session": (
        "[점검 2 · 로그인 시도 후] login_sessions: 전체 행의 수가 로그인 전과 다르다"
        f"(로그인 전: {OTHER_SESSIONS}, 지금: {OTHER_SESSIONS + 1})."
    ),
}


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class FakePage:
    def __init__(self, world: FakeWorld, context: FakeContext) -> None:
        self.world = world
        self.context = context
        self.url = "about:blank"
        self.gotos: list[str] = []

    async def goto(self, url: str, **_: Any) -> None:
        self.gotos.append(url)
        self.url = url

    async def evaluate(self, script: str, arg: list[str]) -> dict[str, object]:
        # 층은 브라우저 안의 fetch로만 서버를 부른다(프론트엔드가 하는 대로).
        assert script == FETCH_SCRIPT
        if self.world.evaluate_error is not None:
            raise self.world.evaluate_error
        path, method = arg
        return self.world.fetch(self.context, path, method)


class FakeContext:
    def __init__(self, world: FakeWorld) -> None:
        self.world = world
        self.jar: list[dict[str, object]] = []
        self.pages: list[FakePage] = []
        self.closed = False

    async def new_page(self) -> FakePage:
        page = FakePage(self.world, self)
        self.pages.append(page)
        return page

    async def cookies(self) -> list[dict[str, object]]:
        return [dict(cookie) for cookie in self.jar]

    async def close(self) -> None:
        self.closed = True


class FakeBrowser:
    def __init__(self, world: FakeWorld) -> None:
        self.world = world
        self.contexts: list[FakeContext] = []
        self.closed = False

    async def new_context(self) -> FakeContext:
        context = FakeContext(self.world)
        self.contexts.append(context)
        return context

    async def close(self) -> None:
        self.closed = True


class FakeChromium:
    def __init__(self, world: FakeWorld) -> None:
        self.world = world

    async def launch(self, **kwargs: object) -> FakeBrowser:
        self.world.launches.append(kwargs)
        if self.world.launch_error is not None:
            raise self.world.launch_error
        return self.world.browser


@dataclass
class FakePlaywright:
    chromium: FakeChromium


class FakeStandIn:
    def __init__(self, world: FakeWorld, **kwargs: object) -> None:
        self.world = world
        world.stand_in_kwargs.append(kwargs)

    def start(self) -> None:
        self.world.stand_in_events.append("start")
        if self.world.stand_in_error is not None:
            raise self.world.stand_in_error

    def stop(self) -> None:
        self.world.stand_in_events.append("stop")


class FakeWorld:
    """표대로 움직이는 서버, 데이터베이스, 브라우저. faults에 FAULTS의 이름을 넣으면 그 자리에서만
    표와 다르게 움직인다. *_error에 예외를 넣으면 그 자리에서 낸다."""

    def __init__(self) -> None:
        self.faults: set[str] = set()
        self.read_error: Exception | None = None
        self.read_error_at = 0  # 몇 번째(0부터) 데이터베이스 읽기에서 read_error를 낼지
        self.evaluate_error: Exception | None = None
        self.launch_error: Exception | None = None
        self.stand_in_error: Exception | None = None
        self.login_error: Exception | None = None

        self.allowed: dict[str, AllowedRow] = {A: AllowedRow(A, "user", ALLOWED_AT)}
        self.users: dict[str, UserRow] = {}
        self.sessions: dict[str, SessionRow] = {}
        self.other_sessions = OTHER_SESSIONS

        self.browser = FakeBrowser(self)
        self.reads: list[tuple[str, tuple[str, ...]]] = []
        self.fetches: list[tuple[str, str]] = []
        self.logins: list[tuple[str, str]] = []
        self.launches: list[dict[str, object]] = []
        self.stand_in_kwargs: list[dict[str, object]] = []
        self.stand_in_events: list[str] = []

    # --- 데이터베이스 -------------------------------------------------------------------------

    async def read_state(self, database_url: str, *, emails: tuple[str, ...]) -> DbState:
        index = len(self.reads)
        self.reads.append((database_url, tuple(emails)))
        if self.read_error is not None and index == self.read_error_at:
            raise self.read_error
        wanted = {email.lower() for email in emails}
        return DbState(
            allowed=tuple(row for email, row in sorted(self.allowed.items()) if email in wanted),
            users=tuple(row for email, row in sorted(self.users.items()) if email in wanted),
            sessions=tuple(row for row in self.sessions.values() if row.user_email in wanted),
            session_total=len(self.sessions) + self.other_sessions,
        )

    # --- 사람이 Google 화면에서 하는 로그인 ------------------------------------------------------

    async def log_in(
        self, page: FakePage, settings: CheckSettings, *, label: str, email: str
    ) -> datetime:
        assert settings == SETTINGS
        self.logins.append((label, email))
        if self.login_error is not None:
            raise self.login_error
        if email not in self.allowed:
            if "denied_adds_session" in self.faults:
                self.other_sessions += 1
            page.url = FRONTEND + NOT_ALLOWED_PATH
            return LOGIN_AT
        if "login_reinserts_allowed_row" in self.faults:
            self.allowed[email] = replace(self.allowed[email], created_at=LOGIN_AT)
        user = UserRow(uuid.uuid4(), email, "google-sub-a", "독자 A", LOGIN_AT)
        self.users[email] = user
        token_hash = _sha256(SESSION_TOKEN)
        self.sessions[token_hash] = SessionRow(
            token_hash, user.id, email, LOGIN_AT + LOGIN_SESSION_TTL, LOGIN_AT
        )
        page.context.jar.append(
            {
                "name": SESSION_COOKIE,
                "value": SESSION_TOKEN,
                "domain": "localhost",
                "path": "/",
                "httpOnly": True,
                "secure": False,
                "sameSite": "Lax",
            }
        )
        page.url = FRONTEND + "/"
        return LOGIN_AT

    # --- 서버 ---------------------------------------------------------------------------------

    def _session_of(self, context: FakeContext) -> SessionRow | None:
        for cookie in context.jar:
            if cookie["name"] == SESSION_COOKIE:
                return self.sessions.get(_sha256(str(cookie["value"])))
        return None

    def fetch(self, context: FakeContext, path: str, method: str) -> dict[str, object]:
        self.fetches.append((method, path))
        session = self._session_of(context)
        if (method, path) == ("GET", ME_PATH):
            if session is None:
                body = {"code": "UNAUTHENTICATED", "message": "로그인이 필요합니다."}
                return {"status": 401, "body": json.dumps(body)}
            if "me_extends_session" in self.faults:
                self.sessions[session.token_hash] = replace(
                    session, expires_at=session.expires_at + timedelta(hours=1)
                )
            user = self.users[session.user_email]
            body = {
                "id": str(user.id),
                "email": user.email,
                "display_name": user.display_name,
                "role": self.allowed[user.email].role,
            }
            return {"status": 200, "body": json.dumps(body)}
        if (method, path) == ("POST", LOGOUT_PATH):
            if session is not None and "logout_keeps_session" not in self.faults:
                del self.sessions[session.token_hash]
            if session is not None and "logout_renames_user" in self.faults:
                user = self.users[session.user_email]
                self.users[session.user_email] = replace(user, display_name="바뀐 이름")
            context.jar = [cookie for cookie in context.jar if cookie["name"] != SESSION_COOKIE]
            return {"status": 204, "body": ""}
        raise AssertionError(f"층이 모르는 요청을 보냈다: {method} {path}")

    # --- Playwright -----------------------------------------------------------------------------

    @asynccontextmanager
    async def async_playwright(self) -> AsyncIterator[FakePlaywright]:
        yield FakePlaywright(chromium=FakeChromium(self))


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> FakeWorld:
    world = FakeWorld()

    async def no_database(database_url: str) -> asyncpg.Connection:
        raise AssertionError(f"가짜를 거치지 않고 데이터베이스({database_url})에 연결하려 했다")

    monkeypatch.setattr(
        login_check, "FrontendStandIn", lambda **kwargs: FakeStandIn(world, **kwargs)
    )
    # run_checks는 부를 때 playwright.async_api에서 가져오므로 모듈의 속성을 바꾼다.
    monkeypatch.setattr(playwright.async_api, "async_playwright", world.async_playwright)
    monkeypatch.setattr(login_check, "read_state", world.read_state)
    monkeypatch.setattr(login_check, "_log_in", world.log_in)
    monkeypatch.setattr(login_check, "connect_read_only", no_database)
    return world


def headings(output: str) -> list[str]:
    return [line.removeprefix("=== ") for line in output.splitlines() if line.startswith("=== ")]


class TestStepsOfChecks:
    """표대로 움직이면 어긋난 것이 없다. 층은 정해진 순서로 대역 서버, 브라우저, 데이터베이스를
    쓴다."""

    async def test_all_match_reports_nothing_and_closes_everything(
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
        # 화면이 보이는 브라우저를 한 번 열고, 점검마다 새 컨텍스트를 만들어 닫는다.
        assert world.launches == [{"headless": False}]
        assert len(world.browser.contexts) == 2
        assert all(context.closed for context in world.browser.contexts)
        assert world.browser.closed
        for context in world.browser.contexts:
            [page] = context.pages
            assert page.gotos == [FRONTEND + "/"]
        assert world.logins == [("A", A), ("B", B)]
        # 여섯 시점마다 두 계정의 상태를 설정의 데이터베이스에서 한 번씩 읽는다.
        assert world.reads == [(SETTINGS.database_url, (A, B))] * 6
        assert world.fetches == [
            ("GET", ME_PATH),  # 점검 1 · 로그인 전
            ("GET", ME_PATH),  # 점검 1 · 로그아웃 전
            ("POST", LOGOUT_PATH),  # 점검 1 · 로그아웃 후
            ("GET", ME_PATH),
            ("GET", ME_PATH),  # 점검 2 · 로그인 시도 후
        ]
        # 사람이 표와 대조할 수 있게 시점마다 상태를 순서대로 출력한다.
        assert headings(capsys.readouterr().out) == TITLES


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


@dataclass(frozen=True)
class Abort:
    """점검을 끝내지 못하게 하는 고장과, 그때 CheckAbortedError가 보여 줄 안내."""

    attribute: str
    error: Exception
    message: str


# 세 번째 읽기(점검 1 · 로그아웃 전)에서 실패하게 해서, 점검 1의 컨텍스트가 열린 채 끝나지 않는지
# 본다.
ABORTS = {
    "database_refused": Abort(
        "read_error",
        ConnectionRefusedError(61, "Connection refused"),
        "점검 중에 개발용 데이터베이스를 읽지 못했다: ConnectionRefusedError",
    ),
    "database_error": Abort(
        "read_error",
        asyncpg.exceptions.UndefinedTableError('relation "users" does not exist'),
        "점검 중에 개발용 데이터베이스를 읽지 못했다: UndefinedTableError",
    ),
    # DB_PORT의 서버가 asyncpg가 지원하지 않는 인증이나 프로토콜을 쓸 때(2차 리뷰 COR-1).
    "database_auth_unsupported": Abort(
        "read_error",
        asyncpg.InterfaceError("unsupported authentication method requested by the server: 99"),
        "점검 중에 개발용 데이터베이스를 읽지 못했다: InterfaceError",
    ),
    "database_protocol_broken": Abort(
        "read_error",
        asyncpg.exceptions.InternalClientError("unexpected message length"),
        "점검 중에 개발용 데이터베이스를 읽지 못했다: InternalClientError",
    ),
    "browser_closed": Abort(
        "evaluate_error",
        # Playwright의 메시지에는 결과 처리의 주소(code와 state)가 들어 있을 수 있다.
        PlaywrightError(
            f"net::ERR_ABORTED at {FRONTEND}/api/auth/google/callback?code=CODESECRET1&state=STATE2"
        ),
        "브라우저가 닫혔거나 Playwright가 실패했다: Error",
    ),
}


class TestAbortedChecks:
    """점검을 끝내지 못하면 CheckAbortedError로 바꾸고, 연 것은 모두 닫는다."""

    @pytest.mark.parametrize("name", list(ABORTS))
    async def test_failure_during_checks_is_aborted_and_closes_everything(
        self, world: FakeWorld, name: str
    ) -> None:
        abort = ABORTS[name]
        setattr(world, abort.attribute, abort.error)
        world.read_error_at = 2

        with pytest.raises(CheckAbortedError) as raised:
            await run_checks(SETTINGS, ARGS)

        assert str(raised.value) == abort.message
        assert "CODESECRET1" not in str(raised.value)
        assert world.browser.contexts, "점검을 시작하기도 전에 끝났다"
        assert all(context.closed for context in world.browser.contexts)
        assert world.browser.closed
        assert world.stand_in_events == ["start", "stop"]

    async def test_login_wait_timeout_is_passed_through(self, world: FakeWorld) -> None:
        message = "5분 안에 http://localhost:5199로 돌아오지 않았다."
        world.login_error = CheckAbortedError(message)

        with pytest.raises(CheckAbortedError) as raised:
            await run_checks(SETTINGS, ARGS)

        assert str(raised.value) == message
        assert world.logins == [("A", A)]
        assert all(context.closed for context in world.browser.contexts)
        assert world.browser.closed
        assert world.stand_in_events == ["start", "stop"]

    async def test_browser_launch_failure_is_aborted_with_install_hint(
        self, world: FakeWorld
    ) -> None:
        world.launch_error = PlaywrightError("Executable doesn't exist at /ms-playwright/chromium")

        with pytest.raises(CheckAbortedError) as raised:
            await run_checks(SETTINGS, ARGS)

        assert "uv run playwright install chromium" in str(raised.value)
        assert world.browser.contexts == []
        assert world.logins == []
        assert world.stand_in_events == ["start", "stop"]

    async def test_stand_in_port_failure_is_aborted_before_browser(self, world: FakeWorld) -> None:
        world.stand_in_error = OSError(48, "Address already in use")

        with pytest.raises(CheckAbortedError) as raised:
            await run_checks(SETTINGS, ARGS)

        assert str(raised.value).startswith(f"대역 서버를 {FRONTEND}에 띄우지 못했다: OSError.")
        assert world.launches == []
        assert world.reads == []


class TestExitCodeWithRealLayer:
    """`main`이 진짜 `run_checks`의 결과로 종료 코드를 고른다.

    브라우저를 열기 전의 확인(preflight)은 통과시킨다.
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
