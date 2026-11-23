# 서버의 컨테이너 이미지. 로컬에서는 docker compose로만 빌드한다(docs/DECISIONS.md의 D-41).
#
# - 빌드 단계에서 uv로 uv.lock대로 운영 의존성만 설치하고, 실행 단계에는 가상환경과 실행에 필요한 것
#   (app/, migrations/, alembic.ini)만 복사한다.
# - Python 베이스 이미지의 주 버전과 부 버전은 `.python-version`과 같아야 한다. 두 단계가 같은 이미지를
#   써야 가상환경의 python 경로가 실행 단계에서도 맞는다(tests/infra/test_dockerfile.py가 확인한다).
# - uv의 버전은 CI가 설치하는 uv와 같아야 한다(docs/DEVELOPMENT.md 1절).
# - `.env`와 비밀값을 넣지 않는다. Docker Hub 저장소가 공개다(D-37). `.dockerignore`도 `.env`를 뺀다.
# - 셸 스크립트를 진입점으로 두지 않는다. Windows의 git이 CRLF로 받은 셸 스크립트는 컨테이너 안에서 깨진다.

FROM python:3.14-slim AS build

COPY --from=ghcr.io/astral-sh/uv:0.12.6 /uv /uvx /bin/

# UV_PYTHON_DOWNLOADS=0: 베이스 이미지의 Python을 쓰고, uv가 다른 Python을 받아 오지 않게 한다.
# UV_COMPILE_BYTECODE=1: 실행 단계는 root가 아닌 사용자라 __pycache__를 쓸 수 없으므로 미리 컴파일한다.
# UV_LINK_MODE=copy: 캐시가 다른 마운트에 있으므로 링크 대신 복사한다.
ENV UV_PYTHON_DOWNLOADS=0 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

COPY pyproject.toml uv.lock .python-version ./
# --locked: uv.lock이 pyproject.toml과 어긋나면 고치지 않고 실패한다. --no-dev: 개발 도구는 넣지 않는다.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project


FROM python:3.14-slim AS runtime

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# 서버는 root가 아닌 사용자로 돈다. 복사한 파일은 root의 것으로 두어 서버가 고칠 수 없게 한다.
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --no-create-home \
       --home-dir /nonexistent --shell /usr/sbin/nologin app

WORKDIR /app

COPY --from=build /app/.venv /app/.venv
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./

# 배포 환경이 이름이 아니라 번호로 root인지 판정하는 경우가 있어 번호로 적는다.
USER 10001:10001

EXPOSE 8080

CMD ["python", "-m", "app"]
