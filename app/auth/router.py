"""Google 로그인을 시작하는 경로와 로그인 결과를 받는 경로(docs/API.md 4.2절).

무엇을 확인하고 무엇을 쓰는지는 service(app/auth/service.py)가 정한다. 라우터는 쿼리와 쿠키를
service에 넘기고, 그 결과를 리디렉션 주소와 쿠키로 바꾼다. 이 모듈이 지키는 것은 다음과 같다.

- 어댑터를 import하지 않는다. 신원 제공자는 create_app()이 set_identity_provider_factory로 넣어 둔
  함수로 만든다. 어댑터는 서버가 시작될 때 주입된다(docs/ARCHITECTURE.md 8절). 테스트는
  app.dependency_overrides[get_identity_provider]로 가짜를 끼운다.
- Location은 FRONTEND_URL로만 만든다. 요청의 Host나 주소로 만들지 않는다. 로그인 뒤에 돌아갈 곳을
  받는 매개변수(next, redirect 등)도 받지 않는다. 언제나 첫 화면으로 돌아간다(ADR-025).
- 실패의 원인은 Location에 담지 않는다. error의 값은 NOT_ALLOWED와 LOGIN_FAILED뿐이다(ADR-025).
  원인은 service가 로그에만 남긴다.
- 결과 처리는 리디렉션으로만 끝난다. 그래서 쿼리는 모두 선택으로 받는다. 필수로 받으면 빠졌을 때
  FastAPI가 400 VALIDATION_ERROR를 낸다.
- 두 경로는 GET이지만 상태를 바꾼다. 출처 확인(app/core/origin.py)은 GET을 보지 않으므로 이 둘은
  state, nonce, PKCE로 지킨다. 이 두 경로 말고는 상태를 바꾸는 GET 경로를 만들지 않는다(ADR-027).
- 임의의 값을 만들지 않는다. service가 security.new_token()으로 만든다(ADR-027).
- 성공했을 때의 쓰기는 DbSession(app/core/database.py)이 경로 함수가 끝난 뒤, 응답을 보내기 전에
  커밋한다. 커밋이 실패하면 이 경로가 만든 응답과 쿠키는 나가지 않고 500이 나간다.
"""

from collections.abc import Callable
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import RedirectResponse, Response

from app.auth.repository import AuthRepository, get_auth_repository
from app.auth.service import AuthService, LoginSucceeded
from app.core.config import Settings, get_settings
from app.core.ports import IdentityProvider

router = APIRouter(prefix="/api", tags=["auth"])

# 로그인 시작이 심고 결과 처리가 지우는 쿠키. 값은 "{state}.{nonce}.{code_verifier}"다.
OAUTH_STATE_COOKIE = "diegesis_oauth_state"
# 이 쿠키는 두 경로에만 붙는다. 지울 때에도 같은 경로를 붙여야 한다. 브라우저는 이름과 경로가 모두
# 같은 쿠키만 지운다.
OAUTH_STATE_COOKIE_PATH = "/api/auth/google"
# 로그인을 시작하고 Google의 화면에서 돌아오기까지의 시간(10분).
OAUTH_STATE_MAX_AGE_SECONDS = 600
SESSION_COOKIE_PATH = "/"
SECONDS_PER_HOUR = 3600

IdentityProviderFactory = Callable[[Settings], IdentityProvider]
_IDENTITY_PROVIDER_FACTORY = "identity_provider_factory"


def set_identity_provider_factory(app: FastAPI, factory: IdentityProviderFactory) -> None:
    """그 앱의 로그인 경로가 쓸 신원 제공자를 만드는 함수를 넣어 둔다. create_app()이 부른다.

    신원 제공자 자체가 아니라 만드는 함수를 넣는 이유는, create_app()과 앱의 시작이 설정을 읽지
    않아야 하기 때문이다(tests/test_main.py). 설정은 요청을 받았을 때 읽는다.
    """
    setattr(app.state, _IDENTITY_PROVIDER_FACTORY, factory)


def get_identity_provider(request: Request) -> IdentityProvider:
    """요청을 받은 앱의 신원 제공자. 이 요청에서 읽은 설정으로 만든다. FastAPI 의존성이다."""
    factory: IdentityProviderFactory = getattr(request.app.state, _IDENTITY_PROVIDER_FACTORY)
    return factory(get_settings())


def get_auth_service(
    repository: Annotated[AuthRepository, Depends(get_auth_repository)],
    identity_provider: Annotated[IdentityProvider, Depends(get_identity_provider)],
) -> AuthService:
    """요청의 저장소, 신원 제공자, LOGIN_SESSION_TTL_HOURS로 만든 service. FastAPI 의존성이다.

    저장소의 세션은 첫 질의를 보낼 때 데이터베이스에 접속한다. 그래서 저장소에 닿지 않는 로그인
    시작은 데이터베이스에 접속하지 않는다.
    """
    session_ttl = timedelta(hours=get_settings().login_session_ttl_hours)
    return AuthService(repository, identity_provider, session_ttl=session_ttl)


AuthServiceDependency = Annotated[AuthService, Depends(get_auth_service)]


def _redirect(location: str) -> Response:
    # RedirectResponse의 기본값은 307이다. 로그인의 두 경로는 302로 보낸다(docs/API.md 4.2절).
    return RedirectResponse(location, status_code=302)


def _set_cookie_header(name: str, value: str, *, path: str, max_age: int, secure: bool) -> str:
    """쿠키를 심는 Set-Cookie의 값. 속성은 docs/API.md 4.2절의 예시와 같은 표기로 적는다.

    Secure는 FRONTEND_URL의 스킴으로만 정한다(settings.cookie_secure, ADR-027). 쿠키 이름에
    `__Host-` 접두사는 붙이지 않는다(ADR-027이 받아들인 위험).
    """
    attributes = [f"{name}={value}", "HttpOnly", "SameSite=Lax", f"Path={path}"]
    attributes.append(f"Max-Age={max_age}")
    if secure:
        attributes.append("Secure")
    return "; ".join(attributes)


@router.get("/auth/google/login", status_code=302, response_class=RedirectResponse)
async def start_google_login(service: AuthServiceDependency) -> Response:
    """브라우저를 Google의 로그인 화면으로 보내고, state, nonce, code_verifier를 쿠키에 담는다."""
    settings = get_settings()
    start = service.start_login()
    response = _redirect(start.authorization_url)
    response.headers.append(
        "set-cookie",
        _set_cookie_header(
            OAUTH_STATE_COOKIE,
            start.state_cookie,
            path=OAUTH_STATE_COOKIE_PATH,
            max_age=OAUTH_STATE_MAX_AGE_SECONDS,
            secure=settings.cookie_secure,
        ),
    )
    return response


@router.get("/auth/google/callback", status_code=302, response_class=RedirectResponse)
async def finish_google_login(
    request: Request,
    service: AuthServiceDependency,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> Response:
    """Google이 돌려준 로그인 결과를 확인하고, 브라우저를 프론트엔드의 주소로 보낸다.

    로그인에 성공했을 때에만 로그인 상태의 쿠키를 심는다. 어느 경우든 diegesis_oauth_state를 지운다.
    """
    settings = get_settings()
    result = await service.complete_login(
        state_cookie=request.cookies.get(OAUTH_STATE_COOKIE),
        state=state,
        code=code,
        error=error,
        current_session_token=request.cookies.get(settings.login_cookie_name),
    )
    if isinstance(result, LoginSucceeded):
        response = _redirect(f"{settings.frontend_url}/")
        response.headers.append(
            "set-cookie",
            _set_cookie_header(
                settings.login_cookie_name,
                result.session_token,
                path=SESSION_COOKIE_PATH,
                max_age=settings.login_session_ttl_hours * SECONDS_PER_HOUR,
                secure=settings.cookie_secure,
            ),
        )
    else:
        response = _redirect(f"{settings.frontend_url}/login?error={result.error}")
    response.headers.append(
        "set-cookie", f"{OAUTH_STATE_COOKIE}=; Max-Age=0; Path={OAUTH_STATE_COOKIE_PATH}"
    )
    return response


@router.post("/auth/logout", status_code=204)
async def logout() -> Response:
    return Response(status_code=204)
