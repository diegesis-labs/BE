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

import argparse
import asyncio
import hashlib
import html
import http.client
import json
import os
import socket
import sys
import threading
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self
from urllib.parse import parse_qs, urlsplit

import asyncpg

if TYPE_CHECKING:
    # 타입 확인에만 쓴다. Playwright는 브라우저를 모는 층이 부를 때에만 불러온다.
    from playwright.async_api import Browser, BrowserContext, Page

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
# 브라우저를 열기 전에 백엔드를 부를 때 기다리는 시간.
PREFLIGHT_TIMEOUT_SECONDS = 5

# compose.yaml의 기본값과 db 서비스의 로컬 전용 계정.
DEFAULT_FRONTEND_URL = "http://localhost:5173"
DEFAULT_API_PORT = 8080
DEFAULT_DB_PORT = 5432
DB_LOGIN = "diegesis:diegesis"
DB_NAME = "diegesis"
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1"})

# compose가 `${...}`를 채우려고 읽는 파일. compose.yaml과 같은 폴더(레포 최상위)에 있다.
DOTENV_PATH = Path(__file__).resolve().parents[1] / ".env"

EXIT_OK = 0
EXIT_MISMATCH = 1
EXIT_PREFLIGHT = 3
EXIT_ABORTED = 4

COMPOSE_UP = "docker compose up --build -d --wait"
PSQL = "docker compose exec db psql -U diegesis -d diegesis"


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
        return f"postgresql://{DB_LOGIN}@localhost:{self.db_port}/{DB_NAME}"


def parse_dotenv(text: str) -> dict[str, str]:
    """`.env`의 `이름=값` 줄을 읽는다. 빈 줄과 `#`으로 시작하는 줄은 건너뛴다.

    값을 따옴표로 감쌌으면 따옴표를 벗기고, 감싸지 않았으면 ` #` 뒤의 줄 끝 주석을 뺀다.
    """
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").lstrip()
        name, sep, value = line.partition("=")
        name, value = name.strip(), value.strip()
        if not sep or not name:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        else:
            value = value.split(" #", 1)[0].rstrip()
        values[name] = value
    return values


def _compose_value(
    name: str, environ: Mapping[str, str], dotenv: Mapping[str, str], default: str
) -> str:
    # compose는 셸의 환경변수를 `.env`보다 먼저 보고, `${이름:-기본값}`은 비어 있는 값도
    # 기본값으로 바꾼다.
    value = environ[name] if name in environ else dotenv.get(name, "")
    return value or default


def _port(name: str, value: str) -> int:
    if not value.isdigit() or not 0 < int(value) < 65536:
        raise ValueError(f"{name}는 1부터 65535까지의 포트 번호여야 한다: {value!r}")
    return int(value)


def resolve_settings(environ: Mapping[str, str], dotenv: Mapping[str, str]) -> CheckSettings:
    """compose의 `${이름:-기본값}`과 같은 방법으로 세 값을 정한다. 값이 잘못됐으면 ValueError.

    `FRONTEND_URL`은 대역 서버가 이 컴퓨터에서 받을 주소이므로 `http://localhost:포트`나
    `http://127.0.0.1:포트` 꼴이어야 한다.
    """
    frontend_url = _compose_value("FRONTEND_URL", environ, dotenv, DEFAULT_FRONTEND_URL)
    parts = urlsplit(frontend_url)
    try:
        _ = parts.port
    except ValueError as error:
        raise ValueError(f"FRONTEND_URL의 포트를 읽지 못했다: {frontend_url!r}") from error
    if (
        parts.scheme != "http"
        or parts.hostname not in LOCAL_HOSTS
        or parts.username is not None
        or parts.path
        or parts.query
        or parts.fragment
    ):
        raise ValueError(
            "로컬 점검의 FRONTEND_URL은 http://localhost:포트나 http://127.0.0.1:포트 꼴이어야 "
            f"한다: {frontend_url!r}"
        )
    return CheckSettings(
        frontend_url=frontend_url,
        api_port=_port("API_PORT", _compose_value("API_PORT", environ, dotenv, "8080")),
        db_port=_port("DB_PORT", _compose_value("DB_PORT", environ, dotenv, "5432")),
    )


@dataclass(frozen=True)
class Args:
    allowed_email: str
    denied_email: str


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="login_check.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "실제 Google 계정 두 개로 로컬의 로그인과 로그아웃을 점검한다(ADR-026).\n"
            "compose로 띄운 서버 앞에 프론트엔드 대역 서버를 띄우고, 화면이 보이는 브라우저를\n"
            "연다. "
            "사람은 브라우저의 Google 화면에서 안내받은 계정을 고르기만 한다.\n"
            "시점마다 세 테이블과 브라우저의 상태를 출력하고, testcase.md의 표와 대조한다."
        ),
        epilog=(
            "FRONTEND_URL, API_PORT, DB_PORT는 환경변수, 레포 최상위의 .env, compose의 기본값의\n"
            "순서로 정한다.\n\n"
            "종료 코드:\n"
            "  0  모든 시점의 상태가 표와 같다.\n"
            "  1  표와 다른 것이 있다.\n"
            "  2  명령의 인자가 잘못됐다.\n"
            "  3  브라우저를 열기 전의 확인이 어긋났다. 고치는 방법을 보여 준다.\n"
            "  4  점검을 끝내지 못했다(기다리는 시간이 지났거나 브라우저가 닫혔다)."
        ),
    )
    parser.add_argument(
        "--allowed-email",
        required=True,
        metavar="EMAIL",
        help="허용 목록에 user로 넣은 Google 계정 A의 이메일",
    )
    parser.add_argument(
        "--denied-email",
        required=True,
        metavar="EMAIL",
        help="허용 목록에 없는 Google 계정 B의 이메일",
    )
    return parser


def parse_args(argv: Sequence[str] | None = None) -> Args:
    """명령의 인자. 이메일은 소문자로 바꾼다."""
    parser = _parser()
    namespace = parser.parse_args(argv)
    allowed = str(namespace.allowed_email).strip().lower()
    denied = str(namespace.denied_email).strip().lower()
    if not allowed or not denied:
        parser.error("두 계정의 이메일이 비어 있으면 안 된다.")
    if allowed == denied:
        parser.error("--allowed-email과 --denied-email은 서로 다른 계정이어야 한다.")
    return Args(allowed_email=allowed, denied_email=denied)


# --- 브라우저를 열기 전의 확인 ---------------------------------------------------------------


@dataclass(frozen=True)
class PreflightProblem:
    problem: str  # 어긋난 것
    fix: str  # 고치는 방법


def health_problems(status: int | None, *, backend_url: str) -> list[PreflightProblem]:
    """백엔드의 `GET /api/health`가 200인지. status가 None이면 닿지 못한 것이다."""
    if status == 200:
        return []
    seen = "닿지 못함" if status is None else f"응답: {status}"
    return [
        PreflightProblem(
            problem=f"백엔드({backend_url})의 GET {HEALTH_PATH}가 200이 아니다({seen}).",
            fix=(
                f"README의 '로컬에서 서버 띄우기'대로 compose로 서버를 띄운다({COMPOSE_UP}). "
                "API_PORT를 바꿔서 띄웠다면 같은 값을 이 스크립트에도 준다(환경변수나 .env)."
            ),
        )
    ]


def login_redirect_problems(
    status: int | None, location: str | None, *, frontend_url: str
) -> list[PreflightProblem]:
    """`GET /api/auth/google/login`의 Location에서 redirect_uri와 client_id를 확인한다.

    서버와 이 스크립트의 `FRONTEND_URL`이 다르거나, `.env`에 Google 클라이언트의 값을 넣지 않고
    compose를 띄웠으면 Google 화면까지 가서야 실패하므로 브라우저를 열기 전에 본다. Location의
    나머지(state, nonce, code_challenge)는 보지도 출력하지도 않는다.
    """
    restart = f"고친 뒤에는 서버가 새 값을 받도록 compose로 다시 띄운다({COMPOSE_UP})."
    if status != 302 or not location:
        return [
            PreflightProblem(
                problem=(
                    f"백엔드의 GET {LOGIN_PATH}가 302와 Location을 돌려주지 않았다"
                    f"(응답: {status if status is not None else '닿지 못함'})."
                ),
                fix=f"서버의 로그(docker compose logs api)를 확인한다. {restart}",
            )
        ]
    query = parse_qs(urlsplit(location).query, keep_blank_values=True)
    problems: list[PreflightProblem] = []
    expected = frontend_url + CALLBACK_PATH
    redirect_uris = query.get("redirect_uri", [])
    if redirect_uris != [expected]:
        actual = ", ".join(redirect_uris) or "(없음)"
        problems.append(
            PreflightProblem(
                problem=(
                    "서버가 Google에 보내는 redirect_uri가 다르다"
                    f"(지금: {actual}, 기대한 값: {expected})."
                ),
                fix=(
                    "서버와 이 스크립트의 FRONTEND_URL이 다르다. 레포 최상위의 .env와 환경변수의 "
                    f"FRONTEND_URL을 {frontend_url}로 맞춘다. {restart}"
                ),
            )
        )
    client_ids = query.get("client_id", [])
    if len(client_ids) != 1 or not client_ids[0]:
        problems.append(
            PreflightProblem(
                problem="서버가 Google에 보내는 client_id가 비어 있다.",
                fix=(
                    "레포 최상위의 .env에 GOOGLE_CLIENT_ID와 GOOGLE_CLIENT_SECRET을 넣는다"
                    "(cp .env.example .env). compose는 이 두 값을 .env에서 서버에 넘긴다. "
                    f"{restart}"
                ),
            )
        )
    return problems


def frontend_port_problems(frontend_url: str, *, in_use: bool) -> list[PreflightProblem]:
    """대역 서버가 뜰 `FRONTEND_URL`의 포트가 비어 있는지."""
    if not in_use:
        return []
    return [
        PreflightProblem(
            problem=f"{frontend_url}에서 이미 다른 프로그램이 연결을 받고 있다.",
            fix=(
                "프론트엔드의 개발 서버가 떠 있으면 끈다. 대역 서버가 서버와 같은 "
                "FRONTEND_URL에 떠야 한다."
            ),
        )
    ]


def port_in_use(host: str, port: int) -> bool:
    """그 주소에 무엇인가가 연결을 받고 있으면 True.

    포트를 잡아 보지 않고 연결해 본다. `localhost`는 IPv4와 IPv6의 두 주소로 풀리므로, 한쪽에
    떠 있는 개발 서버도 찾기 위해서다.
    """
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


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


# 데이터베이스를 읽다가 날 수 있는 예외. 닿지 못함(OSError), 서버가 거부함(PostgresError), 그리고
# asyncpg가 서버와 말을 맞추지 못함(InterfaceError, InternalClientError)이다. 마지막 경우의 예는
# DB_PORT의 서버가 asyncpg가 지원하지 않는 인증이나 프로토콜을 쓸 때다. 뒤의 둘은 앞의 둘의 하위
# 클래스가 아니다(2차 리뷰 COR-1).
DATABASE_ERRORS: tuple[type[Exception], ...] = (
    OSError,
    asyncpg.PostgresError,
    asyncpg.InterfaceError,
    asyncpg.exceptions.InternalClientError,
)


async def connect_read_only(database_url: str) -> asyncpg.Connection:
    """모든 트랜잭션이 읽기 전용인 연결. 이 연결로는 어떤 행도 바꿀 수 없다.

    주소는 asyncpg 형식(`postgresql://`)과 SQLAlchemy 형식(`postgresql+asyncpg://`)을 모두 받는다.
    """
    dsn = database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    return await asyncpg.connect(
        dsn, timeout=10, server_settings={"default_transaction_read_only": "on"}
    )


async def read_db_state(conn: asyncpg.Connection, *, emails: Sequence[str]) -> DbState:
    """두 계정의 이메일에 관한 세 테이블의 행과 login_sessions의 전체 행 수를 한 번에 읽는다.

    네 질의를 읽기 전용 트랜잭션 하나(REPEATABLE READ)에서 돌려, 같은 시점의 상태를 본다.
    이메일은 소문자로 바꿔서 비교한다. 소문자가 아닌 행이 있어도 찾아서 판정이 보게 하기 위해서다.
    """
    lowered = sorted({email.lower() for email in emails})
    async with conn.transaction(isolation="repeatable_read", readonly=True):
        allowed = await conn.fetch(
            "SELECT email, role, created_at FROM allowed_emails "
            "WHERE lower(email) = ANY($1::text[]) ORDER BY email",
            lowered,
        )
        users = await conn.fetch(
            "SELECT id, email, google_sub, display_name, created_at FROM users "
            "WHERE lower(email) = ANY($1::text[]) ORDER BY email",
            lowered,
        )
        sessions = await conn.fetch(
            "SELECT s.token_hash, s.user_id, u.email, s.expires_at, s.created_at "
            "FROM login_sessions AS s JOIN users AS u ON u.id = s.user_id "
            "WHERE lower(u.email) = ANY($1::text[]) ORDER BY s.created_at, s.token_hash",
            lowered,
        )
        total = await conn.fetchval("SELECT count(*) FROM login_sessions")
    if not isinstance(total, int):
        raise TypeError(f"login_sessions의 행 수를 읽지 못했다: {total!r}")
    return DbState(
        allowed=tuple(AllowedRow(r["email"], r["role"], r["created_at"]) for r in allowed),
        users=tuple(
            UserRow(r["id"], r["email"], r["google_sub"], r["display_name"], r["created_at"])
            for r in users
        ),
        sessions=tuple(
            SessionRow(r["token_hash"], r["user_id"], r["email"], r["expires_at"], r["created_at"])
            for r in sessions
        ),
        session_total=total,
    )


async def read_state(database_url: str, *, emails: Sequence[str]) -> DbState:
    conn = await connect_read_only(database_url)
    try:
        return await read_db_state(conn, emails=emails)
    finally:
        await conn.close()


def _sql_email(email: str) -> str:
    return "lower('" + email.replace("'", "''") + "')"


def _allow_as_user_sql(email: str) -> str:
    # README의 "한 사람을 넣습니다. 이미 있으면 역할만 바꿉니다."와 같은 꼴.
    return (
        "INSERT INTO allowed_emails (email, role)\n"
        f"VALUES ({_sql_email(email)}, 'user')\n"
        "ON CONFLICT (email) DO UPDATE SET role = EXCLUDED.role;"
    )


def _remove_from_allowlist_sql(email: str) -> str:
    # README의 "한 사람을 뺍니다."와 같은 꼴.
    value = _sql_email(email)
    return (
        "BEGIN;\n"
        "DELETE FROM login_sessions\n"
        f"WHERE user_id IN (SELECT id FROM users WHERE email = {value});\n"
        f"DELETE FROM allowed_emails WHERE email = {value};\n"
        "COMMIT;"
    )


def _delete_user_sql(email: str) -> str:
    return (
        "-- 그 사람의 login_sessions 행도 함께 지워진다(ON DELETE CASCADE).\n"
        f"DELETE FROM users WHERE email = {_sql_email(email)};"
    )


def precheck_problems(
    state: DbState, *, allowed_email: str, denied_email: str
) -> list[PrecheckProblem]:
    """testcase.md 두 표의 "로그인 전" 줄과 다른 조건. 모두 맞으면 빈 목록이다.

    A가 허용 목록에 `user`로 있다, A의 `users` 행이 없다, B가 허용 목록에 없다, B의 `users` 행이
    없다. A의 `login_sessions` 행은 A의 `users` 행이 없으면 있을 수 없다(외래 키).
    """
    a, b = allowed_email.lower(), denied_email.lower()
    problems: list[PrecheckProblem] = []
    allowed_a = state.allowed_for(a)
    if not allowed_a:
        problems.append(
            PrecheckProblem(
                f"계정 A({a})가 허용 목록에 없다. user로 있어야 한다.", _allow_as_user_sql(a)
            )
        )
    elif allowed_a[0].role != "user":
        problems.append(
            PrecheckProblem(
                f"계정 A({a})의 허용 목록의 역할이 user가 아니다(지금: {allowed_a[0].role}).",
                _allow_as_user_sql(a),
            )
        )
    if state.users_for(a):
        problems.append(
            PrecheckProblem(
                f"계정 A({a})의 users 행이 있다. 로그인 전에는 없어야 한다.", _delete_user_sql(a)
            )
        )
    if state.allowed_for(b):
        problems.append(
            PrecheckProblem(
                f"계정 B({b})가 허용 목록에 있다. 없어야 한다.", _remove_from_allowlist_sql(b)
            )
        )
    if state.users_for(b):
        problems.append(
            PrecheckProblem(f"계정 B({b})의 users 행이 있다. 없어야 한다.", _delete_user_sql(b))
        )
    return problems


async def precheck(
    database_url: str, *, allowed_email: str, denied_email: str
) -> list[PrecheckProblem]:
    """점검 전 상태 확인(TC-1.7.2). 데이터베이스를 읽기만 하고, 맞추는 SQL은 실행하지 않는다."""
    state = await read_state(database_url, emails=(allowed_email, denied_email))
    return precheck_problems(state, allowed_email=allowed_email, denied_email=denied_email)


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


def _sha256(value: str) -> str:
    # 서버가 token_hash를 만드는 방법(SHA-256의 16진수 소문자)과 같다.
    return hashlib.sha256(value.encode()).hexdigest()


def frontend_cookies(raw: Iterable[Mapping[str, object]], *, host: str) -> tuple[CookieState, ...]:
    """Playwright가 돌려준 쿠키 가운데 프론트엔드 주소의 것만, 값을 SHA-256으로 바꿔 담는다.

    쿠키를 읽는 자리에서 바로 부른다. 값 자체는 돌려주는 것 어디에도 남지 않는다. Google의 쿠키는
    프론트엔드의 것이 아니므로 해시도 남기지 않는다.
    """
    return tuple(
        CookieState(
            name=str(cookie.get("name", "")),
            path=str(cookie.get("path", "")),
            http_only=bool(cookie.get("httpOnly")),
            secure=bool(cookie.get("secure")),
            same_site=str(cookie.get("sameSite", "")),
            value_sha256=_sha256(str(cookie.get("value", ""))),
        )
        for cookie in raw
        if str(cookie.get("domain", "")).lstrip(".") == host
    )


def fetch_result(status: int, text: str) -> FetchResult:
    try:
        body = json.loads(text) if text else None
    except ValueError:
        body = None
    return FetchResult(status=status, body=body if isinstance(body, dict) else None)


def returned_to_frontend(url: str, frontend_url: str) -> bool:
    """Google에서 프론트엔드의 화면(`/api` 밖의 경로)으로 돌아왔는지."""
    return url.startswith(frontend_url + "/") and not urlsplit(url).path.startswith(
        API_PREFIX + "/"
    )


def _display_url(url: str) -> str:
    # `/api` 아래의 주소(로그인 결과 처리)는 쿼리에 Google의 code와 state가 있으므로 쿼리를 뺀다.
    parts = urlsplit(url)
    if parts.path.startswith(API_PREFIX + "/") and parts.query:
        return f"{parts.scheme}://{parts.netloc}{parts.path}?(쿼리 생략)"
    return url


# --- 표와의 대조 -----------------------------------------------------------------------------
#
# 판정의 문장은 표의 칸 이름(allowed_emails, users, login_sessions, 브라우저)으로 시작한다. 쿠키의
# 값과 token_hash의 값은 문장에 넣지 않는다.


def _time(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def _row_text(row: AllowedRow | UserRow | SessionRow) -> str:
    match row:
        case AllowedRow():
            return f"{row.email} role={row.role} created_at={_time(row.created_at)}"
        case UserRow():
            return (
                f"{row.email} id={row.id} google_sub={row.google_sub} "
                f"display_name={row.display_name!r} created_at={_time(row.created_at)}"
            )
        case SessionRow():
            return (
                f"{row.user_email} user_id={row.user_id} created_at={_time(row.created_at)} "
                f"expires_at={_time(row.expires_at)}"
            )


def _rows_text(rows: Sequence[AllowedRow | UserRow | SessionRow]) -> str:
    return "; ".join(_row_text(row) for row in rows) or "행 없음"


def _token_hashes(rows: Sequence[AllowedRow | UserRow | SessionRow]) -> set[str]:
    return {row.token_hash for row in rows if isinstance(row, SessionRow)}


def _unchanged(
    column: str,
    previous: Sequence[AllowedRow | UserRow | SessionRow],
    now: Sequence[AllowedRow | UserRow | SessionRow],
    label: str,
) -> list[str]:
    """ "그대로입니다"의 칸. 바로 앞 시점과 값까지 같아야 한다."""
    if tuple(previous) == tuple(now):
        return []
    message = (
        f"{column}: {label} 시점과 같아야 하는데 다르다. "
        f"{label}: {_rows_text(previous)} / 지금: {_rows_text(now)}"
    )
    if _token_hashes(previous) != _token_hashes(now):
        message += " (token_hash가 다르다)"
    return [message]


def _no_cookies(browser: BrowserState) -> list[str]:
    if not browser.cookies:
        return []
    names = ", ".join(cookie.name for cookie in browser.cookies)
    return [f"브라우저: 쿠키가 없어야 하는데 {names}가 있다."]


def _no_cookie(browser: BrowserState, name: str) -> list[str]:
    if not browser.cookies_named(name):
        return []
    return [f"브라우저: {name} 쿠키가 있다. 없어야 한다."]


def _me_status(browser: BrowserState, expected: int) -> list[str]:
    if browser.me is None:
        return [f"브라우저: GET {ME_PATH}를 부르지 않았다."]
    if browser.me.status != expected:
        return [f"브라우저: GET {ME_PATH}가 {expected}가 아니다(지금: {browser.me.status})."]
    return []


def _url(browser: BrowserState, expected: str) -> list[str]:
    if browser.url == expected:
        return []
    return [f"브라우저: 주소가 {expected}가 아니다(지금: {_display_url(browser.url)})."]


def judge_allowed_before_login(now: Snapshot, *, email: str) -> list[str]:
    """점검 1의 로그인 전."""
    mismatches: list[str] = []
    allowed = now.db.allowed_for(email)
    if len(allowed) != 1:
        mismatches.append(f"allowed_emails: A의 행이 {len(allowed)}개다. 하나여야 한다.")
    elif allowed[0].role != "user":
        mismatches.append(f"allowed_emails: A의 role이 user가 아니다(지금: {allowed[0].role}).")
    if users := now.db.users_for(email):
        mismatches.append(f"users: A의 행이 {len(users)}개 있다. 없어야 한다.")
    if sessions := now.db.sessions_for(email):
        mismatches.append(f"login_sessions: A의 행이 {len(sessions)}개 있다. 없어야 한다.")
    mismatches += _no_cookies(now.browser)
    mismatches += _me_status(now.browser, 401)
    return mismatches


def judge_allowed_after_login(
    now: Snapshot, *, before: Snapshot, email: str, login_at: datetime, frontend_url: str
) -> list[str]:
    """점검 1의 로그인 후."""
    mismatches = _unchanged(
        "allowed_emails", before.db.allowed_for(email), now.db.allowed_for(email), "로그인 전"
    )

    users = now.db.users_for(email)
    if len(users) != 1:
        mismatches.append(f"users: A의 행이 {len(users)}개다. 하나가 생겨야 한다.")
    else:
        user = users[0]
        if user.email != email.lower():
            mismatches.append(
                f"users: email이 소문자의 {email.lower()}가 아니다(지금: {user.email})."
            )
        if not user.google_sub:
            mismatches.append("users: google_sub가 비어 있다.")
        if not user.display_name:
            mismatches.append("users: display_name이 비어 있다. A의 Google 이름이어야 한다.")
        if abs(user.created_at - login_at) > TIME_TOLERANCE:
            mismatches.append(
                "users: created_at이 방금이 아니다. 로그인한 시각"
                f"({_time(login_at)})과 1분 안이어야 한다(지금: {_time(user.created_at)})."
            )

    session_cookies = now.browser.cookies_named(SESSION_COOKIE)
    sessions = now.db.sessions_for(email)
    if len(sessions) != 1:
        mismatches.append(f"login_sessions: A의 행이 {len(sessions)}개다. 하나가 생겨야 한다.")
    else:
        session = sessions[0]
        if len(session_cookies) != 1:
            mismatches.append(
                f"login_sessions: {SESSION_COOKIE} 쿠키가 하나가 아니어서 token_hash를 "
                "대조하지 못했다."
            )
        elif session.token_hash != session_cookies[0].value_sha256:
            mismatches.append(
                f"login_sessions: token_hash가 {SESSION_COOKIE} 쿠키 값의 SHA-256과 다르다."
            )
        expected = login_at + LOGIN_SESSION_TTL
        if abs(session.expires_at - expected) > TIME_TOLERANCE:
            mismatches.append(
                "login_sessions: expires_at이 로그인한 시각에 336시간을 더한 시각"
                f"({_time(expected)})과 1분 안이어야 한다(지금: {_time(session.expires_at)})."
            )

    mismatches += _url(now.browser, frontend_url + "/")
    if len(session_cookies) != 1:
        mismatches.append(
            f"브라우저: {SESSION_COOKIE} 쿠키가 {len(session_cookies)}개다. 하나여야 한다."
        )
    else:
        cookie = session_cookies[0]
        if not cookie.http_only:
            mismatches.append(f"브라우저: {SESSION_COOKIE} 쿠키에 HttpOnly가 없다.")
        if cookie.same_site != "Lax":
            mismatches.append(
                f"브라우저: {SESSION_COOKIE} 쿠키의 SameSite가 Lax가 아니다"
                f"(지금: {cookie.same_site or '없음'})."
            )
        if cookie.path != "/":
            mismatches.append(
                f"브라우저: {SESSION_COOKIE} 쿠키의 Path가 /가 아니다(지금: {cookie.path})."
            )
        if cookie.secure:
            mismatches.append(
                f"브라우저: {SESSION_COOKIE} 쿠키에 Secure가 붙었다. http의 FRONTEND_URL에서는 "
                "붙지 않아야 한다."
            )
    mismatches += _no_cookie(now.browser, STATE_COOKIE)
    return mismatches


def judge_allowed_before_logout(now: Snapshot, *, after_login: Snapshot, email: str) -> list[str]:
    """점검 1의 로그아웃 전. 세 테이블은 로그인 후와 값까지 같아야 한다."""
    mismatches = [
        *_unchanged(
            "allowed_emails",
            after_login.db.allowed_for(email),
            now.db.allowed_for(email),
            "로그인 후",
        ),
        *_unchanged("users", after_login.db.users_for(email), now.db.users_for(email), "로그인 후"),
        *_unchanged(
            "login_sessions",
            after_login.db.sessions_for(email),
            now.db.sessions_for(email),
            "로그인 후",
        ),
    ]
    me = now.browser.me
    if me is None or me.status != 200:
        return mismatches + _me_status(now.browser, 200)
    body = me.body or {}
    if body.get("email") != email.lower():
        mismatches.append(
            f"브라우저: GET {ME_PATH}의 email이 A({email.lower()})가 아니다"
            f"(지금: {body.get('email')!r})."
        )
    if body.get("role") != "user":
        mismatches.append(
            f"브라우저: GET {ME_PATH}의 role이 user가 아니다(지금: {body.get('role')!r})."
        )
    users = now.db.users_for(email)
    if len(users) != 1:
        mismatches.append(
            f"브라우저: users에 A의 행이 하나가 아니어서 GET {ME_PATH}의 display_name을 "
            "대조하지 못했다."
        )
    elif body.get("display_name") != users[0].display_name:
        mismatches.append(
            f"브라우저: GET {ME_PATH}의 display_name이 users.display_name과 다르다"
            f"(지금: {body.get('display_name')!r}, users: {users[0].display_name!r})."
        )
    return mismatches


def judge_allowed_after_logout(now: Snapshot, *, before_logout: Snapshot, email: str) -> list[str]:
    """점검 1의 로그아웃 후."""
    mismatches = [
        *_unchanged(
            "allowed_emails",
            before_logout.db.allowed_for(email),
            now.db.allowed_for(email),
            "로그아웃 전",
        ),
        *_unchanged(
            "users", before_logout.db.users_for(email), now.db.users_for(email), "로그아웃 전"
        ),
    ]
    if sessions := now.db.sessions_for(email):
        mismatches.append(f"login_sessions: A의 행이 {len(sessions)}개 남아 있다. 없어야 한다.")
    if now.browser.logout_status is None:
        mismatches.append(f"브라우저: 로그아웃(POST {LOGOUT_PATH})을 부르지 않았다.")
    elif now.browser.logout_status != 204:
        mismatches.append(
            f"브라우저: 로그아웃의 응답이 204가 아니다(지금: {now.browser.logout_status})."
        )
    mismatches += _no_cookie(now.browser, SESSION_COOKIE)
    mismatches += _me_status(now.browser, 401)
    return mismatches


def judge_denied_before_login(now: Snapshot, *, email: str) -> list[str]:
    """점검 2의 로그인 전. login_sessions는 전체 행의 수를 기록하기만 한다."""
    mismatches: list[str] = []
    if allowed := now.db.allowed_for(email):
        mismatches.append(f"allowed_emails: B의 행이 {len(allowed)}개 있다. 없어야 한다.")
    if users := now.db.users_for(email):
        mismatches.append(f"users: B의 행이 {len(users)}개 있다. 없어야 한다.")
    mismatches += _no_cookies(now.browser)
    return mismatches


def judge_denied_after_attempt(
    now: Snapshot, *, before: Snapshot, email: str, frontend_url: str
) -> list[str]:
    """점검 2의 로그인 시도 후."""
    mismatches = [
        *_unchanged(
            "allowed_emails", before.db.allowed_for(email), now.db.allowed_for(email), "로그인 전"
        ),
        *_unchanged("users", before.db.users_for(email), now.db.users_for(email), "로그인 전"),
    ]
    if now.db.session_total != before.db.session_total:
        mismatches.append(
            "login_sessions: 전체 행의 수가 로그인 전과 다르다"
            f"(로그인 전: {before.db.session_total}, 지금: {now.db.session_total})."
        )
    mismatches += _url(now.browser, frontend_url + NOT_ALLOWED_PATH)
    mismatches += _no_cookie(now.browser, SESSION_COOKIE)
    mismatches += _no_cookie(now.browser, STATE_COOKIE)
    mismatches += _me_status(now.browser, 401)
    return mismatches


# --- 출력 ------------------------------------------------------------------------------------


def _token_relation(session: SessionRow, browser: BrowserState) -> str:
    cookies = browser.cookies_named(SESSION_COOKIE)
    if len(cookies) != 1:
        return f"token_hash는 대조하지 않음({SESSION_COOKIE} 쿠키가 {len(cookies)}개)"
    if session.token_hash == cookies[0].value_sha256:
        return f"token_hash는 {SESSION_COOKIE} 쿠키 값의 SHA-256과 같다"
    return f"token_hash는 {SESSION_COOKIE} 쿠키 값의 SHA-256과 다르다"


def _cookie_text(cookie: CookieState) -> str:
    flags = [f"Path={cookie.path}", f"SameSite={cookie.same_site or '(없음)'}"]
    flags.append("HttpOnly" if cookie.http_only else "HttpOnly 없음")
    flags.append("Secure" if cookie.secure else "Secure 없음")
    return f"{cookie.name}: " + ", ".join(flags)


def render_snapshot(
    title: str, snapshot: Snapshot, *, allowed_email: str, denied_email: str
) -> str:
    """한 시점의 세 테이블과 브라우저의 상태. 쿠키의 값과 token_hash의 값은 출력하지 않는다."""
    db, browser = snapshot.db, snapshot.browser
    accounts = (("A", allowed_email), ("B", denied_email))
    lines = [f"=== {title}", "allowed_emails"]
    for label, email in accounts:
        lines.append(f"  {label} {email}: {_rows_text(db.allowed_for(email))}")
    lines.append("users")
    for label, email in accounts:
        lines.append(f"  {label} {email}: {_rows_text(db.users_for(email))}")
    lines.append(f"login_sessions (전체 {db.session_total}행)")
    for label, email in accounts:
        sessions = db.sessions_for(email)
        if not sessions:
            lines.append(f"  {label} {email}: 행 없음")
        for session in sessions:
            relation = _token_relation(session, browser)
            lines.append(f"  {label} {_row_text(session)}, {relation}")
    lines.append("브라우저")
    lines.append(f"  주소: {_display_url(browser.url)}")
    if browser.cookies:
        lines.append("  쿠키:")
        lines.extend(f"    {_cookie_text(cookie)}" for cookie in browser.cookies)
    else:
        lines.append("  쿠키: 없음")
    if browser.me is not None:
        body = json.dumps(browser.me.body, ensure_ascii=False) if browser.me.body else ""
        lines.append(f"  GET {ME_PATH}: {browser.me.status} {body}".rstrip())
    if browser.logout_status is not None:
        lines.append(f"  POST {LOGOUT_PATH}: {browser.logout_status}")
    return "\n".join(lines)


def render_preflight(problems: Sequence[PreflightProblem]) -> str:
    lines = ["브라우저를 열기 전의 확인에서 어긋난 것이 있어, 브라우저를 열지 않고 끝낸다.", ""]
    for number, problem in enumerate(problems, start=1):
        lines.append(f"{number}. {problem.problem}")
        lines.append("   고치는 방법:")
        lines.extend(f"     {line}" for line in problem.fix.splitlines())
        lines.append("")
    return "\n".join(lines).rstrip()


def render_report(mismatches: Sequence[str]) -> str:
    if not mismatches:
        return "=== 결과\n모든 시점의 상태가 testcase.md의 표와 같다."
    lines = [f"=== 결과\ntestcase.md의 표와 다른 것이 {len(mismatches)}개 있다."]
    lines.extend(f"- {mismatch}" for mismatch in mismatches)
    return "\n".join(lines)


# --- 브라우저를 모는 층 ----------------------------------------------------------------------
#
# 아래는 위의 순수 함수들을 부르기만 한다. 판정과 출력의 규칙을 여기에 두지 않는다.


class CheckAbortedError(Exception):
    """점검을 끝내지 못했다. 메시지는 사람에게 보여 줄 안내다."""


def _http_get(backend_url: str, path: str) -> tuple[int, str | None] | None:
    """백엔드에 GET을 보내 상태 코드와 Location을 돌려준다. 닿지 못하면 None.

    리디렉션을 따라가지 않는다. 응답의 Set-Cookie와 본문은 읽기만 하고 버린다.
    """
    parts = urlsplit(backend_url)
    conn = http.client.HTTPConnection(
        parts.hostname or "localhost", parts.port or 80, timeout=PREFLIGHT_TIMEOUT_SECONDS
    )
    try:
        conn.request("GET", path)
        response = conn.getresponse()
        response.read()
        return response.status, response.getheader("Location")
    except OSError, http.client.HTTPException:
        return None
    finally:
        conn.close()


async def preflight(settings: CheckSettings, args: Args) -> list[PreflightProblem]:
    """브라우저를 열기 전의 네 확인. 서버가 응답하지 않으면 나머지는 보지 않는다."""
    health = _http_get(settings.backend_url, HEALTH_PATH)
    problems = health_problems(health[0] if health else None, backend_url=settings.backend_url)
    if problems:
        return problems

    login = _http_get(settings.backend_url, LOGIN_PATH)
    problems += login_redirect_problems(
        login[0] if login else None,
        login[1] if login else None,
        frontend_url=settings.frontend_url,
    )

    try:
        found = await precheck(
            settings.database_url,
            allowed_email=args.allowed_email,
            denied_email=args.denied_email,
        )
    except DATABASE_ERRORS as error:
        problems.append(
            PreflightProblem(
                problem=(
                    f"개발용 데이터베이스(localhost:{settings.db_port})를 읽지 못했다: "
                    f"{type(error).__name__}"
                ),
                fix=(
                    f"compose로 띄웠는지 확인한다({COMPOSE_UP}). DB_PORT를 바꿔서 띄웠다면 "
                    "같은 값을 이 스크립트에도 준다(환경변수나 .env)."
                ),
            )
        )
    else:
        problems += [
            PreflightProblem(
                problem=item.problem,
                fix=(
                    "아래 SQL을 실행한다. 스크립트는 실행하지 않는다. "
                    f"접속은 {PSQL}\n{item.fix_sql}"
                ),
            )
            for item in found
        ]

    problems += frontend_port_problems(
        settings.frontend_url,
        in_use=port_in_use(settings.frontend_host, settings.frontend_port),
    )
    return problems


FETCH_SCRIPT = """
async ([path, method]) => {
  const response = await fetch(path, { method, credentials: 'include' });
  return { status: response.status, body: await response.text() };
}
"""


async def _fetch(page: Page, path: str, method: str = "GET") -> FetchResult:
    """프론트엔드가 하는 대로 브라우저 안에서 `credentials: 'include'`로 부른다."""
    result = await page.evaluate(FETCH_SCRIPT, [path, method])
    return fetch_result(int(result["status"]), str(result["body"]))


async def _browser_state(
    page: Page,
    context: BrowserContext,
    settings: CheckSettings,
    *,
    me: FetchResult | None = None,
    logout_status: int | None = None,
) -> BrowserState:
    # 쿠키를 읽는 자리에서 바로 해시로 바꾼다. 값은 이 줄을 벗어나지 않는다.
    cookies = frontend_cookies(await context.cookies(), host=settings.frontend_host)
    return BrowserState(url=page.url, cookies=cookies, me=me, logout_status=logout_status)


async def _snapshot(
    page: Page,
    context: BrowserContext,
    settings: CheckSettings,
    args: Args,
    *,
    me: FetchResult | None = None,
    logout_status: int | None = None,
) -> Snapshot:
    db = await read_state(settings.database_url, emails=(args.allowed_email, args.denied_email))
    browser = await _browser_state(page, context, settings, me=me, logout_status=logout_status)
    return Snapshot(db=db, browser=browser)


async def _log_in(page: Page, settings: CheckSettings, *, label: str, email: str) -> datetime:
    """프론트엔드가 하는 대로 화면을 로그인 시작 주소로 옮기고, 돌아올 때까지 기다린다."""
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError

    await page.goto(settings.frontend_url + LOGIN_PATH, wait_until="commit")
    print(
        f"\n>>> 브라우저의 Google 화면에서 계정 {label}({email})를 고르세요. 비밀번호를 물으면 "
        f"브라우저에서 직접 넣습니다. 최대 {LOGIN_WAIT_SECONDS // 60}분 기다립니다.",
        flush=True,
    )
    try:
        await page.wait_for_url(
            lambda url: returned_to_frontend(url, settings.frontend_url),
            timeout=LOGIN_WAIT_SECONDS * 1000,
        )
    except PlaywrightTimeoutError:
        raise CheckAbortedError(
            f"{LOGIN_WAIT_SECONDS // 60}분 안에 {settings.frontend_url}로 돌아오지 않았다. "
            "Google이 자동화된 브라우저의 로그인을 막았을 수 있다. 그 경우의 방법은 "
            "docs/ADR.md의 ADR-026 재검토 조건에 따라 사람이 정한다."
        ) from None
    return datetime.now(UTC)


def _report(title: str, snapshot: Snapshot, args: Args) -> None:
    print(
        "\n"
        + render_snapshot(
            title, snapshot, allowed_email=args.allowed_email, denied_email=args.denied_email
        ),
        flush=True,
    )


def _tagged(title: str, mismatches: list[str]) -> list[str]:
    return [f"[{title}] {mismatch}" for mismatch in mismatches]


async def _check_allowed(browser: Browser, settings: CheckSettings, args: Args) -> list[str]:
    """점검 1: 허용된 계정 A의 로그인과 로그아웃 (TC-1.7.3)."""
    email = args.allowed_email
    context = await browser.new_context()
    try:
        page = await context.new_page()
        await page.goto(settings.frontend_url + "/")

        title = "점검 1 · 로그인 전"
        before = await _snapshot(page, context, settings, args, me=await _fetch(page, ME_PATH))
        _report(title, before, args)
        mismatches = _tagged(title, judge_allowed_before_login(before, email=email))

        login_at = await _log_in(page, settings, label="A", email=email)
        title = "점검 1 · 로그인 후"
        after_login = await _snapshot(page, context, settings, args)
        _report(title, after_login, args)
        mismatches += _tagged(
            title,
            judge_allowed_after_login(
                after_login,
                before=before,
                email=email,
                login_at=login_at,
                frontend_url=settings.frontend_url,
            ),
        )

        # 두 시점 사이에는 GET /api/me를 한 번 부른 것만 있다.
        title = "점검 1 · 로그아웃 전"
        me = await _fetch(page, ME_PATH)
        before_logout = await _snapshot(page, context, settings, args, me=me)
        _report(title, before_logout, args)
        mismatches += _tagged(
            title, judge_allowed_before_logout(before_logout, after_login=after_login, email=email)
        )

        title = "점검 1 · 로그아웃 후"
        logout = await _fetch(page, LOGOUT_PATH, "POST")
        me = await _fetch(page, ME_PATH)
        after_logout = await _snapshot(
            page, context, settings, args, me=me, logout_status=logout.status
        )
        _report(title, after_logout, args)
        mismatches += _tagged(
            title,
            judge_allowed_after_logout(after_logout, before_logout=before_logout, email=email),
        )
        return mismatches
    finally:
        await context.close()


async def _check_denied(browser: Browser, settings: CheckSettings, args: Args) -> list[str]:
    """점검 2: 허용 목록 밖 계정 B의 로그인 시도 (TC-1.7.4)."""
    email = args.denied_email
    context = await browser.new_context()
    try:
        page = await context.new_page()
        await page.goto(settings.frontend_url + "/")

        title = "점검 2 · 로그인 전"
        before = await _snapshot(page, context, settings, args)
        _report(title, before, args)
        mismatches = _tagged(title, judge_denied_before_login(before, email=email))

        await _log_in(page, settings, label="B", email=email)
        title = "점검 2 · 로그인 시도 후"
        after = await _snapshot(page, context, settings, args, me=await _fetch(page, ME_PATH))
        _report(title, after, args)
        mismatches += _tagged(
            title,
            judge_denied_after_attempt(
                after, before=before, email=email, frontend_url=settings.frontend_url
            ),
        )
        return mismatches
    finally:
        await context.close()


async def run_checks(settings: CheckSettings, args: Args) -> list[str]:
    """대역 서버와 화면이 보이는 브라우저를 띄워 두 점검을 차례로 하고, 표와 다른 것을 모은다."""
    from playwright.async_api import Error as PlaywrightError
    from playwright.async_api import async_playwright

    stand_in = FrontendStandIn(
        listen_host=settings.frontend_host,
        listen_port=settings.frontend_port,
        backend_url=settings.backend_url,
    )
    try:
        stand_in.start()
    except OSError as error:
        raise CheckAbortedError(
            f"대역 서버를 {settings.frontend_url}에 띄우지 못했다: {type(error).__name__}. "
            "프론트엔드의 개발 서버가 떠 있으면 끈다."
        ) from None
    try:
        async with async_playwright() as playwright:
            try:
                # 점검마다 새 컨텍스트를 만들고, 프로필을 디스크에 남기지 않는다.
                browser = await playwright.chromium.launch(headless=False)
            except PlaywrightError:
                raise CheckAbortedError(
                    "Chromium을 열지 못했다. 처음 한 번 `uv run playwright install chromium`으로 "
                    "브라우저를 설치한다."
                ) from None
            try:
                return [
                    *await _check_allowed(browser, settings, args),
                    *await _check_denied(browser, settings, args),
                ]
            finally:
                await browser.close()
    except PlaywrightError as error:
        # 메시지에는 결과 처리의 주소(code와 state)가 들어 있을 수 있으므로 종류만 보여 준다.
        raise CheckAbortedError(
            f"브라우저가 닫혔거나 Playwright가 실패했다: {type(error).__name__}"
        ) from None
    except DATABASE_ERRORS as error:
        raise CheckAbortedError(
            f"점검 중에 개발용 데이터베이스를 읽지 못했다: {type(error).__name__}"
        ) from None
    finally:
        stand_in.stop()


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        dotenv = (
            parse_dotenv(DOTENV_PATH.read_text(encoding="utf-8")) if DOTENV_PATH.exists() else {}
        )
        settings = resolve_settings(os.environ, dotenv)
    except (OSError, ValueError) as error:
        print(f"설정을 읽지 못했다: {error}", file=sys.stderr)
        return EXIT_PREFLIGHT

    print(
        f"FRONTEND_URL={settings.frontend_url}, 백엔드={settings.backend_url}, "
        f"데이터베이스=localhost:{settings.db_port}",
        flush=True,
    )
    problems = asyncio.run(preflight(settings, args))
    if problems:
        print(render_preflight(problems), file=sys.stderr)
        return EXIT_PREFLIGHT

    try:
        mismatches = asyncio.run(run_checks(settings, args))
    except CheckAbortedError as error:
        print(f"\n점검을 끝내지 못했다. {error}", file=sys.stderr)
        return EXIT_ABORTED

    print("\n" + render_report(mismatches))
    return EXIT_MISMATCH if mismatches else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
