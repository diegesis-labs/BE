"""모든 기능의 모델이 물려받는 공통 Base. 선언만 둔다.

테이블의 이름, 컬럼, 제약은 docs/ARCHITECTURE.md 6절에 있다. 기능의 모델은 그 기능 폴더의
models.py에 두고, migrations/env.py가 그 모듈을 import해야 테이블이 Base.metadata에 실린다.
"""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# 제약과 인덱스의 이름을 정하는 규칙. 모델과 마이그레이션이 같은 이름을 쓰게 하고, 제약 위반의
# 원인을 이름으로 가려낼 수 있게 한다. CHECK 제약은 이름을 반드시 붙여야 한다.
NAMING_CONVENTION = {
    "pk": "pk_%(table_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
