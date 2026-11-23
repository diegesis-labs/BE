# 0-project-setup 리뷰 처분 — 1차

> `review-1.md`의 결함 27건(critical 0 · major 5 · minor 22)에 대한 처분. 2026-11-23.
> 고친 것 23건, 기각 4건, 사람 판단 필요 0건. major 5건은 모두 고쳤다.
> 무인 처분은 16건을 고치고 11건을 사람 판단 필요로 넘겼다. 그 11건은 같은 날 대화형 세션에서 사람이 정했고, 아래 표에서 "사람이 정함"으로 적었다.

## 고쳤다

| ID | 심각도 | 처분 | 커밋 |
|---|---|---|---|
| COR-1 | major | db의 healthcheck를 `pg_isready -h 127.0.0.1 …`로 바꿔 TCP로 확인한다. 재현: `tests/infra/test_compose.py::test_db_healthcheck_checks_tcp_connection` | `138217f` → `f5a3a35` |
| ARC-1 | major | `_HTTP_ERRORS`에 400→`VALIDATION_ERROR`, 500→`INTERNAL_ERROR`를 더하고, 이름 없는 상태(499)는 처리기가 터지지 않고 500 `INTERNAL_ERROR`로 응답한다(아래 상세). 재현: `tests/core/test_errors.py`의 400·500 행과 `test_http_exception_with_unnamed_status_is_an_internal_error` | `138217f` → `f5a3a35` |
| ARC-2 | major | `register_error_handlers`가 `app.openapi`를 감싸 422를 지우고 `ValidationErrorResponse`(`{code, message, detail:[{field, reason}]}`)의 400을 싣는다. 재현: `tests/core/test_errors.py::test_openapi_documents_validation_failure_as_400_in_error_format` | `138217f` → `f5a3a35` |
| TST-1 | major | 정상 스택을 흉내 내는 가짜 docker·curl로 정상이면 0, (1)~(5)를 하나씩 어긋나게 하면 0이 아닌 코드와 `(N)`인지 본다. `tests/infra/test_compose_smoke.py`의 `test_script_passes_when_every_check_holds`와 `test_script_fails_when_*` | `c5a84f5` |
| TST-2 | major | 요청 동안 소켓·`Engine`·`AsyncEngine`의 연결 시도와 `get_settings` 호출을 기록해 0인지 단언한다. `tests/health/test_router.py::test_health_does_not_touch_the_database` | `c5a84f5` |
| COR-2 | minor | 1xx·204·205·304의 HTTP 예외는 `is_body_allowed_for_status_code`로 걸러 본문 없는 `Response`를 돌려준다. 재현: `test_http_exception_without_body_status_has_no_body` | `138217f` → `f5a3a35` |
| COR-5 | minor | 진입점이 uvicorn의 기본 로그 설정에 `app` 로거(LOG_LEVEL, `default` 처리기)를 더해 넘긴다. 재현: `tests/test___main__.py` | `138217f` → `f5a3a35` |
| COR-8 | minor | 스모크가 `${TMPDIR:-/tmp}/diegesis-smoke.lock`을 `mkdir`로 쥐고 돌며, 살아 있는 다른 스모크가 쥐고 있으면 compose를 부르지 않고 멈춘다(아래 상세). 재현: `tests/infra/test_compose_smoke.py`의 잠금 테스트 4개 | `138217f` → `f5a3a35` |
| COR-11 | minor | `alembic.ini`의 `[post_write_hooks]`에 `ruff check --fix`와 `ruff format`을 건다. 재현: `tests/infra/test_migration_template.py` | `138217f` → `f5a3a35` |
| ARC-7 | minor | GLOSSARY.md에 fixture, actionlint(개발 절차), 빌드 맥락, Docker builder, 준비 상태 확인(실행 환경)을 더했다 | `943a133` |
| TST-3 | minor | `import app.main`을 `DATABASE_URL` 없는 환경과 빈 cwd의 새 프로세스에서 돌린다. `tests/test_main.py::test_import_app_main_does_not_read_settings` | `c5a84f5` |
| TST-4 | minor | `check`·`compose-smoke` job과 그 step 전부에 `if`가 없는지 단언한다. `tests/infra/test_workflow.py::test_check_and_smoke_run_on_every_trigger` | `c5a84f5` |
| TST-5 | minor | `check` job의 `uses`를 `actions/checkout`, `astral-sh/setup-uv`로 제한한다. `test_check_job_uses_only_checkout_and_setup_uv` | `c5a84f5` |
| TST-6 | minor | `tests/conftest.py`에 pytester를 켜고, `database_url`을 요청하는 테스트를 Docker 없이 돌려 error 1·skip 0인지 본다. `tests/support/test_postgres.py::test_database_fixture_without_docker_errors_instead_of_skipping` | `c5a84f5`, `e9c7286` |
| BEH-5 | minor | TC-0.4.2의 fixture에 `monkeypatch.chdir(tmp_path)`를 더했다 | `c5a84f5` |
| COR-4 | minor | 사람이 정함(A). 특정 필드를 가리킬 수 없는 검증 오류의 `field`는 `""`이다. API.md 2.3절에 규칙을 적고, `json_invalid`의 `field`를 `""`로 낸다. 재현: `tests/core/test_errors.py::test_body_error_without_a_field_has_empty_field` | `0277d01`, `bdb6151` → `e229d5a` |
| ARC-3 | minor | 사람이 정함(A). API.md 1절의 "API 스펙 공유 방식"에 `/api/docs`를 적었다 | `0277d01` |
| ARC-4 | minor | 사람이 정함(A). ADR-009의 도구 표와 근거에 actionlint를, ARCHITECTURE.md 9절에 actionlint와 testcontainers(ADR-011)를 더했다 | `0277d01` |
| ARC-5 | minor | 사람이 정함(A와 B). ADR-010과 D-23을 "이미지 push까지는 Epic 0에서 만들었고 배포 환경 반영이 남았다"로 고치고 INFRA.md 3.7절로 이었다 | `0277d01` |
| ARC-6 | minor | 사람이 정함(A). DEVELOPMENT.md 4.2절에 `tests/support/`의 자리를 더하고, `tests/infra/`의 대상에 `alembic.ini`와 리비전 템플릿을 더했다(새로 발견한 것의 첫째 항목) | `0277d01` |
| ARC-8 | minor | 사람이 정함(B). CONFIGURATION.md 1절에 compose 변수(`API_PORT`·`DB_PORT`)는 범위 밖이고 README가 맡는다고 적었다 | `0277d01` |
| BEH-2 | minor | 사람이 `gh`로 본 이름과 등록 시각을 MANUAL.md의 관찰한 값에 적었다. 값은 적지 않았다(D-37) | `7ccb8b1` |
| BEH-10 | minor | TC-0.5.1 (5)의 글대로 스모크가 `--user 0`으로 이미지 전체(`/proc`·`/sys`·`/dev` 제외)에서 `.env`를 찾는다. 재현: `test_script_fails_when_env_file_is_anywhere_in_image` | `138217f` → `f5a3a35` |

### ARC-1 상세

API.md 2.3절은 표에 없는 상태에 "그 HTTP 상태의 영문 이름"을 쓰라고만 하고, 이름이 없는 상태(499 같은 비표준 값)는 정하지 않았다. 고치기 전에도 그 경우의 바깥 결과는 500 `INTERNAL_ERROR`였다(처리기가 `ValueError`로 터진 뒤 `Exception` 처리기가 받았다). 그래서 새 계약을 만들지 않고 같은 결과를 처리기 안에서 명시적으로 내게 했고, 로그에는 던진 상태를 남긴다. 이름 없는 상태를 그대로 돌려보내고 다른 code를 쓰기로 정한다면 `_handle_http_exception`의 `except ValueError` 분기와 테스트 한 개만 바꾸면 된다.

### COR-8 상세

잠금은 모든 worktree가 함께 보는 임시 폴더에 둔다(macOS는 사용자의 `TMPDIR`, Linux와 CI는 `/tmp`). 잠금을 얻지 못하면 정리(trap)를 걸기 전에 끝나므로, 다른 스모크의 컨테이너·볼륨·잠금을 건드리지 않는다. pid가 죽은 잠금(kill -9 등)은 넘겨받는다. 다른 스모크가 돌면 기다리지 않고 1로 끝낸다. 따라서 harness의 두 phase가 같은 컴퓨터에서 스모크를 겹쳐 돌리면 뒤의 step AC는 실패한다. 서로의 볼륨을 지워서 둘 다 엉뚱하게 실패하던 것보다는 낫지만, 기다리게 할지는 사람이 정할 수 있다.

### TST-1 상세

가짜 docker는 api 컨테이너에서 도는 파이썬 코드(uid를 읽는 것 제외)를 가짜 이미지 폴더에서 실제로 돌린다. 그래서 (5)의 판정은 출력 형식을 흉내 내지 않고 `.env`를 둔 위치로 어긋나게 한다. 이 설계는 스크립트가 찾을 최상위 폴더를 인자(`/`)로 넘긴다는 것에 기댄다. BEH-10을 고치며 스크립트가 `exec --user 0`을 쓰게 되어, 가짜 docker가 exec의 `--user`·`-u`를 건너뛰게 했다(`f5a3a35`). 단언은 바꾸지 않았다.

## 기각했다

| ID | 심각도 | 기각한 이유 | 기록한 곳 |
|---|---|---|---|
| COR-7 | minor | 사람이 정함(A). 병합하는 사람이 한 명이고(D-35) `latest`를 받아 가는 배포가 아직 없다. 배포 단계는 `latest`가 아니라 `sha-` 태그로 반영해야 한다고 INFRA.md 3.7절에 적었다 | `0277d01` |
| COR-10 | minor | 사람이 정함(기록만). 커밋 메시지 속 낱말의 오탐은 4번 DROP 규칙과 같은 이유로 받아들인다. 따옴표를 가르면 `bash -c` 안의 진짜 명령이 샌다 | `ca0d4ab` (bash-guard.sh 주석) |
| SEC-1 | minor | 사람이 정함(B). 이 가드는 실수를 막는 장치이며 일부러 피해 가는 명령은 범위 밖이다. 놓치는 형태를 주석에 적었다 | `ca0d4ab` (bash-guard.sh 주석) |
| BEH-9 | minor | 사람이 정함(보류). Windows에서 검사를 돌릴 BE 개발자가 아직 없다(D-35). DEVELOPMENT.md 1절에 검사를 macOS와 Linux(CI)에서만 확인했다고 적었다 | `0277d01` |

## 사람 판단 필요

없음. 무인 처분이 넘긴 11건은 사람이 정했다(위 두 표). 아래는 사람이 정하기 전에 무인 처분이 적은 선택지이며, 기록으로 남긴다.

### 무인 처분이 넘긴 선택지

| ID | 심각도 | 무엇을 정해야 하는가 | 선택지 |
|---|---|---|---|
| COR-4 | minor | 필드 위치가 없는 검증 오류의 `field` 값이 API.md 2.3절에 없다. 지금은 깨진 JSON이면 문자 번호(`"9"`), 본문 전체가 틀리면 `""`가 나간다. 실측으로 재현했다 | A: `""`로 정하고 json_invalid의 위치 정수를 버린다 / B: 위치 이름(`"body"`)을 쓴다 / C: 그 항목에서 `field` 키를 뺀다. 어느 쪽이든 API.md 2.3절과 프론트엔드의 타입이 바뀐다 |
| COR-7 | minor | main의 push끼리 서로 기다리지 않아 `:latest`가 오래된 커밋을 가리킬 수 있다. 막는 방법마다 대가가 있고, TC-0.7.3("태그는 latest와 sha-")과 기존 테스트를 고쳐야 한다 | A: 받아들이고 기록한다(관리자 1명, D-35) / B: push 직전 원격 main의 sha가 `github.sha`와 같을 때만 `:latest`를 붙인다(확인과 push 사이의 틈은 남는다) / C: image job을 하나의 concurrency 그룹으로 직렬화한다(기다리던 실행이 취소되어 중간 커밋의 `sha-` 이미지가 빠진다) |
| COR-10 | minor | `scripts/hooks/bash-guard.sh`는 무인 처분이 고칠 수 없다. 커밋 메시지나 echo 안의 `docker push`·`docker login` 낱말에도 막힌다 | A: 따옴표 안을 지운 뒤 맞춘다 / B: 명령 구분자(`;`·`&&`·`\|`·줄 시작) 바로 뒤의 `docker`만 본다. SEC-1과 같은 정규식이라 함께 정해야 한다 |
| SEC-1 | minor | 같은 가드가 절대 경로(`/usr/local/bin/docker push`), 전역 옵션(`--context`·`-H`·`--config`), `compose build --push`, `buildx bake --push`, `manifest push`, `imagetools create`를 통과시킨다 | A: 앞 경계에 `/`를 허용하고 전역 옵션을 건너뛰며 `--push`·`type=registry`는 하위 명령과 상관없이 막는다(오탐이 늘어 COR-10과 부딪힌다) / B: 사고 방지 장치로 보고 지금 범위를 기록만 한다 |
| ARC-3 | minor | 코드 쪽(`/docs/oauth2-redirect`가 열려 있던 것)은 `f5a3a35`에서 닫았고 TC-0.1.5 테스트에 더했다. 남은 것은 `/api/docs`가 API.md에 없다는 것인데, API.md는 결정 문서다 | A: API.md 1절의 "API 스펙 공유 방식"에 `/api/docs`를 적는다 / B: 적지 않는다(`/api/docs`는 TC-0.1.5와 step0이 이미 정했다) |
| ARC-4 | minor | actionlint가 ADR·DEVELOPMENT.md에, testcontainers가 ARCHITECTURE 9절의 기술 스택 표에 없다. 둘 다 결정 문서다 | A: ADR-009의 도구 표에 actionlint를, ARCHITECTURE 9절에 testcontainers를 더한다 / B: actionlint는 별도 ADR로 기록한다 |
| ARC-5 | minor | ADR-010의 결정과 D-23이 "자동 배포는 아직 만들지 않았다"고 하지만 이미지 push는 Epic 0에서 만들었다. 결정의 본문을 고치는 일이다 | A: "이미지 push까지는 Epic 0에서 만들었고 배포 환경 반영만 남았다"로 고친다 / B: 두 곳에서 INFRA.md 3.7절을 참조하게 한다 |
| ARC-6 | minor | DEVELOPMENT.md 4.2절에 `tests/support/`의 자리가 없다. 규칙을 코드에 맞춰 넓힐지는 판단이다(새로 발견한 것의 첫째 항목도 같은 절이다) | A: "여러 테스트가 함께 쓰는 도우미와 그 테스트는 `tests/support/`에 둔다"를 더한다 / B: 도우미를 `tests/conftest.py` 쪽으로 옮겨 규칙에 맞춘다 |
| ARC-8 | minor | (추정) compose 변수 `API_PORT`·`DB_PORT`가 CONFIGURATION.md의 범위인지 정해져 있지 않다 | A: CONFIGURATION.md에 compose 변수 소절을 둔다 / B: 1절에 compose 변수는 범위 밖이고 README가 맡는다고 적는다 |
| BEH-2 | minor | MANUAL.md의 TC-0.7.6 항목이 `[x]`인데 "관찰한 값"이 비어 있다. MANUAL은 사람만 채운다 | 사람이 `gh secret list`·`gh variable list`로 본 이름을 적어 따로 커밋한다. 확인하지 않았다면 체크를 되돌린다 |
| BEH-9 | minor | Windows에서 `scripts/check.sh`를 돌리는 방법이 문서에 없다. 어떤 방법을 안내할지 고르고 실제로 돌려 봐야 하는데, 이 세션은 Windows에서 확인할 수 없다 | A: WSL2를 안내한다 / B: Git Bash를 안내한다. 고른 방법으로 한 번 돌려 본 뒤 DEVELOPMENT.md 1절에 적고 README에서 잇는다 |

## 커밋

`c5a84f5` 테스트 강화(TST-1 · TST-2 · TST-3 · TST-4 · TST-5 · TST-6 · BEH-5) · `138217f` RED(COR-1 · COR-2 · COR-5 · COR-8 · COR-11 · ARC-1 · ARC-2 · ARC-3 · BEH-10) · `f5a3a35` 코드(같은 9건) · `943a133` 문서(ARC-7) · `e9c7286` 테스트(TST-6의 안쪽 실행 경고 제거)

사람 판단 11건: `0277d01` 문서(COR-4 · COR-7 · ARC-3 · ARC-4 · ARC-5 · ARC-6 · ARC-8 · BEH-9) · `bdb6151` RED(COR-4) · `e229d5a` 코드(COR-4) · `ca0d4ab` 가드 주석(COR-10 · SEC-1) · `7ccb8b1` MANUAL(BEH-2)

테스트 결함 커밋 `c5a84f5`는 고치기 전 코드에서도 초록이다. 그래서 RED가 아니고, 아래 돌연변이 반증이 증거다.

## 검증

| 명령 | 결과 |
|---|---|
| `ruff check` | exit 0 |
| `ruff format --check` | exit 0 — 50파일 서식 일치 |
| `pyright` | exit 0 — 오류 0 |
| `pytest` | exit 0 — 268개 통과 (처분 전 226개), 경고 1(StarletteDeprecationWarning, 처분 전과 같다) |
| `scripts/compose-smoke.sh` | 다섯 확인 통과(Docker 28.3.2, vector 0.8.7, api Uid 10001×4). 단독 실행 1회, 동시 실행 시험의 첫 실행 exit 0 |

- 사람 판단 11건을 처분한 뒤: `scripts/check.sh --all`의 네 검사 exit 0(pytest 302개 통과), `scripts/hooks/bash-guard.test.sh` 통과 85 · 실패 0. COR-4의 RED 커밋에서 새 테스트의 `unparsable-json`은 `['22'] == ['']`로 빨갰고, `body-is-not-an-object`는 고치기 전에도 `""`라 초록이다(경계).
- 돌연변이 반증:
  - TST-1: 스크립트의 `|| fail "(N)` 13곳을 `|| true`로 바꾸자 실패 경우 7개가 모두 빨개졌다. uid 반복을 첫 값만 보게 바꾸자 `4-saved-uid-is-root`가 빨개졌다.
  - TST-2: 헬스체크에 `create_engine(get_settings().database_url)` + `SELECT 1` + 예외 삼키기를 넣자 빨개졌다(`Engine.connect()` 기록). `create_async_engine`에 주소를 직접 적고 예외를 삼키게 하자 빨개졌다(`AsyncEngine.connect()`, `socket.connect(('127.0.0.1', 1))`). 그 둘째 돌연변이는 처분 전 테스트를 통과했다.
  - TST-3: `app/health/router.py`가 import될 때 `get_settings()`를 부르게 하자 새 테스트가 빨개졌다. 처분 전 테스트는 `DATABASE_URL`이 있고 `tests/core/test_errors.py`가 먼저 `app.main`을 import한 조건에서 그 돌연변이를 통과했다.
  - TST-4: `check` job에 `if: github.event_name == 'push'`를 붙이자, 그리고 `compose-smoke`의 스크립트 step에 같은 조건을 붙이자 각각 빨개졌다.
  - TST-5: `check` job에 `uses: astral-sh/ruff-action@v3`를 더하자 빨개졌다.
  - TST-6: `postgres_container` fixture가 `DockerUnavailableError`를 잡아 `pytest.skip`하게 하자 빨개졌다(`{'skipped': 1} != {'skipped': 0}`). 경고 제거 커밋 뒤에도 다시 확인했다.
- 실행으로 확인한 것:
  - BEH-5: `LOG_LEVEL=TRACE`가 든 `.env`를 둔 임시 폴더를 작업 경로로 pytest를 돌렸다. 처분 전 테스트는 `ValidationError`로 오류가 났고 새 테스트는 통과했다(레포의 `.env` 자리는 건드리지 않았다).
  - COR-8: 스모크를 하나 띄우고 4초 뒤 하나 더 띄웠다. 뒤의 것은 `다른 스모크(PID …)가 … 돌고 있다`로 exit 1, 앞의 것은 exit 0으로 끝났고 잠금 폴더는 남지 않았다.
  - COR-11: 고친 뒤 `alembic revision`으로 만든 파일에서 쓰지 않는 import가 빠지고 따옴표가 큰따옴표로 바뀐 것을 눈으로 확인했다.
  - COR-1: 고친 healthcheck로 db가 healthy가 되고 migrate가 성공하는 것은 스모크로 확인했다. 첫 초기화 중 소켓은 성공하고 TCP는 실패하는 약 0.1초의 구간은 다시 재현하지 않았다. 그 구간은 리뷰의 실측에 기댄다.
  - 리포트가 말한 코드 결함(304·204의 본문, 400·500의 code, 499에서 처리기가 터짐, OpenAPI의 422와 `HTTPValidationError`, `/docs/oauth2-redirect` 200, json_invalid의 `field: "9"`)은 고치기 전에 임시 스크립트로 모두 재현했다.

## 새로 발견한 것

- (ARC-6에서 처리했다) DEVELOPMENT.md 4.2절은 `tests/infra/`의 대상으로 Dockerfile·.dockerignore·compose.yaml·스모크·workflow만 든다. 이번에 더한 `tests/infra/test_migration_template.py`(alembic.ini와 리비전 템플릿)와 `tests/test___main__.py`(4.2절의 "테스트를 먼저 쓰지 않아도 되는 파일"인 `app/__main__.py`)의 자리는 규칙에 명시되어 있지 않다. ARC-6과 함께 정하면 된다.
- (2차 리뷰 COR-1에서 고쳤다) 처리기가 아니라 코드가 직접 던진 `HTTPException(500)`은 500 `INTERNAL_ERROR`로 나가지만, 처리되지 않은 예외와 달리 로그에 남지 않는다. 고치지 않았다.
- `[post_write_hooks]`의 `module` 방식은 ruff가 없는 환경(개발 의존성 없이 설치한 환경, 컨테이너 이미지)에서 `alembic revision`을 실패시킨다. 리비전은 개발 환경에서만 만들므로 고치지 않았다.

<!-- disposition: fixed=23 rejected=4 needs-human=0 -->
