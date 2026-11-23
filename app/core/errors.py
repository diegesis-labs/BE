"""모든 에러 응답을 {code, message, detail} 형식으로 바꾼다(docs/API.md 2.3절)."""

from fastapi import FastAPI


class AppError(Exception):
    def __init__(
        self, status_code: int, code: str, message: str, detail: object | None = None
    ) -> None: ...


def register_error_handlers(app: FastAPI) -> None: ...
