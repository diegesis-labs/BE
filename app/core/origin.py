"""상태를 바꾸는 요청의 출처 확인(docs/API.md 2.4절). 아직 확인하지 않는 껍데기다."""

from starlette.types import ASGIApp, Receive, Scope, Send


class OriginCheckMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self.app(scope, receive, send)
