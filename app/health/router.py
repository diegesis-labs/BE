"""헬스체크(docs/API.md 4.1절).

서버 프로세스가 살아 있는지만 확인한다. 데이터베이스, 설정, 외부 서비스에 접근하지 않는다.
데이터베이스에 장애가 났을 때 서버까지 죽은 것으로 판정되면 안 되기 때문이다
(docs/DECISIONS.md의 D-39). 서버와 데이터베이스의 연결은 compose 스모크가 확인한다.
"""

from fastapi import APIRouter

from app.health.schemas import HealthResponse

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def get_health() -> HealthResponse:
    return HealthResponse(status="ok")
