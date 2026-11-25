# Epic 1 코드 리뷰 — 2차

대상 `feat-1-login-allowlist` · `main...HEAD` (86파일, +14812/-87) · 커밋 `3daea97..62563da` (1차 이후 처분 커밋 `29c6f9c..62563da`, 39파일 +2169/-234)
리뷰 일시 2026-11-25 · 차원별 모델 correctness=opus, security=opus, architecture=opus, test-coverage=opus, behavioral=opus (diff가 로그인·허용 목록·SQL·`app/core/ports.py`·`app/main.py`·`pyproject.toml`을 건드리고 1,000줄을 넘어 security와 architecture도 opus로 올림)
근거 문서: `docs/backlog/epic-1/` · `docs/DEVELOPMENT.md` · `docs/ARCHITECTURE.md` · `docs/ADR.md`(ADR-024~030) · `docs/API.md` 2~4.3절 · `docs/CONFIGURATION.md` · `docs/GLOSSARY.md` · `phases/1-login-allowlist/step*.md` · `phases/1-login-allowlist/MANUAL.md` · `phases/1-login-allowlist/review/review-1.md` · `fix-1.md`

## 종합 판정

| 차원 | critical | major | minor | 판정 |
|---|---|---|---|---|
| correctness | 0 | 0 | 1 | ✅ |
| security | 0 | 0 | 1 | ✅ |
| architecture | 0 | 0 | 5 | ✅ |
| test coverage | 0 | 0 | 2 | ✅ |
| behavioral | 0 | 0 | 2 | ✅ |
| **합계** | **0** | **0** | **11** | |

판정: critical 있으면 ❌ · major만 있으면 ⚠️ · minor 이하면 ✅ · 차원이 안 돌았으면 `미완`

**phase를 닫아도 되는가**: 가능. 1차의 14건은 모두 닫혔고, 새로 나온 것은 minor뿐이다. 다만 E1의 끝나는 조건인 MANUAL 점검표(TC-1.7.3, TC-1.7.4)는 아직 사람이 실제 Google 계정으로 확인하고 체크해야 한다.

## 실측

`scripts/check.sh --all`, Docker 켜짐(통합 테스트가 testcontainers의 PostgreSQL에서 실제로 돎), 전체 49.6초.

| 명령 | 결과 |
|---|---|
| `ruff check` | exit 0 — 위반 0 |
| `ruff format --check` | exit 0 |
| `pyright` | exit 0 — 오류 0 |
| `pytest` | exit 0 — 1021개 통과, 건너뜀 0, xfail 0, 경고 1(Starlette TestClient의 httpx 폐기 예고, 1차와 같음) (45.01s) |

차원이 따로 실측한 것(모두 레포 밖의 별도 worktree나 스크래치 컨테이너에서 했고, 끝난 뒤 지웠다):

- **실제 진입점의 접근 로그**: security가 `python -m app`으로 서버를 띄우고, 쿼리에 code·state를 실은 요청을 9가지 모양으로 보냈다. 접근 로그에 쿼리는 하나도 남지 않았다(1차 SEC-1).
- **동시 첫 로그인**: correctness가 testcontainers DB에서 첫 쌍 확인 뒤에 Barrier를 걸었다.
  - 같은 사람 요청 2개·3개는 모두 302 성공이었다.
  - 이메일만 같은 경우와 sub만 같은 경우는 한쪽이 성공, 다른 쪽이 302 LOGIN_FAILED였다.
  - 먼저 넣은 쪽이 롤백하면 기다리던 쪽이 그대로 성공했다.
  - 어느 경우에도 500은 없었다(1차 COR-1).
- **돌연변이**:
  - test-coverage가 1차 처분 테스트에 가짜 구현 20여 가지를 넣었고, 모두 빨갰다.
  - 빨개지지 않은 것은 TST-1과 TST-2의 두 자리, 그리고 동치인 변이 둘(Origin을 대소문자 없이 비교, 메서드에 `.upper()`)이다.
  - architecture는 의존 방향 검사에 변이 두 가지를 넣었다. 둘 다 초록이었다(ARC-1).
- **API 형식**: behavioral이 네 경로, 관문, 출처 확인을 실제로 요청해 API.md 2.2·2.3·2.4·3·4.2·4.3절과 필드 하나씩 대조했다. 아래 BEH-1 말고는 차이가 없었다.

## 결함

### correctness

| ID | 심각도 | 위치 | 위반 | 문제점 | 해결 제안 | 연관 |
|---|---|---|---|---|---|---|
| COR-1 | minor | `scripts/login_check.py:1288`, `scripts/login_check.py:1519` | step11.md(종료 코드 규칙) | `preflight`·`run_checks`가 `(OSError, asyncpg.PostgresError)`만 잡아, asyncpg의 `InterfaceError`·`InternalClientError`는 미처리 예외가 되고 종료 코드 1이 `EXIT_MISMATCH`와 구별되지 않는다 | 두 except에 `asyncpg.InterfaceError`와 `asyncpg.exceptions.InternalClientError`를 더해 각각 3(점검 전 확인)과 4(점검 중단)로 끝나게 한다 | |

#### COR-1 상세

- **실측**: correctness가 DB_PORT에 가짜 서버를 띄웠다. 이 서버는 SSL을 거절한 뒤 인증 방식 99를 요구한다. 그 상태에서 `main()`을 부르자 `InterfaceError: unsupported authentication method requested by the server: 99` 트레이스백이 나오고 종료 코드는 1이었다. GSS·SSPI를 요구하는 경우와 길이 프레임이 깨진 경우도 넣어 봤는데, 그때 나는 `InternalClientError`도 잡히지 않았다.
- **발동 조건**: 좁다. behavioral이 HTTP 응답이나 쓰레기 바이트를 내는 서버로 재현해 보니, 그때는 `ConnectionError`(OSError)가 나서 3으로 끝났다. DB_PORT에 asyncpg가 지원하지 않는 인증이나 프로토콜을 쓰는 서버가 떠 있을 때만 발동한다.
- **S1.7은 깨지 않는다**: 브라우저를 열기 전이고 종료 코드도 0이 아니다. 그래서 "브라우저를 열지 않는다"는 요구는 지켜진다.
- **처분 기록과의 관계**: 1차 처분 기록 `fix-1.md`가 "새로 발견한 것"에 (추정)으로 적어 둔 항목이다. 이번에 사실로 확인했다.

### security

| ID | 심각도 | 위치 | 위반 | 문제점 | 해결 제안 | 연관 |
|---|---|---|---|---|---|---|
| SEC-1 | minor | `app/core/database.py:33`, `app/core/errors.py:232` | 없음 (개인정보) | 엔진을 `hide_parameters` 없이 만들어, 문장 실행 중 DB 오류(ADR-030이 받아들인 500)가 나면 예외 로그에 바인딩 값(이메일, google_sub, display_name, token_hash)이 실린다 | `create_async_engine(..., hide_parameters=True)`로 만들고, DB 오류 500의 로그에 이메일과 token_hash가 없음을 보는 테스트를 더한다 | |

#### SEC-1 상세

- **실측**: security가 마이그레이션하지 않은 스크래치 DB에 서버를 띄웠다. 로그 설정은 진입점과 같은 `log_config("INFO")`이고, 가짜 신원 제공자를 끼웠다.
  - 결과 처리를 부르자 두 곳에 `[parameters: ('victim.pii@example.com',)]`가 찍혔다. `app.core.errors`의 `처리되지 않은 예외`와 uvicorn의 `Exception in ASGI application`이다.
  - `python -m app`에 쿠키를 붙여 `/api/me`를 부르자 같은 두 곳에 token_hash가 찍혔다.
  - 쿠키 값은 한 번도 찍히지 않았다.
- **허용 목록 밖의 이메일도 남는다**: 결과 처리의 첫 질의가 `get_allowed_email`이기 때문이다. service가 이메일을 로그에 넣지 않으려고 user_id만 남기는 의도(`app/auth/service.py`)와 어긋난다.
- **critical이나 major가 아닌 이유**: E1의 금지 목록(쿠키 값, code, 토큰, 비밀값, state, nonce, code_verifier)을 깨지 않는다. token_hash로는 쿠키를 되살릴 수 없다. 그래서 그릴 수 있는 공격 경로가 없다.

### architecture

| ID | 심각도 | 위치 | 위반 | 문제점 | 해결 제안 | 연관 |
|---|---|---|---|---|---|---|
| ARC-1 | minor | `tests/core/test_dependency_direction.py:20-36`, `tests/core/test_dependency_direction.py:71`, `tests/auth/test_service.py:578-594` | ARCHITECTURE §8 · ADR-029 · DEVELOPMENT §4.2 | 의존 방향 검사가 import 구문의 AST만 보고 `glob("*.py")`로 하위 폴더를 보지 않는다. 그래서 `importlib.import_module("app.auth…")`나 `app/core/<하위 패키지>/`의 import가 초록이다(실측) | `rglob("*.py")`로 바꾸고, `importlib.import_module`·`__import__`의 문자열 인자도 세며, 검출기 단위 테스트에 두 형태를 더한다 | |
| ARC-2 | minor | `tests/core/test_dependency_direction.py:1` | DEVELOPMENT §4.2 · 1차 ARC-5 전례 | 대상 파일(`app/core/dependency_direction.py`)이 없는 테스트 파일이 ARC-4 처분(`58ed9c5`)에서 새로 생겼다 | 대상이 있는 이름으로 옮기거나, 패키지 단위 구조 테스트의 자리를 DEVELOPMENT 4.2에 정한다(ADR-029가 가리키는 경로도 함께 맞춘다) | |
| ARC-3 | minor | `tests/core/test_config.py:15`, `tests/core/test_frontend_url.py:12`, `tests/core/test_frontend_url.py:23` | DEVELOPMENT §4.2 · 1차 ARC-5 전례 | ARC-3 처분(`29c6f9c`) 뒤로 `test_config.py`가 다른 테스트 모듈 `tests.core.test_frontend_url`에서 TC-1.2.9의 값 목록을 import한다. 여러 테스트가 함께 쓰는 값이 `tests/support/` 밖에 있다 | 두 목록을 `tests/support/`의 모듈로 옮기고, 두 테스트가 거기서 가져다 쓴다 | TST-3 |
| ARC-4 | minor | `app/auth/service.py:36-62`, `docs/ARCHITECTURE.md:411-417` | ARCHITECTURE §8 · DEVELOPMENT §4.2 | 같은 `AuthRepository`를 가리키는 저장소 Protocol이 둘이다. `LoginLookup`은 `app/core/ports.py`에 있고 포트 표에 실렸지만, `AuthStore`는 `service.py`에 선언되어 있고 포트 표에 없다 (추정) | `AuthStore`를 `app/core/ports.py`로 옮겨 포트 표에 더하거나, "service만 쓰는 저장소 Protocol은 그 service.py에 둔다"를 ARCHITECTURE 8절에 적고 근거를 ADR에 남긴다 | |
| ARC-5 | minor | `docs/ARCHITECTURE.md:417`, `docs/ADR.md:1233` | D-17 · GLOSSARY("세션"을 단독으로 쓰지 않음) | ARC-4 처분 문서(`12e4ef1`)가 포트 표와 ADR-029의 재검토 조건에 "전용 세션 저장소"라고 적었다. 같은 ADR의 "데이터베이스 세션"과 섞여 읽힌다 | ARCHITECTURE 8절의 표는 "로그인 상태 전용 저장소"로 고친다. ADR-029의 문구는 ADR.md 머리말의 규칙에 맞는 방법으로 고친다 | BEH-3 |

ARC-4는 기능 폴더 안에서만 쓰는 저장소 Protocol을 "포트"로 볼지 문서가 정하지 않았으므로 추정으로 둔다. `AuthStore`는 step5부터 있었고, ADR-029는 레코드만 `ports.py`로 옮기기로 했다.

### test coverage

| ID | 심각도 | 위치 | 위반 | 문제점 | 해결 제안 | 연관 |
|---|---|---|---|---|---|---|
| TST-1 | minor | `scripts/login_check.py:1399-1480`, `tests/infra/test_login_check_main.py:154`, `phases/1-login-allowlist/MANUAL.md:56` | TC-1.7.3 · TC-1.7.4 · harness.md D-4 | 판정 함수를 부르는 이음새(`run_checks`·`_check_allowed`·`_check_denied`)를 지나가는 테스트가 없다. `judge_allowed_after_logout`에 `before_logout=after_logout`을 넘기게 바꿔도 933개가 모두 초록이었다(실측) | `read_state`·`_log_in`을 monkeypatch로 바꾸고 가짜 Browser·Context·Page를 끼워 `run_checks`를 부르는 unit 테스트를 더한다. 단언할 것은 표와 다른 칸이 보고되는지, 실패가 4로 끝나는지다 | |
| TST-2 | minor | `app/auth/service.py:153-155`, `tests/auth/test_service.py:310-352` | E1 S1.3 못 박을 것 | COR-1 처분이 만든 분기 "등록하지 못했고 다시 조회해도 쌍이 맞는 사용자가 없음"을 지나가는 테스트가 없다. 이 분기의 `_LOGIN_FAILED`를 `_NOT_ALLOWED`로 바꿔도 499개가 초록이었다(실측) | `create_user`가 None을 돌려주고 재조회도 비는 FakeAuthStore 변형으로 이 분기를 부른다. 결과가 `LOGIN_FAILED`인지, 쓰기가 `create_user`뿐인지, 옛 쿠키의 행을 지우지 않는지를 단언한다 | |

#### TST-1 상세

- **설계상 위치**: step11.md는 브라우저를 모는 부분을 "얇은 층"으로 두고 순수 함수만 테스트하라고 했다. 그래서 이 층을 테스트하지 않은 것이 설계를 어긴 것은 아니다.
- **그래도 올리는 이유**: 이 층은 약 120줄의 조립 로직이다. 어느 스냅숏을 어느 판정의 기준으로 넘기는지, 어긋난 것을 쌓는지, 실패를 4로 바꾸는지를 정하며, 모두 가짜 브라우저로 단언할 수 있다.
- **minor로 둔 이유**: 지금 코드가 틀렸다는 증거는 없다. 그리고 MANUAL 점검에서 사람이 실제 스냅숏 출력을 표와 직접 대조하므로, 이음새가 틀리면 그 자리에서 드러난다.

### behavioral

| ID | 심각도 | 위치 | 위반 | 문제점 | 해결 제안 | 연관 |
|---|---|---|---|---|---|---|
| BEH-1 | minor | `docs/API.md:304-315`, `app/auth/service.py:143-155` | API §4.2(동작 순서) · D-56 | COR-1 처분과 ADR-030이 만든 두 동작이 API.md 4.2절의 동작 순서에 없다. 하나는 겹친 첫 로그인의 재확인 분기(한쪽만 같으면 LOGIN_FAILED)이고, 다른 하나는 DB 장애·커밋 실패의 500이다. 500일 때 state 쿠키를 지우지 않으므로 "모든 응답에서 diegesis_oauth_state 쿠키를 지웁니다"(315행)와도 어긋난다(실측) | 다이어그램의 등록 단계에 재확인 분기를 더하고, 315행의 노트를 302 응답으로 좁히거나 ADR-030의 500 예외를 적는다. API.md를 고치므로 프론트엔드의 리뷰를 받는다(DEVELOPMENT 6.4절) | |
| BEH-2 | minor | `docs/CONFIGURATION.md:48`, `docs/CONFIGURATION.md:62`, `app/core/config.py:26` | CONFIGURATION §3·§3.2 | 1차 BEH-3 처분이 3절에 "빈 값을 받는지는 값마다 적습니다"를 더했다. 그런데 3.2절의 `DATABASE_URL` 행에는 그것이 없고, 실제로는 빈 값을 받아 서버가 뜬다(실측) | `DATABASE_URL` 행에 빈 값의 동작을 적는다. 빈 값을 거부하게 바꿀지는 사람이 정한다 | |

BEH-1에서 프론트엔드가 받는 결과(`/`나 `/login?error=LOGIN_FAILED`, 500)는 4.2절의 표와 ADR-030의 범위 안이다. 그래서 계약이 깨진 것은 아니고, 동작 순서를 그린 유일한 문서(D-56)가 코드를 따라오지 못한 것이다.

## 수정 우선순위

| # | 결함 | ID | 규모 |
|---|---|---|---|
| 1 | DB 오류 로그에 이메일과 token_hash가 실린다 | SEC-1 | 엔진 인자 하나와 로그 테스트 1개 |
| 2 | API.md 4.2절 동작 순서에 재확인 분기와 500 예외가 없다 | BEH-1 | 다이어그램 몇 줄. 프론트엔드의 리뷰가 필요하다 |
| 3 | 의존 방향 검사가 동적 import와 하위 패키지를 놓친다 | ARC-1 | 검출기 몇 줄과 단위 테스트 두 줄 |
| 4 | 새 분기와 점검 스크립트 이음새의 테스트 빈틈 | TST-2, TST-1 | service 테스트 1개, `run_checks` unit 테스트 몇 개 |
| 5 | 점검 스크립트가 asyncpg의 일부 예외를 못 잡는다 | COR-1 | except 두 곳에 클래스 둘 |
| 6 | 문서의 용어와 설정 설명 | ARC-5, BEH-2 | 문서 한두 줄씩 |
| 7 | 테스트 파일의 위치와 공용 값 목록 | ARC-2, ARC-3 | 파일 이동이나 DEVELOPMENT 4.2에 한 줄 |
| 8 | `AuthStore`의 자리 | ARC-4 | 결정이 먼저 필요하다. 옮기기는 파일 이동 수준 |

## 이전 라운드 대조

1차 처분 기록(`fix-1.md`)은 14건을 모두 "고쳤다"로 적었다. 각 항목을 코드와 실측으로 다시 확인했다.

| 1차 ID | 심각도 | 판정 | 확인한 것 |
|---|---|---|---|
| SEC-1 | major | 닫힘 | `app/core/log_config.py`의 `AccessLogQueryFilter`가 `uvicorn.access` 로거에 걸려, 경로의 `?` 뒤를 뗀다. 실제 진입점에서 9가지 요청 모양(중복 키, websocket·h2c Upgrade, 절대형 대상, 잘못된 요청줄, 경로 안의 `%3F` 등)으로 확인했다. 필터를 무력화하는 가짜 다섯 가지는 서브프로세스 테스트가 모두 잡았다 |
| COR-1 | major | 닫힘 | `on_conflict_do_nothing()`이 이메일·google_sub 두 고유 제약 모두에 걸린다. 재조회는 READ COMMITTED에서 커밋된 상대 행을 본다. 실제 DB 경합 실측에서 500이 없었다. 남은 분기 하나의 테스트 빈틈은 TST-2로 새로 올렸다 |
| TST-2 | major | 닫힘 | `tests/infra/test_login_check_main.py`가 종료 코드 3·1·0·4와 브라우저를 열지 않음을 본다. 돌연변이 넷이 모두 빨갰다. `run_checks` 안쪽은 TST-1로 새로 올렸다 |
| ARC-1 | minor | 닫힘 | `/api/openapi.json`의 결과 처리 응답이 `302` 하나뿐이고, 매개변수는 선택인 `code`·`state`·`error`다. `HTTPValidationError`는 없다 |
| ARC-3 | minor | 닫힘 | 판정이 `app/core/frontend_url.py`로 옮겨졌고, 1차 시점의 validator와 글자 그대로 같다. 이 파일은 TDD 가드의 대상이다. 값 목록을 함께 쓰는 방식이 ARC-3(2차)을 새로 만들었다 |
| ARC-4 | minor | 닫힘 | `app/core/`에 core 밖의 import가 없다(지연 import, TYPE_CHECKING, importlib 포함). `service.py`는 repository·sqlalchemy를 import하지 않는다. 조립은 `app/main.py:48` 한 곳이다. 검사 테스트의 빈틈은 ARC-1(2차)로, 남은 Protocol의 자리는 ARC-4(2차)로 올렸다 |
| ARC-5 | minor | 닫힘 | 도우미가 `tests/support/`로 옮겨졌고 그 테스트가 있으며, `tests/test_main_routes.py`도 생겼다. 다만 같은 모양이 ARC-2·ARC-3(2차)으로 다시 생겼다 |
| TST-3 | minor | 닫힘 | 실제로 로그인한 뒤 `/api/me`를 세 번 부르고 전후로 세 테이블을 비교한다. 만료된 로그인 상태의 401도 `/api/me`로 본다 |
| TST-4 | minor | 닫힘 | 실제 어댑터와 실제 repository 경로에서 DEBUG까지 모으며, 캡처가 DEBUG를 받는지 먼저 canary로 확인한다 |
| TST-5 | minor | 닫힘 | 검출기가 `os.urandom`·`uuid`·`__import__`·`importlib`·별칭 import까지 잡는다 |
| BEH-2 | minor | 닫힘 | 실측한 로그아웃 Set-Cookie가 API.md 4.2절 예시와 같다(https이면 `Secure`가 붙는 것까지). ADR-030에 기록됐다 |
| BEH-3 | minor | 닫힘 | Google 두 값의 "필수"와 실제 동작이 맞는다. 다만 새로 적은 3절의 규칙이 `DATABASE_URL` 행에는 적용되지 않았다(BEH-2(2차)) |
| BEH-5 | minor | 닫힘 | README 35행이 403 `ORIGIN_MISMATCH`와 5173 화면을 적고 API.md 2.4절로 링크한다 |
| BEH-6 | minor | 닫힘 | README 220행에 로컬 로그인 점검 스크립트가 들어갔다 |

처분 커밋의 TDD 순서도 확인했다.

- RED가 수정 커밋보다 앞선다: `29c6f9c` → `8198a43`, `58ed9c5` → `bab4487`.
- RED 커밋의 `app/` 파일은 껍데기뿐이다.
- `8198a43`이 고친 테스트는 가짜 저장소를 새 약속(None)에 맞춘 것과 단언을 더한 것뿐이다. 약해진 단언은 없다.

## 잘 된 것 (재검증 불필요)

- **1차 처분의 품질**
  - 14건 모두 RED가 먼저 있거나 테스트만 더했다.
  - 처분 기록이 주장한 테스트 함수와 커밋이 모두 실제로 있다.
  - 1차 이후 바뀐 테스트에서 지워지거나 약해진 단언이 없다. `test_config.py`의 -56줄은 값 목록을 옮긴 것이다.
- **경합의 닫힘**: correctness가 실제 DB에서 같은 사람 2~3개, 쌍이 어긋난 두 방향, 먼저 넣은 쪽의 롤백, 같은 옛 쿠키의 재로그인 2개를 겹쳐 돌렸다. 500도 데드락도 없었다.
- **접근 로그 필터**
  - uvicorn의 서식과 인자 모양일 때만 경로를 고치고, 그 밖의 기록은 그대로 둔다. 기록을 버리거나 예외를 내는 경로가 없다.
  - Dockerfile의 CMD가 `python -m app`이므로 운영에도 걸린다.
- **관문과 포트 전환(ADR-029)**: security가 실제 진입점에서 SQL로 상태를 바꿔 가며 판정이 그대로인지 확인했다.
  - 쿠키 없음 401, 모르는 쿠키 401, 허용 목록에서 뺌 403, 다시 넣음 401, 만료 401, 역할 변경은 다음 요청에 반영.
  - 행을 바꾸지 않는다. 팩토리가 없으면 닫힌 채 실패한다.
- **API 형식**
  - 네 경로의 상태 코드, `Location`, `Set-Cookie`(속성과 순서), 에러 `code`, `/api/me`의 네 필드가 API.md 4.2·4.3절의 예시와 같다(실측).
  - OpenAPI의 paths는 다섯 개이고, 문서에 없는 경로는 없다.
- **문서 규칙**
  - ADR-029·030은 ADR.md에만 경위를 남겼다.
  - ARCHITECTURE 8절, API.md 4.2절, CONFIGURATION, E1 S1.3에는 최신 상태만 있고 이유는 ADR 번호로 링크한다.
- **보안 표면 전반**
  - 열린 리디렉션이 없다. CORS 미들웨어도 없다.
  - 출처 확인은 정확 비교이며, `null`과 userinfo 우회를 거절한다.
  - SQL은 모두 바인딩이다. 비밀값의 하드코딩이 없다.
  - 점검 스크립트는 쿠키 값을 출력하지 않고 읽기 전용 트랜잭션으로 읽는다.
- **검사 후퇴 없음**: 새 `# type: ignore`·`# noqa`·`skip`·`xfail`이 없다. ruff는 S311을 더해 더 엄격해졌다.

## 이 리뷰가 판정하지 않은 것

- `docs/backlog/epic-1/testcase.md` "이 Epic에서 판정하지 않는 것"에 해당하는 것.
  - 프론트엔드 화면.
  - 운영 주소의 Google 로그인과 `Secure` 쿠키, 운영 호스팅의 `Origin` 전달(E2).
  - 허용 목록 관리 API가 없는 것, 관리자 실제 경로(E3·E9).
  - 점검 스크립트 출력의 형식과 문구.
  - ID 토큰 서명 미확인, `__Host-` 접두사 없음, 유휴 만료 없음(ADR-027이 받아들인 위험).
- DB 장애·커밋 실패 때 결과 처리가 `500`으로 끝나는 것 자체: ADR-030이 정한 예외다. SEC-1은 그 500의 로그 내용을, BEH-1은 그 동작이 API.md 동작 순서에 빠진 것을 다룬다.
- `MANUAL.md`의 TC-1.7.3, TC-1.7.4: 실제 Google 계정으로 하는 점검이며, 이 리뷰는 실행하지 않았다. 단언으로 옮길 수 있는 부분(스크립트의 이음새)은 TST-1로 올렸다.
- 1차 처분 기록의 "새로 발견한 것" 가운데, 마이그레이션하지 않은 DB에서 점검 전 확인이 내놓는 안내가 원인과 맞지 않는 것: `UndefinedTableError`는 잡혀 3으로 끝나고 브라우저를 열지 않는다. 남는 것은 안내 문구뿐이며, testcase.md가 판정하지 않기로 한 "출력의 문구"에 해당한다.
- correctness가 참고로 남긴 것: COR-1 처분은 PostgreSQL 기본 격리 수준(READ COMMITTED)에 기댄다. 엔진을 REPEATABLE READ로 바꾸면 겹친 첫 로그인의 한쪽이 `SerializationError`로 500이었다(실측). 지금 엔진은 격리 수준을 바꾸지 않으므로 결함으로 올리지 않았다. 격리 수준을 바꾸는 Epic이 다시 볼 것이다.
- test-coverage가 버린 것.
  - 난수원 검출기가 `ssl.RAND_bytes`·`getattr(os, "urandom")`을 못 잡는 것: 정적 검사의 한계다.
  - 동치 돌연변이 둘: Origin을 대소문자 없이 비교하는 것과 메서드에 `.upper()`를 거는 것. 실제 상태 변경이나 공격 경로가 생기지 않는다.
- 1차가 보류한 것(새 근거 없음): `/api/me`의 401·403과 로그아웃의 403이 OpenAPI에 없는 것, 이메일의 Python `lower()`와 PostgreSQL `lower()`가 비ASCII에서 다를 수 있다는 점.
- 기각한 sub-agent 지적 2건 (근거 불일치 0 · 범위 밖 0 · 중복 2): TST-3을 ARC-3으로, BEH-3을 ARC-5로 병합했다. 표에 빠진 ID 번호는 이 병합 때문이다.
- 심각도를 바꾼 것 0건: 올라온 11건을 모두 다시 판정했다.
  - 요구가 깨진 자리가 아니라 테스트나 문서가 코드를 따라오지 못한 자리다.
  - 실제로 깨진 경로(COR-1, SEC-1)도 발동 조건이 이 phase의 핵심 경로가 아니고, 사람이 겪는 결과가 작다.

<!-- verdict: critical=0 major=0 minor=11 -->
