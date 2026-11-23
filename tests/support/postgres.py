"""통합 테스트용 데이터베이스를 띄우는 도구(docs/ADR.md의 ADR-011).

데이터베이스의 이미지는 compose.yaml의 db 서비스에서 읽는다. 이미지의 이름과 버전을 여기에 다시 적지
않는다. 두 곳에 적으면 갈라지기 때문이다(docs/DEVELOPMENT.md 1절, 4.3절).
"""

from pathlib import Path

import yaml
from alembic.config import Config
from docker.errors import DockerException
from testcontainers.community.postgres import PostgresContainer

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = REPO_ROOT / "compose.yaml"
ALEMBIC_INI = REPO_ROOT / "alembic.ini"

# 컨테이너 안에서만 쓰는 계정이다. 무작위 포트로 뜨므로 개발용 데이터베이스와 부딪히지 않는다.
DATABASE_USER = "diegesis"
DATABASE_PASSWORD = "diegesis"
DATABASE_NAME = "diegesis"


class DockerUnavailableError(RuntimeError):
    """Docker에 닿을 수 없어서 통합 테스트용 데이터베이스를 띄우지 못했다."""


def db_image(compose_file: Path = COMPOSE_FILE) -> str:
    """compose 파일의 db 서비스의 이미지."""
    compose = yaml.safe_load(compose_file.read_text(encoding="utf-8"))
    return str(compose["services"]["db"]["image"])


def start_database() -> PostgresContainer:
    """db_image()의 컨테이너를 무작위 포트로 띄워 돌려준다.

    다 쓰면 부른 쪽이 stop()으로 지운다. Docker에 닿을 수 없으면 건너뛰지(skip) 않고
    DockerUnavailableError를 낸다. 건너뛰면 통합 테스트를 하나도 돌리지 않았는데도
    검사가 통과한 것처럼 보이기 때문이다.
    """
    try:
        container = PostgresContainer(
            image=db_image(),
            username=DATABASE_USER,
            password=DATABASE_PASSWORD,
            dbname=DATABASE_NAME,
            driver="asyncpg",
        )
        # 컨테이너를 만들기 전에 Docker에 닿는지 먼저 확인한다. 이미지를 받지 못하는 것처럼
        # Docker에 닿은 뒤에 나는 오류를 "Docker가 없다"로 잘못 알리지 않기 위해서다.
        container.get_docker_client().client.ping()
    except (DockerException, OSError) as error:
        # requests의 연결 오류는 OSError를 잇는다.
        raise DockerUnavailableError(
            "통합 테스트에는 Docker가 필요하다. Docker Desktop을 켠 뒤 다시 실행해라. "
            f"(Docker에 닿지 못했다: {error})"
        ) from error
    return container.start()


def alembic_config(url: str) -> Config:
    """레포의 alembic.ini를 쓰되, 접속 주소는 넘겨받은 것을 쓰는 Alembic 설정.

    migrations/env.py는 이 주소가 있으면 설정 클래스를 읽지 않는다.
    통합 테스트는 마이그레이션을 돌릴 때 반드시 이것으로 컨테이너의 주소를 넘긴다.
    """
    config = Config(str(ALEMBIC_INI))
    # Alembic의 설정은 ConfigParser로 다루므로, %를 %%로 바꿔야 주소가 그대로 들어간다.
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config
