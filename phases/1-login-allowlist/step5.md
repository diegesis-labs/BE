# Step 5: auth-service

## 읽어야 할 파일

먼저 아래 파일들을 읽고 이 step의 근거와 설계 의도를 파악하라:

- `docs/backlog/epic-1/E1-login-allowlist.md` — "못 박을 것 (Epic 전역)" 전부, S1.3(T1.3.1과 "못 박을 것")
- `docs/backlog/epic-1/testcase.md` — S1.3의 TC-1.3.1 ~ TC-1.3.18
- `docs/API.md` 4.2절 — `GET /api/auth/google/callback`의 **설명**과 **동작 순서**(이 step이 구현하는 분기의 순서), `POST /api/auth/logout`의 **설명**
- `docs/ADR.md` — ADR-024의 결정, ADR-025의 "실패 처리", ADR-027의 "로그인 흐름", "사용자의 식별", "로그인 상태의 수명"
- `app/core/ports.py`, `app/core/security.py` (step 3)
- `app/auth/repository.py` (step 2) — `AuthRepository`와 레코드 타입
- `app/adapters/google.py` (step 4) — 어댑터가 언제 `LoginFailedError`를 내는지
- `tests/conftest.py`의 `app_env`, `clean_db`와 데이터베이스 세션 fixture (step 0, 1)

`docs/ARCHITECTURE.md` 6절의 로그인 상태 수명 표와 8절의 의존 방향은 프롬프트에 이미 들어 있다.

이전 step에서 만들어진 코드를 꼼꼼히 읽고, 설계 의도를 이해한 뒤 작업하라.

## 작업

로그인 시작, 로그인 결과 처리, 로그아웃의 규칙을 담은 service를 만든다. HTTP(리디렉션, 쿠키의 속성)는 다음 step의 라우터가 맡고, service는 "무엇을 확인하고 무엇을 쓰고 어떤 결과인지"만 정한다.

### 1. service — `app/auth/service.py`

```python
class AuthStore(Protocol):
    """service가 저장소에 기대하는 것. app/auth/repository.py의 AuthRepository가 구조적으로 만족한다."""
    async def get_allowed_email(self, email: str) -> AllowedEmail | None: ...
    async def find_users_by_email_or_sub(self, *, email: str, google_sub: str) -> list[UserRecord]: ...
    async def create_user(self, *, email: str, google_sub: str, display_name: str | None) -> UserRecord: ...
    async def update_display_name(self, user_id: UUID, display_name: str | None) -> None: ...
    async def add_login_session(self, *, token_hash: str, user_id: UUID, expires_at: datetime) -> None: ...
    async def delete_login_session(self, token_hash: str) -> None: ...
    async def delete_expired_login_sessions(self, user_id: UUID) -> None: ...


@dataclass(frozen=True)
class LoginStart:
    authorization_url: str
    state_cookie: str        # "{state}.{nonce}.{code_verifier}"

@dataclass(frozen=True)
class LoginSucceeded:
    session_token: str       # 쿠키에 담을 값. 저장소에는 hash_token(session_token)만 들어간다.

@dataclass(frozen=True)
class LoginRejected:
    error: Literal["NOT_ALLOWED", "LOGIN_FAILED"]

LoginResult = LoginSucceeded | LoginRejected


class AuthService:
    def __init__(
        self, store: AuthStore, identity_provider: IdentityProvider, *, session_ttl: timedelta
    ) -> None: ...

    def start_login(self) -> LoginStart: ...

    async def complete_login(
        self,
        *,
        state_cookie: str | None,           # diegesis_oauth_state 쿠키
        state: str | None,                  # 쿼리의 state
        code: str | None,                   # 쿼리의 code
        error: str | None,                  # 쿼리의 error (사용자가 동의 화면에서 취소하면 온다)
        current_session_token: str | None,  # 요청에 붙어 온 로그인 상태의 쿠키
    ) -> LoginResult: ...

    async def logout(self, session_token: str | None) -> None: ...
```

**`start_login`**: `state`, `nonce`, `code_verifier`를 `security.new_token()`으로 하나씩 만들고(모듈을 거쳐 부른다. 이유는 `app/core/security.py`의 독스트링), 포트의 `authorization_url`에 넘긴다. 쿠키 값은 세 값을 `.`으로 이은 것이다.

**`complete_login`**: API.md 4.2절의 동작 순서를 그대로 따른다. 순서가 곧 규칙이다.

1. `error`가 있으면 `LOGIN_FAILED`. `code` 교환을 부르지 않는다.
2. `state_cookie`가 없거나 `.`으로 나눈 결과가 정확히 세 부분이 아니면 `LOGIN_FAILED`.
3. 쿠키의 `state`와 쿼리의 `state`를 `security.secure_equals`로 비교해서 다르면(어느 한쪽이 비었으면) `LOGIN_FAILED`.
4. `code`가 없거나 비었으면 `LOGIN_FAILED`.
5. 포트의 `exchange_code(code=..., code_verifier=쿠키의 셋째, expected_nonce=쿠키의 둘째)`. `LoginFailedError`면 `LOGIN_FAILED`.
6. 신원의 `email_verified`가 False면 `LOGIN_FAILED`.
7. 이메일을 소문자로 바꾼다. 이후의 조회와 저장은 모두 이 값으로 한다.
8. 허용 목록에 없으면 `NOT_ALLOWED`. **`users`와 `login_sessions`를 바꾸지 않는다.**
9. `find_users_by_email_or_sub`로 찾은 행 가운데 이메일만 같거나 `google_sub`만 같은 행이 하나라도 있으면 `LOGIN_FAILED`. 그 행을 고치거나 새 행을 만들지 않는다. 이 검사로 `google_sub`의 고유 제약 위반을 미리 막는다(500으로 끝나면 안 된다).
10. 성공. 둘 다 같은 행이 있으면 `display_name`을 갱신하고, 없으면 사용자를 만든다. `current_session_token`이 있으면 그 해시의 행을 지운다(그 행 하나만. 같은 사람의 다른 기기 행은 지우지 않는다). 그 사용자의 만료된 행을 지운다. `security.new_token()`으로 쿠키 값을 만들고, `hash_token`한 값과 `지금 + session_ttl`을 저장한다. `LoginSucceeded(session_token)`을 돌려준다.

- **실패하거나 허용 목록 밖일 때에는 저장소의 쓰기 메서드를 하나도 부르지 않는다.** 성공했을 때의 쓰기는 요청 하나의 트랜잭션(step 2의 `get_db_session`) 안에서 일어나므로, service가 커밋하거나 트랜잭션을 열지 않는다.
- **로그**: 실패와 거부마다 원인을 한 줄 남긴다(예: "로그인 실패: state가 맞지 않음", "로그인 거부: 이메일은 같고 google_sub가 다른 사용자가 있음"). 쿠키 값, `code`, 토큰, 클라이언트 비밀값, `state`, `nonce`, `code_verifier`는 남기지 않는다. `LoginFailedError`의 메시지는 남겨도 된다(어댑터가 비밀을 넣지 않는다). 로거는 `logging.getLogger(__name__)`이다.

**`logout`**: 쿠키가 있으면 그 해시의 행을 지운다. 없거나 모르는 값이어도 아무 예외 없이 끝난다.

**의존 방향**: service는 `app.core.ports`, `app.core.security`, `app.auth.repository`의 레코드 타입만 import한다. FastAPI, SQLAlchemy, httpx, `app.adapters`를 import하지 마라(ARCHITECTURE.md 8절, E1 "못 박을 것": service가 Google을 직접 부르지 않는다).

### 2. 테스트에서 쓰는 가짜 — `tests/auth/fakes.py`

다음 step(관문, 라우터)의 테스트도 이 가짜를 쓴다.

- `FakeIdentityProvider`: 돌려줄 `Identity`나 낼 `LoginFailedError`를 정할 수 있고, `authorization_url`과 `exchange_code`가 받은 인자를 모두 기록한다.
- `FakeAuthStore`: `AuthStore`를 만족하는 메모리 저장소. 쓰기 메서드가 불렸는지를 기록한다. 단위 테스트에서 "저장소에 닿지 않았다"를 확인하는 데 쓴다.

### 3. 테스트

S1.3의 TC는 testcase.md에서 "로그인 결과 처리 경로를 호출"하는 모양으로 적혀 있다. 이 step은 그 가운데 **service가 정하는 부분**(분기, 저장소의 변화, 가짜 신원이 받은 값, 로그)을 service를 직접 불러 확인한다. 리디렉션 주소와 쿠키의 속성은 다음 step이 HTTP로 다시 확인한다. 테스트의 이름이나 독스트링에 TC 번호를 적어라.

- `tests/auth/test_service.py` (`unit`, `FakeIdentityProvider`와 `FakeAuthStore`)
  - `start_login`: 쿠키 값이 세 부분이고, 셋이 서로 다르며, 가짜 신원의 `authorization_url`이 그 세 값을 받았는지.
  - TC-1.3.3의 네 경우, TC-1.3.4: 결과가 `LOGIN_FAILED`이고 `exchange_code`가 한 번도 불리지 않았으며 저장소의 쓰기가 없는지.
  - TC-1.3.5(이메일은 허용 목록에 있음), TC-1.3.6: `LOGIN_FAILED`이고 저장소의 쓰기가 없는지.
  - TC-1.3.18: `exchange_code`가 쿼리의 `code`, 쿠키의 셋째(`code_verifier`), 쿠키의 둘째(`nonce`)를 받았는지. 세 값을 서로 다른 문자열로 둬서 자리가 바뀌면 드러나게 한다.
  - `code`가 없을 때 `LOGIN_FAILED`.
  - `logout(None)`과 `logout("모르는 값")`이 예외 없이 끝나는지(TC-1.3.12의 service 부분).
  - TC-1.3.13의 service 부분: 실패의 여러 경우에서 `caplog`에 원인이 남고, 쿠키 값, `code`, `state`, `nonce`, `code_verifier`가 없는지. 성공한 경우에도 `session_token`이 로그에 없는지.
  - 의존 방향: `app/auth/service.py`의 import 구문(AST)에 `fastapi`, `sqlalchemy`, `httpx`, `app.adapters`가 없는지.
- `tests/auth/test_service_integration.py` (`integration`, `clean_db`, 실제 `AuthRepository`, `FakeIdentityProvider`). 테스트마다 한 트랜잭션 안에서 service를 부르고 커밋한 뒤 테이블을 읽는다.
  - TC-1.3.1: `users`에 한 행이 생기고 `google_sub`가 가짜 신원의 `sub`다. `session_token`은 43자의 base64url이고, `login_sessions`의 `token_hash`는 `session_token`과 다르며 `hashlib.sha256(session_token.encode()).hexdigest()`와 같다. `expires_at`은 지금 + TTL과 1분 안에서 같다.
  - TC-1.3.2: `NOT_ALLOWED`이고 `users`와 `login_sessions`에 행이 없다.
  - TC-1.3.7: 허용 목록에 `reader@example.com`, 신원은 `Reader@Example.com` → 성공하고 `users.email`은 소문자다.
  - TC-1.3.10: 이름을 바꿔 옛 쿠키 없이 다시 로그인 → `users` 한 행, 새 이름, `login_sessions` 두 행.
  - TC-1.3.14: 두 방향(이메일만 같음, `google_sub`만 같음) 모두 `LOGIN_FAILED`, `users`는 처음 행 하나 그대로(값까지), `login_sessions`에 행이 없음, 로그에 거부 이유가 있음. 예외 없이 끝난다(고유 제약 위반이 나지 않는다).
  - TC-1.3.15의 저장소 부분: 쿠키 X와 다른 기기의 Z가 있는 사람이 X를 붙여 다시 로그인 → X의 행은 지워지고 Z와 새 Y의 행이 남는다.
  - TC-1.3.16: P의 만료된 행 둘은 지워지고, P의 만료되지 않은 행과 새 행, Q의 만료된 행은 남는다.

### 4. 순서 — RED 커밋을 남긴다

1. `tests/auth/fakes.py`와 위 테스트를 먼저 쓰고, `AuthService`는 시그니처만 있는 빈 껍데기로 둔다.
2. 테스트가 실패하는 것을 눈으로 확인한다.
3. `test(1-login-allowlist): RED — 로그인 시작, 결과 처리, 로그아웃의 규칙`으로 커밋한다.
4. 구현해서 초록으로 만든다.

## Acceptance Criteria

```bash
uv run pytest tests/auth/test_service.py tests/auth/test_service_integration.py -v
scripts/check.sh
```

**반증 조건** — 아래의 틀린 구현으로도 초록이면 그 테스트가 틀린 것이다.

- `state`를 확인하지 않거나, `==`로 비교해서 빈 `state`끼리 같다고 판정해도 초록이면 TC-1.3.3이 틀렸다.
- `email_verified`를 보지 않아도 초록이면 TC-1.3.5가 틀렸다.
- 허용 목록을 확인하기 전에 `create_user`를 불러도 초록이면 TC-1.3.2가 틀렸다(커밋한 뒤 `users`를 읽어야 드러난다).
- 이메일을 소문자로 바꾸지 않고 비교해도 초록이면 TC-1.3.7이 틀렸다.
- 사용자를 이메일만으로 찾아 `google_sub`를 덮어써도 초록이면 TC-1.3.14가 틀렸다.
- 쿠키 값을 그대로 `token_hash`에 저장해도 초록이면 TC-1.3.1이 틀렸다.
- 다시 로그인할 때 옛 쿠키의 행을 지우지 않거나, 그 사람의 모든 행을 지워도 초록이면 TC-1.3.15의 저장소 부분이 틀렸다.
- 만료된 행을 지우지 않거나, 다른 사람의 만료된 행까지 지워도 초록이면 TC-1.3.16이 틀렸다.
- `exchange_code`에 `nonce`와 `code_verifier`를 바꿔 넘겨도 초록이면 TC-1.3.18이 틀렸다.

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

- 로그인 실패의 원인을 결과 값에 담아 돌려주지 마라(`LOGIN_FAILED`와 `NOT_ALLOWED` 둘뿐이다). 이유: 실패의 원인은 공격자에게 단서가 되므로 돌려보내는 주소에 담지 않고 로그에만 남긴다(ADR-025).
- 허용 목록에 없는 계정의 `users` 행을 만들지 마라. 이유: 서비스를 쓸 수 없는 사람의 정보를 남기지 않는다(ARCHITECTURE.md 6절).
- 역할을 로그인 상태나 결과에 복사해 두지 마라. 이유: SQL로 역할을 바꾸면 다음 요청부터 반영되어야 한다(E1 "못 박을 것").
- 같은 사람의 다른 기기 로그인 상태를 지우지 마라. 이유: E1 S1.3 "못 박을 것".
- `secrets`나 `random`을 import하지 마라. 이유: 임의의 값을 만드는 곳은 `app/core/security.py`의 함수 하나다(ADR-027).
- 라우터, 쿠키의 속성, 리디렉션 주소를 여기서 정하지 마라. 이유: 다음 step의 일이다.
- 기존 테스트를 깨뜨리지 마라
- `MANUAL.md`의 항목을 체크하지 마라. 이유: 그 항목은 사람이 직접 본 것만 체크한다.
