# Step 11: login-check-script

## 읽어야 할 파일

먼저 아래 파일들을 읽고 이 step의 근거와 설계 의도를 파악하라:

- `docs/backlog/epic-1/E1-login-allowlist.md` — S1.7 전체(T1.7.2와 "못 박을 것"), "못 박을 것 (Epic 전역)"의 로그 규칙
- `docs/backlog/epic-1/testcase.md` — TC-1.7.2, TC-1.7.3, TC-1.7.4, 그리고 **"로컬 로그인 점검의 테이블 상태"의 두 표와 그 위의 안내** 전부. 이 표가 이 스크립트의 판정 기준이다.
- `docs/ADR.md` — **ADR-026**(재검토 조건 포함), ADR-027의 "로그인 상태의 수명"
- `docs/API.md` 4.2절과 4.3절 — 프론트엔드가 로그인을 시작하는 방법(화면 이동), `GET /api/me`와 로그아웃의 응답
- `README.md` — "허용 목록에 사람 넣고 빼기"의 SQL(점검 전 상태를 맞추는 SQL을 이 꼴로 보여 준다)
- `compose.yaml` — 개발용 데이터베이스의 계정과 `DB_PORT`, 서버의 `API_PORT`, 서버에 넘기는 `FRONTEND_URL`의 기본값(step 0). 서버에 `LOGIN_SESSION_TTL_HOURS`는 넘기지 않으므로 서버는 기본값 336을 쓴다
- `scripts/login_check.py`, `tests/infra/test_login_check.py` (step 10)
- `app/auth/models.py` (step 1) — 세 테이블의 컬럼. 스크립트는 이것을 import하지 않고 SQL로 읽는다
- `tests/conftest.py`의 `clean_db` (step 1), `tests/infra/test_dependencies.py` (step 4)

이전 step에서 만들어진 코드를 꼼꼼히 읽고, 설계 의도를 이해한 뒤 작업하라.

## 작업

`scripts/login_check.py`를 완성한다. 백엔드 담당자가 프론트엔드 레포 없이, 실제 Google 계정 두 개로 로그인과 로그아웃을 끝까지 따라가며 시점마다 세 테이블과 브라우저의 상태를 보고, 표와 다른 것이 있으면 0이 아닌 종료 코드로 끝나는 점검 스크립트다. 사람은 Google 화면에서 계정을 고르기만 한다.

이 스크립트의 `main`은 `scripts/check.sh`와 CI에서 실행하지 않는다(ADR-026). 그러므로 **판정과 출력은 Playwright와 데이터베이스에서 떼어 낸 순수 함수로 만들고, 그 함수들을 테스트한다.** 브라우저를 모는 부분은 그 함수들을 부르는 얇은 층으로 둔다.

### 1. 의존성

`uv add --dev playwright`. 서버의 이미지에 들어가지 않도록 개발 의존성으로만 둔다(ADR-026). `tests/infra/test_dependencies.py`에 `playwright`가 `[dependency-groups].dev`에 있고 `[project].dependencies`에는 없는지 더한다.

### 2. 실행 방법과 설정

```bash
uv run python scripts/login_check.py --allowed-email <허용 목록에 넣은 계정 A> --denied-email <허용 목록에 없는 계정 B>
```

- 이 인자 이름은 MANUAL 점검표와 README가 그대로 쓴다. 바꾸지 마라.
- 이메일 인자는 소문자로 바꿔서 쓴다.
- `FRONTEND_URL`, `API_PORT`, `DB_PORT`는 compose와 같은 방법으로 정한다. 환경변수가 있으면 그것을, 없으면 레포 최상위의 `.env`를, 그것도 없으면 compose의 기본값(`http://localhost:5173`, `8080`, `5432`)을 쓴다. 이유: 대역 서버는 서버가 쓰는 것과 같은 `FRONTEND_URL`에 떠야 한다(E1 T1.7.3). 백엔드의 주소는 `http://localhost:{API_PORT}`, 데이터베이스는 compose의 로컬 전용 계정으로 `localhost:{DB_PORT}`에 붙는다.
- 파일 맨 위의 독스트링에 실행 방법, 사람이 하는 일, 종료 코드의 뜻을 적는다.

### 3. 브라우저를 열기 전의 확인

아래 가운데 하나라도 어긋나면 **브라우저를 열지 않고** 무엇이 어긋났는지와 고치는 방법을 보여 준 뒤 0이 아닌 코드로 끝난다.

1. 백엔드의 `GET /api/health`가 `200`이다. 아니면 compose로 서버를 띄우라고 안내한다.
2. 백엔드의 `GET /api/auth/google/login`을 리디렉션을 따라가지 않고 불러, `Location`의 `redirect_uri`가 `{FRONTEND_URL}/api/auth/google/callback`과 같고 `client_id`가 비어 있지 않은지 본다. 이유: 서버와 스크립트의 `FRONTEND_URL`이 다르거나 `.env`에 Google 클라이언트의 값을 넣지 않고 compose를 띄웠으면, Google 화면까지 가서야 실패한다. 이 요청은 데이터베이스를 쓰지 않는다.
3. **점검 전 상태 확인**(TC-1.7.2):

   ```python
   @dataclass(frozen=True)
   class PrecheckProblem:
       problem: str    # 맞지 않는 조건
       fix_sql: str    # 그것을 맞추는 SQL. README의 SQL과 같은 꼴(이메일을 lower()로 감쌈)

   async def precheck(database_url: str, *, allowed_email: str, denied_email: str) -> list[PrecheckProblem]: ...
   ```

   조건은 testcase.md 두 표의 "로그인 전" 줄이다. A가 허용 목록에 `user`로 있다, A의 `users` 행이 없다, B가 허용 목록에 없다, B의 `users` 행이 없다. 모두 맞으면 빈 목록이다.
   - **데이터베이스를 읽기만 한다.** 읽기 전용 트랜잭션으로 연결하라(예: asyncpg의 `server_settings`에 `default_transaction_read_only`). 이유: 스크립트가 개발자의 데이터를 지우거나 바꾸면 안 된다(E1 S1.7 "못 박을 것"). 상태를 맞추는 SQL은 보여 주기만 하고 실행하지 않는다.
4. `FRONTEND_URL`의 포트가 비어 있다. 프론트엔드의 개발 서버가 떠 있으면 끄라고 안내한다.

### 4. 점검의 흐름

1. step 10의 `FrontendStandIn`을 `FRONTEND_URL`의 호스트와 포트에, 백엔드를 향해 띄운다.
2. Playwright로 **화면이 보이는** Chromium을 연다(`headless=False`). 점검마다 `browser.new_context()`로 새 컨텍스트를 만든다. 영구 프로필(`launch_persistent_context`, `user_data_dir`)을 쓰지 마라. 이유: 점검마다 쿠키가 없는 상태에서 시작해야 하고, Google의 로그인 상태가 디스크에 남으면 안 된다(E1 S1.7 "못 박을 것").
3. **점검 1(계정 A)**: 대역 서버의 `/`를 연 상태에서 "로그인 전"을 출력한다. 브라우저를 `{FRONTEND_URL}/api/auth/google/login`으로 이동시키고(프론트엔드가 하는 대로 화면 이동), 사람에게 Google 화면에서 계정 A를 고르라고 안내한 뒤, 주소가 `FRONTEND_URL`로 돌아올 때까지 기다린다. 돌아온 시각을 로그인한 시각으로 기록하고 "로그인 후"를 출력한다. 그다음 `GET /api/me`를 부르고 "로그아웃 전"을 출력한 뒤, `POST /api/auth/logout`을 부르고 "로그아웃 후"를 출력한다. `GET /api/me`와 로그아웃은 **브라우저 안에서** `fetch(..., { credentials: 'include' })`로 부른다(E1 T1.7.2).
4. **점검 2(계정 B)**: 새 컨텍스트에서 "로그인 전"을 출력하고(`login_sessions`의 전체 행 수를 기록), 같은 방법으로 로그인을 시도해 "로그인 시도 후"를 출력한다.
5. 시점마다 testcase.md의 표와 대조하고, 다른 것이 하나라도 있으면 끝에 모아 보여 주고 0이 아닌 코드로 끝난다. 모두 같으면 0으로 끝난다.

- 기다리는 시간에는 상한을 둔다(예: 5분). 넘으면 "Google이 자동화된 브라우저의 로그인을 막았을 수 있다. 그 경우의 방법은 ADR-026의 재검토 조건에 따라 사람이 정한다"고 안내하고 0이 아닌 코드로 끝난다.

### 5. 판정과 출력 — 순수 함수

시점의 상태를 담는 값과 판정 함수를 둔다. 모양은 재량이지만 다음을 지킨다.

- 데이터베이스의 상태: 두 계정의 이메일에 관한 `allowed_emails`, `users`, `login_sessions`의 행(만든 시각, 만료 시각, 역할, `google_sub`, `display_name`, `token_hash` 포함)과 `login_sessions`의 전체 행 수.
- 브라우저의 상태: 주소, 쿠키마다 이름과 속성(`Path`, `HttpOnly`, `Secure`, `SameSite`)과 **값의 SHA-256**, `GET /api/me`의 상태 코드와 본문, 로그아웃의 상태 코드. **쿠키의 값 자체는 이 값에 담지 않는다.** Playwright에서 쿠키를 읽는 자리에서 바로 해시로 바꾼다. 이유: 담지 않은 값은 출력하거나 파일에 남길 수 없다.
- 판정 함수는 testcase.md 두 표의 **칸마다** 하나씩 확인해서, 다른 칸을 사람이 읽을 수 있는 문장의 목록으로 돌려준다. 빠뜨리기 쉬운 칸은 다음과 같다.
  - 로그인 후: `token_hash`가 `diegesis_session` 쿠키 값의 SHA-256과 같다. `expires_at`이 로그인한 시각 + 336시간과 1분 안에서 같다. `users.created_at`이 방금이다. `diegesis_session`에 `HttpOnly`, `SameSite=Lax`, `Path=/`가 있고 `Secure`가 없다. `diegesis_oauth_state` 쿠키가 없다. 주소가 `{FRONTEND_URL}/`이다.
  - 로그아웃 전: 세 테이블이 로그인 후와 **값까지** 같다. `GET /api/me`가 `200`이고 `email`이 A, `role`이 `user`, `display_name`이 `users.display_name`과 같다.
  - 로그아웃 후: 로그아웃이 `204`, A의 `login_sessions` 행이 없고 `users` 행은 그대로, `diegesis_session` 쿠키가 없고 `GET /api/me`가 `401`.
  - 점검 2의 로그인 시도 후: 주소가 `{FRONTEND_URL}/login?error=NOT_ALLOWED`, B의 `allowed_emails`와 `users` 행이 없음, `login_sessions`의 전체 행 수가 로그인 전과 같음, 두 쿠키가 모두 없음, `GET /api/me`가 `401`.
- 출력 함수는 시점마다 세 테이블과 브라우저의 상태를 사람이 표와 대조할 수 있게 보여 준다. 형식은 판정 대상이 아니다(testcase.md "이 Epic에서 판정하지 않는 것"). 다만 **쿠키의 값과 `token_hash`의 값을 출력하지 않고**, `token_hash`는 쿠키 값의 SHA-256과 같은지만 출력한다(E1 S1.7 "못 박을 것").

### 6. 테스트

- `tests/infra/test_login_check_precheck.py` (`integration`, `clean_db`): TC-1.7.2. 네 경우(A가 허용 목록에 없음, A의 `users` 행이 있음, B가 허용 목록에 있음, 모두 맞음)에 각각 `precheck`를 부른다. 앞의 세 경우에는 맞지 않는 조건과 그 SQL이 나오고, 마지막 경우에는 빈 목록이다. 각 경우의 전후로 세 테이블의 내용이 같다. 그리고 `precheck`가 쓰는 연결로 `INSERT`를 시도하면 읽기 전용이라 실패하는지 확인한다. B의 `users` 행이 있는 경우도 확인한다.
  - 나온 SQL을 테스트 안에서 실행해 보면(읽기 전용이 아닌 연결로) 그 조건이 맞춰지는지도 확인한다. 이유: 보여 준 SQL이 틀리면 사람이 따라 해도 점검을 시작할 수 없다.
- `tests/infra/test_login_check_judge.py` (`unit`)
  - 표와 같은 상태를 만들어 판정하면 다른 칸이 없다(점검 1의 네 시점, 점검 2의 두 시점).
  - 아래 "반증 조건"의 상태마다 판정이 그 칸을 보고한다.
  - 쿠키 값이 `cookie-secret-marker`인 상태를 출력하면, 출력에 그 값도 그 SHA-256도 없다.
  - `redirect_uri`와 `client_id`의 확인 함수: 같을 때 통과, `redirect_uri`가 `http://localhost:8080/...`일 때와 `client_id`가 비었을 때 보고.
  - 스크립트의 소스에 `launch_persistent_context`, `user_data_dir`, `AutomationControlled`, `stealth`, `headless=True`, 그리고 Google 화면에 입력하는 `.fill(`, `.type(`, `.press(`, `keyboard`가 없다. 이유: 계정을 고르고 비밀번호를 넣는 일은 사람이 하며, 자동화 탐지를 피하는 옵션은 쓰지 않는다(E1 S1.7 "못 박을 것", ADR-026).

### 7. 순서 — RED 커밋을 남긴다

1. 위 테스트를 먼저 쓰고, `precheck`와 판정, 출력 함수는 시그니처만 있는 빈 껍데기로 둔다.
2. 테스트가 실패하는 것을 눈으로 확인한다.
3. `test(1-login-allowlist): RED — 로컬 로그인 점검의 점검 전 확인과 표 대조`로 커밋한다.
4. 구현해서 초록으로 만든다. 브라우저를 모는 부분은 마지막에 쓴다.

## Acceptance Criteria

```bash
uv run pytest tests/infra/test_login_check.py tests/infra/test_login_check_precheck.py tests/infra/test_login_check_judge.py tests/infra/test_dependencies.py -v
uv run python scripts/login_check.py --help    # 인자 설명이 나오고 0으로 끝난다. 브라우저를 열지 않는다.
scripts/check.sh
```

실제 Google 계정으로 하는 점검(TC-1.7.3, TC-1.7.4)은 이 step의 완료 조건이 아니다. 사람이 MANUAL 점검에서 한다. 실행해 보려고 하지 마라.

**반증 조건** — 아래의 틀린 상태를 판정해도 다른 칸이 보고되지 않으면 그 테스트가 틀린 것이다.

- `token_hash`가 쿠키 값의 SHA-256과 다르다(쿠키 값을 그대로 저장한 서버).
- 로그인 후의 `diegesis_session`에 `Secure`가 있다, 또는 `HttpOnly`가 없다.
- 로그인 후에 `diegesis_oauth_state` 쿠키가 남아 있다.
- `expires_at`이 로그인한 시각 + 336시간과 2분 다르다.
- 로그아웃 전의 `login_sessions` 행의 `expires_at`이 로그인 후보다 늘었다(`GET /api/me`가 행을 고친 서버).
- 로그아웃 후에 A의 `login_sessions` 행이 남아 있다, 또는 A의 `users` 행이 지워졌다.
- 점검 2에서 B의 `users` 행이 생겼다, 또는 `login_sessions`의 전체 행 수가 늘었다.
- 점검 2의 주소가 `/login?error=LOGIN_FAILED`다.
- `precheck`가 점검 전 상태를 확인하지 않거나 확인하면서 테이블을 고쳐도 초록이면 TC-1.7.2가 틀렸다.

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

- Google 계정의 비밀번호를 코드, 파일, 환경 변수, 인자로 받지 마라. Google 화면에 아무것도 입력하지 마라. 이유: 계정을 고르고 비밀번호를 넣는 일은 사람이 한다(E1 S1.7 "못 박을 것").
- 자동화 탐지를 피하는 옵션(`--disable-blink-features=AutomationControlled`, 사용자 에이전트 바꾸기, stealth 플러그인 등)을 넣지 마라. 이유: Google 계정의 보호 장치를 우회하는 일이다(ADR-026).
- 개발용 데이터베이스에 쓰지 마라. 상태를 맞추는 SQL을 실행하지 마라. 이유: 개발자의 데이터를 지우거나 바꾸면 안 된다.
- 쿠키의 값과 `token_hash`의 값을 출력하거나 파일(스크린숏, 트레이스, HAR 포함)에 남기지 마라. 이유: 쿠키 값만 있으면 로그인 상태를 가로챌 수 있다.
- `scripts/check.sh`, CI, pytest가 `main`을 실행하거나 브라우저를 열게 만들지 마라. 이유: 실제 Google 계정과 사람의 입력이 필요하다(ADR-026).
- `playwright install`을 실행하지 마라. 이유: 브라우저는 점검하는 사람이 처음에 한 번 설치한다(ADR-026). 이 step의 테스트는 브라우저 없이 돈다.
- `app/`을 import하지 마라. 이유: 스크립트는 compose로 띄운 서버를 바깥에서 본다.
- README를 고치지 마라. 이유: 다음 step이 한다.
- 기존 테스트를 깨뜨리지 마라
- `MANUAL.md`의 항목을 체크하지 마라. 이유: 그 항목은 사람이 직접 본 것만 체크한다.
