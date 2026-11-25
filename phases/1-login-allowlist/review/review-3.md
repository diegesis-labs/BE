# Epic 1 코드 리뷰 — 3차

대상 `feat-1-login-allowlist` · `main...HEAD` (95파일, +17254/-112) · 커밋 `3daea97..8d6ec60` (2차 이후 `62563da..8d6ec60`, 35파일 +3034/-617: 2차 처분 9커밋과 ADR-031 4커밋)
리뷰 일시 2026-11-26 · 차원별 모델 correctness=opus, security=opus, architecture=opus, test-coverage=opus, behavioral=opus (diff가 1,000줄을 넘고 로그인·SQL·`app/core/ports.py`·`app/main.py`·`pyproject.toml`을 건드려 security와 architecture도 opus로 올림)
근거 문서: `docs/backlog/epic-1/` · `docs/DEVELOPMENT.md` · `docs/ARCHITECTURE.md` 1·8절 · `docs/ADR.md`(ADR-024~031) · `docs/API.md` 2~4.3절 · `docs/CONFIGURATION.md` · `docs/GLOSSARY.md` · `phases/1-login-allowlist/step*.md` · `phases/1-login-allowlist/MANUAL.md` · `phases/1-login-allowlist/review/review-2.md` · `fix-2.md`

## 종합 판정

| 차원 | critical | major | minor | 판정 |
|---|---|---|---|---|
| correctness | 0 | 0 | 5 | ✅ |
| security | 0 | 0 | 1 | ✅ |
| architecture | 0 | 0 | 3 | ✅ |
| test coverage | 0 | 1 | 4 | ⚠️ |
| behavioral | 0 | 0 | 2 | ✅ |
| **합계** | **0** | **1** | **15** | |

판정: critical 있으면 ❌ · major만 있으면 ⚠️ · minor 이하면 ✅ · 차원이 안 돌았으면 `미완`

**phase를 닫아도 되는가**: major 1건(TST-1)을 닫은 뒤 가능하다.

- 2차의 11건은 10건이 닫혔고, TST-1 하나는 ADR-031 재작성으로 다르게 터졌다.
- 새로 나온 것 가운데 major는 TST-1 하나다. 점검 스크립트의 진행 층이 ADR-031로 새로 얻은 배선(쿠키 대조 결과, 상태 코드, 시각)을 테스트가 반증하지 못한다.
- 다시 쓴 점검 스크립트 자체는 정상 흐름과 주요 고장에서 맞게 판정했다(correctness와 behavioral이 끝까지 돌려 봄).
- E1의 끝나는 조건인 MANUAL 점검표(TC-1.7.3, TC-1.7.4)는 아직 체크되지 않았다. ADR-031의 방식(게스트 창과 대역 서버의 화면)으로 사람이 실제 Google 계정으로 돌려야 한다.

## 실측

`scripts/check.sh --all`, Docker 켜짐(통합 테스트가 testcontainers의 PostgreSQL에서 실제로 돎), 전체 53초.

| 명령 | 결과 |
|---|---|
| `ruff check` | exit 0 — 위반 0 |
| `ruff format --check` | exit 0 — 102파일 서식 맞음 |
| `pyright` | exit 0 — 오류 0, 경고 0 |
| `pytest` | exit 0 — 1145개 통과, 건너뜀 0, xfail 0, 경고 1(Starlette TestClient의 httpx 폐기 예고, 1·2차와 같음) (47.61s) |

차원이 따로 실측한 것. 모두 레포 밖 복사본(`git archive HEAD`)이나 스크래치 컨테이너에서 했고, 끝난 뒤 지웠다. 레포의 작업 트리는 바뀌지 않았다.

- **점검 흐름을 끝까지 (correctness, behavioral)**: 실제 `create_app()`에 신원 제공자만 가짜로 끼우고, 실제 `FrontendStandIn`과 RFC 6265식 쿠키 저장소를 가진 흉내 브라우저로 `run_checks`(behavioral은 `main`)를 돌렸다.
  - 정상 흐름: 두 점검 여섯 시점 모두 어긋남 0, 종료 코드 0.
  - 브라우저가 세션 쿠키를 거부: 어긋남 5개, 종료 코드 1.
  - 이번 점검에서 심지 않은 쿠키를 붙임: 시점마다 보고되고 종료 코드 1.
  - [로그아웃]을 두 번 누름: 점검 2 "로그인 전"이 새 창이 생기기 전에 판정됨(COR-1).
  - 로그아웃 두 개를 동시에 보냄: 두 번 돌려 두 번 다 거짓 어긋남(COR-2).
  - 점검 중간에 시간 초과: 앞서 모은 어긋남이 버려짐(COR-3).
  - service가 `display_name`을 틀리게 저장: 종료 코드 0(BEH-2).
- **실제 진입점의 DB 오류 로그 (security)**: 마이그레이션하지 않은 스크래치 DB에 `python -m app`을 띄우고 500이 나는 요청 세 가지를 보냈다. 로그 1491줄에서 token_hash, 쿠키 값, 쿼리는 0건이었다. 두 곳(`처리되지 않은 예외`, uvicorn의 `Exception in ASGI application`)에 `[SQL parameters hidden due to hide_parameters=True]`만 남았다(2차 SEC-1).
- **대역 서버와 점검 스크립트의 보안 표면 (security)**:
  - 듣는 주소는 `127.0.0.1`이었다.
  - 화면의 주소는 이스케이프됐다(`<script>`, `"`, `'`).
  - 기록, repr, 출력에 쿠키 값과 token_hash 값이 없었다.
  - 읽기 전용 연결은 `CREATE TABLE`과 `SET … off`를 거부했다.
  - `_sql_email`에 적대적인 입력 여섯 가지를 넣었고, 모두 문자열 리터럴 안에 머물렀다.
- **돌연변이 (test-coverage)**: `tests/infra/test_login_check*.py` 248개로 약 100가지 변이를 넣었다.
  - TC-1.7.5의 굵은 글씨 세 조건은 모두 빨갰다. 이름만 보고 지움 1개, 반영한 뒤 대조 15개, 쿼리 기록 1개다.
  - 판정 변이는 24개 가운데 20개가, 관찰층 변이는 23개 가운데 20개가 빨갰다. 남은 것은 동치이거나 영향이 작다.
  - 진행 층 변이는 24개 가운데 11개가 초록이었다(TST-1).
  - 이 밖에 초록으로 남은 것: 대역 서버의 기록 순서 변이 2개(TST-2), 스레드 넘김 변이(TST-3), DB 읽기 변이 4개(TST-4), `log_message` 제거(TST-5).
  - 2차 처분 변이 셋(TST-2 분기, `hide_parameters=False`, `min_length` 제거)은 모두 빨갰다.
- **의존 방향 검사 (architecture)**:
  - 2차 ARC-1이 실측한 형태 넷은 모두 빨갰다. core 하위 패키지의 상대 import, `import_module`, service의 repository import, service의 Protocol 선언이다.
  - service에 `asyncpg`·`starlette`·`uvicorn`·`pydantic` import를 넣으면 네 번 모두 초록이었다(ARC-1).
- **기타 (behavioral)**:
  - DB를 내린 뒤 결과 처리를 부르면 `500 INTERNAL_ERROR`이고 `Set-Cookie`가 없었다.
  - 빈 `DATABASE_URL`로 `python -m app`을 띄우면 `ValidationError`로 시작하지 않았다.
  - API.md의 mermaid 다섯 개가 모두 렌더링됐다.

## 결함

### correctness

| ID | 심각도 | 위치 | 위반 | 문제점 | 해결 제안 | 연관 |
|---|---|---|---|---|---|---|
| COR-1 | minor | `scripts/login_check.py:1900`, `scripts/login_check.py:1862`, `scripts/login_check.py:1870` | E1 S1.7 T1.7.2 | 두 점검이 큐 하나를 비우지 않고 쓴다. 그래서 점검 1의 창이 남긴 `GET /api/me`(로그아웃을 두 번 누름 등)가 점검 2 "로그인 전"으로 잡히고, 새 게스트 창을 열기 전에 판정과 안내가 앞서 나간다 | `_check_denied`를 시작할 때 큐에 남은 것을 비우거나, 안내(`_ask`) 전에 기록된 Exchange는 그 단계의 대상으로 쓰지 않는다 | COR-2 |
| COR-2 | minor | `scripts/login_check.py:443`, `scripts/login_check.py:1228` | E1 S1.7 못 박을 것(기록 순서) | Exchange를 응답이 끝난 순서로 셈에 반영한다. 그래서 같은 쿠키로 동시에 보낸 `POST /api/auth/logout` 두 개 가운데 뒤의 것이 "이번 점검에서 심지 않은 쿠키"로 거짓 보고된다 | 요청을 받은 순간 순번을 매기고, 그 순번 전에 끝난 응답만 반영한 셈과 견준다 | COR-1 |
| COR-3 | minor | `scripts/login_check.py:1926`, `scripts/login_check.py:1957` | 없음 (모듈 독스트링 "다른 것을 끝에 모아 보여 준다") | 점검이 중간에 4로 끝나면, 그때까지 모은 어긋남이 예외와 함께 버려진다. 특히 스냅숏에 찍히지 않는 쿠키 대조 결과가 그렇다 | 시점마다 어긋남을 바로 출력하거나, `CheckAbortedError`에 실어 `main`이 보여 준 뒤 4로 끝낸다 | |
| COR-4 | minor | `scripts/login_check.py:1905`, `scripts/login_check.py:1228` | E1 S1.7 못 박을 것(심지 않은 쿠키) · ADR-031 | 대역 서버를 지난 모든 요청을 출처를 가리지 않고 지금 점검의 셈에 넣는다. 그래서 평소 창에 남은 탭(끈 Vite의 재연결 요청 등)이 거짓 어긋남과 엉뚱한 안내를 낼 수 있다 (추정) | 쿠키 대조를 대역 화면의 이동과 `/api` 요청으로 좁히거나, 화면이 보내는 요청에 점검마다 다른 표식을 붙인다 | |
| COR-5 | minor | `scripts/login_check.py:621-624` | E1 S1.7 T1.7.3 | `.env`가 `FRONTEND_URL="http://localhost:5174" # dev`처럼 따옴표 값 뒤에 주석을 달면 따옴표를 벗기지 않는다. compose는 뜨는데 스크립트는 3으로 끝난다(값은 보여 줌) | 값이 따옴표로 시작하면 닫는 따옴표까지를 값으로 잡고, 그 뒤의 ` #…`는 버린다 | |

COR-1·COR-2는 사람이 버튼을 겹쳐 누를 때 생긴다. 둘 다 조용히 통과하지는 않는다. 어긋남이나 앞서 나간 안내로 드러나고, 사람이 다시 돌리면 된다. 그래서 minor로 둔다.

### security

| ID | 심각도 | 위치 | 위반 | 문제점 | 해결 제안 | 연관 |
|---|---|---|---|---|---|---|
| SEC-1 | minor | `scripts/login_check.py:364`, `scripts/login_check.py:282`, `scripts/login_check.py:291`, `scripts/login_check.py:1261` | E1 S1.7 T1.7.1 | 백엔드로 넘기는 조건(`startswith("/api")`)과 기록·출력에서 쿼리를 빼는 조건(`"/api/"`)이 다르다. 그래서 `/api?…`와 `/apix…`는 넘어가면서 쿼리가 기록된다. 다만 실제 `code`·`state`가 이 틈으로 오는 경로는 없다 | 넘기는 판정과 쿼리를 빼는 판정을 한 술어로 합친다 | |

SEC-1에서 실제 `code`·`state`가 오지 않는 이유: Google은 등록된 `redirect_uri`로만 돌려보낸다. 그리고 점검 전 확인(`login_redirect_problems`)이 그 값이 정확히 `{FRONTEND_URL}/api/auth/google/callback`인지 본다.

### architecture

| ID | 심각도 | 위치 | 위반 | 문제점 | 해결 제안 | 연관 |
|---|---|---|---|---|---|---|
| ARC-1 | minor | `tests/auth/test_service.py:607`, `tests/auth/test_service.py:691-695`, `tests/auth/test_service.py:771-776` | ARCHITECTURE §8 · DEVELOPMENT 반드시 지킬 규칙 | service의 기술 무지 검사가 금지 목록(`fastapi`·`sqlalchemy`·`httpx`·`app.adapters`)이다. 그래서 `asyncpg`·`starlette`·`uvicorn`·`pydantic` import가 초록이다 | 표준 라이브러리와 `app.core.ports`·`app.core.security`만 허용하는 목록으로 바꾸고, 검출기 테스트에 asyncpg·starlette 사례를 더한다 | |
| ARC-3 | minor | `app/auth/router.py:34`, `app/auth/router.py:73`, `app/auth/router.py:82`, `app/core/ports.py:51` | ARCHITECTURE §8 · ADR-029 | 포트 표에 오른 `AuthStore`의 구현체를 `create_app()`이 아니라 router가 고른다(구체 클래스 `AuthRepository`를 import함). "어댑터는 서버가 시작될 때 주입", "조립을 아는 곳이 `app/main.py` 하나"와 어긋난다 (추정) | `create_app()`이 `AuthStore`를 만드는 함수를 넣게 하거나, 기능 폴더의 저장소 포트는 그 라우터의 의존성이 넣는다고 ARCHITECTURE 8절과 ADR-029에 적는다 | |
| ARC-4 | minor | `README.md:191`, `docs/backlog/epic-1/testcase.md:128`, `docs/backlog/epic-1/E1-login-allowlist.md:207` | D-20 | 브라우저의 상태를 대역 서버의 기록과 `Set-Cookie`의 셈으로 보고, 붙은 `Cookie`가 다르면 어긋남으로 본다는 규칙이 ADR-031 말고도 세 문서에 따로 적혀 있다 (추정) | README는 testcase.md의 그 줄을 가리키고, 사람이 할 일(심지 않은 쿠키가 보이면 새 게스트 창을 확인)만 남긴다 | |

- **ARC-1**: 2차 ARC-1의 처분은 동적 import와 하위 패키지까지 넓혔다. 하지만 `app.` 밖의 import를 거르는 금지 목록은 그대로 네 이름뿐이다.
- **ARC-3을 추정으로 두는 이유**: 이 구조는 step8부터 있었다. 2차 ARC-4의 처분으로 `AuthStore`가 정식 포트가 되면서 문서와 어긋난 것이 드러났다. ADR-029의 "조립은 `app/main.py` 하나"는 `LoginLookup`을 넣는 방식의 근거로 쓴 문장이다. 기능 폴더가 쓰는 저장소 포트를 어디서 넣는지는 문서가 정하지 않았다. 그래서 사람이 정할 일이다.
- **ARC-4를 추정으로 두는 이유**: E1의 Task와 testcase의 합격 기준이 겹치는 것은 문서 구조상 어느 정도 피할 수 없다. 가장 분명한 중복은 README다.
- **ARC-2**: behavioral의 BEH-1과 같은 결함이라 BEH-1에 합쳤다.

### test coverage

| ID | 심각도 | 위치 | 위반 | 문제점 | 해결 제안 | 연관 |
|---|---|---|---|---|---|---|
| TST-1 | major | `scripts/login_check.py:1819`, `scripts/login_check.py:1834`, `scripts/login_check.py:1845`, `scripts/login_check.py:1851`, `scripts/login_check.py:1874`, `scripts/login_check.py:1892`, `tests/infra/test_login_check_run.py:131-159` | E1 S1.7 못 박을 것("쿠키를 따라가는 방식, 안내하는 순서는 테스트로 확인") · TC-1.7.3 · TC-1.7.4 · ADR-031 | ADR-031이 더한 진행 층의 배선을 테스트가 반증하지 못한다. 쿠키 대조 결과를 4자리에서 빼거나, me·로그아웃 상태 코드를 상수로 넘기거나, `login_at`을 로그인 전 시각으로 넘겨도 248개가 초록이다 | FakeWorld에 고장 다섯 가지를 더한다. Exchange마다 `at`을 다르게 주고, 가짜 사람이 다음 `_wait_for`가 시작된 뒤에 요청을 보내게 한다(아래 상세) | TST-3 |
| TST-2 | minor | `scripts/login_check.py:443`, `scripts/login_check.py:467`, `scripts/login_check.py:471`, `tests/infra/test_login_check.py:349-378` | E1 S1.7 못 박을 것("응답을 브라우저에 보내기 전에 기록") · TC-1.7.5 | 이 순서를 보는 테스트는 요청 하나의 응답을 받은 뒤에 다음 요청을 보낸다. 그래서 `_record`를 응답 뒤로 옮겨도 초록이다(18회) | `observe` 안에서 Event로 기록을 멈춰 두고, 그동안 클라이언트가 응답을 받지 못했음을 `_forward`·`_page`·`_plain`마다 단언한다 | |
| TST-3 | minor | `scripts/login_check.py:1905`, `tests/infra/test_login_check_run.py:195-199`, `tests/infra/test_login_check_run.py:425-432` | E1 S1.7 못 박을 것 · E1 T1.7.2 | 가짜 대역 서버가 `observe`를 이벤트 루프 스레드에서 부른다. 그래서 대역 서버 스레드에서 `run_checks`로 넘기는 경로(`call_soon_threadsafe`)를 지나는 테스트가 없다. 바로 `put_nowait`하는 변이가 초록인데, 진짜 대역 서버로는 점검이 4로 끝난다 | 진짜 `FrontendStandIn`과 가짜 백엔드를 띄우고, 별도 스레드의 HTTP 클라이언트로 `run_checks`를 끝까지 돌리는 테스트를 더한다. 아래의 테스트는 루프가 닫힌 뒤에 부르게 고친다 | TST-1 |
| TST-4 | minor | `scripts/login_check.py:940-946`, `scripts/login_check.py:955-959`, `tests/infra/test_login_check_precheck.py:104-127` | TC-1.7.3 · TC-1.7.4 | `read_db_state`가 읽는 `login_sessions` 행과 전체 행 수를 실제 DB의 결과로 단언하는 테스트가 없다. `session_total=0` 고정, 전체 대신 두 계정의 수, sessions 비움이 모두 초록이다 | 실제 DB에 A와 다른 사람의 users·login_sessions를 넣고, `read_state`의 `sessions_for(A)`(token_hash·expires_at·created_at)와 `session_total`을 단언하는 integration 테스트를 더한다 | |
| TST-5 | minor | `scripts/login_check.py:371-373`, `scripts/login_check.py:470-472` | E1 못 박을 것(Epic 전역: 로그에 `code`·`state`를 남기지 않음) | 대역 서버가 요청 줄을 찍지 않는다는 약속을 보는 테스트가 없다. `log_message` 재정의를 지워도 초록이고, 그때 502 응답에서 결과 처리의 `code`·`state`가 stderr에 찍힌다 | capfd로 대역 서버의 stderr를 잡아, 502·411·400과 화면 경로에서 쿼리가 든 요청 줄이 나오지 않음을 단언한다 | |

TST-3에서 고칠 "아래의 테스트"는 `test_exchange_that_arrives_after_the_checks_is_ignored`다. 이 테스트는 루프가 열린 채로 `observe`를 부르므로, 의도한 경로(루프가 닫힌 뒤의 RuntimeError)를 지나지 않는다.

#### TST-1 상세

**초록으로 남은 진행 층 변이(실측, 248개 모두 통과)**

- `take_problems()`를 6자리 가운데 4자리에서 뺐다. 로그인 후, 로그아웃 전, 로그아웃 후, 점검 2 로그인 시도 후다.
- `logout_status`를 204로 고정했다.
- 세 자리의 me 상태 코드를 401로 고정했다.
- `login_at=me.at`로 로그인 전 GET /api/me의 시각을 넘겼다. FakeWorld가 모든 Exchange에 같은 `at`을 주기 때문이다.
- 로그아웃 후의 기준을 `after_login`으로 바꿨다.
- 점검 2에서 결과 처리와 화면을 기다리지 않게 했다.
- 기한을 단계마다 새로 잡게 했다.

**FakeWorld에 더할 고장 다섯 가지**

- 로그아웃 뒤 지운 쿠키를 다시 붙인다.
- 점검 2의 새 창에 쿠키가 남아 있다.
- 로그인 전 me가 200을 돌려준다.
- 로그아웃이 403을 돌려준다.
- 점검 2의 결과 처리 중에 쿠키가 어긋난다.

**major로 두는 이유**

- **AC가 테스트를 요구한다.** E1 S1.7 "못 박을 것"은 요청과 응답을 기록하고 쿠키를 따라가는 방식, 그리고 안내하는 순서를 `scripts/check.sh`의 테스트로 확인하라고 정했다.
- **ADR-031의 판정 근거가 빠져도 초록이다.** ADR-031은 브라우저의 쿠키 저장소를 읽지 못하는 대신, 요청에 붙은 `Cookie`의 대조로 쿠키를 받아들이지 않은 브라우저를 잡는다고 했다. 그 결과를 최종 판정에 모으는 자리 6곳 가운데 4곳이 빠져도 초록이다.
  - 복사본의 probe로 확인했다. 로그아웃 후의 `take_problems()`를 빼면, 지우는 `Set-Cookie`를 무시한 브라우저가 어긋남 0, 종료 코드 0으로 끝났다.
- **사람이 출력을 읽어도 잡지 못한다.** 상태 코드를 상수로 바꾸는 변이는 스냅숏 출력에도 같은 상수를 찍는다. 2차는 같은 자리를 minor로 두면서 "사람이 출력을 직접 대조하니 드러난다"를 근거로 들었는데, 이 변이들에는 그 근거가 서지 않는다.
- **2차가 닫은 자리가 다시 열렸다.** 2차 TST-1의 처분이 덮은 이음새를 ADR-031 재작성이 새 배선으로 다시 열었다.

**잘 덮인 쪽**

- 판정 함수와 셈 자체는 잘 덮여 있다. 빈 곳은 그것들을 잇는 진행 층이다.
- 고장을 표현할 수 없어서 생긴 빈틈도 아니다. probe로 고장 세 가지를 FakeWorld에 넣자 원본은 정확히 보고했고, 해당 변이가 각각 빨개졌다.

#### TST-4 상세

DB 읽기가 틀렸을 때 MANUAL에서 드러나는지는 칸마다 다르다.

- **점검 1의 A 행 칸**: 바로 드러난다. 예를 들어 sessions를 비우면 "로그인 후 A의 행이 하나 생깁니다"가 어긋난다.
- **점검 2의 전체 행 수**: 양쪽이 함께 틀리면 같다고 나온다.

그래도 minor로 둔다. B에게 로그인 상태가 생기는 결함은 브라우저 칸(쿠키, `GET /api/me`)이 따로 잡기 때문이다.

### behavioral

| ID | 심각도 | 위치 | 위반 | 문제점 | 해결 제안 | 연관 |
|---|---|---|---|---|---|---|
| BEH-1 | minor | `scripts/login_check.py:687`, `scripts/login_check.py:700`, `README.md:189` | ADR-031 · E1 S1.7 못 박을 것(브라우저를 열거나 조작하지 않음) | `--help`의 설명과 종료 코드 4가 Playwright 시절 그대로다("화면이 보이는 브라우저를 연다", "브라우저가 닫혔다"). 그런데 README는 종료 코드의 뜻을 이 `--help`에서 보라고 안내한다 | `_parser()`의 description과 epilog를 ADR-031과 모듈 독스트링(35-43행)에 맞추고, ADR-031도 가리키게 한다 | |
| BEH-2 | minor | `scripts/login_check.py:1385`, `scripts/login_check.py:1479`, `scripts/login_check.py:1613`, `README.md:189`, `phases/1-login-allowlist/MANUAL.md:65` | TC-1.7.3 · E1 S1.7 T1.7.2 | 점검 1 표의 "`display_name`은 A의 Google 이름" 두 칸은 스크립트가 판정하지 못한다. 비어 있지 않은지와 `/api/me`가 `users`와 같은지만 본다. 그런데 결과는 "모든 시점의 상태가 표와 같다"고 말한다. 이름을 틀리게 저장해도 0으로 끝났다 | A의 Google 이름을 인자로 받아 판정하거나, 결과 출력·MANUAL·README에 이 칸은 사람이 대조한다고 적는다 | |

- **BEH-1의 범위 판단**: testcase.md가 판정하지 않기로 한 "출력의 형식과 문구"는 시점별 출력의 모양에 관한 것이다. 이 항목은 다르다. 스크립트가 하는 일과 종료 코드의 뜻에 대한 진술이 ADR-031과 반대다. architecture(ARC-2)와 correctness(참고)도 같은 자리를 짚었고, 여기 하나로 합쳤다.

## 수정 우선순위

| # | 결함 | ID | 규모 |
|---|---|---|---|
| 1 | 진행 층의 쿠키 대조·상태 코드·시각 배선을 반증하는 테스트가 없다 | TST-1 | FakeWorld 고장 다섯 가지와 시각·대기 흉내, 테스트 몇 개 |
| 2 | 진짜 대역 서버를 지나는 테스트, 기록 순서와 요청 줄의 테스트가 없다 | TST-3, TST-2, TST-5 | 끝까지 도는 테스트 1개, 순서 테스트 3개, stderr 테스트 1개 |
| 3 | DB 읽기의 sessions·전체 행 수를 실제 DB로 보지 않는다 | TST-4 | integration 테스트 1개 |
| 4 | 버튼을 겹쳐 누르면 단계가 앞서 나가거나 거짓 어긋남이 나온다 | COR-1, COR-2 | 큐 비우기와 요청 순번, 몇 줄 |
| 5 | `--help`가 대체된 설계를 안내하고, `display_name` 칸을 판정한 것처럼 말한다 | BEH-1, BEH-2 | 문자열과 문서 몇 줄 (BEH-2를 인자로 풀면 판정 몇 줄) |
| 6 | 중단 시 어긋남 버림, 다른 탭의 요청, `.env` 따옴표, `/api` 판정 둘 | COR-3, COR-4, COR-5, SEC-1 | 각 몇 줄 |
| 7 | service 검출기가 금지 목록이다 | ARC-1 | 검출기 몇 줄과 사례 둘 |
| 8 | `AuthStore`를 넣는 자리, 규칙의 문서 중복 | ARC-3, ARC-4 | ARC-3은 결정이 먼저 필요하다. ARC-4는 문서 몇 줄 |

## 이전 라운드 대조

2차 처분 기록(`fix-2.md`)은 11건을 모두 "고쳤다"로 적었다. 각 항목을 코드와 실측으로 다시 확인했다.

| 2차 ID | 심각도 | 판정 | 확인한 것 |
|---|---|---|---|
| COR-1 | minor | 닫힘 | ADR-031 재작성 뒤에도 `DATABASE_ERRORS`(OSError, PostgresError, InterfaceError, InternalClientError)를 `preflight`(`scripts/login_check.py:1668`, 3)와 `run_checks`(`:1926`, 4)가 잡는다. `asyncpg.connect`의 `TimeoutError`는 OSError의 하위 클래스다. `tests/infra/test_login_check_main.py`와 `test_login_check_run.py`가 두 경로를 지난다 |
| SEC-1 | minor | 닫힘 | `app/core/database.py`가 `hide_parameters=True`로 엔진을 만든다. fix-2.md가 하지 않은 실제 진입점(`python -m app`)의 uvicorn 출력까지 확인했다(위 실측). `hide_parameters=False` 변이는 2개가 빨갰다 |
| ARC-1 | minor | 닫힘 | `rglob`, 상대 import 풀이, 문자열 인자 세기, 비상수 인자는 닫힌 채 실패한다. 실측한 네 형태가 모두 빨갰다. 금지 목록의 빈틈은 이와 별개라 3차 ARC-1로 올렸다 |
| ARC-2 | minor | 닫힘 | `tests/core/test___init__.py`가 `app/core/__init__.py`에 대응한다. 옛 경로를 가리키는 곳은 0건이다 |
| ARC-3 | minor | 닫힘 | `tests/support/frontend_urls.py`와 그 테스트가 같은 폴더에 있다. tests 아래에서 테스트 모듈끼리 import하는 곳은 0건이다 |
| ARC-4 | minor | 닫힘 | `AuthStore`는 `app/core/ports.py:48`에 있다. `tests/core/test_ports.py`가 `service.py`의 Protocol을 잡는다(변이 빨강). 정식 포트가 되면서 드러난 주입 위치의 어긋남은 3차 ARC-3으로 올렸다 |
| ARC-5 | minor | 닫힘 | "전용 세션 저장소"·"세션 저장소"는 리뷰 기록을 빼면 0건이다 |
| TST-1 | minor | 다르게 터짐 | 재작성 뒤에도 `test_login_check_run.py`가 진짜 `run_checks`·`_check_allowed`·`_check_denied`를 부른다. 2차가 실측한 변이(`before_logout=after_logout`)는 3개가 빨갰다. 다른 기준 스냅숏, 점검 2 결과를 버림, `login_at`을 지금으로, 대역 서버 닫기, DB 오류를 4로 바꾸기도 빨갰다. 하지만 ADR-031이 더한 배선은 반증하지 못한다(3차 TST-1·TST-3) |
| TST-2 | minor | 닫힘 | `test_first_login_whose_raced_row_is_gone_is_login_failed`가 있다. 분기의 `_LOGIN_FAILED`를 `_NOT_ALLOWED`로 바꾸자 1개가 빨갰다 |
| BEH-1 | minor | 닫힘 | API.md 4.2절의 동작 순서에 재확인 `opt` 분기, 302 노트, 500 노트가 있다. DB를 내리면 `500`이고 `Set-Cookie`가 없어 문서와 같다(실측) |
| BEH-2 | minor | 닫힘 | `app/core/config.py:28`이 `Field(min_length=1)`다. CONFIGURATION 3.2절에 적혀 있다. 빈 값으로 `python -m app`을 띄우면 `ValidationError`가 난다(실측). `min_length` 제거 변이는 1개가 빨갰다 |

처분 커밋과 재작성 커밋의 TDD 순서도 확인했다.

- RED가 수정보다 앞선다.
  - `23be896`(6 failed) → `231ca08`
  - `9b19f03`(1 failed, ImportError) → `27a849f`
  - `325f971`(수집 오류 3) → `8fff82e`
- 재작성 커밋에서 지워진 단언은 두 종류뿐이다. 대상이 없어진 Playwright 전용(`frontend_cookies`, `returned_to_frontend`, `fetch_result`, `headless`·`new_context` 문자열)이거나 문구 변경이다.
- `8fff82e`가 고친 테스트는 선택자 문자열 2줄이고, 강도가 같다.

## 잘 된 것 (재검증 불필요)

- **다시 쓴 점검 스크립트의 정상 흐름과 주요 고장**
  - 두 차원이 따로, 실제 앱과 실제 대역 서버로 끝까지 돌렸다. 정상 흐름은 어긋남 0, 종료 코드 0이었다.
  - 세션 쿠키를 거부하는 브라우저와 심지 않은 쿠키는 1로 끝났다.
  - 순서를 어긴 경우와 Google의 오류·취소는 어긋남으로 보고됐다.
  - Google에서 돌아오지 않으면 300초 뒤 4로 끝난다.
- **셈의 규칙**
  - `CookieJar`는 쿠키를 (이름, 경로)로 구별하고, Max-Age를 Expires보다 앞세우고, default-path와 path-match를 RFC 6265대로 따른다. 만료 경계도 `<=`와 `<`로 서로 맞는다.
  - 대조를 먼저 하고 반영을 나중에 한다. 기록은 응답을 보내기 전에 한다.
  - TC-1.7.5의 굵은 글씨 세 조건을 어기는 변이는 모두 빨갰다.
- **표의 칸 대조**: BEH-2의 `display_name` 칸 말고는 testcase.md 두 표의 칸을 모두 `judge_*`가 판정한다. 시점마다 바로 앞 스냅숏을 기준으로 받는다.
- **스레드와 큐**: 셈과 큐는 이벤트 루프 스레드에서만 만진다. `_wait_for`가 시간 초과로 취소돼도 항목을 잃지 않는다.
- **보안 표면**
  - 대역 서버는 `127.0.0.1`에서만 듣고, 화면의 주소를 이스케이프한다.
  - 기록, repr, 출력에 쿠키 값, token_hash 값, 결과 처리의 쿼리가 없다.
  - DB 연결은 읽기 전용이다.
  - `.env`에서는 세 값만 읽고, Google의 비밀값은 읽지 않는다.
- **ADR-031의 문서 규칙**
  - DECISIONS.md는 바뀌지 않았다.
  - ADR-026은 본문 그대로 두고 상태만 "일부 대체"로 바꿨다(ADR-008과 같은 방식).
  - E1, testcase, README, GLOSSARY, INFRA에 경위가 남지 않았다.
  - MANUAL의 두 표는 testcase.md와 글자 그대로 같다.
  - 안내 순서는 MANUAL, README, 스크립트의 `_ask` 일곱 단계가 같다.
- **의존성**
  - playwright와 pyee가 `pyproject.toml`과 `uv.lock`에서 빠졌다. 새 의존성은 없다(표준 라이브러리와 asyncpg).
  - `tests/infra/test_dependencies.py`가 모든 의존성에서 브라우저 자동화 도구를 막는다.
- **검사 후퇴 없음**
  - 2차 뒤로 새 `# type: ignore`·`# noqa`·`skip`·`xfail`은 없다.
  - 새 `cast`는 `tests/core/test_ports.py` 하나이고, pyright에 구조 일치를 확인시키는 용도다.
- **2차 처분의 품질**: 11건 모두 RED가 먼저 있거나 테스트만 더했다. 처분 기록이 주장한 테스트 함수와 커밋은 실제로 있다.

## 이 리뷰가 판정하지 않은 것

- `docs/backlog/epic-1/testcase.md` "이 Epic에서 판정하지 않는 것"
  - 프론트엔드 화면
  - 운영 주소의 Google 로그인과 `Secure` 쿠키, 운영 호스팅의 `Origin` 전달(E2)
  - 허용 목록 관리 API가 없는 것, 관리자의 실제 경로(E3·E9)
  - 점검 스크립트가 시점마다 내는 출력의 형식과 문구
  - ID 토큰 서명 미확인, `__Host-` 접두사 없음, 유휴 만료 없음(ADR-027)
- `MANUAL.md`의 TC-1.7.3, TC-1.7.4: 실제 Google 계정으로 하는 점검이며, 이 리뷰는 실행하지 않았다. 단언으로 옮길 수 있는 부분은 TST-1·TST-3·TST-4로 올렸다.
- DB 장애·커밋 실패 때 결과 처리가 `500`으로 끝나는 것 자체(ADR-030).
- `phases/1-login-allowlist/step10.md`·`step11.md`와 `index.json`의 summary가 ADR-031 이전의 Playwright 설계를 적고 있는 것: harness의 실행 기록이다.
- 1·2차가 보류한 것(새 근거 없음)
  - `/api/me`의 401·403과 로그아웃의 403이 OpenAPI에 없는 것
  - 이메일의 Python `lower()`와 PostgreSQL `lower()`가 비ASCII에서 다를 수 있는 것
  - REPEATABLE READ에서는 경합이 500이 되는 것
  - 난수원 검출기와 의존 방향 검출기의 정적 한계
  - core와 service의 검출기가 두 벌인 것
- test-coverage가 동치이거나 영향이 작다고 보고 버린 변이
  - created_at이 미래인 쪽만 허용하는 판정
  - 세션 쿠키 둘(부분 동치)
  - SameSite 대소문자 무시, A의 allowed 행이 둘
  - Expires를 Max-Age보다 앞세움: 백엔드가 Max-Age만 보낸다(`app/auth/router.py`)
  - 같은 이름·다른 경로의 unexpected: 백엔드가 만들지 않는다
  - Cookie 헤더의 첫 하나만 읽음
  - DB에서 거르지 않음: Python에서 거른다
  - 기준 요청을 callback으로: 판정은 같다
- security가 확인한 것 가운데 결함이 아닌 것: `hide_parameters`가 가리지 못하는 두 채널이 있다. asyncpg `DataError`의 값 repr과 고유 제약 위반의 `DETAIL`이다. 앱에서는 닿지 않는다.
  - `create_user`는 `ON CONFLICT DO NOTHING`이다.
  - 쿠키 값은 해시한 뒤에만 바인딩한다.
  - 허용 목록을 통과한 이메일로는 소문자 검사 제약을 어길 수 없다.
- architecture가 남긴 메모: 점검 스크립트가 쿠키 이름(`diegesis_session`)과 TTL(336시간)을 상수로 둔다. compose가 서버에 `LOGIN_COOKIE_NAME`·`LOGIN_SESSION_TTL_HOURS`를 넘기지 않으므로(`compose.yaml:48-62`) 서버도 늘 기본값을 쓴다. 그래서 결함이 아니다. compose가 그 값을 넘기게 되면 다시 본다.
- 기각한 sub-agent 지적 1건 (근거 불일치 0 · 범위 밖 0 · 중복 1): ARC-2를 BEH-1에 합쳤다. 표에 ARC-2가 없는 것은 이 병합 때문이다. correctness가 참고로 남긴 같은 지적도 BEH-1에 들어 있다.
- 심각도를 바꾼 것 0건. 올라온 16건을 모두 다시 판정했다.
  - TST-1(major)은 낮추지 않았다(위 상세).
  - TST-4, BEH-2, COR-1, COR-2는 올릴지 검토했다. 조용히 틀린 판정을 내는 경로가 없거나, 다른 칸이 같은 결함을 잡아서 minor로 두었다.

<!-- verdict: critical=0 major=1 minor=15 -->
