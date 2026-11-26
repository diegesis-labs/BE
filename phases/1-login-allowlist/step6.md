# Step 6: gate

## 읽어야 할 파일

먼저 아래 파일들을 읽고 이 step의 근거와 설계 의도를 파악하라:

- `docs/backlog/epic-1/E1-login-allowlist.md` — "못 박을 것 (Epic 전역)", S1.4(T1.4.1과 "못 박을 것")
- `docs/backlog/epic-1/testcase.md` — TC-1.4.1 ~ TC-1.4.5, TC-1.4.9
- `docs/API.md` 2.2절 — 관문의 **동작 순서**와 거절할 때의 응답 표, 2.3절 — 에러 응답의 형식과 코드
- `docs/ADR.md` — ADR-024의 결정, ADR-027의 "로그인 상태의 수명"
- `app/auth/repository.py`의 `find_active_login`, `ActiveLogin`, `get_auth_repository` (step 2)
- `app/core/database.py`의 `get_db_session`, `DbSession` (step 2)
- `app/core/security.py`의 `hash_token` (step 3)
- `app/core/errors.py`의 `AppError` (Epic 0)
- `app/core/config.py`의 `login_cookie_name` (step 0)
- `tests/auth/fakes.py`의 `FakeAuthStore` (step 5), `tests/conftest.py`의 `app_env`, `clean_db` (step 0, 1)

`docs/ARCHITECTURE.md` 6절의 로그인 상태 수명 표("보호된 경로를 요청할 때")는 프롬프트에 이미 들어 있다.

이전 step에서 만들어진 코드를 꼼꼼히 읽고, 설계 의도를 이해한 뒤 작업하라.

## 작업

보호된 경로가 거치는 관문을 FastAPI 의존성 두 개로 만든다. 이 Epic의 `GET /api/me`와 이후 Epic의 모든 보호된 경로가 이것을 쓴다.

### 1. 관문 — `app/core/gate.py`

```python
@dataclass(frozen=True)
class CurrentUser:
    id: UUID
    email: str
    display_name: str | None
    role: str        # "user" 또는 "admin". 이번 요청에서 허용 목록에서 읽은 값이다.

async def require_user(request: Request, repo: AuthRepository = Depends(get_auth_repository)) -> CurrentUser: ...
async def require_admin(user: CurrentUser = Depends(require_user)) -> CurrentUser: ...
```

API.md 2.2절의 동작 순서를 그대로 따른다.

1. 설정의 `login_cookie_name`(기본 `diegesis_session`) 쿠키가 없거나 비었으면 `401 NOT_AUTHENTICATED`. **이때 데이터베이스에 닿지 않는다.**
2. `repo.find_active_login(hash_token(쿠키 값))`이 `None`이면(모르는 값이거나 만료됨) `401 NOT_AUTHENTICATED`.
3. `allowed`가 `None`이면(허용 목록에 없음) `403 NOT_ALLOWED`.
4. `session_created_at`이 `allowed.created_at`보다 이르면 `401 NOT_AUTHENTICATED`. 같거나 늦으면 통과다. 이유: 허용 목록에서 뺐다가 다시 넣은 사람의 옛 쿠키가 되살아나면 안 된다(ADR-027).
5. `CurrentUser`를 돌려준다. `role`은 `allowed.role`이다.

`require_admin`은 `require_user`를 거친 뒤 `role`이 `admin`이 아니면 `403 ADMIN_ONLY`를 낸다. 관리자 관문이 사용자 관문을 먼저 거치므로, 허용 목록에서 빠진 사람은 `ADMIN_ONLY`가 아니라 `NOT_ALLOWED`를 받는다(E1 S1.4 "못 박을 것").

- 거절은 `AppError(status_code, code, message)`로 던진다. 코드는 API.md 2.3절의 표에 있는 것만 쓴다. 메시지는 한국어 문장이다.
- **관문은 행을 바꾸지 않는다.** 만료 시각을 늘리거나 마지막 사용 시각을 기록하지 않는다(E1 S1.4 "못 박을 것").
- **허용 목록과 역할을 메모리에 담아 두지 않는다.** 요청마다 데이터베이스에서 읽는다(ADR-024).
- 판정(2~5번)을 `ActiveLogin | None`을 받는 순수 함수로 떼어 두면 단위 테스트가 쉬워진다. 그렇게 할지는 재량이다.
- 쿠키 값을 로그에 남기지 마라.

### 2. 테스트

관문을 건 경로는 테스트 안에서만 앱에 붙인다(예: `GET /api/_test/user`는 `require_user`를 걸고 `CurrentUser`의 값을 돌려주고, `GET /api/_test/admin`은 `require_admin`을 건다). 앱은 `create_app()`으로 만든다. 이유: 관문을 따로 만든 앱에만 걸어서 확인하면, 실제 앱의 조립(에러 처리기 등)이 빠져도 초록이 된다.

- `tests/core/test_gate.py` (`unit`, `app_env`)
  - TC-1.4.1: 쿠키 없이, 그리고 모르는 쿠키 값으로 호출하면 둘 다 `401`이고 본문이 `{"code": "NOT_AUTHENTICATED", "message": ...}`다. 모르는 값의 경우에는 `app.dependency_overrides[get_auth_repository]`로 `find_active_login`이 `None`을 돌려주는 가짜를 끼운다(`tests/auth/fakes.py`의 `FakeAuthStore`에 `find_active_login`을 더해도 된다).
  - 쿠키가 없을 때 데이터베이스에 닿지 않음: 저장소를 바꾸지 않은 채(`DATABASE_URL`은 `app_env`의 닿지 않는 주소) 쿠키 없이 호출해도 `401`이고 500이 아니다.
  - 판정의 경우를 가짜로 하나씩: 허용 목록에 없음 → `403 NOT_ALLOWED`, 로그인 상태를 허용 목록에 들어간 시각보다 먼저 만듦 → `401`, 두 시각이 같음 → 통과, 역할이 `user`인데 관리자 경로 → `403 ADMIN_ONLY`, 허용 목록에 없는데 관리자 경로 → `403 NOT_ALLOWED`.
- `tests/core/test_gate_integration.py` (`integration`, `clean_db`). 로그인 경로는 아직 없으므로, 로그인 상태는 테스트가 직접 만든다. `security.new_token()`으로 쿠키 값을 만들고, 그 `hash_token`으로 `users`, `allowed_emails`, `login_sessions`에 행을 넣는다.
  - TC-1.4.2: 만료 시각이 지난 로그인 상태 → `401 NOT_AUTHENTICATED`.
  - TC-1.4.3: **앱과 `TestClient`를 다시 만들지 않은 채** SQL로 그 사람의 `allowed_emails` 행만 지움 → `403 NOT_ALLOWED`. SQL로 다시 넣음 → 같은 쿠키는 `401 NOT_AUTHENTICATED`. 다시 넣은 **뒤에** 새 트랜잭션에서 만든 새 로그인 상태의 쿠키 → `200`. (다시 로그인하는 것은 이렇게 흉내 낸다. 로그인 경로로 하는 확인은 뒤의 step이 한다.)
  - TC-1.4.4: 역할 `user` → 관리자 경로 `403 ADMIN_ONLY`. 앱을 다시 만들지 않은 채 SQL로 `admin`으로 바꿈 → 같은 쿠키로 `200`.
  - TC-1.4.5: 허용 목록에서 빠진 사람이 관리자 경로 → `403 NOT_ALLOWED`.
  - TC-1.4.9: 사용자 경로를 세 번 호출한 전후로 그 `login_sessions` 행의 모든 컬럼 값이 같다.

### 3. 순서 — RED 커밋을 남긴다

1. 위 테스트를 먼저 쓰고, `require_user`와 `require_admin`은 언제나 통과시키는 빈 껍데기로 둔다.
2. 테스트가 실패하는 것을 눈으로 확인한다.
3. `test(1-login-allowlist): RED — 요청마다 로그인 상태, 허용 목록, 역할을 확인하는 관문`으로 커밋한다.
4. 구현해서 초록으로 만든다.

## Acceptance Criteria

```bash
uv run pytest tests/core/test_gate.py tests/core/test_gate_integration.py -v
scripts/check.sh
```

**반증 조건** — 아래의 틀린 구현으로도 초록이면 그 테스트가 틀린 것이다.

- 허용 목록을 확인하지 않아도, 또는 앱을 만들 때 한 번 읽어 메모리에 담아 두어도 초록이면 TC-1.4.3이 틀렸다(앱을 다시 만들지 않은 채 SQL로 바꿔야 드러난다).
- 다시 넣은 뒤에 옛 로그인 상태가 통과해도(`created_at`을 비교하지 않아도) 초록이면 TC-1.4.3이 틀렸다.
- `created_at`이 같을 때 거절해도 초록이면 판정 테스트가 틀렸다.
- 역할을 처음 확인한 값으로 기억해 두어도 초록이면 TC-1.4.4가 틀렸다.
- 관리자 관문이 역할부터 봐서 허용 목록 밖의 사람에게 `ADMIN_ONLY`를 내도 초록이면 TC-1.4.5가 틀렸다.
- 관문이 만료 시각을 늘리거나 행에 무언가를 기록해도 초록이면 TC-1.4.9가 틀렸다.
- 쿠키가 없을 때도 데이터베이스를 조회해도 초록이면 "데이터베이스에 닿지 않음" 테스트가 틀렸다.

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. `git log --oneline`에 RED 커밋이 구현 커밋보다 먼저 있는지 확인한다.
3. 아키텍처 체크리스트를 확인한다:
   - `docs/ARCHITECTURE.md` 8절의 코드 구조와 의존 방향을 따르는가?
   - `docs/ADR.md`의 기술 스택을 벗어나지 않았는가?
   - `docs/DEVELOPMENT.md`의 "반드시 지킬 규칙"을 위반하지 않았는가?
4. 결과에 따라 `phases/1-login-allowlist/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"`
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 (API 키, 외부 인증, 수동 설정 등) → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- 허용 목록이나 역할을 캐시하지 마라(짧은 수명이라도). 이유: SQL로 뺀 사람이 서버를 다시 띄우지 않아도 다음 요청부터 막혀야 한다(ADR-024). 캐시는 ADR-024의 재검토 조건이 생길 때 다시 정한다.
- 로그인 상태의 행을 바꾸지 마라. 이유: 만료 시각은 늘리지 않는다(ADR-027).
- API.md 2.3절에 없는 에러 코드를 만들지 마라. 이유: 에러 코드는 프론트엔드와 맺은 약속이다.
- 관문을 건 테스트용 경로를 `app/` 아래에 두지 마라. 이유: 실제 서버에 테스트용 경로가 열린다.
- `GET /api/me`나 로그인 경로를 만들지 마라. 이유: 뒤의 step이 한다.
- 출처 확인을 여기에 넣지 마라. 이유: 출처 확인은 관문이 아니라 앱 전체에 거는 미들웨어이며 다음 step의 일이다.
- 기존 테스트를 깨뜨리지 마라
- `MANUAL.md`의 항목을 체크하지 마라. 이유: 그 항목은 사람이 직접 본 것만 체크한다.
