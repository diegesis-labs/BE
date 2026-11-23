# Step 1: database

## 읽어야 할 파일

먼저 아래 파일들을 읽고 이 step의 근거와 설계 의도를 파악하라:

- `docs/backlog/epic-0/E0-project-setup.md` — "못 박을 것 (Epic 전역)", S0.2
- `docs/backlog/epic-0/testcase.md` — TC-0.2.1 ~ TC-0.2.5
- `docs/ADR.md` — ADR-002, ADR-009, ADR-011
- `docs/DECISIONS.md` — D-37, D-40
- `app/core/config.py`, `app/main.py`, `tests/core/test_config.py`, `tests/test_main.py` (step 0)
- `pyproject.toml`

이전 step에서 만들어진 코드를 꼼꼼히 읽고, 설계 의도를 이해한 뒤 작업하라.

## 작업

### 0. Docker 확인

`docker info`가 실패하면 고치려 하지 말고 `index.json`의 이 step을 `"status": "blocked"`, `"blocked_reason": "Docker에 닿을 수 없다 — Docker Desktop을 켜야 한다"`로 적고 즉시 중단하라. 이 step부터 검사 명령의 통합 테스트가 Docker를 쓴다.

### 1. 의존성

```bash
uv add "sqlalchemy[asyncio]" asyncpg alembic pgvector
uv add --dev testcontainers pytest-asyncio pyyaml
```

pyright가 PyYAML의 타입을 찾지 못하면 `types-PyYAML`을 dev 의존성으로 더한다. `# type: ignore`로 넘기지 마라(DEVELOPMENT.md 4.4절).

### 2. compose의 데이터베이스 서비스 — `compose.yaml`

레포 최상위에 `compose.yaml`을 만들고 `db` 서비스 하나만 둔다. 마이그레이션과 서버 서비스는 step 4가 더한다.

- 이미지는 `pgvector/pgvector`의 태그 가운데 **pgvector 확장의 버전과 PostgreSQL의 주 버전이 모두 박힌 것**을 쓴다(예: `<pgvector 버전>-pg<주 버전>`). PostgreSQL은 최신 안정 주 버전, pgvector는 0.8.0 이상의 최신 안정 버전이다. 고르기 전에 `docker manifest inspect <이미지>`로 그 태그가 실제로 있고 `linux/amd64`와 `linux/arm64`를 모두 제공하는지 확인하라.
- `latest`나 주 버전만 있는 태그(예: `pg18`)를 쓰지 마라. 이유: 확장의 버전이 바뀌면 벡터 검색의 동작이 바뀐다. ARCHITECTURE.md 4절이 말하는 반복 스캔은 pgvector 0.8.0부터 있다.
- `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`는 모두 `diegesis`로 둔다. CONFIGURATION.md 3.2절의 예시 주소와 같고, 로컬에서만 쓰는 값이다.
- 호스트 포트는 `${DB_PORT:-5432}:5432`로 연다. 이유: 로컬에 PostgreSQL을 설치해 5432를 쓰는 개발자가 포트를 바꿀 수 있어야 한다.
- 데이터는 이름 있는 볼륨에 두고, `pg_isready`로 healthcheck를 둔다.
- `platform`과 `env_file`을 적지 마라. 이유: Epic 전역의 못 박을 것이다.

### 3. 데이터베이스 연결 — `app/core/database.py`

```python
def create_engine(url: str | None = None) -> AsyncEngine: ...
    # url이 없으면 get_settings().database_url을 쓴다
def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]: ...
```

- 모듈을 import할 때 엔진을 만들거나 설정을 읽지 마라. 이유: 단위 테스트는 `DATABASE_URL` 없이 돈다(TC-0.1.5).
- 판정하는 로직을 넣지 마라. 이유: TDD 가드의 예외 파일(조립)이다.

### 4. Alembic

- 레포 최상위에 `alembic.ini`를, `migrations/` 아래에 비동기 `env.py`와 템플릿을 둔다. `alembic init -t async`의 결과를 다듬어 써도 된다. 기존 `migrations/.gitkeep`은 지운다.
- 접속 주소를 `alembic.ini`에 적지 마라. `env.py`는 호출한 쪽이 Alembic 설정의 `sqlalchemy.url`로 넘긴 주소가 있으면 그것을 쓰고, 없으면 `get_settings().database_url`을 쓴다. 이유: 설정은 설정 클래스로만 읽고(DEVELOPMENT.md 3절), 테스트는 컨테이너의 주소를 직접 넘겨야 한다.
- 첫 마이그레이션은 하나다. upgrade는 `CREATE EXTENSION IF NOT EXISTS vector`이고, downgrade는 그 확장을 지운다.
- 테이블을 만들지 마라. 이유: Epic 전역의 못 박을 것이다. 모델이 아직 없으므로 `target_metadata`는 비워 둔다.

### 5. 통합 테스트의 기반

- `tests/support/postgres.py`
  - `db_image() -> str` — `compose.yaml`의 `services.db.image`를 읽어 돌려준다.
  - `start_database()` — testcontainers로 `db_image()`의 컨테이너를 무작위 포트로 띄워 돌려준다. Docker에 닿을 수 없으면 `pytest.skip`하지 말고, "통합 테스트에는 Docker가 필요하다"는 뜻의 메시지를 담아 예외를 낸다.
- `tests/conftest.py` — 세션 범위의 fixture가 `start_database()`로 컨테이너를 띄우고, 그 컨테이너의 주소로 `alembic upgrade head`를 실행한 뒤, asyncpg 형식의 주소(`postgresql+asyncpg://...`)를 테스트에 넘긴다. 끝나면 컨테이너를 지운다.
- 이 fixture를 autouse로 만들지 마라. 컨테이너는 그 fixture를 요청한 통합 테스트가 있을 때만 뜬다. 이유: 단위 테스트 하나만 돌릴 때(`uv run pytest tests/core/test_config.py`)에는 Docker가 필요 없어야 한다.
- 통합 테스트에 `integration` marker를 붙이고 `pyproject.toml`에 등록한다.
- 비동기 테스트는 pytest-asyncio로 돌린다. 설정은 `pyproject.toml`의 `[tool.pytest.ini_options]`에 둔다. 기존의 `testpaths`와 `addopts`를 줄이거나 지우지 마라.

### 6. 테스트

- `tests/core/test_database.py` (integration) — TC-0.2.1 ~ TC-0.2.4.
  - TC-0.2.1은 `SELECT extversion FROM pg_extension WHERE extname = 'vector'`의 결과를 버전으로 비교한다. 문자열로 비교하지 마라(`"0.10.0" < "0.8.0"`이 참이 된다).
  - TC-0.2.2의 픽스처: 질의 `[1, 0]`, 행 A `[10, 1]`(코사인 거리 ≈ 0.005, 유클리드 거리 ≈ 9.06), 행 B `[0, 0.5]`(코사인 거리 1, 유클리드 거리 ≈ 1.12). 정답은 A다. `CREATE TEMP TABLE`로 만든 임시 테이블에 `pgvector.sqlalchemy`의 벡터 타입을 쓰고, 코사인 거리로 정렬해 하나를 가져온다. 연결은 `app/core/database.py`의 두 함수로 만든다.
  - TC-0.2.3은 다른 테스트와 같은 컨테이너의 상태를 바꾼다. 테스트가 실패하더라도 끝날 때 반드시 head로 되돌려라.
- `tests/support/test_postgres.py` (unit) — TC-0.2.5. Docker에 닿을 수 없는 상태를 만들고(예: `DOCKER_HOST`를 없는 소켓으로) `start_database()`를 불러, skip이 아니라 오류가 나는지 확인한다.

## Acceptance Criteria

```bash
docker compose config --quiet                                    # compose 파일의 문법
uv run pytest tests/core/test_database.py tests/support -v
scripts/check.sh
```

**반증 조건** — 아래의 틀린 구현으로도 초록이면 그 테스트가 틀린 것이다.

- 유클리드 거리(`<->`, `l2_distance`)로 검색해도 초록이면 TC-0.2.2가 틀렸다.
- 마이그레이션이 확장을 만들지 않거나, 0.8.0 미만의 pgvector 이미지를 써도 초록이면 TC-0.2.1이 틀렸다.
- fixture가 `compose.yaml`과 다른 이미지를 띄워도 초록이면 TC-0.2.4가 틀렸다.
- Docker가 없을 때 `pytest.skip`으로 넘어가도 초록이면 TC-0.2.5가 틀렸다.

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - `docs/ARCHITECTURE.md` 8절의 코드 구조와 의존 방향을 따르는가?
   - `docs/ADR.md`의 기술 스택을 벗어나지 않았는가?
   - `docs/DEVELOPMENT.md`의 "반드시 지킬 규칙"을 위반하지 않았는가?
3. 결과에 따라 `phases/0-project-setup/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"`
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 (API 키, 외부 인증, 수동 설정 등) → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- 통합 테스트가 `.env`, 인자 없이 부른 `get_settings()`, compose의 개발용 데이터베이스(`localhost:5432`)에 접속하게 하지 마라. 이유: 마이그레이션을 되돌리는 테스트가 개발용 데이터를 지운다. 컨테이너의 주소만 명시적으로 넘겨라.
- `docker compose up`으로 개발용 데이터베이스를 띄워서 테스트하지 마라. 이유: 통합 테스트의 데이터베이스는 testcontainers로만 띄운다(ADR-011).
- 데이터베이스 이미지의 이름과 버전을 `compose.yaml` 밖에 적지 마라. 이유: 두 곳에 적으면 갈라진다(DEVELOPMENT.md 1절).
- 기능 테이블과 그 모델을 만들지 마라. 이유: Epic 전역의 못 박을 것이다.
- `scripts/check.sh`가 통합 테스트를 빼고 돌게 만들지 마라(marker로 제외하는 `addopts` 포함). 이유: 무인 step이 통합 테스트를 돌리지 않은 채 완료가 된다(ADR-011).
- 헬스체크나 라우터를 만들지 마라. 이유: 다음 step들의 일이다.
- 기존 테스트를 깨뜨리지 마라
- `MANUAL.md`의 항목을 체크하지 마라. 이유: 그 항목은 사람이 직접 본 것만 체크한다.
