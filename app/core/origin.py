"""상태를 바꾸는 요청의 출처 확인(docs/API.md 2.4절, ADR-027).

`GET`, `HEAD`, `OPTIONS`가 아닌 모든 요청이 프론트엔드의 화면에서 왔는지 확인한다. 다른 사이트의
화면이 사용자의 쿠키를 실어 상태를 바꾸는 요청을 보내는 것(CSRF)을 막기 위해서다.

1. `Origin` 헤더가 있으면 그 값이 `FRONTEND_URL`과 글자 그대로 같아야 한다. `null`도 같지 않으므로
   거절한다. `Origin`이 있으면 `Referer`는 보지 않는다.
2. `Origin`이 없으면 `Referer`에서 뽑은 출처(스킴과 `호스트[:포트]`)가 `FRONTEND_URL`과 같아야 한다.
3. 둘 다 없으면 거절한다.

거절하면 `403 ORIGIN_MISMATCH`를 API.md 2.3절의 형식으로 응답하고, 요청을 경로로 넘기지 않는다.

이 모듈이 지키는 것은 다음과 같다.

- 앞부분이나 포함 여부가 아니라 정확히 비교한다. 앞부분만 보면 `http://localhost:5173.evil.example`이
  통과한다. `FRONTEND_URL`은 스킴, 호스트, 포트만 담도록 설정 클래스가 검증하므로 정확한 비교로
  충분하다(app/core/config.py).
- 허용할 출처의 목록, 와일드카드, 끄는 설정, 예외로 두는 경로를 두지 않는다. 비교 기준은
  `FRONTEND_URL` 하나다(E1 S1.4, ADR-027).
- `GET`, `HEAD`, `OPTIONS`에서는 설정도 읽지 않는다. 헬스체크와 API 문서는 설정 없이도
  응답해야 한다.
- 거절 응답은 직접 만들어 돌려준다. 이 미들웨어는 예외 처리기의 바깥에서 돌므로, 여기서 AppError를
  던지면 처리기를 만나지 못하고 500이 된다.
- 거절한 요청은 메서드, 경로, 받은 `Origin`이나 `Referer`를 로그에 남기고, 쿠키는 남기지 않는다.
"""

import logging
from urllib.parse import urlsplit

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import get_settings
from app.core.errors import error_response

logger = logging.getLogger(__name__)

# 확인하지 않는 메서드. 이 메서드로는 상태를 바꾸는 경로를 만들지 않는다(API.md 2.4절).
# HTTP 메서드는 대소문자를 가리므로, 이 셋과 글자가 다른 메서드는 모두 확인한다.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

ORIGIN_MISMATCH_MESSAGE = "프론트엔드가 아닌 곳에서 보낸 요청은 받지 않습니다."


def referer_origin(referer: str) -> str | None:
    """Referer에서 출처(스킴과 `호스트[:포트]`)를 뽑는다. 주소로 읽히지 않으면 None이다.

    호스트의 대소문자나 기본 포트를 고쳐 쓰지 않고 받은 글자 그대로 둔다. 브라우저는 이미 고쳐 쓴
    모양으로 보내므로, 다르게 적힌 값은 거절해도 된다.
    """
    try:
        parts = urlsplit(referer)
    except ValueError:
        # 닫히지 않은 IPv6 주소(`http://[::1/`)처럼 urlsplit이 읽지 못하는 값이다.
        return None
    if not parts.scheme or not parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc}"


def is_from_frontend(origin: str | None, referer: str | None, frontend_url: str) -> bool:
    """요청의 Origin과 Referer로 그 요청이 프론트엔드의 화면에서 왔는지 판정한다."""
    if origin is not None:
        # `null`은 FRONTEND_URL과 같을 수 없으므로 여기서 거절된다.
        return origin == frontend_url
    if referer is not None:
        return referer_origin(referer) == frontend_url
    return False


class OriginCheckMiddleware:
    """상태를 바꾸는 요청의 출처를 확인하는 ASGI 미들웨어. create_app()이 앱 전체에 한 번 건다."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # lifespan과 websocket은 HTTP 요청이 아니다. websocket의 연결 요청은 GET이다.
        if scope["type"] != "http" or scope["method"] in SAFE_METHODS:
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        origin = headers.get("origin")
        referer = headers.get("referer")
        if is_from_frontend(origin, referer, get_settings().frontend_url):
            await self.app(scope, receive, send)
            return
        # 판정에 쓴 헤더만 남긴다. %r로 남겨서 값 안의 제어 문자가 로그의 줄을 바꾸지 못하게 한다.
        if origin is not None:
            received = f"Origin={origin!r}"
        elif referer is not None:
            received = f"Referer={referer!r}"
        else:
            received = "Origin과 Referer가 모두 없음"
        logger.warning(
            "출처가 맞지 않아 거절한 요청: %s %s (%s)", scope["method"], scope["path"], received
        )
        response = error_response(403, "ORIGIN_MISMATCH", ORIGIN_MISMATCH_MESSAGE)
        await response(scope, receive, send)
