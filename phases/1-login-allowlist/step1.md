# Step 1: auth-models

## 읽어야 할 파일

먼저 아래 파일들을 읽고 이 step의 근거와 설계 의도를 파악하라:

- `docs/backlog/epic-1/E1-login-allowlist.md` — "못 박을 것 (Epic 전역)", S1.1(T1.1.1과 그 "못 박을 것")
- `docs/backlog/epic-1/testcase.md` — TC-1.1.1 ~ TC-1.1.5
- `docs/ADR.md` — ADR-024의 결정, ADR-027의 "사용자의 식별"과 "로그인 상태의 수명"
- `README.md` — "허용 목록에 사람 넣고 빼기"의 SQL. 이 스키마에 기대므로 컬럼 이름과 기본값을 맞춰야 한다
- `migrations/env.py`, `migrations/versions/d98e11845e03_enable_pgvector_extension.py`, `migrations/script.py.mako`, `alembic.ini`
- `app/core/database.py`, `tests/conftest.py`, `tests/support/postgres.py`, `tests/core/test_database.py`
- `tests/support/settings.py`와 `tests/conftest.py`의 `app_env` (step 0)

`docs/ARCHITECTURE.md` 6절(데이터 모델)은 프롬프트에 이미 들어 있다. `allowed_emails`, `users`, `login_sessions`의 그림, 그 아래의 "사용자 영역" 설명, 로그인 상태의 수명 표가 이 step의 스키마다.

이전 step에서 만들어진 코드를 꼼꼼히 읽고, 설계 의도를 이해한 뒤 작업하라.

## 작업

세 테이블을 선언하고 마이그레이션을 만든다. 그리고 이후 step의 통합 테스트가 함께 쓸 데이터베이스 fixture를 만든다.

### 1. 공통 Base — `app/core/models.py`

```python
class Base(DeclarativeBase): ...
```

모든 기능의 모델이 이 `Base`를 물려받는다. 이 파일에는 선언만 둔다.

### 2. 모델 — `app/auth/models.py`

`AllowedEmailModel`, `UserModel`, `LoginSessionModel` 세 클래스를 둔다. 테이블의 이름, 컬럼, 타입, 제약은 ARCHITECTURE.md 6절을 그대로 따른다. 특히 다음을 빠뜨리지 마라.

| 테이블 | 반드시 있어야 하는 것 |
| --- | --- |
| `allowed_emails` | `email text` PK, `CHECK (email = lower(email))`, `role text`와 `CHECK (role IN ('user', 'admin'))`, `created_at timestamptz` 기본값 `now()` |
| `users` | `id uuid` PK와 데이터베이스 쪽 기본값(`gen_random_uuid()`), `email text` 고유와 `CHECK (email = lower(email))`, `google_sub text` 고유, `display_name text` NULL 허용, `created_at timestamptz` 기본값 `now()` |
| `login_sessions` | `token_hash text` PK, `user_id uuid` FK → `users.id` `ON DELETE CASCADE`, `expires_at timestamptz`, `created_at timestamptz` 기본값 `now()`, `login_sessions(user_id)`의 인덱스 |

- `users.display_name`을 뺀 모든 컬럼은 `NOT NULL`이다.
- `allowed_emails`와 `users`를 외래 키로 잇지 마라. 이유: 아직 로그인하지 않은 사람도 허용 목록에 있을 수 있고, 목록에서 빠진 사람의 `users` 행은 남아야 한다(ARCHITECTURE.md 6절).
- **기본값은 데이터베이스 쪽(`server_default`)에 둔다.** 이유: README의 SQL은 `created_at`을 적지 않고 넣으며, 이후 step의 관문은 `login_sessions.created_at`과 `allowed_emails.created_at`을 비교한다. 두 시각이 같은 시계(데이터베이스의 `now()`)에서 나와야 비교가 맞다.
- 시각 컬럼은 모두 `timezone=True`로 선언한다.

### 3. 마이그레이션 — `migrations/versions/`, `migrations/env.py`

- 새 리비전 하나를 만든다. `down_revision`은 `d98e11845e03`이다. 위 표의 제약을 모두 담고, `downgrade()`는 세 테이블과 인덱스를 지우되 `vector` 확장은 지우지 않는다.
- `migrations/env.py`의 `target_metadata`를 `Base.metadata`로 바꾸고, 모델 모듈을 import해서 세 테이블이 metadata에 실리게 한다.
- 모델과 마이그레이션이 어긋나지 않는지 확인하는 테스트를 하나 둔다. 마이그레이션을 끝까지 적용한 데이터베이스와 `Base.metadata`를 Alembic으로 비교해서(`alembic check`에 해당하는 것) 차이가 없어야 한다.

### 4. 통합 테스트용 fixture — `tests/conftest.py`

이후 step(repository, service, 관문, 라우터)의 통합 테스트가 이것을 쓴다. 이름과 동작을 바꾸지 마라.

- **`clean_db`** (function 범위, autouse 아님): step 0의 `app_env`를 쓰고, 그 위에서 `DATABASE_URL` 환경변수를 기존 `database_url` fixture(마이그레이션을 끝까지 적용한 컨테이너)의 주소로 바꾸고 `get_settings.cache_clear()`를 부른다. 그리고 `Base.metadata`의 모든 테이블을 비운 뒤(`TRUNCATE ... CASCADE`) 그 주소를 돌려준다.
  - 테이블을 테스트가 끝날 때가 아니라 **시작할 때** 비우는 이유: 앞 테스트가 중간에 실패해도 다음 테스트가 깨끗한 상태에서 시작한다.
  - 동기 테스트(뒤의 step이 쓰는 `TestClient`)와 비동기 테스트 양쪽에서 쓸 수 있어야 한다.
- 테스트가 데이터베이스를 직접 읽고 쓰는 데 쓸 비동기 세션을 얻는 방법도 함께 둔다(예: `clean_db`의 주소로 엔진을 만들고 테스트가 끝나면 `dispose()`하는 비동기 fixture). 엔진은 테스트마다 새로 만든다. 이유: pytest-asyncio가 테스트마다 이벤트 루프를 새로 만들므로(`pyproject.toml`), 다른 루프에서 만든 asyncpg 연결을 다시 쓰면 실패한다.

### 5. 테스트 — `tests/auth/test_models.py`

TC-1.1.1 ~ TC-1.1.5. 모두 `integration` 표시를 붙이고 `clean_db`를 쓴다.

- TC-1.1.1 ~ TC-1.1.4: SQL이나 모델로 넣어 보고, **어느 제약 때문에 거부됐는지까지** 확인한다(예: `IntegrityError`의 원인이 CHECK 위반인지, 고유 위반인지, NOT NULL 위반인지). 그냥 "예외가 났다"만 보면, 다른 이유로 실패한 것도 통과한다.
- TC-1.1.2는 `owner`가 거부되는 것만이 아니라 `user`와 `admin`이 들어가는 것도 확인한다.
- **TC-1.1.5는 공유하는 `database_url`의 데이터베이스에서 하지 마라.** 같은 컨테이너에 새 데이터베이스를 만들거나 새 컨테이너를 띄워 거기서 끝까지 올리고, 한 단계 내리고, 다시 올린다. 이유: 되돌리는 도중에 실패하면 공유 데이터베이스에 테이블이 없는 채로 남아, 뒤의 모든 통합 테스트가 엉뚱한 이유로 깨진다.
- TC-1.1.5는 동기 테스트로 쓴다. 이유: `migrations/env.py`가 `asyncio.run()`을 부르므로, 이미 이벤트 루프가 돌고 있는 비동기 테스트 안에서 Alembic 명령을 부르면 실패한다(기존 `database_url` fixture도 그래서 동기다).

### 6. 순서 — RED 커밋을 남긴다

1. `tests/auth/test_models.py`를 먼저 쓴다. 이때 `clean_db`와 `app/core/models.py`, 빈 `app/auth/models.py`(테이블이 없는 상태)까지만 둔다.
2. 테스트가 "테이블이 없다"는 이유로 실패하는 것을 눈으로 확인한다.
3. `test(1-login-allowlist): RED — 허용 목록, 사용자, 로그인 상태의 제약을 확인한다`로 커밋한다.
4. 모델과 마이그레이션을 만들어 초록으로 만든다.

## Acceptance Criteria

```bash
uv run pytest tests/auth/test_models.py tests/core/test_database.py -v
scripts/compose-smoke.sh    # 마이그레이션을 더했다. compose의 migrate가 새 리비전까지 올라가야 한다.
scripts/check.sh
```

**반증 조건** — 아래의 틀린 구현으로도 초록이면 그 테스트가 틀린 것이다.

- `allowed_emails`나 `users` 가운데 한쪽에서만 소문자 CHECK를 빼도 초록이면 TC-1.1.1이 틀렸다. 두 테이블을 각각 확인해야 한다.
- 역할의 CHECK를 빼도, 또는 CHECK가 `admin`까지 거부해도 초록이면 TC-1.1.2가 틀렸다.
- `google_sub`의 고유 제약이나 `NOT NULL`을 빼도 초록이면 TC-1.1.3이 틀렸다.
- `ON DELETE CASCADE`를 빼도 초록이면 TC-1.1.4가 틀렸다. 로그인 상태를 두 개 만들어 둘 다 지워지는지 확인한다.
- `downgrade()`가 `vector` 확장까지 지워도 초록이면 TC-1.1.5가 틀렸다.
- 모델에는 있는 컬럼을 마이그레이션에서 빠뜨려도 초록이면 metadata 비교 테스트가 틀렸다.

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

- ARCHITECTURE.md 6절과 다른 이름, 타입, 제약을 쓰지 마라. 고쳐야 할 것을 찾으면 문서를 고치지 말고 summary에 적어라. 이유: README의 SQL과 다른 Epic이 이 스키마에 기댄다.
- `user_settings`나 다른 기능의 테이블을 만들지 마라. 이유: 그 Epic이 만든다(E8 등).
- 모델 파일에 판정하는 함수(만료 확인 등)를 두지 마라. 이유: `models.py`는 TDD 가드가 테스트를 요구하지 않는 선언 전용 파일이다. 판정은 repository와 service에 둔다.
- 통합 테스트가 개발자의 `.env`나 compose로 띄운 개발용 데이터베이스에 접속하게 만들지 마라. 이유: 마이그레이션을 되돌리는 테스트가 개발용 데이터를 지울 수 있다(DEVELOPMENT.md 4.3절).
- 셸에서 `psql`로 `DROP`이나 `TRUNCATE`를 실행하지 마라. 이유: 명령 가드가 막는다. 테이블을 비우는 일은 테스트 코드 안에서만 한다.
- repository를 만들지 마라. 이유: 다음 step의 일이다.
- 기존 테스트를 깨뜨리지 마라
- `MANUAL.md`의 항목을 체크하지 마라. 이유: 그 항목은 사람이 직접 본 것만 체크한다.
