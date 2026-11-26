"""IdentityProvider 포트의 Google 구현(ADR-028).

httpx로 Google의 토큰 엔드포인트와 통신하고, 인가 주소, PKCE, ID 토큰의 클레임 확인은 표준
라이브러리로 직접 구현한다. 확인하는 클레임은 docs/API.md 4.2절의 설명과 ADR-027에 있다.

- ID 토큰은 토큰 엔드포인트가 TLS로 돌려준 응답에서만 받으므로 서명은 확인하지 않는다(ADR-027).
  그래서 Google의 공개키를 받아 오지 않는다. 그 대신 클레임을 하나도 빠짐없이 확인한다.
- 실패는 원인이 무엇이든 LoginFailedError 하나로 바꾼다. service는 그 메시지를 로그에 남기므로,
  메시지에는 원인만 적고 code, code_verifier, nonce, 클라이언트 비밀값, 응답 본문, 토큰은 넣지
  않는다(E1 S1.2 "못 박을 것").
- 이 어댑터는 요청을 받지 않는다. 돌아올 주소는 FRONTEND_URL로만 만들고, 요청의 Host로 만들지
  않는다(ADR-025).
"""

import base64
import hashlib
import json
import math
import re
import time
from typing import Any, Self
from urllib.parse import quote, urlencode

import httpx

from app.core import security
from app.core.config import Settings
from app.core.ports import Identity, LoginFailedError

# 두 주소는 코드의 상수다. 설정값이나 요청에서 받지 않는다(E1 S1.2 "못 박을 것").
AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
CALLBACK_PATH = "/api/auth/google/callback"

# Google에는 이 세 범위만 요청한다. 다른 범위를 요청하면 사용자에게 경고 화면이 보인다(ADR-025).
SCOPE = "openid email profile"
# Google이 ID 토큰의 iss에 쓰는 두 값(docs/API.md 4.2절).
ISSUERS = frozenset({"https://accounts.google.com", "accounts.google.com"})
# Google이 응답하지 않을 때 로그인 요청이 끝없이 붙들려 있지 않도록 연결, 읽기, 쓰기, 연결 풀 대기에
# 모두 이 시간을 건다.
TOKEN_REQUEST_TIMEOUT_SECONDS = 10.0

# JWT의 각 부분은 패딩 없는 base64url이다. 표준 base64의 `+`, `/`와 패딩 `=`는 받지 않는다.
_BASE64URL = re.compile(r"[A-Za-z0-9_-]+")


def _code_challenge(code_verifier: str) -> str:
    """PKCE의 S256: code_verifier의 SHA-256을 패딩 없는 base64url로 바꾼 값(RFC 7636 4.2절)."""
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


# 아래 두 도우미는 풀지 못하면 예외를 내지 않고 None을 돌려준다. 부르는 쪽이 except 블록 밖에서
# LoginFailedError를 내야, 풀려던 바이트를 담은 원래의 예외(UnicodeDecodeError 등)가 그 예외의
# __context__로 남지 않는다. 그 바이트는 응답 본문이나 토큰이다.


def _decode_base64url(segment: str) -> bytes | None:
    if not _BASE64URL.fullmatch(segment):
        return None
    try:
        return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))
    except ValueError:
        return None


def _loads_json_object(data: bytes) -> dict[str, Any] | None:
    """UTF-8 JSON 객체로 풀 수 있으면 그 객체를 돌려준다. 배열, 문자열 같은 값도 None이다."""
    try:
        value = json.loads(data.decode("utf-8"))
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def _decode_id_token_payload(id_token: str) -> dict[str, Any]:
    """ID 토큰의 가운데 부분(payload)을 JSON 객체로 푼다. 서명은 확인하지 않는다(ADR-027)."""
    parts = id_token.split(".")
    if len(parts) != 3:
        raise LoginFailedError("ID 토큰이 세 부분으로 나뉘지 않음")
    raw = _decode_base64url(parts[1])
    if raw is None:
        raise LoginFailedError("ID 토큰의 payload가 base64url이 아님")
    claims = _loads_json_object(raw)
    if claims is None:
        raise LoginFailedError("ID 토큰의 payload가 JSON 객체가 아님")
    return claims


def _is_future_timestamp(value: object) -> bool:
    """exp가 숫자이고 지금보다 뒤인지. 불리언, 문자열, 무한대, NaN은 숫자로 보지 않는다."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return False
    # NaN은 어떤 비교도 거짓이라 `<=`만으로는 걸러지지 않는다. int는 isfinite에 넘기지 않는다.
    # 아주 큰 정수를 float로 바꾸다 OverflowError가 나기 때문이다.
    if isinstance(value, float) and not math.isfinite(value):
        return False
    return value > time.time()


class GoogleIdentityProvider:
    """Google의 OpenID Connect로 신원을 확인한다. IdentityProvider 포트를 구조적으로 만족한다."""

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """transport는 테스트가 httpx.MockTransport를 넣는 자리다.

        없으면 httpx의 기본 전송을 쓴다.
        """
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._transport = transport

    @classmethod
    def from_settings(
        cls, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> Self:
        """돌아올 주소는 FRONTEND_URL 뒤에 CALLBACK_PATH를 붙여 만든다(INFRA.md 3.5절)."""
        return cls(
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret.get_secret_value(),
            redirect_uri=settings.frontend_url + CALLBACK_PATH,
            transport=transport,
        )

    def authorization_url(self, *, state: str, nonce: str, code_verifier: str) -> str:
        """Google의 인가 주소. 매개변수는 docs/API.md 4.2절의 예시에 있는 여덟 개뿐이다.

        code_verifier는 주소에 넣지 않고, 그 SHA-256(code_challenge)만 넣는다.
        """
        params = {
            "client_id": self._client_id,
            "redirect_uri": self._redirect_uri,
            "response_type": "code",
            "scope": SCOPE,
            "state": state,
            "nonce": nonce,
            "code_challenge": _code_challenge(code_verifier),
            "code_challenge_method": "S256",
        }
        # docs/API.md 4.2절의 예시처럼 공백은 `+`가 아니라 `%20`으로, `/`와 `:`도 인코딩해서 쓴다.
        # urlencode는 quote에 safe=""를 넘긴다.
        return f"{AUTHORIZATION_ENDPOINT}?{urlencode(params, quote_via=quote)}"

    async def exchange_code(
        self, *, code: str, code_verifier: str, expected_nonce: str
    ) -> Identity:
        """code를 토큰으로 바꾸고 ID 토큰의 클레임을 모두 확인해서 신원을 돌려준다."""
        body = await self._request_tokens(code=code, code_verifier=code_verifier)
        id_token = body.get("id_token")
        if not isinstance(id_token, str):
            raise LoginFailedError("토큰 응답에 id_token이 없음")
        claims = _decode_id_token_payload(id_token)
        return self._identity_from_claims(claims, expected_nonce=expected_nonce)

    async def _request_tokens(self, *, code: str, code_verifier: str) -> dict[str, Any]:
        """토큰 엔드포인트에 폼 본문으로 code를 보내고, 200 응답의 JSON 객체를 돌려준다."""
        form = {
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": code_verifier,
            # 인가 주소에 넣은 것과 같은 값이어야 Google이 교환을 받아들인다.
            "redirect_uri": self._redirect_uri,
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        }
        try:
            # 리다이렉트는 따라가지 않는다. ID 토큰은 TOKEN_ENDPOINT의 응답에서만 받는다(ADR-027).
            async with httpx.AsyncClient(
                transport=self._transport,
                timeout=TOKEN_REQUEST_TIMEOUT_SECONDS,
                follow_redirects=False,
            ) as client:
                response = await client.post(TOKEN_ENDPOINT, data=form)
        except httpx.HTTPError as error:
            # httpx의 예외 메시지에는 요청 본문이 들어가지 않으므로, 원인을 알 수 있게 잇는다.
            raise LoginFailedError(
                f"토큰 엔드포인트와 통신하지 못함({type(error).__name__})"
            ) from error
        if response.status_code != 200:
            raise LoginFailedError(f"토큰 교환이 {response.status_code}로 실패함")
        body = _loads_json_object(response.content)
        if body is None:
            raise LoginFailedError("토큰 응답의 본문이 JSON 객체가 아님")
        return body

    def _identity_from_claims(self, claims: dict[str, Any], *, expected_nonce: str) -> Identity:
        """ID 토큰의 클레임을 모두 확인한다(docs/API.md 4.2절, ADR-027). 하나라도 어긋나면 실패다.

        email_verified는 확인 조건이 아니라 돌려주는 값이다. 거르는 것은 service의 일이다.
        """
        iss = claims.get("iss")
        if not (isinstance(iss, str) and iss in ISSUERS):
            raise LoginFailedError("ID 토큰의 iss가 Google이 아님")
        aud = claims.get("aud")
        # 목록이면 원소가 우리의 클라이언트 ID 하나뿐이어야 한다. 들어 있기만 한 것은 받지 않는다.
        if isinstance(aud, list):
            aud = aud[0] if len(aud) == 1 else None
        if not self._is_our_client_id(aud):
            raise LoginFailedError("ID 토큰의 aud가 클라이언트 ID와 다름")
        if "azp" in claims and not self._is_our_client_id(claims["azp"]):
            raise LoginFailedError("ID 토큰의 azp가 클라이언트 ID와 다름")
        if not _is_future_timestamp(claims.get("exp")):
            raise LoginFailedError("ID 토큰의 exp가 없거나 지났음")
        nonce = claims.get("nonce")
        if not (isinstance(nonce, str) and security.secure_equals(nonce, expected_nonce)):
            raise LoginFailedError("ID 토큰의 nonce가 기대한 값과 다름")
        sub = claims.get("sub")
        if not (isinstance(sub, str) and sub):
            raise LoginFailedError("ID 토큰에 sub가 없음")
        email = claims.get("email")
        if not (isinstance(email, str) and email):
            raise LoginFailedError("ID 토큰에 email이 없음")
        email_verified = claims.get("email_verified")
        name = claims.get("name")
        return Identity(
            sub=sub,
            email=email,
            # Google은 불리언으로 주지만, 문자열 "true"로 주는 경우도 받아들인다.
            email_verified=email_verified is True or email_verified == "true",
            name=name if isinstance(name, str) else None,
        )

    def _is_our_client_id(self, value: object) -> bool:
        """우리의 클라이언트 ID와 같은지. 클라이언트 ID가 비어 있으면 어떤 값도 같지 않다.

        CI의 compose 스모크는 GOOGLE_CLIENT_ID 없이 서버를 띄운다(app/core/config.py). 그 서버가
        aud가 빈 토큰을 받아들이면 안 된다.
        """
        return self._client_id != "" and value == self._client_id
