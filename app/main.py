"""서버의 시작점. 앱을 만들고 라우터와 어댑터를 조립한다.

이 모듈을 import하거나 create_app()을 부르는 것만으로는 설정을 읽지 않는다.
단위 테스트는 DATABASE_URL 없이 돌기 때문이다. 설정은 서버를 실행하는 진입점(app/__main__.py)이,
또는 설정이 필요한 코드가 처음 쓸 때 읽는다.
"""

from fastapi import FastAPI

from app.adapters.google import GoogleIdentityProvider
from app.auth.repository import AuthRepository
from app.auth.router import router as auth_router
from app.auth.router import set_identity_provider_factory
from app.core.database import database_lifespan
from app.core.errors import register_error_handlers
from app.core.gate import set_login_lookup_factory
from app.core.origin import OriginCheckMiddleware
from app.health.router import router as health_router


def create_app() -> FastAPI:
    # 모든 경로에 /api 접두사를 붙인다(docs/API.md 1절).
    # 문서도 그 아래에 두고, 기본 경로(/openapi.json, /docs, /redoc)는 열지 않는다.
    # 문서 화면의 OAuth2 로그인이 돌아오는 경로(/docs/oauth2-redirect)도 쓰지 않으므로 닫는다.
    app = FastAPI(
        title="Diegesis BE",
        openapi_url="/api/openapi.json",
        docs_url="/api/docs",
        redoc_url=None,
        swagger_ui_oauth2_redirect_url=None,
        # 앱이 내려갈 때 그 앱의 데이터베이스 엔진을 닫는다. 시작할 때에는 설정을 읽지 않는다.
        lifespan=database_lifespan,
    )
    # 모든 에러 응답을 {code, message, detail} 형식으로 바꾼다(docs/API.md 2.3절).
    register_error_handlers(app)
    # 상태를 바꾸는 모든 요청의 출처를 확인한다(docs/API.md 2.4절, ADR-027). 경로마다 걸지 않고
    # 앱 전체에 한 번 건다. 등록되지 않은 경로, 공개 경로, 이후에 더할 경로까지 빠짐없이 걸리게 하기
    # 위해서다. 설정은 요청을 받았을 때 읽는다.
    app.add_middleware(OriginCheckMiddleware)
    app.include_router(health_router)
    app.include_router(auth_router)
    # 로그인 경로의 신원 제공자는 Google 어댑터다. 어댑터를 아는 곳은 이 파일뿐이다
    # (docs/ARCHITECTURE.md 8절). 어댑터 자체가 아니라 설정으로 어댑터를 만드는 함수를 넣어 두므로,
    # 여기서는 설정을 읽지 않는다. 어댑터는 로그인 경로가 요청을 받았을 때 만든다.
    set_identity_provider_factory(app, GoogleIdentityProvider.from_settings)
    # 관문(app/core/gate.py)이 로그인 상태를 찾는 곳은 auth의 repository다. core는 기능 폴더를
    # import하지 않으므로 이 파일이 잇는다(ADR-029). 요청마다 그 요청의 세션으로 만든다.
    set_login_lookup_factory(app, AuthRepository)
    return app


app = create_app()
