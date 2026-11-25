"""보호된 경로의 관문. (RED 단계의 빈 껍데기: 언제나 통과시킨다.)"""

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request

from app.auth.repository import AuthRepository, get_auth_repository


@dataclass(frozen=True)
class CurrentUser:
    id: UUID
    email: str
    display_name: str | None
    role: str


async def require_user(
    request: Request, repo: Annotated[AuthRepository, Depends(get_auth_repository)]
) -> CurrentUser:
    return CurrentUser(id=UUID(int=0), email="", display_name=None, role="admin")


async def require_admin(user: Annotated[CurrentUser, Depends(require_user)]) -> CurrentUser:
    return user
