"""모든 에러 응답을 {code, message, detail} 형식으로 바꾼다(docs/API.md 2.3절).

기능 코드는 정해진 에러를 AppError로 던진다. 요청 검증 실패, HTTP 예외(없는 경로의 404와 405 포함),
처리되지 않은 예외는 여기의 처리기가 같은 형식으로 바꾼다. `detail`은 값이 있을 때에만 넣는다.
"""

import logging
from collections.abc import Mapping, Sequence
from http import HTTPStatus
from typing import cast

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

# docs/API.md 2.3절의 표에서 상태만으로 code가 하나로 정해지는 HTTP 예외의 code와 message.
# 403은 NOT_ALLOWED와 ADMIN_ONLY 두 가지라서 상태만으로 고를 수 없다. 그 기능이 AppError로 던진다.
# 표에 없는 상태는 HTTPStatus의 이름을 code로 쓴다(예: 409 → CONFLICT).
_HTTP_ERRORS: dict[int, tuple[str, str]] = {
    401: ("NOT_AUTHENTICATED", "로그인이 필요합니다."),
    404: ("NOT_FOUND", "요청한 대상을 찾을 수 없습니다."),
    405: ("METHOD_NOT_ALLOWED", "이 경로에서는 쓸 수 없는 메서드입니다."),
}
_OTHER_HTTP_ERROR_MESSAGE = "요청을 처리할 수 없습니다."
_VALIDATION_ERROR_MESSAGE = "요청 형식이 올바르지 않습니다."
_INTERNAL_ERROR_MESSAGE = "서버에서 예상하지 못한 문제가 생겼습니다."

# 요청 검증 오류의 위치(loc)에서 첫 요소로 오는 값. 필드 이름에는 넣지 않는다.
_REQUEST_LOCATIONS = frozenset({"body", "query", "path", "header", "cookie"})


class AppError(Exception):
    """기능 코드가 정해진 에러 응답을 내보낼 때 던지는 예외. 값이 응답에 그대로 나간다."""

    def __init__(
        self, status_code: int, code: str, message: str, detail: object | None = None
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.detail = detail


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _handle_app_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    # FastAPI의 HTTPException은 Starlette의 것을 물려받는다.
    # 없는 경로의 404와 405는 Starlette가 낸다.
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
    # Exception에 건 처리기는 Starlette가 가장 바깥의 ServerErrorMiddleware에서 부른다.
    app.add_exception_handler(Exception, _handle_unhandled_exception)


def _error_response(
    status_code: int,
    code: str,
    message: str,
    detail: object | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    content: dict[str, object] = {"code": code, "message": message}
    if detail is not None:
        content["detail"] = jsonable_encoder(detail)
    return JSONResponse(status_code=status_code, content=content, headers=headers)


# 처리기는 Starlette의 형식대로 (Request, Exception)을 받는다. 각 처리기는 등록한 예외에만 불리므로
# cast로 그 타입을 알린다.


async def _handle_app_error(request: Request, exc: Exception) -> JSONResponse:
    error = cast(AppError, exc)
    return _error_response(error.status_code, error.code, error.message, error.detail)


async def _handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
    errors = cast(RequestValidationError, exc).errors()
    detail = [{"field": _field_name(error["loc"]), "reason": str(error["msg"])} for error in errors]
    return _error_response(400, "VALIDATION_ERROR", _VALIDATION_ERROR_MESSAGE, detail)


def _field_name(loc: Sequence[object]) -> str:
    """("body", "item", "price")를 "item.price"로 바꾼다. 목록의 순번도 한 마디로 잇는다."""
    parts = list(loc)
    if parts and parts[0] in _REQUEST_LOCATIONS:
        parts = parts[1:]
    return ".".join(str(part) for part in parts)


async def _handle_http_exception(request: Request, exc: Exception) -> JSONResponse:
    error = cast(StarletteHTTPException, exc)
    status_code = error.status_code
    code, message = _HTTP_ERRORS.get(
        status_code, (HTTPStatus(status_code).name, _OTHER_HTTP_ERROR_MESSAGE)
    )
    # 예외의 detail은 응답에 담지 않는다. 영어 원문("Not Found")이거나
    # 던진 쪽의 내부 사정일 수 있다. 405의 Allow처럼 예외가 함께 실은 헤더는 그대로 보낸다.
    return _error_response(status_code, code, message, headers=error.headers)


async def _handle_unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    # 응답에는 예외의 메시지, 타입, 스택을 넣지 않는다. 저작권이 있는 본문이나
    # 데이터베이스 주소 같은 내부 정보가 새면 안 되기 때문이다(docs/ARCHITECTURE.md 1절).
    # 예외는 서버 로그에만 스택과 함께 남긴다.
    logger.exception("처리되지 않은 예외: %s %s", request.method, request.url.path, exc_info=exc)
    return _error_response(500, "INTERNAL_ERROR", _INTERNAL_ERROR_MESSAGE)
