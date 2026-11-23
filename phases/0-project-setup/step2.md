# Step 2: error-format

## 읽어야 할 파일

먼저 아래 파일들을 읽고 이 step의 근거와 설계 의도를 파악하라:

- `docs/backlog/epic-0/E0-project-setup.md` — "못 박을 것 (Epic 전역)", S0.3
- `docs/backlog/epic-0/testcase.md` — TC-0.3.1 ~ TC-0.3.5
- `docs/API.md` 2.3절 — 에러 응답의 형식, 에러 코드 표, 표에 없는 상태 코드의 `code`
- `app/main.py`, `tests/test_main.py` (step 0)
- `app/core/config.py`, `app/core/database.py`, `tests/conftest.py` (step 0, 1)

이전 step에서 만들어진 코드를 꼼꼼히 읽고, 설계 의도를 이해한 뒤 작업하라.

## 작업

### 1. 에러 처리기 — `app/core/errors.py`

```python
class AppError(Exception):
    def __init__(self, status_code: int, code: str, message: str,
                 detail: object | None = None) -> None: ...

def register_error_handlers(app: FastAPI) -> None: ...
```

`create_app()`(`app/main.py`)이 `register_error_handlers`를 부르게 한다. 모든 에러 응답의 본문은 `{"code", "message", "detail"}`이며, `detail`은 값이 있을 때에만 넣는다. 값이 없으면 키 자체를 빼라(API.md 2.3절).

| 무엇이 일어났나 | 상태 | `code` | `message` | `detail` |
| --- | --- | --- | --- | --- |
| `AppError` | 예외의 값 | 예외의 값 | 예외의 값 | 예외의 값(없으면 키를 뺀다) |
| 요청 검증 실패 | 400 | `VALIDATION_ERROR` | `요청 형식이 올바르지 않습니다.` | `[{"field": ..., "reason": ...}, ...]` |
| HTTP 예외 401 | 401 | `NOT_AUTHENTICATED` | 한국어 문장 | 없음 |
| HTTP 예외 404 (없는 경로 포함) | 404 | `NOT_FOUND` | 한국어 문장 | 없음 |
| HTTP 예외 405 | 405 | `METHOD_NOT_ALLOWED` | 한국어 문장 | 없음 |
| 그 밖의 HTTP 예외 | 그 상태 | `HTTPStatus(상태).name` (예: 409 → `CONFLICT`) | 한국어 문장 | 없음 |
| 처리되지 않은 예외 | 500 | `INTERNAL_ERROR` | 한국어 문장 | 없음 |

- **검증 실패의 `field`**: 오류 위치에서 첫 요소(`body`, `query`, `path`, `header`, `cookie`)를 뺀 나머지를 점으로 잇는다. 예를 들어 `("body", "item", "price")`는 `item.price`다. `reason`은 pydantic의 메시지를 그대로 써도 된다.
- **500**: 응답에는 예외의 메시지, 타입, 스택을 넣지 마라. 예외는 서버 로그에 스택과 함께 남긴다(`logging`의 `exception`). 이유: 저작권이 있는 본문이나 데이터베이스 주소 같은 내부 정보가 응답으로 새면 안 된다(ARCHITECTURE.md 1절).
- **HTTP 예외**: FastAPI의 것만이 아니라 Starlette의 HTTP 예외도 처리하라. 이유: 없는 경로의 404와 405는 Starlette가 낸다.
- 403은 `NOT_ALLOWED`와 `ADMIN_ONLY` 두 가지가 있어서 상태만으로는 고를 수 없다. 이 step에서는 정하지 마라. 그 Epic들이 `AppError`로 던진다.

### 2. 테스트 — `tests/core/test_errors.py`

TC-0.3.1 ~ TC-0.3.5. 테스트는 `create_app()`으로 만든 앱을 쓴다. 검증 실패, 처리되지 않은 예외, `AppError`를 일으킬 경로는 테스트 안에서만 그 앱에 붙인다. 이유: 처리기를 따로 만든 앱에만 등록해서 확인하면, `create_app()`이 처리기를 등록하지 않아도 초록이 된다.

- 처리되지 않은 예외를 확인할 때에는 `TestClient(app, raise_server_exceptions=False)`를 쓴다.
- TC-0.3.3의 예외 메시지에는 `postgresql://user:secret-pw@db/x` 같은 문자열을 넣고, 응답의 텍스트 전체에 `secret-pw`가 없는지 확인한다.
- TC-0.3.1은 본문의 키 집합이 정확히 `{"code", "message"}`인지 확인한다.

### 3. 순서 — RED 커밋을 남긴다

이 step은 판정하는 로직을 만든다. 다음 순서를 지켜라(DEVELOPMENT.md 4.1절).

1. `tests/core/test_errors.py`를 먼저 쓴다. 그다음 `app/core/errors.py`에 시그니처만 있고 아무 일도 하지 않는 빈 껍데기(`AppError`, 처리기를 등록하지 않는 `register_error_handlers`)를 두고 `create_app()`이 그것을 부르게 한다. 이유: 그래야 테스트가 import 오류가 아니라 실제 동작의 차이(422가 나감, 기본 형식이 나감)로 실패한다.
2. 테스트가 실패하는 것을 눈으로 확인한다. 기대한 이유로 실패하는지 본다.
3. 테스트와 빈 껍데기만 담아 `test(0-project-setup): RED — 에러 응답을 {code, message, detail} 형식으로 바꾼다`로 커밋한다.
4. 구현해서 초록으로 만든다.

## Acceptance Criteria

```bash
uv run pytest tests/core/test_errors.py -v
scripts/check.sh
```

**반증 조건** — 아래의 틀린 구현으로도 초록이면 그 테스트가 틀린 것이다.

- 검증 실패가 FastAPI의 기본인 422로 나가도 초록이면 TC-0.3.2가 틀렸다.
- `field`에 `body.item.price`처럼 위치가 붙어 나가도 초록이면 TC-0.3.2가 틀렸다.
- 처리되지 않은 예외의 메시지를 `message`나 `detail`에 담아도 초록이면 TC-0.3.3이 틀렸다.
- `{"detail": "Not Found"}`가 그대로 나가거나, 본문에 `code`와 `message` 밖의 키가 있어도 초록이면 TC-0.3.1이 틀렸다.
- `detail`이 없을 때 `"detail": null`이 나가도 초록이면 TC-0.3.5가 틀렸다.
- `create_app()`이 처리기를 등록하지 않아도 초록이면 테스트가 앱을 잘못 만든 것이다.

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

- 응답에 예외의 내용이나 스택을 넣지 마라. 이유: 위 1번.
- API.md 2.3절에 없는 에러 코드를 표의 상태에 새로 만들지 마라(예: 404에 `ROUTE_NOT_FOUND`). 이유: 에러 코드는 프론트엔드와 맺은 약속이다. 표에 없는 상태만 `HTTPStatus`의 이름을 쓴다.
- `docs/API.md`를 고치지 마라. 이유: 이번 Epic의 개정은 이미 끝났다. 고칠 곳을 찾으면 summary에 적어라.
- 헬스체크 라우터를 만들지 마라. 이유: step 3의 일이다.
- 테스트용 경로를 `app/` 아래에 두지 마라. 이유: 실제 서버에 테스트용 경로가 열린다.
- 기존 테스트를 깨뜨리지 마라
- `MANUAL.md`의 항목을 체크하지 마라. 이유: 그 항목은 사람이 직접 본 것만 체크한다.
