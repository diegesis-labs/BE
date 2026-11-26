# Epic 1 코드 리뷰 — 1차

대상 `feat-1-login-allowlist` · `main...HEAD` (72파일, +12863/-73) · 커밋 `3daea97..1334f68`
리뷰 일시 2026-11-25 · 차원별 모델 correctness=opus, security=opus, architecture=opus, test-coverage=opus, behavioral=opus (diff가 로그인·허용 목록·SQL·`app/core/ports.py`·`app/main.py`·`pyproject.toml`을 건드리고 1,000줄을 넘어 security와 architecture도 opus로 올림)
근거 문서: `docs/backlog/epic-1/` · `docs/DEVELOPMENT.md` · `docs/ARCHITECTURE.md` · `docs/ADR.md` · `docs/API.md` 2~4.3절 · `docs/CONFIGURATION.md` · `phases/1-login-allowlist/step*.md` · `phases/1-login-allowlist/MANUAL.md`

## 종합 판정

| 차원 | critical | major | minor | 판정 |
|---|---|---|---|---|
| correctness | 0 | 1 | 0 | ⚠️ |
| security | 0 | 1 | 0 | ⚠️ |
| architecture | 0 | 0 | 4 | ✅ |
| test coverage | 0 | 1 | 3 | ⚠️ |
| behavioral | 0 | 0 | 4 | ✅ |
| **합계** | **0** | **3** | **11** | |

판정: critical 있으면 ❌ · major만 있으면 ⚠️ · minor 이하면 ✅ · 차원이 안 돌았으면 `미완`

**phase를 닫아도 되는가**: major 3건을 닫은 뒤 가능. 그와 별도로 E1의 끝나는 조건인 MANUAL 점검표(TC-1.7.3, TC-1.7.4)는 사람이 실제 Google 계정으로 확인하고 체크해야 한다.

## 실측

`scripts/check.sh --all`, Docker 켜짐(통합 테스트가 testcontainers의 PostgreSQL에서 실제로 돎), 전체 55초.

| 명령 | 결과 |
|---|---|
| `ruff check` | exit 0 — 위반 0 |
| `ruff format --check` | exit 0 — 91파일 서식 맞음 |
| `pyright` | exit 0 — 오류 0, 경고 0 |
| `pytest` | exit 0 — 879개 통과, 건너뜀 0, xfail 0, 경고 1(Starlette TestClient의 httpx 폐기 예고) (49.68s) |

orchestrator가 따로 재현한 것: `log_config("INFO")`로 띄운 uvicorn에 `GET /api/auth/google/callback?state=STATE_SECRET_VALUE&code=4/CODE_SECRET_VALUE`를 보내면, 서버 출력에 `INFO: 127.0.0.1:55986 - "GET /api/auth/google/callback?state=STATE_SECRET_VALUE&code=4/CODE_SECRET_VALUE&scope=openid HTTP/1.1" 302 Found`가 찍힌다(SEC-1).

## 결함

### correctness

| ID | 심각도 | 위치 | 위반 | 문제점 | 해결 제안 | 연관 |
|---|---|---|---|---|---|---|
| COR-1 | major | `app/auth/service.py:132`, `app/auth/service.py:153-159`, `app/auth/repository.py:86-96` | E1 S1.3 못 박을 것 | 같은 사람이 처음 로그인할 때 두 결과 처리가 겹치면, 쌍 확인과 INSERT 사이의 경합으로 하나가 고유 제약 위반 500으로 끝난다 | `create_user`를 `INSERT … ON CONFLICT DO NOTHING RETURNING`으로 바꾸고, 행이 없으면 다시 조회해 쌍을 확인하거나 `LOGIN_FAILED`로 돌려준다 | BEH-4 |

#### COR-1 상세

- **실측**: correctness 차원이 `/tmp/claude-review-1-login-allowlist/race_exp.py`로 재현했다. testcontainers DB를 썼고, 가짜 신원 제공자의 `exchange_code`에 `asyncio.Barrier(2)`를 걸었다. 같은 새 사용자의 결과 처리 두 개를 동시에 보내자 결과는 `(302, /)`와 `(500, INTERNAL_ERROR)`였고, 로그에 `uq_users_email` 위반이 남았다.
- **원인**: service는 `LoginFailedError`만 잡는다. 그래서 `IntegrityError`가 `get_db_session`에서 되돌려진 뒤 그대로 올라간다.
- **영향**: 데이터는 깨지지 않고, 다시 시도하면 성공한다.
- **major로 올린 이유**: 발동 조건은 동시 첫 로그인뿐이다. 하지만 이 phase가 방금 만든 경로에서 재현되는 경합이고, E1 S1.3이 "어떤 경우에도 500으로 끝나지 않는다", "`google_sub`의 고유 제약에 걸리는 경우도 미리 확인해서 `LOGIN_FAILED`"를 요구한다.
- **사람이 판단할 것**: "커밋이 실패하면 500"은 step8.md와 `app/auth/router.py:18-19`가 의도한 동작이라고 적었다. 그래서 E1 S1.3의 "어떤 경우에도"와 문서끼리 어긋난다. 커밋 실패를 예외로 둘지는 사람이 정해 Epic 문서에 적는다(BEH-4가 이 어긋남을 지적했다).

### security

| ID | 심각도 | 위치 | 위반 | 문제점 | 해결 제안 | 연관 |
|---|---|---|---|---|---|---|
| SEC-1 | major | `app/core/log_config.py:18-20`, `app/__main__.py:13-21`, `app/auth/router.py:123-130` | E1 못 박을 것(Epic 전역) · TC-1.3.13 | 결과 처리 요청마다 Google의 `code`와 `state`가 uvicorn 접근 로그(INFO, 기본값)에 평문으로 남는데, TC-1.3.13 테스트는 TestClient만 써서 초록이다 | `uvicorn.access`에 쿼리를 떼는 필터를 달고, 실제 `log_config`로 띄운 uvicorn의 출력에 두 값이 없는지 보는 서브프로세스 테스트를 더한다 | TST-1, BEH-1 |

#### SEC-1 상세

- **경로**: `log_config`는 uvicorn의 `LOGGING_CONFIG`를 복사해서 쓴다. 그래서 `uvicorn.access`가 INFO로 켜져 있고, 포맷 `"%(request_line)s"`가 쿼리까지 남긴다. 운영 이미지(`python -m app`)와 compose도 같은 설정이다.
- **이 phase의 결함인 이유**: 두 파일은 이번 diff에 없다. 하지만 쿼리로 `code`와 `state`를 받는 경로는 이 phase가 처음 만들었고, E1의 규칙은 Epic 전역이다. step8의 summary가 이 위반을 스스로 적어 놓고 "범위 밖"이라며 넘겼다.
- **가짜 초록(TST-1)**: TC-1.3.13은 "로그에 … `code` … `state` … 가 없습니다"를 요구한다. 그런데 테스트는 caplog와 TestClient로만 돌아서 uvicorn의 접근 로그가 처음부터 생기지 않는다.
- **critical이 아닌 이유**: `code`는 PKCE의 `code_verifier`(HttpOnly 쿠키)와 클라이언트 비밀값 없이는 교환할 수 없고, 한 번만 쓸 수 있다. 그래서 그릴 수 있는 공격 경로가 없다. 또 DEVELOPMENT.md 3절 규칙 7의 문구("쿠키 값과 토큰")를 정면으로 깨지는 않는다. 쿠키 값과 ID·액세스 토큰은 로그에 없다.

### architecture

| ID | 심각도 | 위치 | 위반 | 문제점 | 해결 제안 | 연관 |
|---|---|---|---|---|---|---|
| ARC-1 | minor | `app/auth/router.py:123-130`, `app/core/errors.py:116-119` | API §4.2 · 전례 Epic 0 ARC-2 | 쿼리가 모두 선택이라 일어날 수 없는 `400 VALIDATION_ERROR`가 `/api/openapi.json`의 결과 처리 경로에 실려 있다(실측: 응답 키 `302`, `400`) | 결과 처리 경로의 OpenAPI 응답을 302만 남기고, 그것을 단언하는 테스트를 더한다 | |
| ARC-3 | minor | `app/core/config.py:41-81`, `scripts/hooks/tdd-guard.sh:114` | DEVELOPMENT §4.2 | 선언 전용이라 TDD 가드에서 빠진 `config.py`에 약 30줄의 `FRONTEND_URL` 판정이 들어갔다. 다음에 이 판정을 고칠 때에는 테스트를 먼저 쓰라는 강제가 걸리지 않는다 | 판정을 테스트 대상 모듈로 옮기고 validator는 그 함수를 부르기만 하게 하거나, 이 예외를 DECISIONS.md에 기록한다 | |
| ARC-4 | minor | `app/core/gate.py:29`, `app/core/gate.py:68-79`, `app/auth/repository.py:180-182` | ARCHITECTURE §8 | 공통 층인 `core/gate.py`가 기능 폴더의 `AuthRepository`·`get_auth_repository`를 직접 import해서, 이후 모든 기능 폴더가 `require_user`를 쓰는 순간 auth의 repository에 묶인다 (추정) | 관문이 쓰는 조회를 `app/core/ports.py`의 Protocol로 두고 `create_app()`에서 주입하거나, 지금 구조를 ADR에 기록한다 | |
| ARC-5 | minor | `tests/test_routes.py:1`, `tests/auth/fakes.py:1`, `tests/core/gated_app.py:1` | DEVELOPMENT §4.2 | 대상 파일이 없는 `test_routes.py`가 있다. 여러 폴더의 테스트가 함께 쓰는 도우미 둘(`fakes.py`는 tests/auth의 4개 파일과 tests/core/test_gate.py가, `gated_app.py`는 테스트 2개가 쓴다)이 `tests/support/` 밖에 있고, 도우미 자체의 테스트도 없다 | `tests/test_main_routes.py`로 옮기고, 두 도우미는 `tests/support/`로 옮겨 가짜가 지키는 약속의 테스트를 둔다 | |

ARC-4는 "core는 기능 폴더를 import하지 않는다"는 명시 규칙이 문서에 없어 추정으로 둔다. ARCHITECTURE §8의 그림에서 repository는 포트 뒤의 "나가는 쪽"에 있고, Google 어댑터만 `app/main.py`에서 주입되어 주입 방식이 둘로 갈렸다는 것이 근거다.

### test coverage

| ID | 심각도 | 위치 | 위반 | 문제점 | 해결 제안 | 연관 |
|---|---|---|---|---|---|---|
| TST-2 | major | `scripts/login_check.py:1268-1290`, `scripts/login_check.py:1527-1555`, `tests/infra/test_login_check_precheck.py:109` | E1 T1.7.2 · S1.7 못 박을 것 · TC-1.7.2 · 전례 Epic 0 TST-1 | 두 가지를 함께 망가뜨려도 154개 테스트가 모두 초록이었다(실측). 하나는 `preflight`가 `precheck`를 부르지 않게 한 것이고, 다른 하나는 `main`이 문제가 있을 때 3으로 끝나지 않게 한 것이다 | `_http_get`, `precheck`, `port_in_use`, `run_checks`를 monkeypatch로 바꿔 `main()`을 부른다. 그리고 3(브라우저를 열지 않음)과 1과 0을 돌려주는 분기를 단언한다 | |
| TST-3 | minor | `tests/core/test_gate_integration.py:141-146`, `tests/core/test_gate_integration.py:222-240` | TC-1.4.9 · TC-1.4.2 | TC가 지정한 `GET /api/me` 대신 테스트 전용 경로와 SQL로 넣은 로그인 상태를 쓴다. 그래서 `/api/me`가 행을 고치게 바꿔도 초록이다(실측) | 실제 로그인 뒤 `/api/me`를 세 번 부르고 `login_sessions`의 전후를 비교하는 통합 테스트를 더하고, 만료 쿠키의 401도 `/api/me`로 본다 | |
| TST-4 | minor | `tests/adapters/test_google.py:176`, `tests/auth/test_router_integration.py:459-470` | step4.md 금지사항 · step8.md 반증 조건 · TC-1.3.13 | 로그에 비밀값이 없는지는 가짜 어댑터·가짜 저장소를 끼운 경로에서만 확인한다. 실제 어댑터나 repository에 `code`·비밀값·`token_hash`를 찍는 로그를 넣어도 초록이다(실측) | 어댑터 테스트와 실제 repository를 쓰는 통합 테스트 한 곳에서 caplog를 DEBUG로 모으고, 비밀값과 `token_hash`가 없다는 단언을 더한다 | |
| TST-5 | minor | `tests/core/test_security.py:24`, `tests/core/test_security.py:109-130` | TC-1.3.17 · step3.md 금지사항 | "임의의 값은 한 곳에서" 정적 검사가 `secrets`·`random`의 import 구문만 본다. 그래서 `os.urandom`, `uuid.uuid4()`, `__import__`/`importlib`로 만든 값은 통과한다(실측) | 검출 대상에 `os.urandom`·`uuid`·동적 import를 더하고, 검출기의 단위 테스트에도 그 형태를 넣는다 | |

#### TST-2 상세

- **요구**: T1.7.2는 "표와 다른 것이 있으면 0이 아닌 종료 코드로 끝납니다", S1.7은 "점검 전의 상태가 표와 다르면 브라우저를 열지 않고 … 끝냅니다"를 요구한다.
- **현재 테스트**: TC-1.7.2 테스트는 `precheck` 함수만 직접 부른다. 그 결과를 `preflight`가 문제 목록에 넣는지, `main`이 그것을 보고 3으로 끝나는지는 어떤 테스트도 지나가지 않는다.
- **major로 올린 이유**: 지금 코드는 요구를 지킨다. 하지만 TC의 반증 문장("점검 전 상태를 확인하지 않으면 실패해야")을 테스트가 보장하지 않는다. 판정 스크립트의 종료 코드를 돌려 보지 않은 Epic 0 TST-1의 전례와 같은 모양이다.

### behavioral

| ID | 심각도 | 위치 | 위반 | 문제점 | 해결 제안 | 연관 |
|---|---|---|---|---|---|---|
| BEH-2 | minor | `app/auth/router.py:175-184`, `docs/API.md:330` | API §4.2 | 로그아웃의 쿠키 삭제가 `diegesis_session=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0`이다. 문서 예시(`diegesis_session=; Max-Age=0; Path=/`)와 속성 구성·순서가 다르고, 같은 서버의 state 쿠키 삭제 표기와도 다르다 | API.md 예시를 구현에 맞출지, 코드를 예시 표기에 맞출지 사람이 정한다(step9가 발견하고 남겨 둔 것) | |
| BEH-3 | minor | `docs/CONFIGURATION.md:48`, `docs/CONFIGURATION.md:68-69`, `docs/CONFIGURATION.md:44`, `app/core/config.py:33-37` | CONFIGURATION §3·§3.3 | 3.3절은 `GOOGLE_CLIENT_ID`·`GOOGLE_CLIENT_SECRET`을 "필수(채우지 않으면 서버가 시작되지 않음)"로 적었다. 그런데 코드와 2절(44행)은 빈 값도 받아 서버가 뜬다고 하여 같은 문서 안에서 모순된다 | 3.3절의 두 행이나 3절의 "필수" 정의를 "변수는 있어야 하지만 빈 값은 받고, 빈 값이면 Google 로그인만 실패"로 고친다 | ARC-2 |
| BEH-5 | minor | `README.md:35` | API §2.4 | README는 `http://localhost:8080/api/docs`에서 "직접 요청을 보내 볼 수 있다"고 안내한다. 하지만 이 phase의 출처 확인 때문에 그 화면에서 보낸 로그아웃은 `403 ORIGIN_MISMATCH`다 | 상태를 바꾸는 요청은 프론트엔드 주소(5173)의 문서에서 보낸다고 덧붙이고 API.md 2.4절로 링크한다 | |
| BEH-6 | minor | `README.md:220` | D-42 | 폴더 구조의 `scripts/` 설명("검사 스크립트와 harness")에, 이 phase가 더한 로컬 로그인 점검 스크립트가 빠졌다(step12가 발견하고 남겨 둔 것) | `scripts/` 설명에 로컬 로그인 점검 스크립트를 더한다 | ARC-6 |

## 수정 우선순위

| # | 결함 | ID | 규모 |
|---|---|---|---|
| 1 | 접근 로그에 `code`·`state`가 남는다 | SEC-1 | `log_config`의 필터 10~20줄과 uvicorn 서브프로세스 테스트 1개 |
| 2 | 동시 첫 로그인에서 결과 처리가 500으로 끝난다 | COR-1 | repository 메서드 1개(ON CONFLICT), service 분기 몇 줄, 경합 통합 테스트 1개 |
| 3 | 점검 스크립트의 점검 전 확인과 종료 코드가 테스트되지 않는다 | TST-2 | monkeypatch로 `main()`을 부르는 unit 테스트 3~4개 |
| 4 | CONFIGURATION의 "필수"와 실제 동작이 모순된다 | BEH-3 | 문서 두세 줄 |
| 5 | OpenAPI에 일어나지 않는 400이 실려 있다 | ARC-1 | 경로의 `responses` 지정이나 치환 함수 조건, 테스트 1개 |
| 6 | 로그아웃 Set-Cookie가 API.md 예시와 다르다 | BEH-2 | 사람이 기준을 정한 뒤 한 줄 |
| 7 | 테스트의 빈틈(`/api/me` 행 불변, 실제 어댑터·repository 로그, 생성처 검출기) | TST-3, TST-4, TST-5 | 테스트 몇 개씩 |
| 8 | README 안내(5173 문서, 폴더 구조) | BEH-5, BEH-6 | 문서 한두 줄씩 |
| 9 | 구조(config의 판정 로직, core→auth 의존, 테스트 도우미의 위치) | ARC-3, ARC-4, ARC-5 | 결정이 먼저 필요하다. 옮기기는 각각 파일 이동 수준 |

## 이전 라운드 대조

1차 리뷰이므로 해당 없음.

## 잘 된 것 (재검증 불필요)

- **관문**(`app/core/gate.py`)
  - 순서가 API §2.2의 다이어그램과 거절 표와 같다: 쿠키 없음 401 → 로그인 상태 없음이나 만료 401 → 허용 목록 없음 403 → 허용 목록에 들어간 시각보다 먼저 만든 로그인 상태 401 → 관리자 경로의 역할 불일치 403.
  - 요청마다 질의 하나로 DB를 읽고, 행을 바꾸지 않으며, 역할을 메모리에 담지 않는다.
- **출처 확인**(`app/core/origin.py`)
  - 순수 ASGI 미들웨어로 앱 전체에 한 번 걸고, 예외로 두는 경로나 끄는 설정이 없다.
  - 메서드는 대소문자를 구분해 비교한다. 그래서 `post`·`PURGE` 같은 메서드도 확인을 받는다(실측 403).
  - `null` 거절, 정확 비교, Referer로 넘어가는 규칙이 API §2.4와 같다.
- **Google 어댑터**
  - 인가 주소의 매개변수 8개, S256, 토큰 엔드포인트 상수, `follow_redirects=False`를 지킨다.
  - 클레임 7개를 모두 확인한다: aud가 목록이면 원소가 하나여야 하고, exp는 bool·NaN·inf를 거부하며, 클라이언트 ID가 비면 어떤 aud도 통과하지 못한다.
  - 예외 체인에 비밀값이 남지 않는다.
- **로그인 service**
  - 분기 순서가 API §4.2의 동작 순서 다이어그램과 같다.
  - 실패하거나 허용 목록 밖이면 쓰기를 하나도 부르지 않는다.
  - 붙어 온 쿠키의 행 하나와 그 사용자의 만료된 행만 지운다.
  - state·nonce는 `hmac.compare_digest`로 비교하고, 빈 값은 실패다.
- **데이터 모델과 마이그레이션**: ARCHITECTURE §6과 컬럼·타입·CHECK·UK·FK CASCADE·`login_sessions(user_id)` 인덱스까지 같다. 모델과 리비전의 비교 테스트가 있고, 기존 리비전은 고치지 않았다.
- **설정**: 새 설정값 다섯 개가 설정 클래스·CONFIGURATION 3절·`.env.example` 세 곳에 모두 있다. `APP_ENV`와 `BOOTSTRAP_ADMIN_EMAILS`는 없다. `Secure`는 `FRONTEND_URL`의 스킴으로만 정한다.
- **공개 경로 전수 검사**(`tests/test_routes.py`): `app.routes`를 펼쳐서 메서드마다 경로를 뽑는다. 0개 수집을 막는 단언과 검출기 자체의 검증이 있고, Mount를 만나면 TypeError로 멈춘다.
- **TDD 순서**: step0~11의 RED 커밋이 모두 구현 커밋보다 앞서고, RED 커밋의 `app/`·`scripts/` 파일은 껍데기뿐이다. 기존 테스트에서 지워지거나 약해진 단언이 없다.
- **README 허용 목록 SQL 테스트(TC-1.6.1)**: SQL을 옮겨 적지 않고 README에서 읽어, BEGIN·COMMIT까지 적힌 그대로 실행한다.
- **점검 스크립트**
  - 대역 서버는 hop-by-hop 헤더를 빼고, Set-Cookie 여러 개를 합치지 않으며, `log_message`를 막는다.
  - 점검 전 확인은 `default_transaction_read_only=on`인 읽기 전용 트랜잭션으로 한다.
  - 쿠키 값은 읽는 자리에서 바로 SHA-256으로 바꾼다.
  - 자동화 탐지를 피하는 옵션이 없고, 점검마다 `new_context()`로 새 프로필을 쓴다.
- **SQL과 시크릿**: SQL은 모두 바인딩이다. 하드코딩된 비밀값이 없고, `google_client_secret`은 SecretStr이다.
- **ADR**: ADR-028을 ADR.md에만 기록했고, ARCHITECTURE §9의 기술스택도 최신 내용으로 고쳤다. 새 의존성은 httpx(운영)와 playwright(개발)뿐이다.

## 이 리뷰가 판정하지 않은 것

- `docs/backlog/epic-1/testcase.md` "이 Epic에서 판정하지 않는 것"에 해당하는 것: 프론트엔드 화면, 운영 주소의 Google 로그인과 `Secure` 쿠키(E2), 허용 목록 관리 API가 없는 것, 관리자 실제 경로(E3·E9), 점검 스크립트 출력의 형식, ID 토큰 서명 미확인·`__Host-` 접두사 없음·유휴 만료 없음(ADR-027이 받아들인 위험).
- `MANUAL.md`의 TC-1.7.3, TC-1.7.4: 실제 Google 계정으로 하는 점검이며, 이 리뷰는 실행하지 않았다. 두 항목에는 "테스트로 덮을 수 없는 이유"가 적혀 있고, 단언으로 옮길 수 있는 항목은 없었다.
- `/api/me`의 401·403과 로그아웃의 403이 OpenAPI에 실리지 않은 것: Epic 0부터 실패 응답은 OpenAPI에 싣지 않았고, 그것을 요구하는 문서가 없어 올리지 않았다(architecture 차원의 보류 판단).
- 이메일의 Python `lower()`와 PostgreSQL `lower()`가 비ASCII에서 다를 수 있다는 점: 실제 공격 경로를 그릴 수 없어 security 차원이 버렸다.
- 기각한 sub-agent 지적 5건 (근거 불일치 0 · 범위 밖 0 · 중복 5): TST-1과 BEH-1은 SEC-1로, BEH-4는 COR-1로, ARC-2는 BEH-3으로, ARC-6은 BEH-6으로 병합했다. 표에 빠진 ID 번호는 이 병합 때문이다.
- 심각도를 올린 것 2건: COR-1(minor→major, 이 phase가 만든 경로에서 재현되는 경합이 S1.3의 "어떤 경우에도 500이 아니다"를 깬다), TST-2(minor→major, TC-1.7.2와 T1.7.2가 요구한 것을 테스트가 보장하지 않는 가짜 초록).

<!-- verdict: critical=0 major=3 minor=11 -->
