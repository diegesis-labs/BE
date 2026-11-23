# Step 3: health-router

## 읽어야 할 파일

먼저 아래 파일들을 읽고 이 step의 근거와 설계 의도를 파악하라:

- `docs/backlog/epic-0/E0-project-setup.md` — "못 박을 것 (Epic 전역)", S0.4
- `docs/backlog/epic-0/testcase.md` — TC-0.4.1 ~ TC-0.4.3
- `docs/API.md` 4.1절 — 헬스체크의 요청과 응답
- `docs/DECISIONS.md` — D-39 (헬스체크는 데이터베이스를 확인하지 않는다)
- `app/main.py`, `app/core/errors.py`, `app/core/config.py`, `tests/core/test_errors.py`, `tests/test_main.py` (step 0, 2)

이전 step에서 만들어진 코드를 꼼꼼히 읽고, 설계 의도를 이해한 뒤 작업하라.

## 작업

### 1. 헬스체크 — `app/health/`

- `app/health/__init__.py`
- `app/health/schemas.py` — 응답 형식. `status` 필드 하나이며 값은 `"ok"`뿐이다(OpenAPI 문서에 형식이 드러나게 한다).
- `app/health/router.py` — `GET /api/health`가 200과 `{"status": "ok"}`를 돌려준다. 접두사 `/api`는 라우터에 둔다.

`create_app()`이 이 라우터를 등록한다. ARCHITECTURE.md 8절대로 `health/`에는 `router.py`와 `schemas.py`만 둔다. 규칙도 저장할 데이터도 없기 때문이다.

### 2. 테스트 — `tests/health/test_router.py`

TC-0.4.1 ~ TC-0.4.3.

- TC-0.4.2: 환경변수 `DATABASE_URL`을 `postgresql+asyncpg://u:p@127.0.0.1:1/x`로 두고 `get_settings()`의 캐시를 비운 뒤, `create_app()`으로 만든 앱에 요청한다. 데이터베이스에 질의하는 구현이면 실패하거나 오래 걸려야 한다.
- 본문은 `== {"status": "ok"}`로 정확히 비교한다. 키가 있는지만 보지 마라.

### 3. 순서 — RED 커밋을 남긴다

1. `tests/health/test_router.py`를 먼저 쓴다.
2. 테스트가 기대한 이유(404 `NOT_FOUND`)로 실패하는 것을 눈으로 확인한다.
3. 테스트만 담아 `test(0-project-setup): RED — GET /api/health가 서버 상태를 돌려준다`로 커밋한다.
4. 구현해서 초록으로 만든다.

## Acceptance Criteria

```bash
uv run pytest tests/health/test_router.py -v
scripts/check.sh
```

**반증 조건** — 아래의 틀린 구현으로도 초록이면 그 테스트가 틀린 것이다.

- 헬스체크가 데이터베이스에 `SELECT 1`을 보내도 초록이면 TC-0.4.2가 틀렸다.
- 응답이 `{"status": "ok", "db": "ok"}`처럼 키가 더 있어도 초록이면 TC-0.4.1이 틀렸다.
- 경로가 `/health`(접두사 없음)여도 초록이면 TC-0.4.1이 틀렸다.
- `POST /api/health`가 FastAPI의 기본 형식으로 나가도 초록이면 TC-0.4.3이 틀렸다.

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. `git log --oneline`에 RED 커밋이 구현 커밋보다 먼저 있는지 확인한다.
3. 아키텍처 체크리스트를 확인한다:
   - `docs/ARCHITECTURE.md` 8절의 코드 구조와 의존 방향을 따르는가?
   - `docs/ADR.md`의 기술 스택을 벗어나지 않았는가?
   - `docs/DEVELOPMENT.md`의 "반드시 지킬 규칙"을 위반하지 않았는가?
4. 결과에 따라 `phases/0-project-setup/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"`
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 (API 키, 외부 인증, 수동 설정 등) → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- 헬스체크에서 데이터베이스, 설정, 외부 서비스에 접근하지 마라. 이유: 데이터베이스에 장애가 났을 때 서버까지 죽은 것으로 판정되면 안 된다(D-39).
- 준비 상태 확인 엔드포인트(`/api/health/ready` 등)를 만들지 마라. 이유: API.md에 없는 엔드포인트이며, 배포 환경이 요구할 때 만든다(D-39).
- `app/main.py`에 경로를 직접 정의하지 마라. 이유: `app/main.py`는 조립만 하는 TDD 가드의 예외다.
- 기존 테스트를 깨뜨리지 마라
- `MANUAL.md`의 항목을 체크하지 마라. 이유: 그 항목은 사람이 직접 본 것만 체크한다.
