"""Google 로그인을 시작하는 경로와 로그인 결과를 받는 경로(docs/API.md 4.2절)."""

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, Response

from app.auth.service import AuthService
from app.core.config import get_settings
from app.core.ports import IdentityProvider

router = APIRouter(prefix="/api", tags=["auth"])

OAUTH_STATE_COOKIE = "diegesis_oauth_state"


def get_identity_provider(request: Request) -> IdentityProvider:
    raise NotImplementedError


def get_auth_service() -> AuthService:
    raise NotImplementedError


def _login_failed() -> Response:
    return RedirectResponse(
        f"{get_settings().frontend_url}/login?error=LOGIN_FAILED", status_code=302
    )


@router.get("/auth/google/login")
async def start_google_login() -> Response:
    return _login_failed()


@router.get("/auth/google/callback")
async def finish_google_login() -> Response:
    return _login_failed()
