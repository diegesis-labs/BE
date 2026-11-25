"""로컬 로그인 점검 스크립트.

백엔드 담당자가 프론트엔드 레포 없이, 로컬에서 실제 Google 계정으로 로그인과 로그아웃을 끝까지
확인하는 도구다(docs/ADR.md의 ADR-026, docs/backlog/epic-1/E1-login-allowlist.md의 S1.7).

## 실행 방법

compose로 서버를 띄우고, 허용 목록에 계정 A를 `user`로 넣은 뒤 실행한다.

    uv run python scripts/login_check.py --allowed-email <허용 목록에 넣은 계정 A> \
        --denied-email <허용 목록에 없는 계정 B>

`FRONTEND_URL`, `API_PORT`, `DB_PORT`는 compose와 같은 방법으로 정한다. 환경변수가 있으면 그것을,
없으면 레포 최상위의 `.env`를, 그것도 없으면 compose의 기본값을 쓴다. 대역 서버는 서버가 쓰는 것과
같은 `FRONTEND_URL`에 떠야 하기 때문이다(E1 T1.7.3).

## 사람이 하는 일

스크립트가 연 브라우저의 Google 화면에서, 안내받은 계정을 고르고 필요하면 비밀번호를 넣는다.
스크립트는 Google 화면에 아무것도 입력하지 않으며, 비밀번호를 받지 않는다. 그리고 시점마다 출력된
상태를 docs/backlog/epic-1/testcase.md의 "로컬 로그인 점검의 테이블 상태"와 대조한다. 스크립트도
같은 표로 판정해서, 다른 것을 끝에 모아 보여 준다.

## 종료 코드

- 0: 모든 시점의 상태가 표와 같다.
- 1: 표와 다른 것이 있다. 끝에 모아 보여 준다.
- 2: 명령의 인자가 잘못됐다.
- 3: 브라우저를 열기 전의 확인(서버, Google 설정, 점검 전의 테이블 상태, 포트)이 어긋났다.
  브라우저를 열지 않고, 어긋난 것과 고치는 방법을 보여 준다. 상태를 맞추는 SQL은 보여 주기만 한다.
- 4: 점검을 끝내지 못했다. 로그인을 기다리는 시간이 지났거나, 브라우저가 닫혔거나, 데이터베이스에
  닿지 못했다.

## 지키는 것

- 사람이 phase의 MANUAL 점검에서 실행한다. 실제 Google 계정과 사람의 입력이 필요하므로
  `scripts/check.sh`와 CI에서는 실행하지 않는다. 검사가 확인하는 것은 Google 없이 확인할 수 있는
  부분(대역 서버, 점검 전 확인, 표와의 대조, 출력)뿐이며, 그 테스트는
  `tests/infra/test_login_check*.py`에 있다. 그래서 판정과 출력은 Playwright와 데이터베이스에서
  떼어 낸 순수 함수로 두고, 브라우저를 모는 부분은 그 함수들을 부르는 얇은 층으로 둔다.
- 개발용 데이터베이스를 읽기 전용 트랜잭션으로만 읽는다. 개발자의 데이터를 지우거나 바꾸지 않는다.
- 브라우저는 점검마다 새 컨텍스트로 열고, 프로필을 디스크에 남기지 않는다. 자동화를 탐지하는 장치를
  피하는 옵션을 쓰지 않는다. Google이 자동화된 브라우저의 로그인을 막으면, 그때의 방법은 ADR-026의
  재검토 조건에 따라 사람이 정한다.
- 쿠키의 값은 읽는 자리에서 바로 SHA-256으로 바꾸고, 값 자체는 어디에도 담지 않는다. 쿠키의 값과
  `token_hash`의 값은 출력하지 않으며, `token_hash`는 쿠키 값의 SHA-256과 같은지만 출력한다.
  스크린숏, 트레이스, HAR도 남기지 않는다.

이 파일은 `app/`을 import하지 않는다. 점검 스크립트는 compose로 띄운 서버를 바깥에서 보는 도구다.
서버의 코드를 끌어오면 서버를 거치지 않은 것을 확인하게 된다.

## 프론트엔드 대역 서버

`FrontendStandIn`은 프론트엔드의 개발 서버(Vite)를 흉내 낸다. `FRONTEND_URL`의 주소에서 요청을
받아, `/api`로 시작하는 요청은 백엔드로 넘기고 그 밖의 경로에는 지금의 주소를 보여 주는 빈 화면을
낸다. 백엔드로 넘길 때 하는 일은 다음과 같다.

- `Host`는 백엔드의 `호스트:포트`로 바꾼다. 프론트엔드의 개발 서버가 `changeOrigin: true`로 하는
  일이다(ADR-025). 그래서 돌아올 주소를 요청의 Host로 만드는 결함이 로컬에서도 드러난다(ADR-026).
- `Origin`, `Referer`, `Cookie`를 포함한 나머지 헤더와 메서드, 경로와 쿼리, 본문은 그대로 넘긴다.
  백엔드의 출처 확인과 로그인 상태가 이 값을 본다. 연결 하나에만 해당하는 hop-by-hop 헤더만 뺀다.
- 백엔드의 응답은 리디렉션을 따라가지 않고 상태 코드, 헤더, 본문을 그대로 돌려준다. `Set-Cookie`가
  여러 개면 하나로 합치지 않고 각각 따로 돌려준다. 로그인 결과 처리는 `diegesis_oauth_state`를
  지우는 것과 로그인 상태의 쿠키를 심는 것을 함께 보내므로, 합치거나 하나를 빠뜨리면 브라우저의
  상태가 실제 프론트엔드와 달라진다.

백엔드와는 `http.client`로 통신한다. `http.client`는 리디렉션을 따라가지 않고, 응답 헤더를 받은
그대로(같은 이름이 여러 번 와도 따로따로) 돌려준다.
"""

import html
import http.client
import threading
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Self
from urllib.parse import urlsplit

import asyncpg

# 이 접두사로 시작하는 경로를 백엔드로 넘긴다. 프론트엔드의 개발 서버의 proxy 설정과 같은 꼴이다.
API_PREFIX = "/api"

# 연결 하나에만 해당하는 헤더(RFC 9110 7.6.1). 대역 서버는 백엔드와 연결을 따로 맺으므로 넘기지
# 않는다. `Connection` 헤더에 이름이 적힌 헤더도 함께 뺀다.
HOP_BY_HOP_HEADERS = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "proxy-connection",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
)

# 로그인 결과 처리는 백엔드가 Google과 `code`를 교환한 뒤에 응답한다. 그 교환의 타임아웃(10초)보다
# 넉넉하게 기다린다.
BACKEND_TIMEOUT_SECONDS = 30

# 요청을 받는 스레드가 멈추라는 신호를 확인하는 간격. stop()이 이만큼 안에 돌아온다.
SHUTDOWN_POLL_SECONDS = 0.05


@dataclass(frozen=True)
class _Backend:
    url: str
    host: str
    port: int
    netloc: str

    @classmethod
    def parse(cls, url: str) -> Self:
        """`http://호스트:포트` 꼴의 주소만 받는다. 경로, 쿼리, 사용자 정보가 붙으면 거절한다."""
        parts = urlsplit(url)
        if (
            parts.scheme != "http"
            or not parts.hostname
            or parts.username is not None
            or parts.path not in ("", "/")
            or parts.query
            or parts.fragment
        ):
            raise ValueError(f"backend_url은 http://호스트:포트 꼴이어야 한다: {url!r}")
        return cls(url=url, host=parts.hostname, port=parts.port or 80, netloc=parts.netloc)


def _dropped_headers(connection_values: list[str]) -> frozenset[str]:
    """넘기지 않을 헤더 이름(소문자). hop-by-hop 헤더와 `Connection`에 적힌 이름이다."""
    listed = {token.strip().lower() for value in connection_values for token in value.split(",")}
    return HOP_BY_HOP_HEADERS | {name for name in listed if name}


def _may_have_body(method: str, status: int) -> bool:
    return method != "HEAD" and not (100 <= status < 200 or status in (204, 304))


class _StandInServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], backend: _Backend) -> None:
        super().__init__(address, _StandInHandler)
        self.backend = backend


class _StandInHandler(BaseHTTPRequestHandler):
    def _handle(self) -> None:
        if self.path.startswith(API_PREFIX):
            self._forward()
        else:
            self._page()

    do_GET = do_HEAD = do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = _handle

    def log_message(self, format: str, *args: Any) -> None:
        # 요청 줄을 찍지 않는다. 로그인 결과 처리의 요청 줄에는 Google의 `code`와 `state`가 있다.
        return

    def _forward(self) -> None:
        server = self.server
        assert isinstance(server, _StandInServer)
        backend = server.backend

        # 본문은 Content-Length만큼 읽는다. 다른 방식으로 온 본문을 빈 본문으로 넘기지 않는다.
        if "Transfer-Encoding" in self.headers:
            self._plain(411, "대역 서버는 Content-Length가 있는 요청 본문만 넘긴다.")
            return
        length = self.headers.get("Content-Length")
        try:
            body = self.rfile.read(int(length)) if length is not None else None
        except ValueError:
            self._plain(400, f"Content-Length를 읽지 못했다: {length!r}")
            return

        dropped = _dropped_headers(self.headers.get_all("Connection") or [])
        conn = http.client.HTTPConnection(
            backend.host, backend.port, timeout=BACKEND_TIMEOUT_SECONDS
        )
        try:
            conn.putrequest(self.command, self.path, skip_host=True, skip_accept_encoding=True)
            conn.putheader("Host", backend.netloc)
            for name, value in self.headers.items():
                if name.lower() != "host" and name.lower() not in dropped:
                    conn.putheader(name, value)
            conn.endheaders(body)
            response = conn.getresponse()
            status, reason = response.status, response.reason
            headers = response.getheaders()
            content = response.read()
        except (OSError, http.client.HTTPException) as exc:
            self._plain(502, f"백엔드({backend.url})에 닿지 못했다: {type(exc).__name__}")
            return
        finally:
            conn.close()

        # send_response는 Server와 Date를 덧붙이므로 쓰지 않는다. 백엔드가 보낸 헤더만 돌려준다.
        self.send_response_only(status, reason)
        response_dropped = _dropped_headers([v for k, v in headers if k.lower() == "connection"])
        has_length = False
        for name, value in headers:
            if name.lower() in response_dropped:
                continue
            has_length = has_length or name.lower() == "content-length"
            self.send_header(name, value)
        if not has_length and _may_have_body(self.command, status):
            # 백엔드가 길이 없이(chunked) 보낸 본문은 다 읽었으므로 길이를 붙여 돌려준다.
            self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(content)

    def _page(self) -> None:
        """지금의 주소(경로와 쿼리)를 보여 주는 빈 화면.

        점검 스크립트가 이 화면에서 `fetch`를 부른다.
        """
        page = (
            "<!doctype html>\n"
            '<html lang="ko"><head><meta charset="utf-8"><title>프론트엔드 대역</title></head>\n'
            f'<body><p id="address">{html.escape(self.path)}</p></body></html>\n'
        )
        self._send(200, "text/html; charset=utf-8", page)

    def _plain(self, status: int, message: str) -> None:
        self._send(status, "text/plain; charset=utf-8", message + "\n")

    def _send(self, status: int, content_type: str, text: str) -> None:
        content = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(content)


class FrontendStandIn:
    """프론트엔드의 개발 서버를 흉내 내는 대역 서버. 백그라운드 스레드에서 요청을 받는다."""

    def __init__(self, *, listen_host: str, listen_port: int, backend_url: str) -> None:
        self._address = (listen_host, listen_port)
        self._backend = _Backend.parse(backend_url)
        self._server: _StandInServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """포트를 잡고 백그라운드 스레드에서 요청을 받기 시작한다."""
        if self._server is not None:
            raise RuntimeError("대역 서버가 이미 떠 있다.")
        server = _StandInServer(self._address, self._backend)
        thread = threading.Thread(
            target=server.serve_forever,
            kwargs={"poll_interval": SHUTDOWN_POLL_SECONDS},
            name="frontend-stand-in",
            daemon=True,
        )
        thread.start()
        self._server, self._thread = server, thread

    def stop(self) -> None:
        """요청을 그만 받고 포트를 놓는다. 뜨지 않았으면 아무것도 하지 않는다."""
        server, thread = self._server, self._thread
        if server is None:
            return
        server.shutdown()
        server.server_close()
        if thread is not None:
            thread.join()
        self._server = self._thread = None

    @property
    def port(self) -> int:
        """듣고 있는 포트. `listen_port=0`이면 운영체제가 고른 포트다."""
        if self._server is None:
            raise RuntimeError("대역 서버가 아직 뜨지 않았다. start()를 먼저 부른다.")
        return self._server.server_port


# ---------------------------------------------------------------------------------------------
# 점검 스크립트
# ---------------------------------------------------------------------------------------------

SESSION_COOKIE = "diegesis_session"
STATE_COOKIE = "diegesis_oauth_state"

HEALTH_PATH = "/api/health"
LOGIN_PATH = "/api/auth/google/login"
CALLBACK_PATH = "/api/auth/google/callback"
ME_PATH = "/api/me"
LOGOUT_PATH = "/api/auth/logout"
NOT_ALLOWED_PATH = "/login?error=NOT_ALLOWED"

# compose는 서버에 LOGIN_SESSION_TTL_HOURS를 넘기지 않으므로 서버는 기본값을 쓴다
# (docs/CONFIGURATION.md 3.3절).
LOGIN_SESSION_TTL = timedelta(hours=336)
# 표의 "1분 안에서 같다"와 "방금"의 폭.
TIME_TOLERANCE = timedelta(minutes=1)
# 사람이 Google 화면에서 계정을 고를 때까지 기다리는 시간의 상한.
LOGIN_WAIT_SECONDS = 300

# compose.yaml의 기본값과 db 서비스의 로컬 전용 계정.
DEFAULT_FRONTEND_URL = "http://localhost:5173"
DEFAULT_API_PORT = 8080
DEFAULT_DB_PORT = 5432
DB_USER_AND_PASSWORD = "diegesis:diegesis"
DB_NAME = "diegesis"
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1"})

EXIT_OK = 0
EXIT_MISMATCH = 1
EXIT_PREFLIGHT = 3
EXIT_ABORTED = 4


# --- 설정과 인자 ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CheckSettings:
    """점검이 쓰는 주소. compose와 같은 방법으로 정한다(resolve_settings)."""

    frontend_url: str
    api_port: int
    db_port: int

    @property
    def frontend_host(self) -> str:
        return urlsplit(self.frontend_url).hostname or ""

    @property
    def frontend_port(self) -> int:
        return urlsplit(self.frontend_url).port or 80

    @property
    def backend_url(self) -> str:
        return f"http://localhost:{self.api_port}"

    @property
    def database_url(self) -> str:
        return f"postgresql://{DB_USER_AND_PASSWORD}@localhost:{self.db_port}/{DB_NAME}"


def parse_dotenv(text: str) -> dict[str, str]:
    """`.env`의 `이름=값` 줄을 읽는다. 빈 줄과 `#`으로 시작하는 줄은 건너뛴다."""
    raise NotImplementedError


def resolve_settings(environ: Mapping[str, str], dotenv: Mapping[str, str]) -> CheckSettings:
    """compose의 `${이름:-기본값}`과 같은 방법으로 세 값을 정한다. 값이 잘못됐으면 ValueError."""
    raise NotImplementedError


@dataclass(frozen=True)
class Args:
    allowed_email: str
    denied_email: str


def parse_args(argv: Sequence[str] | None = None) -> Args:
    """명령의 인자. 이메일은 소문자로 바꾼다."""
    raise NotImplementedError


# --- 브라우저를 열기 전의 확인 ---------------------------------------------------------------


@dataclass(frozen=True)
class PreflightProblem:
    problem: str  # 어긋난 것
    fix: str  # 고치는 방법


def health_problems(status: int | None, *, backend_url: str) -> list[PreflightProblem]:
    """백엔드의 `GET /api/health`가 200인지. status가 None이면 닿지 못한 것이다."""
    raise NotImplementedError


def login_redirect_problems(
    status: int | None, location: str | None, *, frontend_url: str
) -> list[PreflightProblem]:
    """`GET /api/auth/google/login`의 Location에서 redirect_uri와 client_id를 확인한다."""
    raise NotImplementedError


def frontend_port_problems(frontend_url: str, *, in_use: bool) -> list[PreflightProblem]:
    """대역 서버가 뜰 `FRONTEND_URL`의 포트가 비어 있는지."""
    raise NotImplementedError


def port_in_use(host: str, port: int) -> bool:
    """그 주소에 무엇인가가 연결을 받고 있으면 True."""
    raise NotImplementedError


# --- 데이터베이스의 상태 ---------------------------------------------------------------------


@dataclass(frozen=True)
class AllowedRow:
    email: str
    role: str
    created_at: datetime


@dataclass(frozen=True)
class UserRow:
    id: uuid.UUID
    email: str
    google_sub: str
    display_name: str | None
    created_at: datetime


@dataclass(frozen=True)
class SessionRow:
    """login_sessions의 행. user_email은 users와 이어서 읽은 그 사람의 이메일이다.

    token_hash는 쿠키 값의 SHA-256과 같은지 판정하는 데에만 쓰고 출력하지 않는다. repr에도 넣지
    않는다.
    """

    token_hash: str = field(repr=False)
    user_id: uuid.UUID
    user_email: str
    expires_at: datetime
    created_at: datetime


@dataclass(frozen=True)
class DbState:
    """한 시점의 세 테이블.

    행은 두 계정의 이메일에 관한 것만 담고, session_total은 login_sessions의 전체 행의 수다.
    """

    allowed: tuple[AllowedRow, ...]
    users: tuple[UserRow, ...]
    sessions: tuple[SessionRow, ...]
    session_total: int

    def allowed_for(self, email: str) -> tuple[AllowedRow, ...]:
        return tuple(row for row in self.allowed if row.email.lower() == email.lower())

    def users_for(self, email: str) -> tuple[UserRow, ...]:
        return tuple(row for row in self.users if row.email.lower() == email.lower())

    def sessions_for(self, email: str) -> tuple[SessionRow, ...]:
        return tuple(row for row in self.sessions if row.user_email.lower() == email.lower())


@dataclass(frozen=True)
class PrecheckProblem:
    problem: str  # 맞지 않는 조건
    fix_sql: str  # 그것을 맞추는 SQL. README의 SQL과 같은 꼴(이메일을 lower()로 감쌈)


async def connect_read_only(database_url: str) -> asyncpg.Connection:
    """모든 트랜잭션이 읽기 전용인 연결. 이 연결로는 어떤 행도 바꿀 수 없다."""
    raise NotImplementedError


async def read_db_state(conn: asyncpg.Connection, *, emails: Sequence[str]) -> DbState:
    """두 계정의 이메일에 관한 세 테이블의 행과 login_sessions의 전체 행 수를 한 번에 읽는다."""
    raise NotImplementedError


def precheck_problems(
    state: DbState, *, allowed_email: str, denied_email: str
) -> list[PrecheckProblem]:
    """testcase.md 두 표의 "로그인 전" 줄과 다른 조건. 모두 맞으면 빈 목록이다."""
    raise NotImplementedError


async def precheck(
    database_url: str, *, allowed_email: str, denied_email: str
) -> list[PrecheckProblem]:
    """점검 전 상태 확인(TC-1.7.2). 데이터베이스를 읽기만 하고, 맞추는 SQL은 실행하지 않는다."""
    raise NotImplementedError


# --- 브라우저의 상태 -------------------------------------------------------------------------


@dataclass(frozen=True)
class CookieState:
    """쿠키 하나. 값은 담지 않고 그 SHA-256만 담는다(repr에도 넣지 않는다)."""

    name: str
    path: str
    http_only: bool
    secure: bool
    same_site: str
    value_sha256: str = field(repr=False)


@dataclass(frozen=True)
class FetchResult:
    """브라우저 안에서 부른 요청의 결과. body는 JSON 객체로 읽혔을 때만 있다."""

    status: int
    body: dict[str, object] | None


@dataclass(frozen=True)
class BrowserState:
    url: str
    cookies: tuple[CookieState, ...]
    me: FetchResult | None = None
    logout_status: int | None = None

    def cookies_named(self, name: str) -> tuple[CookieState, ...]:
        return tuple(cookie for cookie in self.cookies if cookie.name == name)


@dataclass(frozen=True)
class Snapshot:
    db: DbState
    browser: BrowserState


def frontend_cookies(raw: Iterable[Mapping[str, object]], *, host: str) -> tuple[CookieState, ...]:
    """Playwright가 돌려준 쿠키 가운데 프론트엔드 주소의 것만, 값을 SHA-256으로 바꿔 담는다."""
    raise NotImplementedError


def fetch_result(status: int, text: str) -> FetchResult:
    raise NotImplementedError


def returned_to_frontend(url: str, frontend_url: str) -> bool:
    """Google에서 프론트엔드의 화면(`/api` 밖의 경로)으로 돌아왔는지."""
    raise NotImplementedError


# --- 표와의 대조 -----------------------------------------------------------------------------


def judge_allowed_before_login(now: Snapshot, *, email: str) -> list[str]:
    """점검 1의 로그인 전."""
    raise NotImplementedError


def judge_allowed_after_login(
    now: Snapshot, *, before: Snapshot, email: str, login_at: datetime, frontend_url: str
) -> list[str]:
    """점검 1의 로그인 후."""
    raise NotImplementedError


def judge_allowed_before_logout(now: Snapshot, *, after_login: Snapshot, email: str) -> list[str]:
    """점검 1의 로그아웃 전."""
    raise NotImplementedError


def judge_allowed_after_logout(now: Snapshot, *, before_logout: Snapshot, email: str) -> list[str]:
    """점검 1의 로그아웃 후."""
    raise NotImplementedError


def judge_denied_before_login(now: Snapshot, *, email: str) -> list[str]:
    """점검 2의 로그인 전."""
    raise NotImplementedError


def judge_denied_after_attempt(
    now: Snapshot, *, before: Snapshot, email: str, frontend_url: str
) -> list[str]:
    """점검 2의 로그인 시도 후."""
    raise NotImplementedError


# --- 출력 ------------------------------------------------------------------------------------


def render_snapshot(
    title: str, snapshot: Snapshot, *, allowed_email: str, denied_email: str
) -> str:
    """한 시점의 세 테이블과 브라우저의 상태. 쿠키의 값과 token_hash의 값은 출력하지 않는다."""
    raise NotImplementedError


def render_preflight(problems: Sequence[PreflightProblem]) -> str:
    raise NotImplementedError


def render_report(mismatches: Sequence[str]) -> str:
    raise NotImplementedError
