"""데이터베이스 연결을 조립한다. 판정하는 로직은 두지 않는다.

이 모듈을 import하는 것만으로는 엔진을 만들거나 설정을 읽지 않는다.
단위 테스트는 DATABASE_URL 없이 돌기 때문이다. 엔진은 서버를 조립하는 쪽이나
마이그레이션 환경(migrations/env.py)이 부를 때 만든다.
"""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
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


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    raise NotImplementedError
    yield


DbSession = Annotated[AsyncSession, Depends(get_db_session, scope="function")]
