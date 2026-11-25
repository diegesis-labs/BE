# Step 0: settings

## 읽어야 할 파일

먼저 아래 파일들을 읽고 이 step의 근거와 설계 의도를 파악하라:

- `docs/backlog/epic-1/E1-login-allowlist.md` — "못 박을 것 (Epic 전역)", S1.2의 T1.2.2, S1.5의 T1.5.1, S1.7의 T1.7.3과 그 "못 박을 것"의 마지막 항목(CI의 compose 스모크)
- `docs/backlog/epic-1/testcase.md` — TC-1.2.9, 그리고 맨 위의 두 문단(테스트의 `Origin`, 정상 ID 토큰)
- `docs/ADR.md` — ADR-027의 "`Secure`와 `FRONTEND_URL`"
- `app/core/config.py`, `tests/core/test_config.py` — 지금의 설정 클래스와 그 테스트(TC-0.1.x)
- `app/__main__.py`, `tests/test___main__.py`, `tests/test_main.py` — 서버가 시작할 때 설정을 읽는 곳과, `create_app()`이 설정을 읽지 않는다는 테스트
- `migrations/env.py` — 마이그레이션도 설정 클래스를 읽는다
- `compose.yaml`, `tests/infra/test_compose.py`, `scripts/compose-smoke.sh`
- `tests/conftest.py`, `tests/support/postgres.py`
- `.env.example`

이전 step에서 만들어진 코드를 꼼꼼히 읽고, 설계 의도를 이해한 뒤 작업하라.

## 작업

이 Epic이 쓸 설정값을 설정 클래스에 더하고, 설정값이 늘어나도 compose(로컬 실행과 CI의 스모크)가 계속 뜨게 한다. 그리고 이후 step의 테스트가 함께 쓸 설정 환경 fixture를 만든다.

### 1. 설정 클래스 — `app/core/config.py`

아래 다섯 값을 더한다. 이름, 뜻, 기본값은 `docs/CONFIGURATION.md` 3.1절과 3.3절에 이미 있다. `.env.example`에도 이미 있으므로 고치지 않아도 된다(빠진 것이 있으면 더한다).

```python
class Settings(BaseSettings):
    ...
    frontend_url: str                  # 필수. 아래 검증을 거친다.
    google_client_id: str              # 필수. 기본값 없음.
    google_client_secret: SecretStr    # 필수. 기본값 없음.
    login_session_ttl_hours: int = 336 # 0보다 커야 한다.
    login_cookie_name: str = "diegesis_session"

    @property
    def cookie_secure(self) -> bool: ...   # frontend_url의 스킴이 https이면 True
```

- **`FRONTEND_URL`의 검증**: CONFIGURATION.md 3.1절의 조건을 그대로 검증하고, 맞지 않으면 설정을 만들 때 검증 오류를 낸다. 스킴은 `http`나 `https`이고, 호스트가 있으며, 포트는 있어도 되고, 경로(끝의 `/` 포함), 쿼리, 프래그먼트, 사용자 정보가 없어야 한다. 스킴이 `http`이면 호스트가 `localhost`나 `127.0.0.1`일 때만 받아들인다. TC-1.2.9의 받아들일 값과 거부할 값을 그대로 테스트하라.
- **`cookie_secure`**: `Secure`를 붙일지는 이 속성 하나로만 정한다. 이후 step의 라우터가 이것을 읽는다. `APP_ENV`를 만들지 마라(ADR-027이 없앴다).
- **`google_client_secret`은 `SecretStr`로 둔다.** 이유: 설정 객체가 로그나 예외 메시지에 찍혀도 비밀값이 드러나지 않게 하기 위해서다(E1 "못 박을 것"의 로그 규칙).
- **Google의 두 값은 필수이지만 빈 문자열은 받아들인다.** 길이 검증을 걸지 마라. 이유: CI의 compose 스모크는 Google의 값 없이 서버를 띄운다(아래 3번). 빈 값으로 뜬 서버는 Google 로그인만 실패한다.

### 2. 새 필수 값 때문에 깨지는 기존 테스트

`FRONTEND_URL`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`이 필수가 되면 `DATABASE_URL`만 넣고 설정을 읽던 기존 테스트가 깨진다(`tests/core/test_config.py`의 TC-0.1.x, `tests/test___main__.py` 등). 이 테스트들은 **단언의 의도를 그대로 두고** 필요한 값을 더해서 고친다.

- 예: "`.env`에 다른 값만 있고 `DATABASE_URL`이 없으면 `database_url` 하나만 빠졌다고 나온다"는 테스트는, `.env`에 새 필수 값을 함께 적어서 여전히 `database_url` 하나만 빠지게 만든다. 빠진 값의 목록을 넓혀서 통과시키지 마라.
- `tests/core/test_config.py`의 `SETTING_NAMES`처럼 테스트가 지우는 환경변수의 목록에 새 이름을 더한다. 이유: 개발자의 셸에 그 값이 있으면 테스트 결과가 사람마다 달라진다.

### 3. compose — `compose.yaml`

`migrations/env.py`는 설정 클래스로 `DATABASE_URL`을 읽는다. 그래서 필수 값이 늘면 `api`만이 아니라 **`migrate`도** 그 값이 없으면 실패한다. 두 서비스의 `environment`에 아래 세 값을 똑같이 넣어라.

| 이름 | 값 |
| --- | --- |
| `FRONTEND_URL` | `${FRONTEND_URL:-http://localhost:5173}` |
| `GOOGLE_CLIENT_ID` | `${GOOGLE_CLIENT_ID:-}` |
| `GOOGLE_CLIENT_SECRET` | `${GOOGLE_CLIENT_SECRET:-}` |

- compose는 레포 최상위의 `.env`를 변수 치환에만 읽는다. 그래서 위처럼 쓰면 개발자의 `.env`에서 이 세 값만 컨테이너로 들어가고, `.env`의 `DATABASE_URL`은 들어가지 않는다. `env_file:`을 쓰지 마라. 이유: compose.yaml 맨 위의 주석대로, 개발자의 `.env`에 든 `localhost` 주소가 컨테이너 안의 주소를 덮어쓴다.
- `scripts/compose-smoke.sh`는 `--env-file /dev/null`로 돌므로 위의 기본값으로 뜬다. 스모크 스크립트는 고치지 않아도 되며, 고치더라도 Google의 값을 스크립트에 넣지 마라. 이유: CI에는 Google 클라이언트의 비밀값이 없다(E1 S1.7 "못 박을 것").
- `tests/infra/test_compose.py`에 테스트를 더한다. `api`와 `migrate`가 세 값을 가지는지, 두 서비스의 값이 같은지, `FRONTEND_URL`의 기본값이 `http://localhost:5173`인지, 어느 서비스에도 `env_file`이 없는지를 본다.

### 4. 테스트용 설정 환경 — `tests/conftest.py`, `tests/support/settings.py`

이후 step의 테스트는 앱을 만들 때 설정이 필요하다(라우터, 관문, 출처 확인이 설정을 읽는다). 설정을 준비하는 방법이 테스트마다 갈라지지 않도록 지금 한 곳에 만든다.

- `tests/support/settings.py`에 테스트가 쓰는 값을 상수로 둔다.

  ```python
  TEST_FRONTEND_URL = "http://localhost:5173"
  TEST_GOOGLE_CLIENT_ID = "test-client-id.apps.googleusercontent.com"
  TEST_GOOGLE_CLIENT_SECRET = "test-google-client-secret-4f9a"   # 로그에서 찾기 쉬운 고유한 값
  UNREACHABLE_DATABASE_URL = "postgresql+asyncpg://diegesis:diegesis@127.0.0.1:1/diegesis"
  ```

- `tests/conftest.py`에 fixture `app_env`(function 범위, autouse 아님)를 둔다. 이 fixture는 작업 경로를 빈 임시 폴더로 옮기고, 설정 클래스의 모든 환경변수를 지운 뒤 `DATABASE_URL=UNREACHABLE_DATABASE_URL`, `FRONTEND_URL`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`을 위 상수로 넣고, 앞뒤로 `get_settings.cache_clear()`를 부른다.
  - 작업 경로를 옮기는 이유: 개발자의 `.env`에 다른 `FRONTEND_URL`이 있으면 테스트가 그 값으로 돈다.
  - `DATABASE_URL`을 닿지 않는 주소로 두는 이유: 단위 테스트가 실수로 데이터베이스에 닿으면 조용히 통과하지 않고 연결 오류로 드러나게 하기 위해서다. 통합 테스트는 다음 step이 만드는 fixture가 이 값을 컨테이너의 주소로 바꾼다.
- `tests/support/test_settings.py`에 이 fixture를 쓴 상태에서 `get_settings()`가 위 상수를 돌려주는지, 작업 경로에 있던 `.env`의 값이 보이지 않는지를 확인하는 테스트를 둔다(DEVELOPMENT.md 4.2절: `tests/support/`의 도우미는 같은 폴더에서 테스트한다).

### 5. 순서 — RED 커밋을 남긴다

`FRONTEND_URL`의 검증은 판정하는 로직이다. 다음 순서를 지켜라(DEVELOPMENT.md 4.1절).

1. TC-1.2.9와 `cookie_secure`의 테스트를 먼저 쓰고, 필드는 두되 검증은 하지 않는 상태(거부할 값도 받아들임)로 둔다.
2. 거부할 값의 테스트가 실패하는 것을 눈으로 확인한다.
3. `test(1-login-allowlist): RED — FRONTEND_URL의 조건을 검증한다`로 커밋한다.
4. 검증을 구현해서 초록으로 만든다.

## Acceptance Criteria

```bash
uv run pytest tests/core/test_config.py tests/support/test_settings.py tests/infra/test_compose.py tests/test___main__.py tests/test_main.py -v
scripts/compose-smoke.sh    # compose.yaml을 고쳤다. Google의 값 없이 서버와 마이그레이션이 떠야 한다.
scripts/check.sh
```

**반증 조건** — 아래의 틀린 구현으로도 초록이면 그 테스트가 틀린 것이다.

- `http://diegesis.example`(localhost가 아닌 http)을 받아들여도 초록이면 TC-1.2.9가 틀렸다.
- `https://diegesis.example/`나 `https://diegesis.example/app`을 받아들여도 초록이면 TC-1.2.9가 틀렸다(문자열이 `/`로 끝나는지만 보는 구현은 `/app`을 놓친다).
- `http://127.0.0.1:5173`을 거부해도 초록이면 TC-1.2.9가 틀렸다.
- `cookie_secure`가 언제나 `True`이거나 언제나 `False`여도 초록이면 그 테스트가 틀렸다. https와 http 두 값을 모두 확인해야 한다.
- `migrate`에 세 값을 넣지 않아도 초록이면 compose 테스트가 틀렸다(스모크도 그때 빨개져야 한다).
- `app_env`가 작업 경로를 옮기지 않아서 개발자의 `.env`가 보여도 초록이면 `tests/support/test_settings.py`가 틀렸다.

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

- `APP_ENV`, `BOOTSTRAP_ADMIN_EMAILS`를 설정 클래스에 만들지 마라. 이유: ADR-027과 ADR-024가 없앤 값이다.
- `FRONTEND_URL`의 검증을 느슨하게 하지 마라(끝의 `/`를 잘라 받아들이기, http를 경고만 하고 받아들이기 등). 이유: 운영 주소를 http로 잘못 적었을 때 서버가 떠서는 안 된다(ADR-027).
- `create_app()`이나 `import app.main`이 설정을 읽게 만들지 마라. 이유: 단위 테스트는 설정 없이 돈다(`tests/test_main.py`).
- compose.yaml에 `env_file:`을 쓰지 마라. 이유: 위 3번.
- `.env` 파일을 만들거나 커밋하지 마라. 이유: 비밀값이 들어가는 파일이다.
- 로그인 경로, 관문, 어댑터를 만들지 마라. 이유: 뒤의 step이 한다.
- 기존 테스트를 깨뜨리지 마라. 새 필수 값 때문에 고쳐야 하는 테스트는 위 2번대로 의도를 지키며 고친다.
- `MANUAL.md`의 항목을 체크하지 마라. 이유: 그 항목은 사람이 직접 본 것만 체크한다.
