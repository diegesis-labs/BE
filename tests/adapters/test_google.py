"""Google 어댑터의 테스트 (TC-1.2.1 ~ TC-1.2.8, ADR-027, ADR-028).

네트워크를 쓰지 않는다. 토큰 엔드포인트는 httpx.MockTransport로 흉내 내고, ID 토큰은 테스트 안에서
클레임을 base64url로 인코딩해 `header.payload.signature` 모양으로 만든다. 어댑터는 서명을 확인하지
않으므로 서명 부분은 아무 문자열이어도 된다(ADR-027).

"정상 ID 토큰"은 docs/backlog/epic-1/testcase.md 맨 위의 정의를 그대로 쓰고, 각 케이스는 적힌
클레임만 바꾼다.

TC-1.2.1 가운데 요청의 Host가 `localhost:8080`일 때의 확인은 로그인 경로를 만드는 step에서 한다.
어댑터는 요청을 받지 않으므로 Host를 볼 수 없다.
"""

import base64
import json
import logging
import time
from collections.abc import Callable
from urllib.parse import parse_qsl, urlsplit

import httpx
import pytest

from app.adapters import google
from app.adapters.google import GoogleIdentityProvider
from app.core.config import get_settings
from app.core.ports import Identity, IdentityProvider, LoginFailedError
from tests.support.settings import TEST_GOOGLE_CLIENT_ID, TEST_GOOGLE_CLIENT_SECRET

Handler = Callable[[httpx.Request], httpx.Response]

# 상수의 값을 코드에서 읽지 않고 글자로 적는다. 어댑터의 상수가 바뀌면 테스트가 실패해야 한다.
AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
# FRONTEND_URL이 http://localhost:5173일 때의 돌아올 주소(INFRA.md 3.5절).
CALLBACK_URL = "http://localhost:5173/api/auth/google/callback"

STATE = "fixed-state-value"
NONCE = "fixed-nonce-value"
WRONG_NONCE = "wrong-nonce-marker"
OTHER_CLIENT_ID = "other-client-id.apps.googleusercontent.com"

# RFC 7636 부록 B의 예시. code_challenge를 테스트 안에서 어댑터와 같은 식으로 계산해 비교하면, 둘이
# 같은 실수를 해도 통과한다. 그래서 RFC가 적어 둔 값과 비교한다.
RFC7636_CODE_VERIFIER = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
RFC7636_CODE_CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"

# 아래 값들은 예외의 메시지에 들어가면 안 된다. 다른 글자와 헷갈리지 않도록 고유한 값을 쓴다.
CODE = "4/0AeaYSH-code-marker"
CODE_VERIFIER = "code-verifier-marker-0123456789abcdefghijklm"
ACCESS_TOKEN_MARKER = "access-token-marker"
SECRETS = (
    CODE,
    CODE_VERIFIER,
    TEST_GOOGLE_CLIENT_SECRET,
    ACCESS_TOKEN_MARKER,
    NONCE,
    WRONG_NONCE,
)

# 클레임을 뺀다는 표시.
MISSING = object()

# 정상 ID 토큰의 신원(testcase.md 맨 위).
VALID_IDENTITY = Identity(
    sub="1234567890", email="reader@example.com", email_verified=True, name="독자"
)


# --- ID 토큰과 토큰 응답 ----------------------------------------------------------


def b64url(data: bytes) -> str:
    """패딩(`=`) 없는 base64url. JWT의 각 부분은 이 모양이다."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def valid_claims() -> dict[str, object]:
    """정상 ID 토큰의 클레임(testcase.md 맨 위). `exp`는 지금부터 1시간 뒤다."""
    return {
        "iss": "https://accounts.google.com",
        "aud": TEST_GOOGLE_CLIENT_ID,
        "azp": TEST_GOOGLE_CLIENT_ID,
        "exp": int(time.time()) + 3600,
        "nonce": NONCE,
        "sub": "1234567890",
        "email": "reader@example.com",
        "email_verified": True,
        "name": "독자",
    }


def claims_with(changes: dict[str, object]) -> dict[str, object]:
    """정상 ID 토큰에서 적힌 클레임만 바꾼다. 값이 MISSING이면 그 클레임을 뺀다."""
    claims = valid_claims()
    for name, value in changes.items():
        if value is MISSING:
            claims.pop(name, None)
        else:
            claims[name] = value
    return claims


def encode_payload(payload: object) -> str:
    # Google은 이름을 UTF-8 그대로 담는다. 어댑터가 UTF-8로 푸는지 보도록 escape하지 않는다.
    return b64url(json.dumps(payload, ensure_ascii=False).encode("utf-8"))


HEADER = b64url(json.dumps({"alg": "RS256", "kid": "test-key", "typ": "JWT"}).encode())


def encode_id_token(payload: object) -> str:
    return f"{HEADER}.{encode_payload(payload)}.not-a-real-signature"


def token_body(id_token: object) -> dict[str, object]:
    """토큰 엔드포인트의 성공 응답. 응답 본문의 다른 값이 새는지 보도록 표식을 넣어 둔다."""
    return {
        "access_token": ACCESS_TOKEN_MARKER,
        "expires_in": 3599,
        "scope": "openid https://www.googleapis.com/auth/userinfo.email",
        "token_type": "Bearer",
        "id_token": id_token,
    }


def respond(response: httpx.Response) -> Handler:
    def handle(request: httpx.Request) -> httpx.Response:
        return response

    return handle


def respond_with_claims(claims: dict[str, object]) -> Handler:
    return respond(httpx.Response(200, json=token_body(encode_id_token(claims))))


def raise_error(error_type: type[httpx.TransportError]) -> Handler:
    def handle(request: httpx.Request) -> httpx.Response:
        raise error_type("simulated transport failure", request=request)

    return handle


def make_provider(
    handler: Handler, *, client_id: str = TEST_GOOGLE_CLIENT_ID
) -> GoogleIdentityProvider:
    return GoogleIdentityProvider(
        client_id=client_id,
        client_secret=TEST_GOOGLE_CLIENT_SECRET,
        redirect_uri=CALLBACK_URL,
        transport=httpx.MockTransport(handler),
    )


async def exchange(provider: GoogleIdentityProvider, *, expected_nonce: str = NONCE) -> Identity:
    return await provider.exchange_code(
        code=CODE, code_verifier=CODE_VERIFIER, expected_nonce=expected_nonce
    )


def exception_texts(error: BaseException) -> list[str]:
    """예외와 그 원인들의 문자열. 로그에는 원인의 메시지도 함께 찍힌다."""
    texts: list[str] = []
    seen: set[int] = set()
    pending: list[BaseException] = [error]
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        texts += [str(current), repr(current)]
        pending += [linked for linked in (current.__cause__, current.__context__) if linked]
    return texts


async def assert_login_fails(
    handler: Handler,
    *,
    expected_nonce: str = NONCE,
    client_id: str = TEST_GOOGLE_CLIENT_ID,
    extra_secrets: tuple[str, ...] = (),
) -> None:
    """LoginFailedError가 나고, 그 메시지와 원인들의 메시지에 비밀이 없는지 본다.

    service는 이 예외의 메시지를 로그에 남긴다. code, code_verifier, 클라이언트 비밀값, nonce,
    응답 본문, 토큰이 메시지에 들어가면 로그에 남는다(E1 "못 박을 것").
    """
    provider = make_provider(handler, client_id=client_id)

    with pytest.raises(LoginFailedError) as caught:
        await exchange(provider, expected_nonce=expected_nonce)

    texts = exception_texts(caught.value)
    for secret in (*SECRETS, *extra_secrets):
        for text in texts:
            assert secret not in text, (secret, text)


# --- 포트 ------------------------------------------------------------------------


def test_google_identity_provider_satisfies_the_port() -> None:
    # 타입 검사(pyright)가 IdentityProvider의 모양과 다른 메서드를 잡는다.
    provider: IdentityProvider = make_provider(respond(httpx.Response(500)))

    assert isinstance(provider, GoogleIdentityProvider)


# --- TC-1.2.1 인가 주소 --------------------------------------------------------------


def test_authorization_url_has_exactly_the_documented_parameters(app_env: None) -> None:
    provider = GoogleIdentityProvider.from_settings(get_settings())

    url = provider.authorization_url(state=STATE, nonce=NONCE, code_verifier=RFC7636_CODE_VERIFIER)

    parts = urlsplit(url)
    assert f"{parts.scheme}://{parts.netloc}{parts.path}" == AUTHORIZATION_ENDPOINT
    assert parts.fragment == ""
    pairs = parse_qsl(parts.query, keep_blank_values=True, strict_parsing=True)
    # 같은 이름이 두 번 나오면 dict로 바꿀 때 하나가 사라지므로, 개수를 먼저 본다.
    assert len(pairs) == 8, pairs
    assert dict(pairs) == {
        "client_id": TEST_GOOGLE_CLIENT_ID,
        "redirect_uri": CALLBACK_URL,
        "response_type": "code",
        "scope": "openid email profile",
        "state": STATE,
        "nonce": NONCE,
        "code_challenge": RFC7636_CODE_CHALLENGE,
        "code_challenge_method": "S256",
    }
    # code_verifier는 code_challenge로만 보낸다. 주소의 어디에도 있으면 안 된다.
    assert RFC7636_CODE_VERIFIER not in url


def test_authorization_url_challenge_is_unpadded_base64url_sha256_of_the_verifier(
    app_env: None,
) -> None:
    provider = GoogleIdentityProvider.from_settings(get_settings())

    url = provider.authorization_url(state=STATE, nonce=NONCE, code_verifier=CODE_VERIFIER)

    challenge = dict(parse_qsl(urlsplit(url).query))["code_challenge"]
    # SHA-256은 32바이트이고, 패딩 없는 base64url로 43자다.
    assert len(challenge) == 43
    assert "=" not in challenge
    assert challenge != CODE_VERIFIER
    assert CODE_VERIFIER not in url


@pytest.mark.parametrize(
    ("frontend_url", "callback_url"),
    [
        ("http://localhost:5173", "http://localhost:5173/api/auth/google/callback"),
        ("https://diegesis.example", "https://diegesis.example/api/auth/google/callback"),
    ],
)
def test_redirect_uri_is_frontend_url_plus_callback_path(
    app_env: None, monkeypatch: pytest.MonkeyPatch, frontend_url: str, callback_url: str
) -> None:
    monkeypatch.setenv("FRONTEND_URL", frontend_url)
    get_settings.cache_clear()
    provider = GoogleIdentityProvider.from_settings(get_settings())

    url = provider.authorization_url(state=STATE, nonce=NONCE, code_verifier=CODE_VERIFIER)

    assert dict(parse_qsl(urlsplit(url).query))["redirect_uri"] == callback_url


# --- TC-1.2.8 토큰 교환 요청 --------------------------------------------------------


async def test_token_exchange_posts_the_form_with_code_verifier(app_env: None) -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=token_body(encode_id_token(valid_claims())))

    provider = GoogleIdentityProvider.from_settings(
        get_settings(), transport=httpx.MockTransport(handle)
    )
    authorization_redirect_uri = dict(
        parse_qsl(
            urlsplit(
                provider.authorization_url(state=STATE, nonce=NONCE, code_verifier=CODE_VERIFIER)
            ).query
        )
    )["redirect_uri"]

    await exchange(provider)

    # 토큰 엔드포인트에 한 번만 보낸다. 공개키(JWKS)나 사용자 정보를 따로 받아 오지 않는다.
    assert len(requests) == 1
    request = requests[0]
    assert request.method == "POST"
    # 쿼리가 붙지 않은 주소와 정확히 같다. code를 주소에 담으면 실패한다.
    assert str(request.url) == TOKEN_ENDPOINT
    assert request.headers["content-type"] == "application/x-www-form-urlencoded"
    pairs = parse_qsl(request.content.decode("ascii"), keep_blank_values=True, strict_parsing=True)
    assert len(pairs) == 6, pairs
    assert dict(pairs) == {
        "grant_type": "authorization_code",
        "code": CODE,
        "code_verifier": CODE_VERIFIER,
        "redirect_uri": CALLBACK_URL,
        "client_id": TEST_GOOGLE_CLIENT_ID,
        "client_secret": TEST_GOOGLE_CLIENT_SECRET,
    }
    # 인가 주소와 같은 돌아올 주소를 보내야 Google이 교환을 받아들인다.
    assert dict(pairs)["redirect_uri"] == authorization_redirect_uri


async def test_token_exchange_sets_an_explicit_timeout() -> None:
    timeouts: list[dict[str, float | None]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        timeouts.append(request.extensions["timeout"])
        return httpx.Response(200, json=token_body(encode_id_token(valid_claims())))

    await exchange(make_provider(handle))

    # Google이 응답하지 않을 때 로그인 요청이 끝없이 붙들려 있으면 안 된다.
    seconds = google.TOKEN_REQUEST_TIMEOUT_SECONDS
    assert 0 < seconds <= 30
    assert timeouts == [{"connect": seconds, "read": seconds, "write": seconds, "pool": seconds}]


async def test_token_exchange_does_not_follow_redirects() -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if str(request.url) == TOKEN_ENDPOINT:
            return httpx.Response(302, headers={"location": "https://evil.example/token"})
        return httpx.Response(200, json=token_body(encode_id_token(valid_claims())))

    await assert_login_fails(handle)

    assert [str(request.url) for request in requests] == [TOKEN_ENDPOINT]


# --- TC-1.2.2 오류 응답과 형식이 틀린 응답 -----------------------------------------


@pytest.mark.parametrize(
    "handler",
    [
        pytest.param(
            respond(
                httpx.Response(
                    400,
                    json={
                        "error": "invalid_grant",
                        "error_description": f"Bad Request {ACCESS_TOKEN_MARKER}",
                    },
                )
            ),
            id="400-error-body",
        ),
        # 본문에 정상 ID 토큰이 있어도 200이 아니면 실패다. 상태 코드를 보지 않으면 통과해 버린다.
        pytest.param(
            respond(httpx.Response(400, json=token_body(encode_id_token(valid_claims())))),
            id="400-with-valid-token",
        ),
        pytest.param(
            respond(httpx.Response(500, text=f"<html>{ACCESS_TOKEN_MARKER}</html>")),
            id="500",
        ),
        pytest.param(
            respond(httpx.Response(200, text=f"<html>{ACCESS_TOKEN_MARKER}</html>")),
            id="non-json-body",
        ),
        pytest.param(respond(httpx.Response(200, content=b"")), id="empty-body"),
        pytest.param(
            respond(httpx.Response(200, content=b"\xff\xfe" + ACCESS_TOKEN_MARKER.encode())),
            id="non-utf8-body",
        ),
        pytest.param(
            respond(httpx.Response(200, json=[token_body(encode_id_token(valid_claims()))])),
            id="json-array-body",
        ),
        pytest.param(
            respond(
                httpx.Response(
                    200, json={"access_token": ACCESS_TOKEN_MARKER, "token_type": "Bearer"}
                )
            ),
            id="missing-id-token",
        ),
        pytest.param(respond(httpx.Response(200, json=token_body(12345))), id="id-token-number"),
        pytest.param(respond(httpx.Response(200, json=token_body(None))), id="id-token-null"),
        pytest.param(raise_error(httpx.ConnectError), id="connect-error"),
        pytest.param(raise_error(httpx.ReadTimeout), id="read-timeout"),
    ],
)
async def test_failed_token_exchange_raises_login_failed_error(handler: Handler) -> None:
    await assert_login_fails(handler)


# --- 형식이 틀린 ID 토큰 ------------------------------------------------------------


@pytest.mark.parametrize(
    "id_token",
    [
        pytest.param("", id="empty"),
        pytest.param(f"{HEADER}.{encode_payload(valid_claims())}", id="two-parts"),
        pytest.param(f"{encode_id_token(valid_claims())}.extra", id="four-parts"),
        pytest.param(f"{HEADER}.!!!$$$.signature", id="payload-not-base64"),
        # 5자는 4의 배수보다 1 많아서 base64로 풀 수 없다.
        pytest.param(f"{HEADER}.abcde.signature", id="payload-impossible-length"),
        pytest.param(f"{HEADER}.{b64url(b'not json')}.signature", id="payload-not-json"),
        pytest.param(f"{HEADER}.{b64url(b'\xff\xfe\xfd')}.signature", id="payload-not-utf8"),
        pytest.param(f"{HEADER}.{encode_payload([valid_claims()])}.signature", id="payload-array"),
        pytest.param(f"{HEADER}.{encode_payload('claims')}.signature", id="payload-string"),
        pytest.param(f"{HEADER}..signature", id="payload-empty"),
    ],
)
async def test_malformed_id_token_raises_login_failed_error(id_token: str) -> None:
    handler = respond(httpx.Response(200, json=token_body(id_token)))

    extra_secrets = (id_token,) if id_token else ()
    await assert_login_fails(handler, extra_secrets=extra_secrets)


# --- TC-1.2.3 정상 ID 토큰 ----------------------------------------------------------


@pytest.mark.parametrize("issuer", ["https://accounts.google.com", "accounts.google.com"])
async def test_valid_id_token_returns_the_identity(issuer: str) -> None:
    requests: list[httpx.Request] = []
    claims = claims_with({"iss": issuer})

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=token_body(encode_id_token(claims)))

    identity = await exchange(make_provider(handle))

    assert identity == VALID_IDENTITY
    # 서명을 확인하려고 Google의 공개키를 받아 오지 않는다(ADR-027).
    assert [str(request.url) for request in requests] == [TOKEN_ENDPOINT]


async def test_id_token_without_email_verified_returns_false() -> None:
    identity = await exchange(
        make_provider(respond_with_claims(claims_with({"email_verified": MISSING})))
    )

    assert identity == Identity(
        sub="1234567890", email="reader@example.com", email_verified=False, name="독자"
    )


@pytest.mark.parametrize(
    ("email_verified", "expected"),
    [
        (True, True),
        ("true", True),
        (False, False),
        ("false", False),
        ("True", False),
        (1, False),
        (None, False),
    ],
)
async def test_email_verified_is_true_only_for_boolean_or_string_true(
    email_verified: object, expected: bool
) -> None:
    # email_verified가 false인 신원을 거르는 것은 service의 일이다. 어댑터는 값만 돌려준다.
    identity = await exchange(
        make_provider(respond_with_claims(claims_with({"email_verified": email_verified})))
    )

    assert identity.email_verified is expected
    assert identity.sub == "1234567890"


@pytest.mark.parametrize("name", [MISSING, None, 42])
async def test_name_is_none_unless_it_is_a_string(name: object) -> None:
    identity = await exchange(make_provider(respond_with_claims(claims_with({"name": name}))))

    assert identity == Identity(
        sub="1234567890", email="reader@example.com", email_verified=True, name=None
    )


async def test_email_is_returned_as_google_gave_it() -> None:
    # 소문자로 바꾸는 것은 service의 일이다(app/core/ports.py의 Identity).
    identity = await exchange(
        make_provider(respond_with_claims(claims_with({"email": "Reader@Example.COM"})))
    )

    assert identity.email == "Reader@Example.COM"


async def test_aud_list_with_only_our_client_id_and_no_azp_is_accepted() -> None:
    identity = await exchange(
        make_provider(
            respond_with_claims(claims_with({"aud": [TEST_GOOGLE_CLIENT_ID], "azp": MISSING}))
        )
    )

    assert identity == VALID_IDENTITY


async def test_payload_is_decoded_as_unpadded_base64url() -> None:
    # JWT의 각 부분은 패딩 없는 base64url이다. 패딩을 붙이지 않고 풀거나 표준 base64로 풀면, 길이와
    # 글자에 따라 Google의 정상 토큰을 거부하게 된다. 그래서 payload의 길이를 4로 나눈 나머지가
    # 0, 2, 3인 경우를 모두 만들고, payload에 `-`와 `_`가 들어가게 한다. `???`는 표준 base64의
    # `/`, `>>>`는 `+`로 바뀌는 바이트이고, 여섯 개씩 이어 두면 정렬과 관계없이 세 바이트가 한
    # 묶음이 된다.
    exp = int(time.time()) + 3600
    remainders: set[int] = set()
    for filler in ("", "x", "xx"):
        name = "독자" + "?" * 6 + ">" * 6 + filler
        claims = claims_with({"name": name, "exp": exp})
        payload = encode_payload(claims)
        assert "-" in payload and "_" in payload, payload
        remainders.add(len(payload) % 4)

        identity = await exchange(make_provider(respond_with_claims(claims)))

        assert identity.name == name
    assert remainders == {0, 2, 3}


# --- TC-1.2.4 aud와 azp -------------------------------------------------------------


@pytest.mark.parametrize(
    "changes",
    [
        pytest.param({"aud": OTHER_CLIENT_ID}, id="aud-other-client"),
        # 우리 ID가 목록에 들어 있기만 하면 통과시키는 구현을 거른다.
        pytest.param({"aud": [TEST_GOOGLE_CLIENT_ID, OTHER_CLIENT_ID]}, id="aud-list-with-other"),
        pytest.param({"aud": [OTHER_CLIENT_ID, TEST_GOOGLE_CLIENT_ID]}, id="aud-list-other-first"),
        pytest.param({"aud": [TEST_GOOGLE_CLIENT_ID, TEST_GOOGLE_CLIENT_ID]}, id="aud-list-twice"),
        pytest.param({"aud": []}, id="aud-empty-list"),
        pytest.param({"aud": MISSING}, id="aud-missing"),
        pytest.param({"aud": ""}, id="aud-empty"),
        pytest.param({"aud": 42}, id="aud-number"),
        pytest.param({"aud": {"id": TEST_GOOGLE_CLIENT_ID}}, id="aud-object"),
        pytest.param({"azp": OTHER_CLIENT_ID}, id="azp-other-client"),
        pytest.param({"azp": None}, id="azp-null"),
        pytest.param({"azp": ""}, id="azp-empty"),
        pytest.param({"azp": [TEST_GOOGLE_CLIENT_ID]}, id="azp-list"),
    ],
)
async def test_id_token_for_another_client_raises_login_failed_error(
    changes: dict[str, object],
) -> None:
    claims = claims_with(changes)

    await assert_login_fails(respond_with_claims(claims), extra_secrets=(encode_id_token(claims),))


async def test_empty_client_id_never_matches_an_empty_aud() -> None:
    # CI의 compose 스모크는 GOOGLE_CLIENT_ID 없이 서버를 띄운다(app/core/config.py). 그 서버가 aud가
    # 빈 토큰을 받아들이면 안 된다.
    claims = claims_with({"aud": "", "azp": ""})

    await assert_login_fails(respond_with_claims(claims), client_id="")


# --- TC-1.2.5 iss ------------------------------------------------------------------


@pytest.mark.parametrize(
    "changes",
    [
        pytest.param({"iss": "https://evil.example"}, id="iss-evil"),
        pytest.param({"iss": "http://accounts.google.com"}, id="iss-http"),
        pytest.param({"iss": "https://accounts.google.com/"}, id="iss-trailing-slash"),
        pytest.param({"iss": "accounts.google.com.evil.example"}, id="iss-suffix"),
        pytest.param({"iss": MISSING}, id="iss-missing"),
        pytest.param({"iss": ["https://accounts.google.com"]}, id="iss-list"),
    ],
)
async def test_id_token_from_another_issuer_raises_login_failed_error(
    changes: dict[str, object],
) -> None:
    await assert_login_fails(respond_with_claims(claims_with(changes)))


# --- TC-1.2.6 exp ------------------------------------------------------------------


@pytest.mark.parametrize(
    "exp",
    [
        pytest.param(lambda: int(time.time()) - 60, id="exp-one-minute-ago"),
        # 확인하는 순간은 이 값을 만든 순간보다 뒤이므로, 이 값은 언제나 지금보다 뒤가 아니다.
        pytest.param(lambda: int(time.time()), id="exp-now"),
        pytest.param(lambda: MISSING, id="exp-missing"),
        pytest.param(lambda: str(int(time.time()) + 3600), id="exp-string"),
        pytest.param(lambda: None, id="exp-null"),
        pytest.param(lambda: True, id="exp-boolean"),
        # json.dumps는 무한대를 `Infinity`로 쓰고, json.loads는 그것을 float로 읽는다.
        pytest.param(lambda: float("inf"), id="exp-infinity"),
        pytest.param(lambda: float("nan"), id="exp-nan"),
    ],
)
async def test_expired_or_invalid_exp_raises_login_failed_error(exp: Callable[[], object]) -> None:
    await assert_login_fails(respond_with_claims(claims_with({"exp": exp()})))


# --- TC-1.2.7 nonce, sub, email ----------------------------------------------------


@pytest.mark.parametrize(
    "changes",
    [
        pytest.param({"nonce": WRONG_NONCE}, id="nonce-different"),
        pytest.param({"nonce": MISSING}, id="nonce-missing"),
        pytest.param({"nonce": ""}, id="nonce-empty"),
        pytest.param({"nonce": None}, id="nonce-null"),
        pytest.param({"nonce": 42}, id="nonce-number"),
        pytest.param({"nonce": NONCE + "x"}, id="nonce-longer"),
        pytest.param({"sub": MISSING}, id="sub-missing"),
        pytest.param({"sub": ""}, id="sub-empty"),
        pytest.param({"sub": 1234567890}, id="sub-number"),
        pytest.param({"sub": None}, id="sub-null"),
        pytest.param({"email": MISSING}, id="email-missing"),
        pytest.param({"email": ""}, id="email-empty"),
        pytest.param({"email": ["reader@example.com"]}, id="email-list"),
        pytest.param({"email": None}, id="email-null"),
    ],
)
async def test_id_token_with_bad_nonce_sub_or_email_raises_login_failed_error(
    changes: dict[str, object],
) -> None:
    await assert_login_fails(respond_with_claims(claims_with(changes)))


async def test_empty_expected_nonce_never_matches() -> None:
    # 빈 값끼리 같다고 판정하면 nonce의 확인이 무력해진다(ADR-027).
    await assert_login_fails(respond_with_claims(claims_with({"nonce": ""})), expected_nonce="")


# --- 어댑터 자신의 로그 (1차 리뷰 TST-4, TC-1.3.13) -------------------------
#
# 예외의 메시지만이 아니라, 어댑터가 남기는 로그에도 code, code_verifier, 클라이언트 비밀값, nonce,
# 토큰이 없어야 한다(E1 "못 박을 것"). 서버에서 LOG_LEVEL이 걸리는 것은 `app` 로거와 그 아래이므로
# (app/core/log_config.py), 그 로거를 DEBUG로 모은다.

ADAPTER_LOGGER = "app.adapters.google"


def start_capturing_app_debug_logs(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger="app")
    # 이 캡처가 어댑터 로거의 DEBUG를 받는지 먼저 확인한다. 받지 못하면 아래의 확인이 비어 버린다.
    logging.getLogger(ADAPTER_LOGGER).debug("canary-adapter-debug")
    assert "canary-adapter-debug" in caplog.text


def assert_no_secret_in_logs(caplog: pytest.LogCaptureFixture, *extra: str) -> None:
    texts = [caplog.text, *(record.getMessage() for record in caplog.records)]
    for secret in (*SECRETS, *extra):
        for text in texts:
            assert secret not in text, (secret, text)


async def test_successful_exchange_logs_no_secret(caplog: pytest.LogCaptureFixture) -> None:
    id_token = encode_id_token(valid_claims())
    provider = make_provider(respond(httpx.Response(200, json=token_body(id_token))))
    start_capturing_app_debug_logs(caplog)

    assert await exchange(provider) == VALID_IDENTITY

    assert_no_secret_in_logs(caplog, id_token)


@pytest.mark.parametrize(
    "handler",
    [
        pytest.param(respond_with_claims(claims_with({"nonce": WRONG_NONCE})), id="bad-claim"),
        pytest.param(respond(httpx.Response(400, json={"error": "invalid_grant"})), id="error"),
        pytest.param(raise_error(httpx.ConnectError), id="transport"),
    ],
)
async def test_failed_exchange_logs_no_secret(
    caplog: pytest.LogCaptureFixture, handler: Handler
) -> None:
    provider = make_provider(handler)
    start_capturing_app_debug_logs(caplog)

    with pytest.raises(LoginFailedError):
        await exchange(provider)

    assert_no_secret_in_logs(caplog)
