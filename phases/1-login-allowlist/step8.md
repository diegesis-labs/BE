# Step 8: login-routes

## 읽어야 할 파일

먼저 아래 파일들을 읽고 이 step의 근거와 설계 의도를 파악하라:

- `docs/backlog/epic-1/E1-login-allowlist.md` — "못 박을 것 (Epic 전역)" 전부, S1.3과 S1.5의 "못 박을 것", S1.5의 T1.5.1
- `docs/backlog/epic-1/testcase.md` — 맨 위 두 문단, TC-1.2.1, TC-1.3.1 ~ TC-1.3.10, TC-1.3.13, TC-1.3.14, TC-1.3.16 ~ TC-1.3.18, TC-1.5.1
- `docs/API.md` 4.2절 — `GET /api/auth/google/login`과 `GET /api/auth/google/callback`의 Request Header, Response Header, **설명**, **동작 순서** 전부
- `docs/ADR.md` — ADR-025, ADR-027
- `app/auth/service.py`, `tests/auth/fakes.py`, `tests/auth/test_service*.py` (step 5) — 이 step은 service를 HTTP에 잇는다
- `app/adapters/google.py` (step 4), `app/core/ports.py`, `app/core/security.py` (step 3)
- `app/auth/repository.py`의 `get_auth_repository`, `app/core/database.py`의 `DbSession` (step 2)
- `app/core/origin.py` (step 7), `app/core/gate.py` (step 6)
- `app/core/config.py`의 `frontend_url`, `cookie_secure`, `login_session_ttl_hours`, `login_cookie_name` (step 0)
- `app/main.py`, `tests/test_main.py`, `tests/conftest.py`(`app_env`, `clean_db`), `tests/support/settings.py`

이전 step에서 만들어진 코드를 꼼꼼히 읽고, 설계 의도를 이해한 뒤 작업하라.

## 작업

로그인을 시작하는 경로와 로그인 결과를 받는 경로를 만들고, Google 어댑터를 앱에 조립한다. 로그아웃과 `GET /api/me`는 다음 step이 만든다.

### 1. 경로 — `app/auth/router.py`

```python
router = APIRouter(prefix="/api", tags=["auth"])
OAUTH_STATE_COOKIE = "diegesis_oauth_state"

def get_identity_provider(...) -> IdentityProvider: ...   # 테스트는 app.dependency_overrides로 가짜를 끼운다
def get_auth_service(...) -> AuthService: ...              # 저장소(get_auth_repository), 신원 제공자, TTL로 만든다

@router.get("/auth/google/login")
async def start_google_login(...) -> Response: ...

@router.get("/auth/google/callback")
async def finish_google_login(...) -> Response: ...
```

**`GET /api/auth/google/login`**: `service.start_login()`의 결과로 `302`와 `Location: 인가 주소`를 응답하고, `diegesis_oauth_state` 쿠키에 `state_cookie`를 심는다. 쿠키의 속성은 `HttpOnly`, `SameSite=Lax`, `Path=/api/auth/google`, `Max-Age=600`이고, `settings.cookie_secure`가 참이면 `Secure`를 더한다.

**`GET /api/auth/google/callback`**: 쿼리의 `code`, `state`, `error`와 쿠키의 `diegesis_oauth_state`, `settings.login_cookie_name`을 service의 `complete_login`에 넘기고, 결과를 아래처럼 응답한다.

| 결과 | `Location` | 쿠키 |
| --- | --- | --- |
| `LoginSucceeded` | `{FRONTEND_URL}/` | `diegesis_oauth_state`를 지우고, 로그인 상태의 쿠키를 심는다 |
| `LoginRejected("NOT_ALLOWED")` | `{FRONTEND_URL}/login?error=NOT_ALLOWED` | `diegesis_oauth_state`를 지운다 |
| `LoginRejected("LOGIN_FAILED")` | `{FRONTEND_URL}/login?error=LOGIN_FAILED` | `diegesis_oauth_state`를 지운다 |

- 로그인 상태의 쿠키: 이름은 `settings.login_cookie_name`, 속성은 `HttpOnly`, `SameSite=Lax`, `Path=/`, `Max-Age=login_session_ttl_hours × 3600`, 그리고 `cookie_secure`가 참이면 `Secure`.
- `diegesis_oauth_state`를 지우는 `Set-Cookie`는 `Max-Age=0`이고, **심을 때와 같은 `Path=/api/auth/google`**을 붙인다. 이유: 브라우저는 이름과 경로가 모두 같은 쿠키만 지운다. 경로를 빼면 쿠키가 남는다.
- **상태 코드는 `302`다.** `RedirectResponse`의 기본값은 `307`이므로 직접 정해라.
- **`code`, `state`, `error` 쿼리는 모두 선택으로 받는다**(`str | None = None`). 이유: 필수로 선언하면 빠졌을 때 FastAPI가 `400 VALIDATION_ERROR`를 낸다. 그 경우도 `LOGIN_FAILED`로 돌려보내야 한다(API.md 4.2절: 로그인 결과 처리는 리디렉션으로만 끝난다).
- `Location`은 `FRONTEND_URL`로만 만든다. 요청의 Host나 `request.url`을 쓰지 마라(ADR-025).
- 실패의 원인을 `Location`에 담지 마라. `error`의 값은 위 두 가지뿐이다(ADR-025).

### 2. 조립 — `app/main.py`

- `create_app()`이 auth 라우터를 등록한다.
- 실제 `IdentityProvider`는 `GoogleIdentityProvider.from_settings(get_settings())`다. 이것을 `get_identity_provider`에 잇는 방법(예: `create_app()`이 `app.state`에 어댑터를 만드는 함수를 넣어 두고 `get_identity_provider`가 처음 불릴 때 설정을 읽어 만듦)은 재량이지만, 다음 셋은 지켜라.
  1. `app/auth/router.py`와 `app/auth/service.py`는 `app.adapters`를 import하지 않는다. 어댑터를 아는 곳은 `app/main.py`뿐이다(ARCHITECTURE.md 8절: 어댑터는 서버가 시작될 때 주입된다).
  2. `create_app()`과 앱의 시작은 설정을 읽지 않는다(`tests/test_main.py`).
  3. 테스트는 `app.dependency_overrides[get_identity_provider]`로 가짜를 끼운다. 로그인 시작 경로는 덮어쓰지 않고도 실제 어댑터로 동작해야 한다(TC-1.5.1).
- 이 step부터 서버가 시작할 때 `app.adapters.google`이 import되므로 httpx가 런타임 의존성이어야 한다(step 4). compose 스모크로 확인한다.

### 3. 테스트

쿠키의 속성은 **`Set-Cookie` 헤더를 직접 파싱해서** 확인한다(`response.headers.get_list("set-cookie")`). 이유: `TestClient`의 쿠키 저장소는 `HttpOnly`, `Secure`, `Max-Age`를 보여 주지 않는다. 속성은 API.md 4.2절의 예시와 같은 표기(`SameSite=Lax`)로 나가게 하라. `Location`은 `FRONTEND_URL`을 붙인 전체 주소를 비교한다. 리디렉션을 따라가지 않도록 `follow_redirects=False`를 쓴다.

- `tests/auth/test_router.py` (`unit`, `app_env`). `app.dependency_overrides`로 `get_identity_provider`에는 `FakeIdentityProvider`를, `get_auth_repository`에는 `FakeAuthStore`를 끼운다(TC-1.5.1과 TC-1.2.1만 예외).
  - TC-1.5.1: 실제 어댑터로(덮어쓰지 않고) 로그인 시작을 호출한다. `302`, `Location`의 앞부분이 `https://accounts.google.com/o/oauth2/v2/auth?`, 쿠키의 속성, 쿠키 값의 세 부분(각 43자의 base64url, 서로 다름), 첫째 = 인가 주소의 `state`, 둘째 = `nonce`, 셋째의 S256 = `code_challenge`.
  - TC-1.2.1의 Host 부분: `TestClient(app, base_url="http://localhost:8080")`로 실제 어댑터의 로그인 시작을 호출해도 인가 주소의 `redirect_uri`가 `http://localhost:5173/api/auth/google/callback`이다.
  - TC-1.3.3(네 경우), TC-1.3.4, TC-1.3.5, TC-1.3.6: `302`이고 `Location`이 `{FRONTEND_URL}/login?error=LOGIN_FAILED`이며, 로그인 상태의 쿠키를 심지 않는다. TC-1.3.3과 TC-1.3.4는 가짜 신원의 `exchange_code`가 불리지 않았는지도 본다.
  - `code`와 `state` 쿼리가 모두 없을 때도 `400`이 아니라 `302 LOGIN_FAILED`다.
  - TC-1.3.8: 성공, 허용 목록 밖, 실패의 세 경우 모두 `diegesis_oauth_state=`을 지우는 `Set-Cookie`가 있고 `Max-Age=0`과 `Path=/api/auth/google`이 붙는다.
  - TC-1.3.9: `FRONTEND_URL`을 `https://diegesis.example`로 바꾸면(환경변수를 바꾸고 `get_settings.cache_clear()`) 로그인 시작의 `diegesis_oauth_state`와 로그인 성공의 로그인 상태 쿠키에 모두 `Secure`가 붙고, `http://localhost:5173`이면 둘 다 붙지 않는다.
  - TC-1.3.13: 로그인 시작, 성공, 그리고 여러 실패를 거치는 동안의 로그(`caplog`, 레벨 DEBUG)에 쿠키 값, 가짜에 넘긴 `code`, `TEST_GOOGLE_CLIENT_SECRET`, `state`, `nonce`, `code_verifier`가 하나도 없고, 실패한 경우에는 원인이 있다.
  - TC-1.3.17의 뒷부분: `app.core.security.new_token`을 정해진 값(`"tok-1"`, `"tok-2"`, …)을 차례로 내는 가짜로 바꾼 뒤 로그인 시작과 로그인 성공을 호출하면, `diegesis_oauth_state`의 세 값과 로그인 상태 쿠키의 값이 모두 가짜가 낸 값이다.
  - TC-1.3.18: `diegesis_oauth_state`를 `{s}.{n}.{v}`로, 쿼리의 `state`를 `{s}`로 붙이면 가짜 신원의 `exchange_code`가 쿼리의 `code`, `{v}`, `{n}`을 받는다.
  - 의존 방향: `app/auth/router.py`의 import 구문(AST)에 `app.adapters`가 없다.
- `tests/auth/test_router_integration.py` (`integration`, `clean_db`, 실제 저장소, `FakeIdentityProvider`)
  - TC-1.3.1: `302`, `Location`이 `{FRONTEND_URL}/`, 로그인 상태 쿠키의 속성(`HttpOnly`, `SameSite=Lax`, `Path=/`, `Max-Age=1209600`), `users`의 행과 `google_sub`, 쿠키 값이 43자의 base64url이고 `token_hash`가 쿠키 값과 다르며 SHA-256과 같음, `expires_at`이 지금 + TTL과 1분 안.
  - TC-1.3.2: `Location`이 `{FRONTEND_URL}/login?error=NOT_ALLOWED`, 로그인 상태 쿠키 없음, `users`와 `login_sessions`에 행 없음.
  - TC-1.3.7, TC-1.3.10, TC-1.3.14, TC-1.3.16을 경로로 다시 확인한다(TC-1.3.14는 `302 LOGIN_FAILED`이고 500이 아니어야 한다).
  - **커밋이 실패하면 쿠키가 나가지 않는다**: `AsyncSession.commit`을 예외를 내는 것으로 바꾸고(`raise_server_exceptions=False`) 로그인 성공을 호출하면 응답이 `302`가 아니라 `500`이고, 로그인 상태 쿠키의 `Set-Cookie`가 없으며, `users`에 행이 없다. 이유: 저장되지 않은 로그인 상태의 쿠키를 받으면 사용자는 로그인한 줄 알지만 다음 요청에서 401을 받는다.

### 4. 순서 — RED 커밋을 남긴다

1. 위 테스트를 먼저 쓰고, 두 경로는 언제나 `{FRONTEND_URL}/login?error=LOGIN_FAILED`로 보내는 빈 껍데기로 두고 `create_app()`에 등록한다.
2. 테스트가 실패하는 것을 눈으로 확인한다.
3. `test(1-login-allowlist): RED — Google 로그인을 시작하고 결과를 받는 경로`로 커밋한다.
4. 구현해서 초록으로 만든다.

## Acceptance Criteria

```bash
uv run pytest tests/auth/test_router.py tests/auth/test_router_integration.py tests/test_main.py -v
scripts/compose-smoke.sh    # 서버가 Google 어댑터를 import한다. Google의 값 없이도 서버가 떠야 한다.
scripts/check.sh
```

**반증 조건** — 아래의 틀린 구현으로도 초록이면 그 테스트가 틀린 것이다.

- `redirect_uri`를 `request.base_url`로 만들어도 초록이면 TC-1.2.1의 Host 부분이 틀렸다.
- 쿠키의 `state`와 인가 주소의 `state`가 서로 다른 값이어도 초록이면 TC-1.5.1이 틀렸다.
- `Secure`를 언제나 붙이거나 언제나 빼도 초록이면 TC-1.3.9가 틀렸다.
- `diegesis_oauth_state`를 지우는 `Set-Cookie`에 `Path`가 없어도, 또는 실패한 경우에만 지우지 않아도 초록이면 TC-1.3.8이 틀렸다.
- `RedirectResponse`의 기본값(307)이 나가도 초록이면 테스트가 상태 코드를 보지 않은 것이다.
- `code`가 없을 때 `400`이 나가도 초록이면 그 테스트가 틀렸다.
- 경로가 `secrets`를 직접 써서 로그인 상태 쿠키를 만들어도 초록이면 TC-1.3.17의 뒷부분이 틀렸다.
- 커밋을 응답 뒤에 해서 커밋이 실패해도 `302`와 쿠키가 나가도 초록이면 커밋 실패 테스트가 틀렸다.
- 로그에 `code`나 클라이언트 비밀값이 찍혀도 초록이면 TC-1.3.13이 틀렸다.

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

- 로그인 결과 처리 경로를 `POST`로 바꾸거나, 이 두 경로 말고 상태를 바꾸는 `GET` 경로를 만들지 마라. 이유: 출처 확인은 `GET`을 보지 않는다. 예외는 Google 로그인의 두 경로뿐이다(ADR-027).
- 로그인 뒤에 원래 보던 화면으로 돌려보내는 매개변수(`next`, `redirect` 등)를 받지 마라. 이유: 언제나 첫 화면으로 돌아간다(ADR-025). 열린 리디렉션의 구멍이 된다.
- 실패의 원인을 `Location`에 담지 마라. 이유: ADR-025.
- 쿠키 이름에 `__Host-` 접두사를 붙이지 마라. 이유: ADR-027이 받아들인 위험이다. 테스트와 프론트엔드가 `diegesis_session`을 기대한다.
- 경로에서 `secrets`로 값을 만들지 마라. 이유: 임의의 값은 service가 `security.new_token()`으로 만든다(ADR-027).
- 로그아웃과 `GET /api/me`를 만들지 마라. 이유: 다음 step이 한다.
- `docs/API.md`를 고치지 마라. 이유: 이 Epic의 계약은 이미 합의되었다. 고칠 곳을 찾으면 summary에 적어라.
- 기존 테스트를 깨뜨리지 마라
- `MANUAL.md`의 항목을 체크하지 마라. 이유: 그 항목은 사람이 직접 본 것만 체크한다.
