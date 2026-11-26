# Step 9: logout-me-routes

## 읽어야 할 파일

먼저 아래 파일들을 읽고 이 step의 근거와 설계 의도를 파악하라:

- `docs/backlog/epic-1/E1-login-allowlist.md` — "못 박을 것 (Epic 전역)", S1.4와 S1.5(T1.5.1, T1.5.2와 그 "못 박을 것": 공개 경로의 목록)
- `docs/backlog/epic-1/testcase.md` — TC-1.3.11, TC-1.3.12, TC-1.3.15, TC-1.4.6, TC-1.4.8, TC-1.5.2 ~ TC-1.5.4
- `docs/API.md` 2.2절(관문), 2.4절(출처 확인), 3절(엔드포인트 목록과 권한), 4.2절의 `POST /api/auth/logout`(Response Header, **설명**, **동작 순서**), 4.3절 `GET /api/me` 전부
- `docs/ADR.md` — ADR-024의 결정, ADR-025의 "로그아웃"
- `app/auth/router.py`, `app/main.py`, `tests/auth/test_router*.py` (step 8)
- `app/auth/service.py`의 `logout`, `tests/auth/fakes.py` (step 5)
- `app/core/gate.py`의 `require_user`, `CurrentUser` (step 6)
- `app/core/origin.py` (step 7)
- `tests/conftest.py`(`app_env`, `clean_db`), `tests/support/settings.py`

이전 step에서 만들어진 코드를 꼼꼼히 읽고, 설계 의도를 이해한 뒤 작업하라.

## 작업

로그아웃과 내 정보 경로를 만들고, 앱의 모든 경로가 관문과 출처 확인을 거치는지 확인하는 테스트를 둔다. 이 step이 끝나면 이 Epic의 네 경로가 모두 있다.

### 1. 경로 — `app/auth/router.py`, `app/auth/schemas.py`

```python
# app/auth/schemas.py
class MeResponse(BaseModel):
    id: UUID
    email: str
    display_name: str | None
    role: Literal["user", "admin"]
```

```python
# app/auth/router.py에 더한다
@router.post("/auth/logout", status_code=204)
async def logout(...) -> Response: ...

@router.get("/me")
async def get_me(user: CurrentUser = Depends(require_user)) -> MeResponse: ...
```

**`POST /api/auth/logout`**

- 관문을 걸지 않는다. 출처 확인은 미들웨어가 이미 건다(step 7).
- 요청의 `settings.login_cookie_name` 쿠키를 `service.logout()`에 넘긴다. 쿠키가 없거나 모르는 값이어도, 허용 목록에서 빠진 사람이어도 `204`다(ADR-025).
- 응답에는 로그인 상태의 쿠키를 지우는 `Set-Cookie`를 붙인다. `Max-Age=0`, `Path=/`이며, 심을 때와 같은 `HttpOnly`, `SameSite=Lax`, 그리고 `cookie_secure`가 참이면 `Secure`를 붙인다.
- `204` 응답에는 본문이 없어야 한다.
- 요청에 붙은 쿠키의 행 하나만 지운다. 같은 사람의 다른 기기 행은 그대로 둔다.

**`GET /api/me`**

- `require_user`를 건다. 응답은 `CurrentUser`의 값 그대로다(`role`은 이번 요청에서 허용 목록에서 읽은 값이다).
- 역할이나 이름을 다른 곳에 기억해 두지 마라. SQL로 역할을 바꾸면 다음 요청부터 바뀐 값이 나와야 한다(API.md 4.3절).

### 2. 모든 경로의 관문과 출처 확인 — `tests/test_routes.py`

T1.5.2. 이후 Epic이 경로를 더할 때마다 이 테스트가 그 경로를 자동으로 검사한다.

- **공개 경로의 목록은 이 파일의 상수 하나(`PUBLIC_ROUTES`)에만 둔다.** 목록은 E1 S1.5 "못 박을 것"의 여섯 개다: `GET /api/health`, `GET /api/auth/google/login`, `GET /api/auth/google/callback`, `POST /api/auth/logout`, `GET /api/openapi.json`, `GET /api/docs`. 상수 위에, 이후 Epic이 공개 경로를 더하려면 이 목록을 고치고 그 이유를 그 Epic 문서에 적는다는 주석을 단다.
- 경로는 손으로 나열하지 않고 `create_app()`이 만든 앱의 `app.routes`에서 **메서드마다** 뽑는다(`HEAD`, `OPTIONS` 제외). 경로 매개변수(`{book_id}` 등)는 임의의 값으로 채운다.
- TC-1.5.2: 공개 경로를 뺀 모든 (메서드, 경로)를 쿠키 없이, `Origin: TEST_FRONTEND_URL`을 붙여 호출하면 모두 `401`이고 `code`가 `NOT_AUTHENTICATED`다.
- TC-1.5.4: `POST`, `PUT`, `PATCH`, `DELETE`를 받는 모든 경로(공개 경로 포함)를 쿠키 없이 `Origin: https://evil.example`로 그 메서드마다 호출하면 모두 `403 ORIGIN_MISMATCH`다. `401`이나 `2xx`가 하나도 없다.
- **이 검사가 실제로 잡는지 확인하는 테스트도 둔다.** 검사를 함수로 만들고(예: 401이 아닌 경로의 목록을 돌려주는 함수), 테스트 안에서 관문을 걸지 않은 경로를 하나 더 붙인 앱에 그 함수를 돌리면 그 경로가 보고되는지 본다. 출처 확인도 마찬가지로, 미들웨어 없이 만든 앱(또는 미들웨어를 우회하는 경우)에서 그 함수가 경로를 보고하는지 본다. 이유: 경로를 하나도 뽑지 못하는 검사도 "모두 401"을 통과한다.
- 뽑은 경로의 수가 0이 아니고, 이 Epic의 네 경로와 헬스체크가 들어 있는지도 확인한다.

### 3. 그 밖의 테스트

- `tests/auth/test_router.py`에 더한다 (`unit`, `app_env`, 가짜 저장소)
  - TC-1.3.12: 쿠키 없이, 모르는 쿠키 값으로 각각 로그아웃(`Origin: TEST_FRONTEND_URL`) → 둘 다 `204`, 본문 없음, 쿠키를 지우는 `Set-Cookie`(`Max-Age=0`, `Path=/`).
  - TC-1.5.3: `/api/openapi.json`에 이 Epic의 네 경로(`/api/auth/google/login`, `/api/auth/google/callback`, `/api/auth/logout`, `/api/me`)가 있고, `/api/admin/allowed-emails`로 시작하는 경로는 없다.
- `tests/auth/test_router_integration.py`에 더한다 (`integration`, `clean_db`, `FakeIdentityProvider`). 로그인 상태는 **로그인 결과 처리 경로를 실제로 호출해서** 만든다(가짜 신원과 올바른 `diegesis_oauth_state`를 붙여서).
  - TC-1.3.11: 같은 사람이 두 번 로그인해 쿠키 두 개를 얻고, 하나로 로그아웃 → `204`와 쿠키를 지우는 `Set-Cookie`. 그 쿠키로 `GET /api/me` → `401`, 다른 쿠키 → `200`.
  - TC-1.3.15: 쿠키 X로 로그인해 있고 다른 기기의 로그인 상태 Z도 있는 사람이 X를 붙인 채 다시 로그인해 새 쿠키 Y를 얻는다. X → `401`, Y와 Z → `200`.
  - TC-1.4.6: 허용 목록에 `admin`으로 있는 사람 → `GET /api/me`가 `200`, 본문의 키가 정확히 `{"id", "email", "display_name", "role"}`이고 `role`이 `admin`, `id`와 `email`이 `users`의 행과 같다.
  - TC-1.4.8: 로그인한 사람의 쿠키로 `POST /api/auth/logout`을 `Origin: https://evil.example`로 → `403 ORIGIN_MISMATCH`이고 `login_sessions` 행이 그대로. 그다음 `Origin: TEST_FRONTEND_URL`로 → `204`이고 그 행이 지워진다.
  - TC-1.4.3의 마지막 부분을 실제 로그인으로: SQL로 허용 목록에서 뺐다가 다시 넣은 뒤, 로그인 결과 처리 경로로 다시 로그인한 새 쿠키는 `GET /api/me`에서 `200`이다.

### 4. 순서 — RED 커밋을 남긴다

1. 위 테스트를 먼저 쓰고, 로그아웃은 아무것도 지우지 않고 `204`만 내는 빈 껍데기로, `/api/me`는 아직 만들지 않은 채로 둔다.
2. 테스트가 실패하는 것을 눈으로 확인한다.
3. `test(1-login-allowlist): RED — 로그아웃, 내 정보, 모든 경로의 관문과 출처 확인`으로 커밋한다.
4. 구현해서 초록으로 만든다.

## Acceptance Criteria

```bash
uv run pytest tests/test_routes.py tests/auth/test_router.py tests/auth/test_router_integration.py -v
scripts/check.sh
```

**반증 조건** — 아래의 틀린 구현으로도 초록이면 그 테스트가 틀린 것이다.

- 로그아웃에 `require_user`를 걸어도 초록이면 TC-1.3.12가 틀렸다(쿠키 없는 로그아웃이 401이 된다).
- 로그아웃이 그 사람의 모든 로그인 상태를 지워도 초록이면 TC-1.3.11이 틀렸다.
- 로그아웃의 `Set-Cookie`에 `Path=/`가 없어도 초록이면 TC-1.3.12가 틀렸다.
- `GET /api/me`가 역할을 허용 목록이 아닌 곳에서 읽어도(예: 언제나 `user`) 초록이면 TC-1.4.6이 틀렸다.
- 로그아웃을 출처 확인에서 빼도 초록이면 TC-1.4.8이 틀렸다.
- 관문을 걸지 않은 경로를 하나 더 등록해도 초록이면 TC-1.5.2가 틀렸다. 검사 함수의 확인 테스트가 이것을 잡아야 한다.
- 경로를 하나도 뽑지 못해도 초록이면 `tests/test_routes.py`가 틀렸다.
- 공개 경로의 목록이 두 곳 이상에 있으면 TC-1.5.2를 어긴 것이다.

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

- 허용 목록을 조회하거나 바꾸는 경로(`/api/admin/allowed-emails` 등)를 만들지 마라. 이유: 허용 목록은 SQL로만 다룬다(ADR-024).
- 로그아웃을 `GET`으로도 받지 마라. 이유: 상태를 바꾸는 경로를 `GET`으로 만들지 않는다(ADR-027).
- 공개 경로를 `PUBLIC_ROUTES` 밖에 따로 적거나, 검사에서 빼는 예외를 두지 마라. 이유: E1 S1.5 "못 박을 것".
- API.md 3절에 없는 경로를 만들지 마라. 이유: 문서에 없는 엔드포인트를 만들지 않는다(DEVELOPMENT.md 3절).
- `docs/API.md`를 고치지 마라. 이유: 이 Epic의 계약은 이미 합의되었다. 고칠 곳을 찾으면 summary에 적어라.
- 기존 테스트를 깨뜨리지 마라
- `MANUAL.md`의 항목을 체크하지 마라. 이유: 그 항목은 사람이 직접 본 것만 체크한다.
