"""`scripts/login_check.py`가 대역 서버를 지난 요청과 응답으로 브라우저를 따라가는 부분의 테스트.

점검 스크립트는 브라우저를 조종하지 않는다(ADR-031). 그래서 표의 "브라우저" 칸은 대역 서버가 본
것으로 판정한다.

- 주소: 브라우저가 마지막으로 연 화면(`/api` 밖의 경로).
- 쿠키와 그 속성: 백엔드가 보낸 `Set-Cookie`를 브라우저처럼 이름과 경로로 쌓은 것.
- 브라우저가 쿠키를 실제로 받아들였는지: 다음 요청에 붙은 `Cookie`와의 대조.

이 셈이 틀리면 표와 다른 브라우저를 표와 같다고 판정한다. 그래서 아래를 본다.

- 지우는 `Set-Cookie`는 이름과 경로가 모두 같을 때에만 지운다. 이름만 보고 지우면, 경로가 틀려 실제
  브라우저에서는 지워지지 않는 쿠키를 지워졌다고 센다.
- 요청에 붙은 `Cookie`는 그 요청의 응답을 반영하기 전의 셈과 견준다. 반영한 뒤와 견주면, 로그인 결과
  처리처럼 받은 쿠키를 지우는 응답에서 멀쩡한 요청을 어긋났다고 보고한다.
- 쿠키의 값은 SHA-256으로만 담고, `repr`에도 넣지 않는다.
"""

import hashlib
from dataclasses import fields
from datetime import UTC, datetime, timedelta

import pytest

from scripts.login_check import (
    SESSION_COOKIE,
    STATE_COOKIE,
    BrowserState,
    BrowserWatch,
    CookieJar,
    CookieMismatch,
    CookieState,
    DbState,
    Exchange,
    FetchResult,
    SentCookie,
    SentCookies,
    SetCookie,
    Snapshot,
    cookie_path_matches,
    default_cookie_path,
    is_navigation,
    parse_cookie_header,
    parse_set_cookie,
    render_snapshot,
    request_target,
)

FRONTEND = "http://localhost:5173"
T0 = datetime(2026, 11, 25, 7, 0, 0, tzinfo=UTC)
TOKEN = "sessionTokenMarker7Q"
OTHER_TOKEN = "otherSessionTokenMarker"
STATE = "stateCookieMarker.n.v"

SESSION_SET = f"{SESSION_COOKIE}={TOKEN}; HttpOnly; SameSite=Lax; Path=/; Max-Age=1209600"
SESSION_DELETE = f"{SESSION_COOKIE}=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0"
STATE_SET = f"{STATE_COOKIE}={STATE}; HttpOnly; SameSite=Lax; Path=/api/auth/google; Max-Age=600"
STATE_DELETE = f"{STATE_COOKIE}=; Max-Age=0; Path=/api/auth/google"


def sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def exchange(
    target: str = "/",
    *,
    method: str = "GET",
    navigation: bool = False,
    sent: str | None = None,
    status: int = 200,
    set_cookies: tuple[str, ...] = (),
    body: dict[str, object] | None = None,
    at: datetime = T0,
) -> Exchange:
    return Exchange(
        at=at,
        method=method,
        target=target,
        navigation=navigation,
        sent=parse_cookie_header(sent),
        status=status,
        set_cookies=tuple(parse_set_cookie(header) for header in set_cookies),
        body=body,
    )


def session_cookie(token: str = TOKEN) -> CookieState:
    return CookieState(
        name=SESSION_COOKIE,
        path="/",
        http_only=True,
        secure=False,
        same_site="Lax",
        value_sha256=sha(token),
    )


def state_cookie() -> CookieState:
    return CookieState(
        name=STATE_COOKIE,
        path="/api/auth/google",
        http_only=True,
        secure=False,
        same_site="Lax",
        value_sha256=sha(STATE),
    )


def text_of(value: SentCookie | SetCookie) -> str:
    """repr과 모든 필드의 문자열. 쿠키의 값이 어디에도 없는지 보는 데 쓴다."""
    parts = [repr(value)]
    parts += [str(getattr(value, f.name)) for f in fields(value)]
    return " ".join(parts)


# --- 헤더를 읽기 ------------------------------------------------------------------------------


class TestParseCookieHeader:
    def test_names_and_hashed_values_in_order(self) -> None:
        assert parse_cookie_header(f"{SESSION_COOKIE}={TOKEN}; {STATE_COOKIE}={STATE}") == (
            SentCookie(SESSION_COOKIE, sha(TOKEN)),
            SentCookie(STATE_COOKIE, sha(STATE)),
        )

    @pytest.mark.parametrize("header", [None, ""])
    def test_no_header_is_no_cookie(self, header: str | None) -> None:
        assert parse_cookie_header(header) == ()

    def test_spaces_and_broken_parts(self) -> None:
        # `=`이 없는 조각은 쿠키가 아니다. 값이 빈 쿠키는 쿠키다.
        assert parse_cookie_header("  a=1 ;b ; c=") == (
            SentCookie("a", sha("1")),
            SentCookie("c", sha("")),
        )

    def test_value_is_not_kept(self) -> None:
        [cookie] = parse_cookie_header(f"{SESSION_COOKIE}={TOKEN}")
        assert TOKEN not in text_of(cookie)
        assert sha(TOKEN) not in repr(cookie)


class TestParseSetCookie:
    def test_session_cookie(self) -> None:
        assert parse_set_cookie(SESSION_SET) == SetCookie(
            name=SESSION_COOKIE,
            value_sha256=sha(TOKEN),
            path="/",
            http_only=True,
            secure=False,
            same_site="Lax",
            max_age=1209600,
            expires=None,
        )

    def test_deleting_cookie(self) -> None:
        cookie = parse_set_cookie(STATE_DELETE)
        assert (cookie.name, cookie.path, cookie.max_age) == (STATE_COOKIE, "/api/auth/google", 0)
        assert (cookie.http_only, cookie.secure, cookie.same_site) == (False, False, "")

    def test_attribute_names_ignore_case(self) -> None:
        cookie = parse_set_cookie("a=1; httponly; SECURE; samesite=lax; path=/x; max-age=5")
        assert (cookie.http_only, cookie.secure, cookie.same_site) == (True, True, "Lax")
        assert (cookie.path, cookie.max_age) == ("/x", 5)

    def test_expires_and_values_that_cannot_be_read(self) -> None:
        cookie = parse_set_cookie(
            "a=1; Expires=Wed, 21 Oct 2015 07:28:00 GMT; Max-Age=abc; Path=relative"
        )
        assert cookie.expires == datetime(2015, 10, 21, 7, 28, tzinfo=UTC)
        # 읽지 못하는 Max-Age와 `/`로 시작하지 않는 Path는 없는 것으로 본다(RFC 6265 5.2).
        assert cookie.max_age is None
        assert cookie.path is None

    def test_value_is_not_kept(self) -> None:
        cookie = parse_set_cookie(SESSION_SET)
        assert TOKEN not in text_of(cookie)
        assert sha(TOKEN) not in repr(cookie)


class TestRequestTarget:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            # 로그인 결과 처리의 쿼리에는 Google의 code와 state가 있으므로 담지 않는다.
            ("/api/auth/google/callback?code=CODE1&state=STATE2", "/api/auth/google/callback"),
            ("/api/me", "/api/me"),
            # 대역 서버가 백엔드로 넘기는 것(`/api`로 시작하는 것)은 모두 쿼리를 담지 않는다. 넘기는
            # 판정과 쿼리를 빼는 판정이 같아야 한다(3차 리뷰 SEC-1).
            ("/api?code=CODE1&state=STATE2", "/api"),
            ("/apix?code=CODE1&state=STATE2", "/apix"),
            # 화면의 주소는 쿼리까지 담는다. 점검 2는 /login?error=NOT_ALLOWED를 본다.
            ("/login?error=NOT_ALLOWED", "/login?error=NOT_ALLOWED"),
            ("/", "/"),
        ],
    )
    def test_target(self, raw: str, expected: str) -> None:
        assert request_target(raw) == expected


class TestIsNavigation:
    @pytest.mark.parametrize(
        ("sec_fetch_dest", "accept", "expected"),
        [
            ("document", None, True),
            ("document", "*/*", True),
            # fetch는 Sec-Fetch-Dest가 empty다.
            ("empty", "text/html", False),
            ("image", "image/avif,image/webp,*/*", False),
            # Sec-Fetch-Dest를 보내지 않는 브라우저는 Accept로 가른다.
            (None, "text/html,application/xhtml+xml,*/*;q=0.8", True),
            (None, "*/*", False),
            (None, None, False),
        ],
    )
    def test_navigation(
        self, sec_fetch_dest: str | None, accept: str | None, expected: bool
    ) -> None:
        assert is_navigation(sec_fetch_dest, accept) is expected


class TestCookiePath:
    @pytest.mark.parametrize(
        ("request_path", "expected"),
        [
            ("/api/auth/google/login", "/api/auth/google"),
            ("/api", "/"),
            ("/", "/"),
            ("", "/"),
        ],
    )
    def test_default_path(self, request_path: str, expected: str) -> None:
        assert default_cookie_path(request_path) == expected

    @pytest.mark.parametrize(
        ("request_path", "cookie_path", "expected"),
        [
            ("/api/auth/google/callback", "/api/auth/google", True),
            ("/api/auth/google", "/api/auth/google", True),
            ("/api/auth/googlex", "/api/auth/google", False),
            ("/api/me", "/api/auth/google", False),
            ("/", "/api/auth/google", False),
            ("/login", "/", True),
            ("/api/me", "/api/", True),
        ],
    )
    def test_path_match(self, request_path: str, cookie_path: str, expected: bool) -> None:
        assert cookie_path_matches(request_path, cookie_path) is expected


# --- 브라우저에 남아 있어야 할 쿠키 -----------------------------------------------------------


class TestCookieJar:
    def test_set_cookie_is_held_with_its_attributes(self) -> None:
        jar = CookieJar()
        jar.apply(exchange("/api/auth/google/callback", status=302, set_cookies=(SESSION_SET,)))

        assert jar.cookies(T0) == (session_cookie(),)

    def test_deleting_needs_the_same_name_and_path(self) -> None:
        jar = CookieJar()
        jar.apply(exchange("/api/auth/google/login", status=302, set_cookies=(STATE_SET,)))

        # 경로가 다른 지우기는 실제 브라우저에서 아무것도 지우지 않는다.
        jar.apply(
            exchange(
                "/api/auth/google/callback",
                status=302,
                set_cookies=(f"{STATE_COOKIE}=; Max-Age=0; Path=/api",),
            )
        )
        assert jar.cookies(T0) == (state_cookie(),)

        jar.apply(exchange("/api/auth/google/callback", status=302, set_cookies=(STATE_DELETE,)))
        assert jar.cookies(T0) == ()

    def test_cookie_without_path_takes_the_default_path_of_the_request(self) -> None:
        jar = CookieJar()
        jar.apply(exchange("/api/auth/google/login", set_cookies=("a=1",)))

        [cookie] = jar.cookies(T0)
        assert cookie.path == "/api/auth/google"

    def test_same_name_and_path_is_replaced(self) -> None:
        jar = CookieJar()
        jar.apply(exchange(set_cookies=(SESSION_SET,)))
        jar.apply(exchange(set_cookies=(SESSION_SET.replace(TOKEN, OTHER_TOKEN),)))

        assert jar.cookies(T0) == (session_cookie(OTHER_TOKEN),)

    def test_expired_cookie_is_not_held(self) -> None:
        jar = CookieJar()
        jar.apply(exchange(set_cookies=(STATE_SET,)))
        assert jar.cookies(T0 + timedelta(seconds=599)) == (state_cookie(),)
        assert jar.cookies(T0 + timedelta(seconds=600)) == ()

        jar.apply(exchange(set_cookies=("b=1; Path=/; Expires=Wed, 21 Oct 2015 07:28:00 GMT",)))
        assert all(cookie.name != "b" for cookie in jar.cookies(T0))

    def test_cookie_the_browser_did_not_send(self) -> None:
        jar = CookieJar()
        jar.apply(exchange(set_cookies=(SESSION_SET,)))

        assert jar.compare(exchange("/api/me")) == [
            CookieMismatch("missing", SESSION_COOKIE, "GET /api/me")
        ]

    def test_cookie_not_set_during_this_check(self) -> None:
        jar = CookieJar()

        assert jar.compare(exchange("/api/me", sent=f"{SESSION_COOKIE}={TOKEN}")) == [
            CookieMismatch("unexpected", SESSION_COOKIE, "GET /api/me")
        ]

    def test_cookie_with_another_value(self) -> None:
        jar = CookieJar()
        jar.apply(exchange(set_cookies=(SESSION_SET,)))

        assert jar.compare(exchange("/", sent=f"{SESSION_COOKIE}={OTHER_TOKEN}")) == [
            CookieMismatch("different", SESSION_COOKIE, "GET /")
        ]

    def test_cookie_deleted_during_this_check_and_sent_again(self) -> None:
        # 브라우저가 지우는 Set-Cookie를 받아들이지 않으면, 지운 쿠키를 다음 요청에 그대로 붙인다.
        # 이번 점검에서 심은 쿠키이므로 "심지 않은 쿠키"가 아니다. 새 게스트 창에서 다시 해도 같은
        # 결과가 나오므로, 사람을 새 창 확인으로 보내면 원인을 찾지 못한다(4차 리뷰 BEH-1).
        jar = CookieJar()
        jar.apply(exchange("/api/auth/google/callback", status=302, set_cookies=(SESSION_SET,)))
        jar.apply(
            exchange("/api/auth/logout", method="POST", status=204, set_cookies=(SESSION_DELETE,))
        )

        assert jar.compare(exchange("/api/me", sent=f"{SESSION_COOKIE}={TOKEN}")) == [
            CookieMismatch("kept", SESSION_COOKIE, "GET /api/me")
        ]
        # 지운 것과 값이 다른 쿠키는 이번 점검에서 심지 않은 쿠키다.
        assert jar.compare(exchange("/api/me", sent=f"{SESSION_COOKIE}={OTHER_TOKEN}")) == [
            CookieMismatch("unexpected", SESSION_COOKIE, "GET /api/me")
        ]

    def test_deleted_cookie_is_kept_only_on_requests_its_path_matches(self) -> None:
        # 지운 쿠키의 경로가 맞지 않는 요청에 같은 이름이 붙었으면, 브라우저가 지운 쿠키가 아니다.
        jar = CookieJar()
        jar.apply(exchange("/api/auth/google/login", status=302, set_cookies=(STATE_SET,)))
        jar.apply(exchange("/api/auth/google/callback", status=302, set_cookies=(STATE_DELETE,)))

        sent = f"{STATE_COOKIE}={STATE}"
        assert jar.compare(exchange("/api/auth/google/callback", sent=sent)) == [
            CookieMismatch("kept", STATE_COOKIE, "GET /api/auth/google/callback")
        ]
        assert jar.compare(exchange("/api/me", sent=sent)) == [
            CookieMismatch("unexpected", STATE_COOKIE, "GET /api/me")
        ]

    def test_cookie_set_again_after_deleting_is_held(self) -> None:
        jar = CookieJar()
        jar.apply(exchange(set_cookies=(SESSION_SET,)))
        jar.apply(exchange(set_cookies=(SESSION_DELETE,)))
        jar.apply(exchange(set_cookies=(SESSION_SET.replace(TOKEN, OTHER_TOKEN),)))

        assert jar.compare(exchange("/", sent=f"{SESSION_COOKIE}={OTHER_TOKEN}")) == []
        assert jar.compare(exchange("/", sent=f"{SESSION_COOKIE}={TOKEN}")) == [
            CookieMismatch("different", SESSION_COOKIE, "GET /")
        ]

    def test_copy_remembers_deleted_cookies(self) -> None:
        # BrowserWatch는 요청을 보낸 때의 셈(복사본)과 견준다. 복사본도 지운 쿠키를 기억해야 한다.
        jar = CookieJar()
        jar.apply(exchange(set_cookies=(SESSION_SET,)))
        jar.apply(exchange(set_cookies=(SESSION_DELETE,)))

        assert jar.copy().compare(exchange("/api/me", sent=f"{SESSION_COOKIE}={TOKEN}")) == [
            CookieMismatch("kept", SESSION_COOKIE, "GET /api/me")
        ]

    def test_only_cookies_whose_path_matches_are_expected(self) -> None:
        jar = CookieJar()
        jar.apply(exchange("/api/auth/google/login", set_cookies=(STATE_SET,)))

        assert jar.compare(exchange("/api/me")) == []
        assert jar.compare(exchange("/api/auth/google/callback")) == [
            CookieMismatch("missing", STATE_COOKIE, "GET /api/auth/google/callback")
        ]
        assert (
            jar.compare(exchange("/api/auth/google/callback", sent=f"{STATE_COOKIE}={STATE}")) == []
        )

    def test_mismatch_text_names_request_and_cookie_but_no_value(self) -> None:
        for kind in ("missing", "unexpected", "different", "kept"):
            text = CookieMismatch(kind, SESSION_COOKIE, "GET /api/me").text()
            assert text.startswith("브라우저: ")
            assert "GET /api/me" in text and SESSION_COOKIE in text

    def test_kept_cookie_points_to_the_deleting_set_cookie(self) -> None:
        # 지운 쿠키를 다시 붙인 원인은 새 창이 아니라 브라우저가 받아들이지 않은 지우는 Set-Cookie다
        # (4차 리뷰 BEH-1).
        text = CookieMismatch("kept", SESSION_COOKIE, "GET /api/me").text()
        assert "이번 점검에서 지운" in text
        assert "지우는 Set-Cookie" in text
        assert "속성" in text
        assert "새 게스트 창" not in text


# --- 한 점검 동안의 브라우저 ------------------------------------------------------------------


def login_flow() -> list[Exchange]:
    """점검 1에서 표대로 움직인 브라우저가 대역 서버로 보내는 요청과 받는 응답."""
    return [
        exchange("/", navigation=True),
        exchange("/api/me", status=401, body={"code": "NOT_AUTHENTICATED"}),
        exchange("/api/auth/google/login", navigation=True, status=302, set_cookies=(STATE_SET,)),
        exchange(
            "/api/auth/google/callback",
            navigation=True,
            sent=f"{STATE_COOKIE}={STATE}",
            status=302,
            set_cookies=(SESSION_SET, STATE_DELETE),
        ),
        exchange("/", navigation=True, sent=f"{SESSION_COOKIE}={TOKEN}"),
    ]


class TestBrowserWatch:
    def test_login_flow_of_the_table_has_no_mismatch(self) -> None:
        watch = BrowserWatch(FRONTEND)
        flow = login_flow()
        for item in flow:
            watch.observe(item)

        state = watch.state(flow[-1])
        assert state.url == f"{FRONTEND}/"
        # 로그인 결과 처리가 diegesis_oauth_state를 같은 경로로 지웠으므로 남지 않는다.
        assert state.cookies == (session_cookie(),)
        assert state.sent == SentCookies("GET /", (SESSION_COOKIE,))
        assert watch.take_problems() == []

        logout = exchange(
            "/api/auth/logout",
            method="POST",
            sent=f"{SESSION_COOKIE}={TOKEN}",
            status=204,
            set_cookies=(SESSION_DELETE,),
        )
        me = exchange("/api/me", status=401)
        watch.observe(logout)
        watch.observe(me)

        state = watch.state(me, me=FetchResult(401, None), logout_status=204)
        assert state.cookies == ()
        assert state.me == FetchResult(401, None)
        assert state.logout_status == 204
        assert state.sent == SentCookies("GET /api/me", ())
        assert watch.take_problems() == []

    def test_request_is_compared_before_its_own_response(self) -> None:
        # 결과 처리의 요청은 diegesis_oauth_state를 붙이고, 그 응답이 그 쿠키를 지운다.
        watch = BrowserWatch(FRONTEND)
        for item in login_flow()[:4]:
            watch.observe(item)

        assert watch.take_problems() == []

    def test_browser_that_dropped_the_session_cookie_is_reported(self) -> None:
        watch = BrowserWatch(FRONTEND)
        flow = login_flow()
        flow[-1] = exchange("/", navigation=True)
        for item in flow:
            watch.observe(item)

        [problem] = watch.take_problems()
        assert problem == CookieMismatch("missing", SESSION_COOKIE, "GET /").text()

    def test_url_is_the_last_page_the_browser_opened(self) -> None:
        watch = BrowserWatch(FRONTEND)
        assert watch.state(exchange()).url == ""

        watch.observe(exchange("/login?error=NOT_ALLOWED", navigation=True))
        # `/api` 아래로 화면을 옮긴 것(로그인 시작, 결과 처리)과 화면 안의 fetch는 주소를 바꾸지
        # 않는다.
        watch.observe(exchange("/api/auth/google/login", navigation=True, status=302))
        watch.observe(exchange("/somewhere"))

        assert watch.state(exchange()).url == f"{FRONTEND}/login?error=NOT_ALLOWED"

    def test_forwarded_path_that_is_not_under_api_slash_is_not_a_page(self) -> None:
        # `/apix`도 대역 서버가 백엔드로 넘기므로 대역의 화면이 아니다(3차 리뷰 SEC-1).
        watch = BrowserWatch(FRONTEND)
        watch.observe(exchange("/", navigation=True))
        watch.observe(exchange("/apix", navigation=True, status=404))

        assert watch.state(exchange()).url == f"{FRONTEND}/"

    def test_request_that_is_neither_a_page_nor_api_is_not_compared(self) -> None:
        # 대역 서버에는 게스트 창의 화면 이동과 /api 요청 말고도, 다른 창에 남은 탭이 보낸 요청(끈
        # Vite의 재연결 요청 같은 것)이 온다. 그런 요청에는 평소 창의 쿠키가 붙어 있다. 표의
        # 브라우저가 아니므로 쿠키를 대조하지 않는다(3차 리뷰 COR-4).
        watch = BrowserWatch(FRONTEND)
        for item in login_flow():
            watch.observe(item)
        assert watch.take_problems() == []

        watch.observe(exchange("/", sent=f"{SESSION_COOKIE}={OTHER_TOKEN}; theme=dark"))
        watch.observe(exchange("/favicon.ico", sent="theme=dark"))
        assert watch.take_problems() == []

        # 화면 이동과 /api 요청은 그대로 대조한다.
        watch.observe(exchange("/", navigation=True, sent=f"{SESSION_COOKIE}={OTHER_TOKEN}"))
        watch.observe(exchange("/api/me", sent=f"{SESSION_COOKIE}={TOKEN}; theme=dark"))
        assert watch.take_problems() == [
            CookieMismatch("different", SESSION_COOKIE, "GET /").text(),
            CookieMismatch("unexpected", "theme", "GET /api/me").text(),
        ]

    def test_problem_is_reported_once_per_cookie_until_taken(self) -> None:
        # 이전 점검의 쿠키가 남은 창에서 시작하면 요청마다 같은 쿠키가 붙는다.
        watch = BrowserWatch(FRONTEND)
        watch.observe(exchange("/", navigation=True, sent=f"{SESSION_COOKIE}={OTHER_TOKEN}"))
        watch.observe(exchange("/api/me", sent=f"{SESSION_COOKIE}={OTHER_TOKEN}", status=401))

        assert watch.take_problems() == [
            CookieMismatch("unexpected", SESSION_COOKIE, "GET /").text()
        ]
        assert watch.take_problems() == []

        watch.observe(exchange("/api/me", sent=f"{SESSION_COOKIE}={OTHER_TOKEN}", status=401))
        assert watch.take_problems() == [
            CookieMismatch("unexpected", SESSION_COOKIE, "GET /api/me").text()
        ]


# --- 출력 -------------------------------------------------------------------------------------


def snapshot_with(sent: SentCookies | None) -> Snapshot:
    db = DbState(allowed=(), users=(), sessions=(), session_total=0)
    return Snapshot(db=db, browser=BrowserState(url=f"{FRONTEND}/", cookies=(), sent=sent))


class TestRenderSentCookies:
    def test_names_of_sent_cookies_are_shown(self) -> None:
        output = render_snapshot(
            "로그인 후",
            snapshot_with(SentCookies("GET /", (SESSION_COOKIE,))),
            allowed_email="a@example.com",
            denied_email="b@example.com",
        )
        assert f"  보낸 쿠키(GET /): {SESSION_COOKIE}" in output.splitlines()

    def test_no_sent_cookie_is_shown_as_none(self) -> None:
        output = render_snapshot(
            "로그인 전",
            snapshot_with(SentCookies("GET /api/me", ())),
            allowed_email="a@example.com",
            denied_email="b@example.com",
        )
        assert "  보낸 쿠키(GET /api/me): 없음" in output.splitlines()

    def test_api_address_is_shown_without_query(self) -> None:
        # 백엔드로 넘기는 주소(`/api`로 시작하는 것)는 쿼리를 보여 주지 않는다(3차 리뷰 SEC-1).
        db = DbState(allowed=(), users=(), sessions=(), session_total=0)
        for url in (f"{FRONTEND}/api?code=SECRETCODE1", f"{FRONTEND}/apix?code=SECRETCODE1"):
            output = render_snapshot(
                "로그인 후",
                Snapshot(db=db, browser=BrowserState(url=url, cookies=())),
                allowed_email="a@example.com",
                denied_email="b@example.com",
            )
            assert "SECRETCODE1" not in output

    def test_line_is_left_out_without_a_request(self) -> None:
        output = render_snapshot(
            "로그인 전",
            snapshot_with(None),
            allowed_email="a@example.com",
            denied_email="b@example.com",
        )
        assert "보낸 쿠키" not in output
