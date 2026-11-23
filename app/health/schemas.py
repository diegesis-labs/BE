"""헬스체크의 응답 형식(docs/API.md 4.1절)."""

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    # 값은 "ok"뿐이다. 서버가 응답했다는 것 자체가 살아 있다는 뜻이므로 다른 값을 두지 않는다.
    status: Literal["ok"]
