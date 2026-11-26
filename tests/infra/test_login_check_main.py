"""`scripts/login_check.py`의 `main`이 어떤 종료 코드로 끝나는지의 테스트 (E1 S1.7, T1.7.2).

E1 S1.7의 "못 박을 것"은 점검 전의 상태가 표와 다르면 점검을 시작하지 않고, 상태를 맞추는 SQL을
보여 준 뒤 끝내라고 한다. T1.7.2는 표와 다른 것이 있으면 0이 아닌 종료 코드로 끝내라고 한다.
`precheck`의 판정은 test_login_check_precheck.py(TC-1.7.2)가, 판정과 출력의 순수 함수는
test_login_check_judge.py가 확인한다. 이 파일은 그 둘을 `main`까지 잇는 부분을 확인한다.

- `preflight`는 명령의 인자로 받은 두 이메일로 `precheck`를 부르고, 그 결과를 어긋난 것의 목록에
  넣는다.
- 점검을 시작하기 전의 확인에서 어긋난 것이 하나라도 있으면 `main`은 3으로 끝나고, 점검
  (`run_checks`. 대역 서버를 띄우고 사람에게 안내하는 곳)을 시작하지 않는다. 어긋난 것과
  맞추는 SQL은 출력에 그대로 나온다.
- 점검이 표와 다른 것을 돌려주면 1, 없으면 0, 점검을 끝내지 못하면 4로 끝난다.

네트워크, 데이터베이스, 대역 서버에 닿는 함수(`_http_get`, `precheck`, `port_in_use`,
`run_checks`)는 monkeypatch로 가짜로 바꾸고, 불린 인자를 기록한다. 데이터베이스에 연결하는 가장
아래의 함수(`connect_read_only`)는 불리면 테스트가 실패하게 바꾼다. 가짜를 거치지 않고
데이터베이스에 닿는 길이 생겨도 개발용 데이터베이스에 닿지 않고 바로 드러나게 하기 위해서다. 설정은
임시 폴더의 `.env`에서 읽게 해서, 개발자의 `.env`와 환경변수가 결과를 바꾸지 않게 한다.
"""

import asyncio
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlencode

import asyncpg
import pytest

from scripts import login_check
from scripts.login_check import (
    CALLBACK_PATH,
    HEALTH_PATH,
    LOGIN_PATH,
    PSQL,
    Args,
    CheckAbortedError,
    CheckSettings,
    PrecheckProblem,
    main,
    preflight,
)

A = "reader-a@example.com"
B = "outsider-b@example.com"
ARGV = ["--allowed-email", A, "--denied-email", B]

# compose의 기본값과 다른 값을 써서, `.env`에서 읽은 값이 그대로 각 확인에 쓰이는지 본다.
FRONTEND = "http://localhost:5199"
API_PORT = 18080
DB_PORT = 15432
BACKEND = f"http://localhost:{API_PORT}"
DATABASE = f"postgresql://diegesis:diegesis@localhost:{DB_PORT}/diegesis"
SETTINGS = CheckSettings(frontend_url=FRONTEND, api_port=API_PORT, db_port=DB_PORT)

PREFLIGHT_HEADER = "점검을 시작하기 전의 확인에서 어긋난 것이 있어, 점검을 시작하지 않고 끝낸다."

# precheck가 돌려주는 것과 같은 꼴의 맞지 않는 조건 두 개. 맞추는 SQL은 여러 줄이다.
A_NOT_ALLOWED = PrecheckProblem(
    problem=f"계정 A({A})가 허용 목록에 없다. user로 있어야 한다.",
    fix_sql=(
        "INSERT INTO allowed_emails (email, role)\n"
        f"VALUES (lower('{A}'), 'user')\n"
        "ON CONFLICT (email) DO UPDATE SET role = EXCLUDED.role;"
    ),
)
B_ALLOWED = PrecheckProblem(
    problem=f"계정 B({B})가 허용 목록에 있다. 없어야 한다.",
    fix_sql=(
        "BEGIN;\n"
        "DELETE FROM login_sessions\n"
        f"WHERE user_id IN (SELECT id FROM users WHERE email = lower('{B}'));\n"
        f"DELETE FROM allowed_emails WHERE email = lower('{B}');\n"
        "COMMIT;"
    ),
)


def google_location(**params: str) -> str:
    """`GET /api/auth/google/login`이 돌려주는 Location. 기본값은 확인을 모두 통과하는 꼴이다."""
    query = {
        "client_id": "test-client.apps.googleusercontent.com",
        "redirect_uri": FRONTEND + CALLBACK_PATH,
        "response_type": "code",
        "scope": "openid email profile",
        "state": "s",
        "nonce": "n",
        "code_challenge": "c",
        "code_challenge_method": "S256",
        **params,
    }
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(query)


HttpReply = tuple[int, str | None] | None


@dataclass
class Fakes:
    """가짜 함수가 돌려줄 것과, 가짜 함수가 불린 인자의 기록. 기본값은 모든 확인을 통과한다."""

    health: HttpReply = (200, None)
    login: HttpReply = (302, google_location())
    precheck_result: list[PrecheckProblem] = field(default_factory=list)
    precheck_error: Exception | None = None
    port_busy: bool = False
    mismatches: list[str] = field(default_factory=list)
    run_error: Exception | None = None

    http_calls: list[tuple[str, str]] = field(default_factory=list)
    precheck_calls: list[tuple[str, str, str]] = field(default_factory=list)
    port_calls: list[tuple[str, int]] = field(default_factory=list)
    run_calls: list[tuple[CheckSettings, Args]] = field(default_factory=list)


@pytest.fixture
def dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """`main`이 읽는 `.env`. 세 값의 환경변수는 지워서 이 파일의 값이 쓰이게 한다."""
    path = tmp_path / ".env"
    path.write_text(
        f"FRONTEND_URL={FRONTEND}\nAPI_PORT={API_PORT}\nDB_PORT={DB_PORT}\n", encoding="utf-8"
    )
    monkeypatch.setattr(login_check, "DOTENV_PATH", path)
    for name in ("FRONTEND_URL", "API_PORT", "DB_PORT"):
        monkeypatch.delenv(name, raising=False)
    return path


@pytest.fixture
def fakes(monkeypatch: pytest.MonkeyPatch, dotenv: Path) -> Fakes:
    fakes = Fakes()

    def fake_http_get(backend_url: str, path: str) -> HttpReply:
        fakes.http_calls.append((backend_url, path))
        if path == HEALTH_PATH:
            return fakes.health
        if path == LOGIN_PATH:
            return fakes.login
        raise AssertionError(f"점검을 시작하기 전의 확인이 모르는 경로를 불렀다: {path}")

    async def fake_precheck(
        database_url: str, *, allowed_email: str, denied_email: str
    ) -> list[PrecheckProblem]:
        fakes.precheck_calls.append((database_url, allowed_email, denied_email))
        if fakes.precheck_error is not None:
            raise fakes.precheck_error
        return list(fakes.precheck_result)

    def fake_port_in_use(host: str, port: int) -> bool:
        fakes.port_calls.append((host, port))
        return fakes.port_busy

    async def fake_run_checks(settings: CheckSettings, args: Args) -> list[str]:
        # 진짜 run_checks는 대역 서버를 띄우고 사람이 안내대로 할 때까지 기다린다.
        fakes.run_calls.append((settings, args))
        if fakes.run_error is not None:
            raise fakes.run_error
        return list(fakes.mismatches)

    async def no_database(database_url: str) -> asyncpg.Connection:
        raise AssertionError(f"가짜를 거치지 않고 데이터베이스({database_url})에 연결하려 했다")

    monkeypatch.setattr(login_check, "_http_get", fake_http_get)
    monkeypatch.setattr(login_check, "precheck", fake_precheck)
    monkeypatch.setattr(login_check, "port_in_use", fake_port_in_use)
    monkeypatch.setattr(login_check, "run_checks", fake_run_checks)
    monkeypatch.setattr(login_check, "connect_read_only", no_database)
    return fakes


def numbered(output: str) -> list[str]:
    """render_preflight가 번호를 붙인 줄. 어긋난 것 하나가 한 줄이다."""
    return [line for line in output.splitlines() if re.match(r"\d+\. ", line)]


def shown_sql(sql: str) -> str:
    """render_preflight가 고치는 방법을 보여 주는 꼴. 고치는 방법의 줄마다 5칸을 들인다."""
    return "\n".join(f"     {line}" for line in sql.splitlines())


def assert_all_checks_ran(fakes: Fakes) -> None:
    """점검을 시작하기 전의 네 확인을 모두 했다. 각 확인은 `.env`의 값과 명령의 인자를 썼다."""
    assert fakes.http_calls == [(BACKEND, HEALTH_PATH), (BACKEND, LOGIN_PATH)]
    assert fakes.precheck_calls == [(DATABASE, A, B)]
    assert fakes.port_calls == [("localhost", 5199)]


class TestPrecheckStopsBeforeChecks:
    """E1 S1.7 "못 박을 것", TC-1.7.2. 점검 전의 상태가 표와 다르면 SQL만 보여 주고 끝낸다."""

    def test_precheck_problems_exit_3_show_sql_and_start_no_check(
        self, fakes: Fakes, capsys: pytest.CaptureFixture[str]
    ) -> None:
        fakes.precheck_result = [A_NOT_ALLOWED, B_ALLOWED]

        code = main(ARGV)

        out, err = capsys.readouterr()
        assert code == 3
        assert fakes.run_calls == [], "점검 전의 상태가 다른데 점검을 시작했다"
        assert_all_checks_ran(fakes)
        assert PREFLIGHT_HEADER in err
        # 다른 확인은 모두 통과했으므로, 어긋난 것은 precheck가 돌려준 두 조건뿐이다.
        assert numbered(err) == [f"1. {A_NOT_ALLOWED.problem}", f"2. {B_ALLOWED.problem}"]
        # 맞추는 SQL은 줄을 빠뜨리거나 바꾸지 않고 그대로 보여 주며, 실행하지 않는다고 알린다.
        for item in (A_NOT_ALLOWED, B_ALLOWED):
            assert shown_sql(item.fix_sql) in err
        assert "스크립트는 실행하지 않는다." in err
        assert PSQL in err
        assert "=== 결과" not in out

    def test_preflight_puts_each_precheck_problem_into_its_list(self, fakes: Fakes) -> None:
        fakes.precheck_result = [A_NOT_ALLOWED, B_ALLOWED]

        problems = asyncio.run(preflight(SETTINGS, Args(allowed_email=A, denied_email=B)))

        assert fakes.precheck_calls == [(DATABASE, A, B)]
        assert [problem.problem for problem in problems] == [
            A_NOT_ALLOWED.problem,
            B_ALLOWED.problem,
        ]
        for problem, item in zip(problems, (A_NOT_ALLOWED, B_ALLOWED), strict=True):
            assert problem.fix.endswith("\n" + item.fix_sql)
            assert PSQL in problem.fix

    def test_precheck_gets_lowercased_emails_from_arguments(
        self, fakes: Fakes, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(["--allowed-email", "Reader-A@Example.com", "--denied-email", B.upper()])

        assert code == 0, capsys.readouterr().err
        assert_all_checks_ran(fakes)


@dataclass(frozen=True)
class Broken:
    """점검을 시작하기 전의 확인 하나를 어긋나게 하는 가짜의 값과, 그때 보여야 하는 어긋난 것."""

    changes: dict[str, object]
    problem: str
    # False면 서버가 응답하지 않는 경우라, 나머지 확인을 하지 않는다(preflight의 docstring).
    checks_rest: bool = True


BROKEN = {
    "server_unreachable": Broken(
        {"health": None},
        f"백엔드({BACKEND})의 GET {HEALTH_PATH}가 200이 아니다(닿지 못함).",
        checks_rest=False,
    ),
    "server_unhealthy": Broken(
        {"health": (500, None)},
        f"백엔드({BACKEND})의 GET {HEALTH_PATH}가 200이 아니다(응답: 500).",
        checks_rest=False,
    ),
    "login_not_redirecting": Broken(
        {"login": (500, None)},
        f"백엔드의 GET {LOGIN_PATH}가 302와 Location을 돌려주지 않았다(응답: 500).",
    ),
    "redirect_uri_differs": Broken(
        {"login": (302, google_location(redirect_uri=BACKEND + CALLBACK_PATH))},
        "서버가 Google에 보내는 redirect_uri가 다르다"
        f"(지금: {BACKEND}{CALLBACK_PATH}, 기대한 값: {FRONTEND}{CALLBACK_PATH}).",
    ),
    "client_id_empty": Broken(
        {"login": (302, google_location(client_id=""))},
        "서버가 Google에 보내는 client_id가 비어 있다.",
    ),
    "database_unreachable": Broken(
        {"precheck_error": ConnectionRefusedError(61, "Connection refused")},
        f"개발용 데이터베이스(localhost:{DB_PORT})를 읽지 못했다: ConnectionRefusedError",
    ),
    "database_missing": Broken(
        {"precheck_error": asyncpg.exceptions.InvalidCatalogNameError("no database")},
        f"개발용 데이터베이스(localhost:{DB_PORT})를 읽지 못했다: InvalidCatalogNameError",
    ),
    # DB_PORT에 asyncpg가 지원하지 않는 인증이나 프로토콜을 쓰는 서버가 떠 있을 때(2차 리뷰 COR-1).
    # 두 예외는 OSError와 PostgresError의 하위 클래스가 아니다.
    "database_auth_unsupported": Broken(
        {
            "precheck_error": asyncpg.InterfaceError(
                "unsupported authentication method requested by the server: 99"
            )
        },
        f"개발용 데이터베이스(localhost:{DB_PORT})를 읽지 못했다: InterfaceError",
    ),
    "database_protocol_broken": Broken(
        {"precheck_error": asyncpg.exceptions.InternalClientError("unexpected message length")},
        f"개발용 데이터베이스(localhost:{DB_PORT})를 읽지 못했다: InternalClientError",
    ),
    "frontend_port_busy": Broken(
        {"port_busy": True},
        f"{FRONTEND}에서 이미 다른 프로그램이 연결을 받고 있다.",
    ),
}


class TestOtherPreflightProblemsStopBeforeChecks:
    """점검 전의 상태 말고 다른 확인(서버, Google 설정, 데이터베이스, 포트)이 어긋나도 3이다."""

    @pytest.mark.parametrize("name", list(BROKEN))
    def test_exits_3_shows_problem_and_starts_no_check(
        self, fakes: Fakes, capsys: pytest.CaptureFixture[str], name: str
    ) -> None:
        broken = BROKEN[name]
        for attribute, value in broken.changes.items():
            setattr(fakes, attribute, value)

        code = main(ARGV)

        out, err = capsys.readouterr()
        assert code == 3
        assert fakes.run_calls == [], "확인이 어긋났는데 점검을 시작했다"
        assert PREFLIGHT_HEADER in err
        assert numbered(err) == [f"1. {broken.problem}"]
        assert "=== 결과" not in out
        if broken.checks_rest:
            assert_all_checks_ran(fakes)
        else:
            assert fakes.http_calls == [(BACKEND, HEALTH_PATH)]
            assert fakes.precheck_calls == []
            assert fakes.port_calls == []

    def test_invalid_settings_exit_3_before_any_check(
        self, fakes: Fakes, dotenv: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        dotenv.write_text("FRONTEND_URL=https://diegesis.example\n", encoding="utf-8")

        code = main(ARGV)

        err = capsys.readouterr().err
        assert code == 3
        assert "설정을 읽지 못했다:" in err
        assert "https://diegesis.example" in err
        assert fakes.http_calls == []
        assert fakes.precheck_calls == []
        assert fakes.port_calls == []
        assert fakes.run_calls == []


class TestResultOfChecks:
    """T1.7.2. 확인을 모두 통과하면 점검을 한 번 하고, 그 결과로 종료 코드를 정한다."""

    def test_mismatch_exits_1_and_reports_each(
        self, fakes: Fakes, capsys: pytest.CaptureFixture[str]
    ) -> None:
        fakes.mismatches = [
            "[점검 1 · 로그인 후] login_sessions: A의 행이 1개가 아니다(지금: 0개).",
            "[점검 2 · 로그인 시도 후] users: B의 행이 없어야 한다(지금: 1개).",
        ]

        code = main(ARGV)

        out, err = capsys.readouterr()
        assert code == 1
        assert fakes.run_calls == [(SETTINGS, Args(allowed_email=A, denied_email=B))]
        assert_all_checks_ran(fakes)
        assert "=== 결과\ntestcase.md의 표와 다른 것이 2개 있다." in out
        for mismatch in fakes.mismatches:
            assert f"- {mismatch}" in out
        assert PREFLIGHT_HEADER not in err

    def test_all_match_exits_0(self, fakes: Fakes, capsys: pytest.CaptureFixture[str]) -> None:
        code = main(ARGV)

        out, err = capsys.readouterr()
        assert code == 0
        assert fakes.run_calls == [(SETTINGS, Args(allowed_email=A, denied_email=B))]
        assert_all_checks_ran(fakes)
        assert f"FRONTEND_URL={FRONTEND}, 백엔드={BACKEND}, 데이터베이스=localhost:{DB_PORT}" in out
        assert "=== 결과\n스크립트가 판정하는 칸은 모든 시점에서 testcase.md의 표와 같다." in out
        assert err == ""

    def test_aborted_exits_4(self, fakes: Fakes, capsys: pytest.CaptureFixture[str]) -> None:
        fakes.run_error = CheckAbortedError("5분 안에 돌아오지 않았다.")

        code = main(ARGV)

        out, err = capsys.readouterr()
        assert code == 4
        assert len(fakes.run_calls) == 1
        assert "점검을 끝내지 못했다. 5분 안에 돌아오지 않았다." in err
        assert "=== 결과" not in out
