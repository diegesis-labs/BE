# Step 2: auth-repository

## 읽어야 할 파일

먼저 아래 파일들을 읽고 이 step의 근거와 설계 의도를 파악하라:

- `docs/backlog/epic-1/E1-login-allowlist.md` — "못 박을 것 (Epic 전역)", S1.1(T1.1.2와 그 "못 박을 것"), S1.3의 "못 박을 것"(성공했을 때의 쓰기는 한 트랜잭션)
- `docs/backlog/epic-1/testcase.md` — TC-1.1.6
- `docs/API.md` 2.2절 — 관문이 데이터베이스에서 확인하는 순서(이 step의 `find_active_login`이 그 조회를 맡는다)
- `docs/ADR.md` — ADR-027의 "로그인 상태의 수명"
- `app/core/models.py`, `app/auth/models.py`, 새 마이그레이션 (step 1)
- `tests/conftest.py`의 `app_env`, `clean_db`와 데이터베이스 세션 fixture (step 0, 1)
- `app/core/database.py`, `tests/core/test_database.py`, `app/main.py`, `tests/test_main.py`

`docs/ARCHITECTURE.md` 6절의 로그인 상태 수명 표는 프롬프트에 이미 들어 있다.

이전 step에서 만들어진 코드를 꼼꼼히 읽고, 설계 의도를 이해한 뒤 작업하라.

## 작업

세 테이블을 읽고 쓰는 repository를 만들고, 요청마다 데이터베이스 세션과 트랜잭션을 하나씩 주는 의존성을 만든다. 이후 step의 service, 관문, 라우터가 아래의 이름과 시그니처를 그대로 쓴다.

### 1. 레코드와 repository — `app/auth/repository.py`

```python
@dataclass(frozen=True)
class AllowedEmail:
    email: str
    role: str            # "user" 또는 "admin"
    created_at: datetime

@dataclass(frozen=True)
class UserRecord:
    id: UUID
    email: str
    google_sub: str
    display_name: str | None

@dataclass(frozen=True)
class ActiveLogin:
    """만료되지 않은 로그인 상태 하나, 그 사용자, 그 사용자의 이메일에 해당하는 허용 목록 행(없으면 None)."""
    user: UserRecord
    session_created_at: datetime
    allowed: AllowedEmail | None


class AuthRepository:
    def __init__(self, session: AsyncSession) -> None: ...

    async def get_allowed_email(self, email: str) -> AllowedEmail | None: ...
    async def find_users_by_email_or_sub(self, *, email: str, google_sub: str) -> list[UserRecord]: ...
    async def create_user(self, *, email: str, google_sub: str, display_name: str | None) -> UserRecord: ...
    async def update_display_name(self, user_id: UUID, display_name: str | None) -> None: ...
    async def add_login_session(self, *, token_hash: str, user_id: UUID, expires_at: datetime) -> None: ...
    async def find_active_login(self, token_hash: str) -> ActiveLogin | None: ...
    async def delete_login_session(self, token_hash: str) -> None: ...
    async def delete_expired_login_sessions(self, user_id: UUID) -> None: ...


def get_auth_repository(session: DbSession) -> AuthRepository: ...   # FastAPI 의존성
```

메서드마다 지킬 것:

- **repository는 커밋하지 않는다.** 트랜잭션의 경계는 아래 2번의 `get_db_session`이 정한다. 이유: 로그인에 성공했을 때의 쓰기(사용자 등록, 옛 로그인 상태와 만료된 로그인 상태의 삭제, 새 로그인 상태의 저장)가 한 트랜잭션이어야 한다(E1 S1.3 "못 박을 것"). 메서드마다 커밋하면 중간에 실패했을 때 반쯤 쓴 상태가 남는다. `flush`는 해도 된다.
- **이메일은 받은 그대로 비교한다.** 소문자로 바꾸는 것은 service의 일이다. repository가 몰래 바꾸면 service가 바꾸지 않는 결함을 테스트가 놓친다.
- `find_users_by_email_or_sub`: 이메일이 같거나 `google_sub`가 같은 행을 **모두** 돌려준다. 이메일만으로 찾는 메서드를 따로 만들지 마라. 이유: 사용자를 이메일만으로 찾으면 같은 이메일을 새로 가진 다른 Google 계정이 기존 사람의 기록을 넘겨받는다(ADR-027).
- `add_login_session`: `created_at`은 넘기지 않고 데이터베이스의 기본값(`now()`)에 맡긴다. 이유: 관문이 이 값을 `allowed_emails.created_at`과 비교하므로 같은 시계에서 나와야 한다.
- `find_active_login`: 쿠키 값의 해시로 **만료되지 않은**(`expires_at`이 지금보다 뒤인) 로그인 상태를 찾고, 그 사용자와, 그 사용자의 이메일로 찾은 허용 목록 행을 함께 돌려준다. 허용 목록에 없으면 `allowed`가 `None`이다. 한 번의 질의로 해도 되고 나눠도 된다. 행을 바꾸지 마라(마지막 사용 시각 기록, 만료 연장 등). 이유: 로그인 상태의 만료 시각은 늘리지 않는다(ADR-027).
- `delete_login_session`: 해시가 가리키는 행 하나만 지운다. 없으면 아무 일도 하지 않고 예외도 내지 않는다.
- `delete_expired_login_sessions`: 그 사용자의 만료된 행만 지운다. 다른 사용자의 행과 만료되지 않은 행은 그대로 둔다.
- "지금"을 데이터베이스의 `now()`로 할지 파이썬의 시각으로 할지는 재량이다. 다만 `find_active_login`과 `delete_expired_login_sessions`가 같은 기준을 써야 한다.

### 2. 요청마다의 세션과 트랜잭션 — `app/core/database.py`

```python
async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]: ...
DbSession = Annotated[AsyncSession, Depends(get_db_session, scope="function")]
```

- 요청 하나에 세션과 트랜잭션 하나다. 경로가 정상으로 끝나면 커밋하고, 예외가 나면 되돌린다.
- **커밋은 응답을 보내기 전에 끝나야 한다.** 설치된 FastAPI(0.165)의 yield 의존성은 기본값(`scope="request"`)에서 응답을 보낸 **뒤에** 정리된다. 그러면 커밋이 실패해도 클라이언트는 이미 성공 응답과 쿠키를 받는다. `Depends(..., scope="function")`을 쓰면 경로 함수가 끝난 뒤, 응답을 보내기 전에 정리된다. 이 의존성을 쓰는 곳은 모두 `DbSession` 별칭을 거치게 하라.
- **엔진은 앱 인스턴스마다 하나이며, 처음 쓰일 때 만든다.** `app.state`에 두고, 앱이 내려갈 때(`create_app()`의 lifespan) `dispose()`한다. 이유: (1) `create_app()`과 앱의 시작은 설정을 읽지 않아야 한다(`tests/test_main.py`). (2) 테스트마다 앱과 이벤트 루프가 새로 뜨는데, 모듈 전역에 둔 엔진은 다른 이벤트 루프에서 만든 연결을 다시 써서 asyncpg가 실패한다.
- 세션은 첫 질의를 보낼 때까지 데이터베이스에 접속하지 않게 둔다. 이후 step의 관문은 쿠키가 없으면 데이터베이스에 닿지 않고 401을 내야 한다.
- `app/main.py`에는 lifespan을 더하는 조립만 한다.

### 3. 테스트

- `tests/auth/test_repository.py` (`integration`, `clean_db` 사용): TC-1.1.6과 메서드마다의 동작을 확인한다. 적어도 다음을 넣는다.
  - TC-1.1.6: 만료 시각이 지난 것과 지나지 않은 것을 각각 `find_active_login`으로 찾는다.
  - `find_active_login`이 허용 목록에 없는 사용자에게 `allowed=None`을, 있는 사용자에게 그 행(역할과 `created_at`)을 돌려주는지. 그리고 부른 뒤에 `login_sessions` 행의 모든 값이 그대로인지.
  - `find_users_by_email_or_sub`가 이메일만 같은 행, `google_sub`만 같은 행, 둘 다 같은 행을 모두 찾고, 둘 다 다른 행은 찾지 않는지. 두 행에 하나씩 걸리는 경우(이메일은 A 행, `google_sub`는 B 행) 두 행을 다 돌려주는지.
  - `delete_expired_login_sessions`가 그 사용자의 만료된 행만 지우는지(다른 사용자의 만료된 행, 그 사용자의 만료되지 않은 행은 남는다).
  - `delete_login_session`이 없는 해시에 예외를 내지 않는지.
  - 같은 세션에서 `create_user`와 `add_login_session`을 부른 뒤 커밋하지 않고 되돌리면 두 행이 모두 남지 않는지(repository가 몰래 커밋하지 않는다).
- `tests/core/test_database.py`에 `get_db_session`의 테스트를 더한다(`integration`). 테스트 안에서만 붙이는 경로로 확인한다.
  - 경로가 `allowed_emails`에 한 행을 넣고 정상으로 끝나면 그 행이 남는다.
  - 경로가 행을 넣은 뒤 예외를 내면 그 행이 남지 않는다.
  - **커밋이 실패하면 응답이 500이다**(`AsyncSession.commit`을 예외를 내는 것으로 바꾸고 `raise_server_exceptions=False`로 확인한다). 커밋을 응답 뒤에 하는 구현은 200을 낸다.
  - 앱 두 개를 차례로 만들어 각각 `TestClient`로 데이터베이스를 쓰는 요청을 보내도 둘 다 성공한다(엔진이 앱마다 따로다).

### 4. 순서 — RED 커밋을 남긴다

1. 위 테스트를 먼저 쓰고, `AuthRepository`와 `get_db_session`은 시그니처만 있는 빈 껍데기로 둔다.
2. 테스트가 실패하는 것을 눈으로 확인한다.
3. `test(1-login-allowlist): RED — 로그인 상태와 허용 목록을 읽고 쓰는 repository`로 커밋한다.
4. 구현해서 초록으로 만든다.

## Acceptance Criteria

```bash
uv run pytest tests/auth/test_repository.py tests/core/test_database.py tests/test_main.py -v
scripts/check.sh
```

**반증 조건** — 아래의 틀린 구현으로도 초록이면 그 테스트가 틀린 것이다.

- `find_active_login`이 만료 시각을 거르지 않아도 초록이면 TC-1.1.6이 틀렸다.
- `find_active_login`이 허용 목록을 보지 않고 언제나 `allowed=None`(또는 언제나 어떤 행)을 돌려줘도 초록이면 그 테스트가 틀렸다.
- `find_users_by_email_or_sub`가 이메일로만 찾아도 초록이면 그 테스트가 틀렸다.
- `delete_expired_login_sessions`가 그 사용자의 모든 행, 또는 모든 사용자의 만료된 행을 지워도 초록이면 그 테스트가 틀렸다.
- repository의 메서드가 안에서 커밋해도 초록이면 되돌리기 테스트가 틀렸다.
- `get_db_session`이 응답을 보낸 뒤에 커밋해도(`scope`를 빼도) 초록이면 커밋 실패 테스트가 틀렸다.
- 엔진을 모듈 전역에 하나만 두어도 초록이면 앱 두 개의 테스트가 틀렸다.

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

- 이메일만으로 사용자를 찾는 메서드를 만들지 마라. 이유: 위 1번(ADR-027).
- 쿠키 값을 받거나 저장하는 메서드를 만들지 마라. repository는 해시만 다룬다. 이유: 데이터베이스의 내용이 새어도 로그인 상태를 가로챌 수 없어야 한다(ARCHITECTURE.md 6절).
- 허용 목록을 바꾸는 메서드(넣기, 빼기, 역할 바꾸기)를 만들지 마라. 이유: 허용 목록은 SQL로만 다룬다(ADR-024).
- 허용 목록이나 로그인 상태를 프로세스 메모리에 담아 두지 마라(캐시, 전역 사전 등). 이유: SQL로 바꾼 것이 다음 요청부터 반영되어야 한다(ADR-024).
- `create_app()`이나 lifespan의 시작에서 설정을 읽거나 엔진을 만들지 마라. 이유: 위 2번.
- service, 관문, 라우터를 만들지 마라. 이유: 뒤의 step이 한다.
- 기존 테스트를 깨뜨리지 마라
- `MANUAL.md`의 항목을 체크하지 마라. 이유: 그 항목은 사람이 직접 본 것만 체크한다.
