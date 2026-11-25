"""로그인 기능의 응답 형식(docs/API.md 4.3절)."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class MeResponse(BaseModel):
    """GET /api/me의 응답. 관문이 돌려준 사용자(app/core/gate.py의 CurrentUser)의 값 그대로다."""

    # CurrentUser(dataclass)의 속성을 그대로 읽어 만든다.
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    display_name: str | None
    # 허용 목록에 적힌 역할이다. 관문이 이번 요청에서 허용 목록에서 읽은 값이다.
    role: Literal["user", "admin"]
