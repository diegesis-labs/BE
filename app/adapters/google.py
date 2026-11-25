"""IdentityProvider 포트의 Google 구현(ADR-028). 아직 시그니처만 있다."""

from typing import Self

import httpx

from app.core.config import Settings
from app.core.ports import Identity

AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
CALLBACK_PATH = "/api/auth/google/callback"
TOKEN_REQUEST_TIMEOUT_SECONDS = 10.0


class GoogleIdentityProvider:
    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        raise NotImplementedError

    @classmethod
    def from_settings(
        cls, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> Self:
        raise NotImplementedError

    def authorization_url(self, *, state: str, nonce: str, code_verifier: str) -> str:
        raise NotImplementedError

    async def exchange_code(
        self, *, code: str, code_verifier: str, expected_nonce: str
    ) -> Identity:
        raise NotImplementedError
