"""관문을 건 경로를 붙인 앱. 관문의 단위 테스트와 통합 테스트가 함께 쓰며, 이 도우미의 약속은
tests/support/test_gated_app.py가 본다.

앱은 create_app()으로 만든다. 관문을 따로 만든 앱에만 걸어서 확인하면, 실제 앱의 조립(에러 처리기
등)이 빠져도 초록이 되기 때문이다. 관문을 건 경로는 여기에서만 붙이고 app/ 아래에 두지 않는다.
실제 서버에 테스트용 경로가 열리면 안 되기 때문이다.
"""

from typing import Annotated

from fastapi import Depends, FastAPI

from app.core.gate import CurrentUser, require_admin, require_user
from app.main import create_app

USER_ROUTE = "/api/_test/user"
ADMIN_ROUTE = "/api/_test/admin"


def describe(user: CurrentUser) -> dict[str, str | None]:
    """관문이 돌려준 CurrentUser의 값. 두 경로의 응답 본문이다."""
    return {
        "id": str(user.id),
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
    }


def create_gated_app() -> FastAPI:
    """USER_ROUTE에 require_user를, ADMIN_ROUTE에 require_admin을 건 앱."""
    app = create_app()

    @app.get(USER_ROUTE)
    async def user_route(
        user: Annotated[CurrentUser, Depends(require_user)],
    ) -> dict[str, str | None]:
        return describe(user)

    @app.get(ADMIN_ROUTE)
    async def admin_route(
        user: Annotated[CurrentUser, Depends(require_admin)],
    ) -> dict[str, str | None]:
        return describe(user)

    return app
