# 1-login-allowlist 리뷰 처분 — 1차

> `review-1.md`의 결함 14건(critical 0 · major 3 · minor 11)에 대한 처분. 2026-11-25.
> 고친 것 14건, 기각 0건, 사람 판단 필요 0건.
> 처음 처분에서는 12건을 고치고 ARC-4·BEH-2를 사람 판단으로 넘겼다. 사람이 정한 뒤(2026-11-25) 두 건을 고쳐 "고쳤다"로 옮겼다.

## 고쳤다

| ID | 심각도 | 처분 | 커밋 |
|---|---|---|---|
| SEC-1 | major | `log_config`가 `uvicorn.access`에 `AccessLogQueryFilter`를 걸어 접근 로그의 경로에서 `?` 뒤를 뗀다. 실제 진입점으로 uvicorn을 띄워 결과 처리를 부르는 테스트 `tests/test___main__.py::test_access_log_does_not_keep_login_callback_query`, 필터 단위 테스트 `tests/core/test_log_config.py` | `29c6f9c` `8198a43` |
| COR-1 | major | `create_user`를 `INSERT … ON CONFLICT DO NOTHING RETURNING`으로 바꾸고, service는 None이면 쌍을 다시 확인한다(같은 사람이면 로그인, 한쪽만 같으면 `LOGIN_FAILED`). 실제 DB 경합 `tests/auth/test_router_integration.py::test_concurrent_first_logins_of_same_person_both_succeed`, 저장소·service 재현 테스트 | `29c6f9c` `8198a43` |
| TST-2 | major | 네트워크·DB·브라우저를 가짜로 바꾸고 `main()`을 불러 종료 코드 3·1·0·4와 브라우저를 열지 않음을 단언하는 `tests/infra/test_login_check_main.py`(15개) | `f9782bc` |
| ARC-1 | minor | 결과 처리 경로가 쿼리를 `request.query_params`에서 읽고 `openapi_extra`로 선택인 매개변수 셋을 적는다. 문서의 응답은 302뿐. `tests/auth/test_router.py::test_openapi_documents_callback_as_redirect_only` | `29c6f9c` `8198a43` |
| ARC-3 | minor | FRONTEND_URL의 판정과 https 여부를 `app/core/frontend_url.py`로 옮기고 설정 클래스는 부르기만 한다. `tests/core/test_frontend_url.py`(받아들일 값·거부할 값 목록을 이리로 옮김) | `29c6f9c` `8198a43` |
| ARC-5 | minor | `tests/test_routes.py`→`tests/test_main_routes.py`, `tests/auth/fakes.py`→`tests/support/auth_fakes.py`, `tests/core/gated_app.py`→`tests/support/gated_app.py`. 도우미의 약속 테스트 `tests/support/test_auth_fakes.py`·`test_gated_app.py` | `f30f218` |
| TST-3 | minor | 실제로 로그인한 뒤 `GET /api/me` 세 번 전후의 세 테이블 비교(TC-1.4.9)와 만료된 로그인 상태의 `/api/me` 401(TC-1.4.2)을 `tests/auth/test_router_integration.py`에 더했다 | `f9782bc` |
| TST-4 | minor | 실제 어댑터(`tests/adapters/test_google.py`)와 실제 repository 경로(`tests/auth/test_router_integration.py`)에서 `app` 로거를 DEBUG로 모아 비밀값·토큰·`token_hash`가 없음을 본다. 캡처가 DEBUG를 받는지 먼저 확인한다 | `f9782bc` |
| TST-5 | minor | `tests/core/test_security.py`의 검출기가 `os.urandom`·`getrandom`, `uuid1`·`uuid4` 등, `__import__`·`importlib.import_module`, 다른 이름으로 가져온 것까지 센다. 검출기 단위 테스트에 그 형태를 더했다 | `f9782bc` |
| BEH-3 | minor | CONFIGURATION 3절의 "필수"를 "변수가 아예 없으면 시작되지 않음"으로, 3.3절의 Google 두 값에 "빈 값도 받으며 Google 로그인만 되지 않음(2절)"을 적었다 | `3351020` |
| BEH-5 | minor | README의 8080 API 문서 화면에서 보낸 상태 변경 요청은 `403 ORIGIN_MISMATCH`이고 5173을 거친 화면에서 보낸다고 적고 API.md 2.4절로 링크했다 | `3351020` |
| BEH-6 | minor | README 폴더 구조의 `scripts/`에 로컬 로그인 점검 스크립트를 더했다 | `3351020` |
| ARC-4 | minor | 사람이 A안(포트)을 골랐다. `AllowedEmail`·`UserRecord`·`ActiveLogin`과 `LoginLookup` 포트를 `app/core/ports.py`로 옮기고, 관문은 `get_login_lookup`(앱의 factory와 요청의 세션)으로 찾는 곳을 받으며 `create_app()`이 `set_login_lookup_factory(app, AuthRepository)`로 잇는다. service도 레코드를 포트에서 가져온다. `tests/core/test_dependency_direction.py`(core가 core 밖의 app 모듈을 import하지 않음), `tests/auth/test_service.py`의 허용 규칙 강화, `tests/test_main.py::test_gate_of_created_app_finds_logins_with_auth_repository`, `tests/core/test_gate.py::test_login_lookup_without_factory_fails_loudly`. ADR-029, ARCHITECTURE 8절 | `58ed9c5` `bab4487` `12e4ef1` |
| BEH-2 | minor | 사람이 A안(문서를 구현에 맞춤)을 골랐다. API.md 4.2절의 로그아웃 예시를 `diegesis_session=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0`(https면 `Secure`)으로 고쳤다. 코드는 바꾸지 않았다. API.md를 고쳤으므로 PR에 프론트엔드의 리뷰가 필요하다(DEVELOPMENT 6.4절). ADR-030 | `12e4ef1` |

### COR-1 상세

- **리포트와 다른 점**: 해결 제안의 두 갈래("다시 조회해 쌍을 확인" / "`LOGIN_FAILED`") 가운데 다시 조회하는 쪽을 골랐다. 그래서 같은 사람의 첫 로그인 두 개가 겹치면 둘 다 성공하고 로그인 상태가 하나씩 생긴다. 겹친 요청이 만든 행이 이메일만 같거나 `google_sub`만 같으면 `LOGIN_FAILED`이며, 이때 `users`와 `login_sessions`를 바꾸지 않는다. 다만 `create_user`는 불린다(아무것도 쓰지 않음). 그래서 service의 머리말에서 "쓰기 메서드를 하나도 부르지 않는다"를 이 경우만 예외로 고쳐 적었다.
- **RED의 근거**: `29c6f9c`에서 통합 테스트는 `assert 500 == 302`로 실패했다(`uq_users_email` 위반). 저장소 테스트 3개는 `IntegrityError`로, service 테스트 3개는 `FakeConstraintError`로 실패했다. `FakeAuthStore`는 RED 때 지금의 DB처럼 위반을 내게 두었고, 수정 커밋에서 `ON CONFLICT DO NOTHING`처럼 None을 돌려주게 바꿨다. 가짜가 각 커밋의 실제 저장소와 같은 약속을 지키게 하려는 것이다.
- **통합 테스트가 경합을 정하는 방법**: `get_auth_repository`를 오버라이드해 요청마다 처음의 쌍 확인 뒤에 `asyncio.Barrier(2)`를 기다리게 했다. 두 요청이 모두 "행이 없다"를 본 뒤에야 INSERT로 넘어가므로, 타이밍에 기대지 않고 매번 부딪힌다. 30초가 지나면 멈추지 않고 실패한다.
- **사람이 정한 것(2026-11-25)**: 커밋 실패의 500을 E1 S1.3에 예외로 적기로 했다. E1 S1.3에 예외와 겹친 첫 로그인의 동작을 적고, 경위는 ADR-030에 남겼다(`12e4ef1`). 아래는 처음 처분 때의 기록이다.
- **남은 것, 사람이 정할 것**: 리포트의 "사람이 판단할 것"(BEH-4에서 병합)은 이번 수정으로 닫히지 않는다. 경합은 더 이상 500이 아니다. 하지만 커밋 자체가 실패하면(DB 장애 등) 500으로 끝나며, 이것은 `app/auth/router.py`의 머리말, step8.md, `test_commit_failure_sends_no_session_cookie`가 의도한 동작이다. E1 S1.3의 "어떤 경우에도 500으로 끝나지 않습니다"에서 이 경우를 예외로 둘지는 Epic 문서를 고칠 사람이 정한다. 무인 처분은 Epic 문서의 범위 문장을 고치지 않았다.

### SEC-1 상세

- 필터는 uvicorn이 쓰는 서식 `'%s - "%s %s HTTP/%s" %d'`과 인자 다섯 개의 모양일 때만 셋째 인자(경로)를 고치고, 그 밖의 기록은 그대로 둔다. 기록을 버리지 않으므로 접근 로그는 남는다. uvicorn이 서식을 바꾸면 쿼리가 다시 남을 수 있는데, 서브프로세스 테스트가 그것을 잡는다.
- `test_uvicorn_logging_config_is_kept`에서 `uvicorn.access`는 `filters` 키를 뺀 나머지가 uvicorn의 것과 같은지 보게 고쳤다. `filters`의 정확한 값은 새 테스트 `test_access_logger_has_only_the_query_filter`가 본다. 그래서 단언은 약해지지 않았다.
- 테스트의 쿼리 값은 영문자와 숫자만 쓴다. `4/CODE…`처럼 쓰면 로그에는 `4%2F…`로 남아서, 쿼리가 새어도 확인이 찾지 못하기 때문이다.

### ARC-3 상세

- 리포트의 범위(`config.py:41-81`)에 맞춰 `cookie_secure`의 스킴 판정도 `uses_https`로 옮겼다.
- TC-1.2.9의 값 목록은 `tests/core/test_frontend_url.py`로 옮겼고, `tests/core/test_config.py`는 그 목록을 가져와 같은 값들로 설정 클래스가 판정을 거치는지 계속 본다. 그래서 줄어든 경우는 없다.

### BEH-3 상세

- CONFIGURATION.md는 결정을 맡은 문서다. 다만 이번 수정은 규칙을 바꾸지 않는다. 빈 값을 받는 것은 같은 문서의 2절(44행), E1 S1.7("Google의 설정값이 없는 CI에서도 compose 스모크가 계속 통과해야 합니다"), `app/core/config.py`의 주석이 이미 정한 동작이다. 수정은 3절과 3.3절의 문구를 그것에 맞춘 것뿐이다. 고친 줄은 `3351020`의 두 곳이며, 다른 판단이면 되돌리면 된다.

## 기각했다

없음

## 사람 판단 필요

없음. 처음 처분에서 넘긴 ARC-4와 BEH-2는 사람이 정한 뒤 고쳐 "고쳤다"로 옮겼다. 그때 비교한 선택지와 고른 이유는 ADR-029와 ADR-030에 있다.

## 커밋

`29c6f9c` RED(SEC-1 · COR-1 · ARC-1 · ARC-3) · `8198a43` 코드(SEC-1 · COR-1 · ARC-1 · ARC-3) · `f9782bc` 테스트(TST-2 · TST-3 · TST-4 · TST-5) · `f30f218` 테스트 구조(ARC-5) · `3351020` 문서(BEH-3 · BEH-5 · BEH-6) · `58ed9c5` RED(ARC-4) · `bab4487` 코드(ARC-4) · `12e4ef1` 문서(ARC-4 · BEH-2 · COR-1의 예외, ADR-029 · ADR-030)

## 검증

`scripts/check.sh --all`, Docker 켜짐(통합 테스트가 testcontainers의 PostgreSQL에서 돎).

| 명령 | 결과 |
|---|---|
| `ruff check` | exit 0 — 위반 0 |
| `ruff format --check` | exit 0 — 96파일 서식 맞음 |
| `pyright` | exit 0 — 오류 0, 경고 0 |
| `pytest` | exit 0 — 996개 통과, 건너뜀 0 (처분 전 879개). 경고 1(Starlette TestClient의 httpx 폐기 예고, 처분 전과 같음) |

- 돌연변이 반증 (넣은 뒤 빨개진 것을 확인하고 되돌렸다. 되돌린 뒤 `git diff`가 비어 있음을 확인했다):
  - TST-2: 리뷰가 실측한 조합, 즉 `preflight`가 `precheck`를 부르지 않고 `main`이 문제가 있어도 3을 돌려주지 않게 하자 `tests/infra/`의 login_check 테스트 13개가 빨갰다(리뷰 때는 154개가 모두 초록). 하위 에이전트가 따로 넣은 것: `precheck` 결과를 목록에 넣지 않음(2개 빨감), 확인이 어긋나도 0(9개), 표와 달라도 0(1개).
  - TST-3: `/api/me`가 `login_sessions.expires_at`을 늘리게 하자 `test_me_three_times_changes_no_row`만 빨갰다. 기존 `tests/core/test_gate_integration.py`의 TC-1.4.9는 초록이었다. 만료 조건을 하루 늦추자 `test_me_with_expired_login_session_is_not_authenticated`가 빨갰다.
  - TST-4: 어댑터의 `exchange_code`에 `code`를 찍는 DEBUG 로그를 넣자 어댑터 로그 테스트 4개가, repository의 `add_login_session`에 `token_hash`를 찍는 DEBUG 로그를 넣자 `test_login_relogin_me_and_logout_log_no_secret`가 빨갰다.
  - TST-5: `app/auth/service.py`에 `os.urandom(32)`, `uuid.uuid4().hex`, `__import__("secrets")`, `importlib.import_module("random")`을 하나씩 넣자 네 번 모두 `test_only_security_module_has_a_random_source`가 빨갰다.
  - ARC-5: `FakeAuthStore.find_active_login`이 만료를 거르지 않게 하거나 `get_allowed_email`이 소문자로 바꾸게 하자 `test_auth_fakes.py`가 각각 빨갰다. 관리자 경로에 사용자 관문을 걸자 `test_gated_app.py`가 빨갰다.
- 실행으로 확인한 것: SEC-1은 실제 uvicorn을 서브프로세스로 띄워 확인했다. 수정 전 출력은 `"GET /api/auth/google/callback?state=STATESECRETVALUE4f2a&code=CODESECRETVALUE9c1e HTTP/1.1" 302`였고, 수정 후에는 `"GET /api/auth/google/callback HTTP/1.1" 302`다. 이 확인은 테스트로 남겼다.

## 새로 발견한 것

- (추정) `scripts/login_check.py`의 `preflight`와 `run_checks`는 `except (OSError, asyncpg.PostgresError)`만 잡는다. 그런데 `asyncpg.InterfaceError`, `InternalClientError`, `ProtocolError`는 두 클래스의 하위 클래스가 아니다(클래스 관계만 확인함). 그런 예외가 나면 미처리 예외로 끝나고, 그 종료 코드 1이 `EXIT_MISMATCH`(표와 다름)와 구별되지 않는다. 예를 들어 DB_PORT에 PostgreSQL이 아닌 서비스가 떠 있을 때다. 이 상황을 재현하지는 않았고, 고치지 않았다.
- 마이그레이션하지 않은 DB에서 점검 전 확인이 실패하면, 보여 주는 고치는 방법이 "compose로 띄웠는지 확인한다"여서 원인(마이그레이션 없음)과 맞지 않는다. 고치지 않았다.
- (ARC-4와 함께 고침, `bab4487`) `app/auth/service.py`가 `AllowedEmail`과 `UserRecord`를 `app/auth/repository.py`에서 import한다. ARCHITECTURE 8절은 "service는 포트에만 의존"한다고 적는다. ARC-4와 같은 결정(저장소의 레코드와 약속을 어디에 둘지)에 묶이므로 함께 정하면 된다. 처음 처분에서는 고치지 않았고, ARC-4에서 레코드를 포트로 옮기며 함께 풀었다.

<!-- disposition: fixed=14 rejected=0 needs-human=0 -->
