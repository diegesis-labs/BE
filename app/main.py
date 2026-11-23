"""서버의 시작점. 앱을 만들고 라우터와 어댑터를 조립한다.

이 모듈을 import하거나 create_app()을 부르는 것만으로는 설정을 읽지 않는다.
단위 테스트는 DATABASE_URL 없이 돌기 때문이다. 설정은 서버를 실행하는 진입점(app/__main__.py)이,
또는 설정이 필요한 코드가 처음 쓸 때 읽는다.
"""

from fastapi import FastAPI

from app.core.errors import register_error_handlers
from app.health.router import router as health_router


def create_app() -> FastAPI:
    # 모든 경로에 /api 접두사를 붙인다(docs/API.md 1절).
    # 문서도 그 아래에 두고, 기본 경로(/openapi.json, /docs, /redoc)는 열지 않는다.
    app = FastAPI(
        title="Diegesis BE",
        openapi_url="/api/openapi.json",
        docs_url="/api/docs",
        redoc_url=None,
    )
    # 모든 에러 응답을 {code, message, detail} 형식으로 바꾼다(docs/API.md 2.3절).
    register_error_handlers(app)
    app.include_router(health_router)
    return app


app = create_app()
