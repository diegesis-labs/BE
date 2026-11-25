"""데이터베이스 연결을 조립한다. 판정하는 로직은 두지 않는다.

이 모듈을 import하는 것만으로는 엔진을 만들거나 설정을 읽지 않는다.
단위 테스트는 DATABASE_URL 없이 돌기 때문이다. 엔진은 서버를 조립하는 쪽이나
마이그레이션 환경(migrations/env.py)이 부를 때 만든다.

서버의 엔진은 앱 인스턴스마다 하나이며, 요청이 처음 세션을 받을 때 만들어 app.state에 둔다.
create_app()과 앱의 시작은 설정을 읽지 않아야 하고(tests/test_main.py), 모듈 전역에 둔 엔진은
다른 이벤트 루프에서 만든 연결을 다시 써서 asyncpg가 실패하기 때문이다. 앱이 내려갈 때
database_lifespan이 그 엔진을 닫는다.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings


def create_engine(url: str | None = None) -> AsyncEngine:
    """비동기 엔진을 만든다. 주소를 주지 않으면 설정 클래스의 database_url을 쓴다.

    통합 테스트는 컨테이너의 주소를 직접 넘긴다. 개발자의 `.env`에 든 주소에 접속하지 않기 위해서다.
    """
    return create_async_engine(url if url is not None else get_settings().database_url)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    # 커밋한 뒤에도 객체의 값을 읽을 수 있게 한다. 비동기 세션에서는 만료된 속성을 읽을 때
    # 암묵적으로 질의를 보낼 수 없기 때문이다.
    return async_sessionmaker(engine, expire_on_commit=False)


def _session_factory(app: FastAPI) -> async_sessionmaker[AsyncSession]:
    """그 앱의 세션 팩토리. 처음 부를 때 설정을 읽어 엔진과 함께 만든다."""
    factory: async_sessionmaker[AsyncSession] | None = getattr(
        app.state, "db_session_factory", None
    )
    if factory is None:
        engine = create_engine()
        factory = create_session_factory(engine)
        app.state.db_engine = engine
        app.state.db_session_factory = factory
    return factory


@asynccontextmanager
async def database_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """앱이 내려갈 때 그 앱의 엔진을 닫는다.

    시작할 때에는 아무것도 하지 않는다. 설정을 읽거나 엔진을 만들지 않는다. 엔진을 만든 적이 없으면
    닫을 것도 없다.
    """
    try:
        yield
    finally:
        engine: AsyncEngine | None = getattr(app.state, "db_engine", None)
        if engine is not None:
            del app.state.db_session_factory
            del app.state.db_engine
            await engine.dispose()


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """요청 하나에 세션과 트랜잭션 하나를 준다.

    경로가 정상으로 끝나면 커밋하고, 예외가 나면 되돌린다. 로그인에 성공했을 때의 쓰기처럼 여러 번의
    쓰기가 한 트랜잭션이어야 하기 때문이다(E1 S1.3). 그래서 repository는 커밋하지 않는다.

    세션은 첫 질의를 보낼 때 데이터베이스에 접속한다. 질의하지 않은 요청은 데이터베이스에 닿지
    않는다. 이 의존성은 반드시 DbSession을 거쳐 쓴다.
    """
    async with _session_factory(request.app)() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        await session.commit()


# scope="function"이면 경로 함수가 끝난 뒤, 응답을 보내기 전에 위의 커밋이 돈다. 기본값
# (scope="request")은 응답을 보낸 뒤에 정리하므로, 커밋이 실패해도 클라이언트는 이미 성공 응답과
# 쿠키를 받는다.
DbSession = Annotated[AsyncSession, Depends(get_db_session, scope="function")]
