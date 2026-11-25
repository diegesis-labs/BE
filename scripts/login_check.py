"""로컬 로그인 점검 스크립트.

백엔드 담당자가 프론트엔드 레포 없이, 로컬에서 실제 Google 계정으로 로그인과 로그아웃을 끝까지
확인하는 도구다(docs/ADR.md의 ADR-026, docs/backlog/epic-1/E1-login-allowlist.md의 S1.7).

사람이 phase의 MANUAL 점검에서 실행한다. 실제 Google 계정과 사람의 입력이 필요하므로
`scripts/check.sh`와 CI에서는 실행하지 않는다. 검사가 확인하는 것은 Google 없이 확인할 수 있는
부분뿐이며, 그 테스트는 `tests/infra/test_login_check.py`에 있다.

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
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Self
from urllib.parse import urlsplit

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
