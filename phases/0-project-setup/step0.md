# Step 0: app-skeleton

## 읽어야 할 파일

먼저 아래 파일들을 읽고 이 step의 근거와 설계 의도를 파악하라:

- `docs/backlog/epic-0/E0-project-setup.md` — "못 박을 것 (Epic 전역)", S0.1
- `docs/backlog/epic-0/testcase.md` — TC-0.1.1 ~ TC-0.1.5
- `docs/API.md` 1절 — OpenAPI 문서의 경로(`/api/openapi.json`)
- `pyproject.toml`, `.python-version`, `.env.example`
- `scripts/hooks/tdd-guard.sh` — "개별 파일 예외"의 `app/__main__.py`

이 레포에는 아직 서버 코드가 없다. `app/` 아래의 기능 폴더에는 `.gitkeep`만 있다.

## 작업

### 1. 의존성

```bash
uv add fastapi uvicorn pydantic-settings
uv add --dev httpx
```

버전은 uv가 고르는 최신 안정 버전을 그대로 쓴다(`pyproject.toml`의 하한, `uv.lock`의 정확한 버전). `uvicorn`에 extras(`[standard]`)를 붙이지 마라. 이유: 쓰지 않는 의존성이 늘어난다.

### 2. 설정 클래스 — `app/core/config.py`

```python
class Settings(BaseSettings):
    port: int = 8080                                                    # PORT
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"    # LOG_LEVEL
    database_url: str                                                   # DATABASE_URL, 기본값 없음

def get_settings() -> Settings: ...   # 한 번 만든 인스턴스를 재사용한다
```

- 이 세 값만 선언한다. 이유: CONFIGURATION.md 1절 — 클래스에는 코드가 실제로 읽는 값만 둔다. `GOOGLE_CLIENT_ID` 같은 필수값까지 넣으면 compose와 CI에서 서버가 시작되지 않는다.
- 프로젝트 최상위의 `.env`를 읽고, 같은 이름이 있으면 환경변수가 우선한다.
- `.env`에 클래스에 없는 값이 있어도 오류를 내지 않고 무시한다. pydantic-settings의 기본 동작은 거부다. 이유: `.env.example`에 다음 Epic들의 값이 이미 있어서, 기본 동작대로 두면 `cp .env.example .env`를 하자마자 설정을 읽지 못한다.
- `database_url`에 기본값을 넣지 마라. 이유: 값이 없으면 서버가 시작하는 순간 실패해야 한다(CONFIGURATION.md 1절).

### 3. 앱 조립 — `app/main.py`

```python
def create_app() -> FastAPI: ...
app = create_app()
```

- OpenAPI 문서는 `/api/openapi.json`, 문서 화면은 `/api/docs`에 둔다. 기본 경로(`/openapi.json`, `/docs`, `/redoc`)는 열지 않는다.
- `import app.main`과 `create_app()`은 설정을 읽지 않는다. `DATABASE_URL`이 없어도 둘 다 성공해야 한다. 이유: 단위 테스트는 데이터베이스 설정 없이 돈다. 설정은 서버를 실행하는 진입점이, 또는 설정이 필요한 코드가 처음 쓸 때 읽는다.
- 라우터와 에러 처리기는 다음 step들이 여기에 등록한다. 지금은 라우트가 없는 앱이다.

### 4. 서버 진입점 — `app/__main__.py`

`python -m app`으로 서버를 띄운다. `get_settings()`에서 `port`와 `log_level`을 읽어 uvicorn에 넘기고, host는 `0.0.0.0`으로 둔다. 컨테이너 안에서 바깥의 요청을 받아야 하기 때문이다. 이 파일은 TDD 가드의 개별 예외로 이미 등록되어 있다.

- uvicorn을 실행하는 것 외의 로직을 넣지 마라. 이유: 테스트 없이 통과하는 파일이다.
- 설정은 반드시 `get_settings()`로 읽는다. `os.environ`을 직접 읽지 마라(DEVELOPMENT.md 3절).

### 5. 테스트

- `tests/core/test_config.py` — TC-0.1.1 ~ TC-0.1.4.
  - 테스트는 개발자의 실제 `.env`를 읽으면 안 된다. 임시 폴더를 만들어 그 안의 `.env`만 읽게 하고(작업 경로를 옮기거나 `.env` 경로를 명시), 관련 환경변수를 지운 상태에서 확인하라.
  - TC-0.1.2의 `.env`에는 `.env.example`에 실제로 있는 이름(`APP_ENV`, `GOOGLE_CLIENT_ID`, `RECOMMENDATION_TOP_K` 등)을 넣어라.
  - `get_settings()`의 캐시가 테스트 사이에 새지 않게 하라.
- `tests/test_main.py` — TC-0.1.5. `DATABASE_URL`을 지운 상태에서 `app.main`을 import하고, `create_app()`으로 만든 앱을 `TestClient`로 요청한다.

이 step의 대상 파일(설정 클래스, 조립, 진입점)은 모두 TDD 가드의 예외라서 RED 커밋은 요구하지 않는다. 그래도 테스트를 먼저 쓰고 실패를 확인한 뒤 구현하라.

## Acceptance Criteria

```bash
uv run pytest tests/core/test_config.py tests/test_main.py -v
scripts/check.sh
```

**반증 조건** — 아래의 틀린 구현으로도 초록이면 그 테스트가 틀린 것이다.

- `database_url`에 기본값을 넣어도 초록이면 TC-0.1.1이 틀렸다.
- 클래스에 없는 값을 거부하는 기본 동작을 그대로 두어도 초록이면 TC-0.1.2가 틀렸다.
- 환경변수보다 `.env`가 우선해도 초록이면 TC-0.1.3이 틀렸다.
- OpenAPI를 `/openapi.json`에 그대로 두어도 초록이면 TC-0.1.5가 틀렸다.
- 테스트가 개발자의 `.env`를 읽어야만 통과한다면 틀렸다. `.env`가 없는 CI에서 결과가 달라진다.

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

- 이 step이 쓰지 않는 의존성(SQLAlchemy, Alembic, authlib 등)을 넣지 마라. 이유: 쓰는 코드가 없는 의존성은 검증할 수 없다(D-31). 데이터베이스 의존성은 step 1이 넣는다.
- 설정 클래스에 `PORT`, `LOG_LEVEL`, `DATABASE_URL` 밖의 값을 넣지 마라. 이유: 위 2번.
- `app/core/config.py` 밖에서 환경변수를 읽지 마라. 이유: DEVELOPMENT.md 3절.
- `.env.example`과 `docs/CONFIGURATION.md`를 고치지 마라. 이유: 이 step은 새 설정값을 만들지 않으며, 세 값은 이미 문서에 있다.
- 라우터, 에러 처리기, 데이터베이스 코드를 만들지 마라. 이유: 다음 step들의 일이다.
- `.env` 파일을 만들거나 읽지 마라. 이유: 비밀값이 들어 있는 개발자의 파일이다. 테스트는 임시 폴더의 `.env`만 쓴다.
- 기존 테스트를 깨뜨리지 마라
- `MANUAL.md`의 항목을 체크하지 마라. 이유: 그 항목은 사람이 직접 본 것만 체크한다.
