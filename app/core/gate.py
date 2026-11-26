"""보호된 경로의 관문(docs/API.md 2.2절).

보호된 경로는 require_user나 require_admin을 FastAPI 의존성으로 건다. 관문은 아래 순서로 확인하고,
통과하지 못하면 API.md 2.3절의 코드로 거절한다.

1. 로그인 상태의 쿠키가 없거나 비었으면 401 NOT_AUTHENTICATED. 이때 데이터베이스에 닿지 않는다.
2. 쿠키 값의 해시로 찾은 로그인 상태가 없거나 만료됐으면 401 NOT_AUTHENTICATED.
3. 그 사용자의 이메일이 허용 목록에 없으면 403 NOT_ALLOWED.
4. 로그인 상태를 허용 목록에 들어간 시각보다 먼저 만들었으면 401 NOT_AUTHENTICATED. 허용 목록에서
   뺐다가 다시 넣은 사람의 옛 쿠키가 되살아나면 안 되기 때문이다(ADR-027).
5. 관리자 경로인데 역할이 admin이 아니면 403 ADMIN_ONLY. 관리자 관문은 사용자 관문을 먼저 거치므로,
   허용 목록에서 빠진 사람은 ADMIN_ONLY가 아니라 NOT_ALLOWED를 받는다(E1 S1.4).

이 모듈이 지키는 것은 다음과 같다.

- 허용 목록과 역할을 메모리에 담아 두지 않고 요청마다 데이터베이스에서 읽는다. SQL로 뺀 사람이
  서버를 다시 띄우지 않아도 다음 요청부터 막혀야 하기 때문이다(ADR-024).
- 로그인 상태의 행을 바꾸지 않는다. 만료 시각을 늘리거나 마지막 사용 시각을 기록하지 않는다
  (ADR-027).
- 쿠키 값을 로그에 남기지 않는다.
- 기능 폴더를 import하지 않는다. 로그인 상태는 LoginLookup 포트(app/core/ports.py)로 찾고, 그
  구현체(AuthRepository)는 create_app()이 set_login_lookup_factory로 넣는다(ADR-029).
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import DbSession
from app.core.errors import AppError
from app.core.ports import ActiveLogin, LoginLookup
from app.core.security import hash_token

ADMIN_ROLE = "admin"

LoginLookupFactory = Callable[[AsyncSession], LoginLookup]
_LOGIN_LOOKUP_FACTORY = "login_lookup_factory"


def set_login_lookup_factory(app: FastAPI, factory: LoginLookupFactory) -> None:
    """그 앱의 관문이 로그인 상태를 찾을 곳을 요청의 세션으로 만드는 함수를 넣어 둔다.

    create_app()이 부른다. 구현체 자체가 아니라 만드는 함수를 넣는 이유는, 찾는 곳이 요청마다의
    데이터베이스 세션(get_db_session)을 써야 하기 때문이다.
    """
    setattr(app.state, _LOGIN_LOOKUP_FACTORY, factory)


def get_login_lookup(request: Request, session: DbSession) -> LoginLookup:
    """요청을 받은 앱의 관문이 로그인 상태를 찾는 곳. FastAPI 의존성이다.

    세션은 첫 질의를 보낼 때 데이터베이스에 접속하므로(get_db_session), 쿠키가 없어 찾지 않는
    요청은 데이터베이스에 닿지 않는다. 조립되지 않은 앱이면 바로 실패한다. 조용히 다른 곳을 보면
    관문이 엉뚱한 저장소를 보고 통과할 수 있기 때문이다.
    """
    factory: LoginLookupFactory | None = getattr(request.app.state, _LOGIN_LOOKUP_FACTORY, None)
    if factory is None:
        raise RuntimeError(
            "관문이 로그인 상태를 찾을 곳이 없다. "
            "create_app()처럼 set_login_lookup_factory를 불러라."
        )
    return factory(session)


@dataclass(frozen=True)
class CurrentUser:
    """관문을 통과한 사용자."""

    id: UUID
    email: str
    display_name: str | None
    role: str  # "user" 또는 "admin". 이번 요청에서 허용 목록에서 읽은 값이다.


def _not_authenticated() -> AppError:
    return AppError(401, "NOT_AUTHENTICATED", "로그인이 필요합니다.")


def authorize(login: ActiveLogin | None) -> CurrentUser:
    """찾은 로그인 상태로 사용자 관문의 2~4번을 판정한다. 통과하지 못하면 AppError를 던진다."""
    if login is None:
        raise _not_authenticated()
    if login.allowed is None:
        raise AppError(403, "NOT_ALLOWED", "허용 목록에 없는 계정입니다.")
    # 같은 시각이면 통과다. 두 시각은 모두 데이터베이스의 now()에서 나온다(app/auth/models.py).
    if login.session_created_at < login.allowed.created_at:
        raise _not_authenticated()
    return CurrentUser(
        id=login.user.id,
        email=login.user.email,
        display_name=login.user.display_name,
        role=login.allowed.role,
    )


async def require_user(
    request: Request, lookup: Annotated[LoginLookup, Depends(get_login_lookup)]
) -> CurrentUser:
    """로그인한 사용자를 요구하는 관문.

    lookup을 받아도 세션은 첫 질의를 보낼 때 데이터베이스에 접속하므로(get_db_session), 쿠키가
    없을 때에는 데이터베이스에 닿지 않는다.
    """
    token = request.cookies.get(get_settings().login_cookie_name)
    if not token:
        raise _not_authenticated()
    return authorize(await lookup.find_active_login(hash_token(token)))


async def require_admin(user: Annotated[CurrentUser, Depends(require_user)]) -> CurrentUser:
    """관리자를 요구하는 관문. 사용자 관문을 먼저 거친다."""
    if user.role != ADMIN_ROLE:
        raise AppError(403, "ADMIN_ONLY", "관리자만 쓸 수 있는 경로입니다.")
    return user
