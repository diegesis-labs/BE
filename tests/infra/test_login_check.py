"""`scripts/login_check.py`의 프론트엔드 대역 서버의 테스트 (TC-1.7.1).

받은 요청을 기록하는 가짜 백엔드를 무작위 포트에 띄우고, 그 앞에 대역 서버를 띄운 뒤 대역
서버로 요청을 보낸다. 가짜 백엔드가 받은 것과 대역 서버가 돌려준 것을, 이 테스트가 보낸 것과
가짜 백엔드가 보낸 것에 견준다. 네트워크는 이 컴퓨터 안(`127.0.0.1`)만 쓰고, 실제 백엔드와
compose는 띄우지 않는다.

요청을 보내는 쪽은 `http.client`를 직접 쓴다. 리디렉션을 따라가지 않고, 이 테스트가 적은 헤더
말고는 아무것도 더하지 않으므로(`skip_host`, `skip_accept_encoding`), 대역 서버가 받은 헤더가
정확히 무엇인지 이 테스트가 안다.
"""

import ast
import http.client
import socket
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from scripts.login_check import FrontendStandIn

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "login_check.py"
CHECK_SCRIPT = REPO_ROOT / "scripts" / "check.sh"
WORKFLOWS = REPO_ROOT / ".github" / "workflows"

LOOPBACK = "127.0.0.1"
FRONTEND_ORIGIN = "http://localhost:5173"
LOCATION = "http://example.invalid/after"
SET_COOKIES = ["a=1; Path=/", "b=; Max-Age=0; Path=/api/auth/google"]
BACKEND_BODY = b"moved"

Headers = list[tuple[str, str]]


@dataclass(frozen=True)
class Received:
    """가짜 백엔드가 받은 요청 하나."""

    method: str
    target: str
    headers: Headers
    body: bytes


@dataclass(frozen=True)
class Reply:
    """대역 서버에서 받은 응답 하나."""

    status: int
    headers: Headers
    body: bytes

    def all(self, name: str) -> list[str]:
        return [value for key, value in self.headers if key.lower() == name.lower()]


@dataclass
class FakeBackend:
    """받은 요청을 모두 기록하고, 어떤 요청에도 302와 `Set-Cookie` 두 개로 답하는 가짜 백엔드."""

    port: int
    location: str = LOCATION
    received: list[Received] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def url(self) -> str:
        return f"http://{LOOPBACK}:{self.port}"

    @property
    def netloc(self) -> str:
        return f"{LOOPBACK}:{self.port}"

    def requests(self) -> list[Received]:
        with self.lock:
            return list(self.received)


def make_backend_handler(backend: FakeBackend) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def handle_any(self) -> None:
            length = self.headers.get("Content-Length")
            body = self.rfile.read(int(length)) if length is not None else b""
            with backend.lock:
                backend.received.append(
                    Received(self.command, self.path, list(self.headers.items()), body)
                )
            self.send_response_only(302, "Found")
            self.send_header("Location", backend.location)
            for cookie in SET_COOKIES:
                self.send_header("Set-Cookie", cookie)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(BACKEND_BODY)))
            self.end_headers()
            self.wfile.write(BACKEND_BODY)

        do_GET = do_POST = handle_any

        def log_message(self, format: str, *args: object) -> None:
            return

    return Handler


@dataclass
class Running:
    backend: FakeBackend
    stand_in: FrontendStandIn


@pytest.fixture
def running() -> Iterator[Running]:
    backend = FakeBackend(port=0)
    server = ThreadingHTTPServer((LOOPBACK, 0), make_backend_handler(backend))
    backend.port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    stand_in = FrontendStandIn(listen_host=LOOPBACK, listen_port=0, backend_url=backend.url)
    stand_in.start()
    try:
        yield Running(backend, stand_in)
    finally:
        stand_in.stop()
        server.shutdown()
        server.server_close()
        thread.join()


def send(port: int, method: str, target: str, headers: Headers, body: bytes | None = None) -> Reply:
    """대역 서버에 요청 하나를 보낸다. 적은 헤더만 보내며, 리디렉션을 따라가지 않는다."""
    conn = http.client.HTTPConnection(LOOPBACK, port, timeout=10)
    try:
        conn.putrequest(method, target, skip_host=True, skip_accept_encoding=True)
        for name, value in headers:
            conn.putheader(name, value)
        conn.endheaders(body)
        response = conn.getresponse()
        return Reply(response.status, response.getheaders(), response.read())
    finally:
        conn.close()


def normalized(headers: Headers) -> list[tuple[str, str]]:
    """이름의 대소문자와 순서를 무시하고 견주기 위해, 이름을 소문자로 바꾸고 정렬한다."""
    return sorted((name.lower(), value) for name, value in headers)


def only(headers: Headers, name: str) -> str:
    values = [value for key, value in headers if key.lower() == name.lower()]
    assert len(values) == 1, f"{name} 헤더가 정확히 하나가 아니다: {values}"
    return values[0]


def callback_request(port: int) -> Headers:
    return [
        ("Host", f"{LOOPBACK}:{port}"),
        ("Accept", "text/html"),
        ("Cookie", "diegesis_session=c1; diegesis_oauth_state=s.n.v"),
    ]


LOGOUT_BODY = '{"reason": "테스트"}'.encode()


def logout_request(port: int) -> Headers:
    return [
        ("Host", f"{LOOPBACK}:{port}"),
        ("Origin", FRONTEND_ORIGIN),
        ("Referer", f"{FRONTEND_ORIGIN}/books/1?page=2"),
        ("Cookie", "diegesis_session=c1"),
        ("Content-Type", "application/json"),
        ("X-Requested-With", "fetch"),
        ("Content-Length", str(len(LOGOUT_BODY))),
    ]


def assert_forwarded(
    received: Received,
    method: str,
    target: str,
    sent: Headers,
    body: bytes,
    backend: FakeBackend,
    stand_in: FrontendStandIn,
) -> None:
    """가짜 백엔드가 받은 요청이, 대역 서버가 받은 요청에서 Host만 바꾼 것인지 확인한다."""
    assert received.method == method
    assert received.target == target
    assert received.body == body

    # Host는 백엔드의 주소로 바뀐다. 대역 서버의 주소가 그대로 가면 돌아올 주소를 Host로 만드는
    # 결함이 로컬에서 드러나지 않는다(ADR-026).
    assert only(received.headers, "Host") == backend.netloc
    assert only(received.headers, "Host") != f"{LOOPBACK}:{stand_in.port}"

    # Origin, Referer, Cookie는 백엔드의 출처 확인과 로그인 상태가 보는 값이라, 바뀌거나 빠지면
    # 안 된다.
    for name in ("Origin", "Referer", "Cookie"):
        sent_values = [value for key, value in sent if key == name]
        received_values = [value for key, value in received.headers if key.lower() == name.lower()]
        assert received_values == sent_values, name

    # 그 밖의 헤더도 더하거나 빼지 않는다. Host 말고는 보낸 것과 정확히 같다.
    expected = [(name, value) for name, value in sent if name != "Host"]
    expected.append(("Host", backend.netloc))
    assert normalized(received.headers) == normalized(expected)


def assert_relayed(reply: Reply, backend: FakeBackend) -> None:
    """대역 서버의 응답이 가짜 백엔드의 응답을 그대로 담았는지 확인한다."""
    assert reply.status == 302
    assert reply.all("Location") == [backend.location]
    # 두 Set-Cookie는 하나로 합치지 않고 각각 따로 온다. 순서도 그대로다.
    assert reply.all("Set-Cookie") == SET_COOKIES
    assert reply.body == BACKEND_BODY


class TestApiRequests:
    """TC-1.7.1. `/api`로 시작하는 요청은 Host만 바꿔 백엔드로 넘기고, 응답을 그대로 돌려준다."""

    @pytest.fixture(params=["elsewhere", "backend"])
    def location(self, request: pytest.FixtureRequest, running: Running) -> str:
        # 백엔드 자신을 가리키는 Location도 본다. 대역 서버가 리디렉션을 따라가면 가짜 백엔드가 받은
        # 요청의 수가 늘어난다. 바깥을 가리키는 Location은 따라가면 닿지 못해 302가 나오지 않는다.
        if request.param == "backend":
            running.backend.location = f"{running.backend.url}/api/after"
        return running.backend.location

    def test_callback_get_forwards_cookie_and_relays_redirect(
        self, running: Running, location: str
    ) -> None:
        backend, stand_in = running.backend, running.stand_in
        target = "/api/auth/google/callback?code=x&state=s"
        sent = callback_request(stand_in.port)

        reply = send(stand_in.port, "GET", target, sent)

        requests = backend.requests()
        assert len(requests) == 1, "대역 서버가 리디렉션을 따라갔다"
        assert_forwarded(requests[0], "GET", target, sent, b"", backend, stand_in)
        assert_relayed(reply, backend)

    def test_logout_post_forwards_origin_referer_and_body(
        self, running: Running, location: str
    ) -> None:
        backend, stand_in = running.backend, running.stand_in
        target = "/api/auth/logout"
        sent = logout_request(stand_in.port)

        reply = send(stand_in.port, "POST", target, sent, LOGOUT_BODY)

        requests = backend.requests()
        assert len(requests) == 1, "대역 서버가 리디렉션을 따라갔다"
        assert_forwarded(requests[0], "POST", target, sent, LOGOUT_BODY, backend, stand_in)
        assert_relayed(reply, backend)

    def test_requests_in_sequence_reach_backend_once_each(
        self, running: Running, location: str
    ) -> None:
        backend, stand_in = running.backend, running.stand_in

        first = send(
            stand_in.port,
            "GET",
            "/api/auth/google/callback?code=x&state=s",
            callback_request(stand_in.port),
        )
        second = send(
            stand_in.port, "POST", "/api/auth/logout", logout_request(stand_in.port), LOGOUT_BODY
        )

        assert [(r.method, r.target) for r in backend.requests()] == [
            ("GET", "/api/auth/google/callback?code=x&state=s"),
            ("POST", "/api/auth/logout"),
        ]
        assert_relayed(first, backend)
        assert_relayed(second, backend)


class TestPages:
    """`/api`가 아닌 경로에는 지금의 주소를 보여 주는 빈 화면을 내고, 백엔드로 넘기지 않는다."""

    @pytest.mark.parametrize("target", ["/", "/login?error=NOT_ALLOWED"])
    def test_page_shows_address_without_backend(self, running: Running, target: str) -> None:
        reply = send(running.stand_in.port, "GET", target, [("Host", "localhost:5173")])

        assert reply.status == 200
        assert only(reply.headers, "Content-Type").startswith("text/html")
        assert target in reply.body.decode("utf-8")
        assert running.backend.requests() == []

    def test_page_escapes_address(self, running: Running) -> None:
        reply = send(running.stand_in.port, "GET", "/?q=<b>x</b>&r=1", [("Host", "localhost")])

        page = reply.body.decode("utf-8")
        assert "<b>" not in page
        assert "/?q=&lt;b&gt;x&lt;/b&gt;&amp;r=1" in page


class TestEdges:
    def test_backend_unreachable_is_502(self) -> None:
        # 포트를 하나 잡았다가 놓으면, 그 포트에는 아무도 듣지 않는다.
        with socket.socket() as probe:
            probe.bind((LOOPBACK, 0))
            closed_port = probe.getsockname()[1]
        stand_in = FrontendStandIn(
            listen_host=LOOPBACK, listen_port=0, backend_url=f"http://{LOOPBACK}:{closed_port}"
        )
        stand_in.start()
        try:
            reply = send(stand_in.port, "GET", "/api/health", [("Host", "localhost")])
        finally:
            stand_in.stop()

        assert reply.status == 502

    def test_chunked_request_body_is_refused(self, running: Running) -> None:
        # 대역 서버는 Content-Length로 본문을 읽는다. 다른 방식의 본문을 빈 본문으로 넘기지 않는다.
        reply = send(
            running.stand_in.port,
            "POST",
            "/api/auth/logout",
            [("Host", "localhost"), ("Origin", FRONTEND_ORIGIN), ("Transfer-Encoding", "chunked")],
            b"2\r\nhi\r\n0\r\n\r\n",
        )

        assert reply.status == 411
        assert running.backend.requests() == []

    @pytest.mark.parametrize(
        "backend_url",
        ["https://127.0.0.1:8080", "http://127.0.0.1:8080/api", "127.0.0.1:8080", "http://"],
    )
    def test_backend_url_must_be_http_origin(self, backend_url: str) -> None:
        with pytest.raises(ValueError):
            FrontendStandIn(listen_host=LOOPBACK, listen_port=0, backend_url=backend_url)

    def test_port_before_start_raises(self) -> None:
        stand_in = FrontendStandIn(
            listen_host=LOOPBACK, listen_port=0, backend_url=f"http://{LOOPBACK}:8080"
        )
        with pytest.raises(RuntimeError):
            _ = stand_in.port


def imported_modules(source: str) -> set[str]:
    """소스가 import하는 모듈의 전체 이름. `from a.b import c`는 `a.b`로 센다."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.add(node.module)
    return found


def imports_app(source: str) -> bool:
    return any(name == "app" or name.startswith("app.") for name in imported_modules(source))


class TestBoundaries:
    """점검 스크립트는 서버를 바깥에서 보는 도구이며, 검사와 CI에서 돌지 않는다(ADR-026)."""

    @pytest.mark.parametrize(
        ("source", "expected"),
        [
            ("import app", True),
            ("import app.core.config", True),
            ("from app import main", True),
            ("from app.auth.service import AuthService", True),
            ("def f():\n    import app.main\n", True),
            ("import apple", False),
            ("from application import x", False),
            ("from scripts import login_check", False),
            ("from . import app", False),
        ],
    )
    def test_import_detector(self, source: str, expected: bool) -> None:
        assert imports_app(source) is expected

    def test_script_does_not_import_app(self) -> None:
        assert not imports_app(SCRIPT.read_text(encoding="utf-8"))

    def test_check_and_ci_do_not_run_script(self) -> None:
        workflows = sorted(WORKFLOWS.glob("*.y*ml"))
        assert workflows, "워크플로 파일을 찾지 못했다"
        for path in [CHECK_SCRIPT, *workflows]:
            assert "login_check" not in path.read_text(encoding="utf-8"), path
