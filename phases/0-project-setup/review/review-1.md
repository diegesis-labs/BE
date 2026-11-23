# Epic 0 코드 리뷰 — 1차

대상 `feat-0-project-setup` · `main...HEAD` (62파일, +4879/-22) · 커밋 `de889eb..6398f3f`
리뷰 일시 2026-11-23 · 차원별 모델 correctness=opus, security=sonnet, architecture=opus, test-coverage=opus, behavioral=opus
근거 문서: `docs/backlog/epic-0/` · `docs/DEVELOPMENT.md` · `docs/ARCHITECTURE.md` · `docs/ADR.md` · `docs/API.md` · `docs/CONFIGURATION.md` · `docs/DECISIONS.md` · `docs/INFRA.md` · `phases/0-project-setup/step*.md`

architecture는 `app/main.py`의 조립과 `pyproject.toml`의 검사 설정이 diff에 있어서 opus로 올렸다. security는 로그인·본문·음원·묶음·SQL 표면이 이 phase에 없어 기본값(sonnet)으로 두었다.

## 종합 판정

| 차원 | critical | major | minor | 판정 |
|---|---|---|---|---|
| correctness | 0 | 1 | 7 | ⚠️ |
| security | 0 | 0 | 1 | ✅ |
| architecture | 0 | 2 | 6 | ⚠️ |
| test coverage | 0 | 2 | 4 | ⚠️ |
| behavioral | 0 | 0 | 4 | ✅ |
| **합계** | **0** | **5** | **22** | |

판정: critical 있으면 ❌ · major만 있으면 ⚠️ · minor 이하면 ✅ · 차원이 안 돌았으면 `미완`

**phase를 닫아도 되는가**: critical은 없다. major 5건을 닫은 뒤 가능하다.

## 실측

| 명령 | 결과 |
|---|---|
| `ruff check` | exit 0 — 위반 0 |
| `ruff format --check` | exit 0 — 48파일 서식 일치 |
| `pyright` | exit 0 — 오류 0, 경고 0 |
| `pytest` | exit 0 — 226개 통과, 건너뜀 0, xfail 0, 경고 1(StarletteDeprecationWarning) (20.2s) |
| `scripts/compose-smoke.sh` | exit 0 — 다섯 가지 확인 통과, vector 0.8.7, api Uid 10001×4 (14s) |

`scripts/check.sh --all`과 스모크 모두 orchestrator가 Docker 28.3.2를 켠 상태에서 직접 돌렸다. pytest 226개 가운데 통합 테스트(`tests/core/test_database.py`) 4개도 기본 실행에서 돌았다.

## 결함

### correctness

| ID | 심각도 | 위치 | 위반 | 문제점 | 해결 제안 | 연관 |
|---|---|---|---|---|---|---|
| COR-1 | major | `compose.yaml:26` | D-40 | db의 healthcheck가 `-h` 없이 유닉스 소켓만 봐서 첫 초기화 중 임시 서버가 뜬 순간 healthy가 되고, 그 뒤 TCP로 붙는 migrate가 거부당해 1로 끝날 수 있다 (발생 빈도는 추정) | `pg_isready -h 127.0.0.1 -U diegesis -d diegesis`로 TCP를 확인하고 test_compose.py에 단언을 더한다 | |
| COR-2 | minor | `app/core/errors.py:95-103` | 없음 | 본문을 가질 수 없는 상태(1xx·204·205·304)의 HTTP 예외에도 JSON 본문을 붙여 h11이 `Too much data for declared Content-Length`를 낸다 | `is_body_allowed_for_status_code`가 거짓이면 본문 없는 `Response`를 돌려준다 | |
| COR-4 | minor | `app/core/errors.py:83`, `app/core/errors.py:87-92` | API §2.3 | 깨진 JSON이면 오류 위치(문자 번호)가 `field: "9"`로, 본문 전체가 잘못되면 `field: ""`로 나간다 | `json_invalid`의 위치 정수를 버리고, 경로가 비면 쓸 값을 정해 API.md 2.3절과 테스트에 적는다 | BEH-6 |
| COR-5 | minor | `app/__main__.py:13-15`, `app/core/errors.py:18`, `app/core/errors.py:110` | CONFIGURATION §3.1 | `LOG_LEVEL`이 uvicorn의 로거에만 걸려 앱 로거(`app.*`)는 레벨이 바뀌지 않고, 500의 스택 로그는 서식 없는 `lastResort`로만 나간다 | 진입점에서 `app` 로거(또는 root)의 레벨과 처리기를 `settings.log_level`로 맞춘다 | BEH-7 |
| COR-7 | minor | `.github/workflows/ci.yml:29-31`, `.github/workflows/ci.yml:108-110` | 없음 | main의 push끼리 서로 기다리지 않아, 연달아 합치면 `:latest`가 더 오래된 커밋의 이미지를 가리킬 수 있다 | push 직전에 원격 main의 sha가 `github.sha`와 같을 때만 `:latest`를 붙인다 | |
| COR-8 | minor | `scripts/compose-smoke.sh:23`, `scripts/compose-smoke.sh:66`, `scripts/compose-smoke.sh:82` | 없음 | 모든 worktree가 같은 프로젝트 이름을 써서 스모크 두 개가 겹치면 서로의 컨테이너와 볼륨을 지운다 (동시 실행 빈도는 추정) | 시작 전에 이미 도는 `diegesis-smoke`가 있으면 멈추거나 잠금 폴더로 직렬화한다 | |
| COR-10 | minor | `scripts/hooks/bash-guard.sh:95-99` | 없음 | 명령 전체 문자열을 보므로 커밋 메시지·echo 인자 안의 `docker login`·`docker push` 낱말에도 무인 세션의 정상 명령이 막힌다 | 따옴표 안의 내용을 지운 뒤 맞춰 보거나, 명령 구분자 바로 뒤의 `docker`만 본다 | |
| COR-11 | minor | `migrations/script.py.mako:11-12`, `migrations/script.py.mako:16-19`, `alembic.ini:18` | DEVELOPMENT §2 | 리비전 템플릿이 쓰지 않는 import와 `repr()`의 작은따옴표 때문에 `ruff check`와 `ruff format --check`를 통과하지 못하는 파일을 만든다 | `[post_write_hooks]`에 ruff check --fix와 ruff format을 걸거나 템플릿을 고친다 | |

#### COR-1 상세

correctness 차원이 같은 이미지(`pgvector/pgvector:0.8.7-pg19`)를 띄우고 소켓 방식과 TCP 방식의 `pg_isready`를 약 80ms 간격으로 번갈아 확인했다. 첫 초기화 도중 entrypoint가 띄우는 임시 서버(`listen_addresses=''`)가 떠 있는 동안 소켓은 성공하고 TCP는 실패하는 구간이 약 0.1초 있었다. 스모크와 CI는 매번 볼륨을 지운 상태에서 시작하므로(`compose-smoke.sh`의 사전 정리) 이 초기화 경로를 매번 지난다. 그래서 확률은 낮아도 CI의 compose-smoke가 까닭 없이 빨개질 수 있고, 팀원이 README대로 처음 띄울 때 migrate가 실패할 수 있다. 이 phase가 만든 경로에서 재현되므로 major로 올렸다.

### security

| ID | 심각도 | 위치 | 위반 | 문제점 | 해결 제안 | 연관 |
|---|---|---|---|---|---|---|
| SEC-1 | minor | `scripts/hooks/bash-guard.sh:95-99` | D-36 | 이미지 push·로그인 가드가 절대 경로(`/usr/local/bin/docker push`), 전역 옵션(`--context`·`-H`·`--config`), `compose build --push`, `buildx bake --push`, `manifest push`, `imagetools create`를 통과시킨다 | 앞 경계에서 `/`를 허용하고 전역 옵션을 건너뛰게 하며, `--push`·`type=registry`는 하위 명령과 상관없이 막는다 | COR-9 |

가드는 사고를 막는 장치이지 적대적 방어가 아니어서 minor로 두었다. 다만 Docker Desktop에 Docker Hub 로그인이 남아 있는 컴퓨터에서는 통과한 형태의 push가 실제로 공개 저장소에 올라간다(D-37). correctness 차원이 `HARNESS_RUN=1`로 가드에 넣어 9가지 형태가 모두 통과하는 것을 실측했다.

### architecture

| ID | 심각도 | 위치 | 위반 | 문제점 | 해결 제안 | 연관 |
|---|---|---|---|---|---|---|
| ARC-1 | major | `app/core/errors.py:23-27`, `app/core/errors.py:98-100` | API §2.3, step2.md 금지사항 | `_HTTP_ERRORS`에 401·404·405만 있어, 2.3절 표에 있는 상태인 400과 500의 HTTP 예외가 표에 없는 `BAD_REQUEST`·`INTERNAL_SERVER_ERROR`로 나간다 | 맵에 400→`VALIDATION_ERROR`, 500→`INTERNAL_ERROR`를 더하고, `HTTPStatus`에 없는 상태의 대체 규칙을 두고 재현 테스트를 둔다 | BEH-1, COR-3 |
| ARC-2 | major | `app/main.py:17-22`, `app/core/errors.py:81-84` | API §1, API §2.3 | 처리기는 런타임 응답만 400으로 바꾸고, OpenAPI에는 FastAPI 기본의 422와 `HTTPValidationError` 스키마가 그대로 문서화된다 | `create_app()`에서 OpenAPI의 422를 공통 에러 스키마의 400으로 바꾸고, 어떤 operation에도 422가 없는지 테스트한다 | BEH-4 |
| ARC-3 | minor | `app/main.py:17-22` | API §1, step0.md 작업 3 | `swagger_ui_oauth2_redirect_url`을 두지 않아 FastAPI 기본값 `/docs/oauth2-redirect`가 `/api` 밖에 200으로 열려 있고, `/api/docs`는 API.md에 적혀 있지 않다 | 그 경로를 `None`으로 닫거나 `/api` 아래로 옮겨 TC-0.1.5 테스트에 더하고, API.md 1절에 `/api/docs`를 적는다 | COR-6, BEH-3 |
| ARC-4 | minor | `pyproject.toml:52`, `docs/ADR.md:348-359`, `docs/ARCHITECTURE.md:463-475` | ADR-009, DEVELOPMENT §1 | 새로 들인 actionlint는 ADR과 DEVELOPMENT.md 어디에도 없고, testcontainers(ADR-011)는 ARCHITECTURE 9절의 기술스택 표에 없다 | ADR-009의 도구 표(또는 별도 기록)에 actionlint를, ARCHITECTURE 9절에 testcontainers를 더한다 | BEH-8 |
| ARC-5 | minor | `docs/ADR.md:388`, `docs/DECISIONS.md:54` | D-20 | ADR-010과 D-23은 이미지 자동 생성을 "아직 만들지 않았다"고 하지만, INFRA.md 3.7절과 `ci.yml`에는 main push에서 이미지를 올리는 단계가 이미 있다 | 두 곳을 "이미지 push까지는 Epic 0에서 만들었고 배포 환경 반영만 남았다"는 뜻으로 고치거나 INFRA.md 3.7절을 참조하게 한다 | |
| ARC-6 | minor | `tests/support/postgres.py:1`, `tests/support/test_postgres.py:1`, `docs/DEVELOPMENT.md:106-117` | DEVELOPMENT §4.2 | 테스트 위치 규칙은 `tests/`가 `app/`과 같은 구조이고 예외는 `tests/infra/`뿐이라 하는데, `tests/support/`의 자리가 규칙에 없다 | DEVELOPMENT.md 4.2절에 "여러 테스트가 함께 쓰는 도우미와 그 테스트는 `tests/support/`에 둔다"를 더한다 | |
| ARC-7 | minor | `docs/DEVELOPMENT.md:20`, `docs/DEVELOPMENT.md:143`, `docs/DECISIONS.md:92`, `docs/DECISIONS.md:94`, `docs/INFRA.md:137`, `docs/backlog/epic-0/testcase.md:51`, `docs/backlog/epic-0/testcase.md:64` | D-17 | 이번 개정에 새로 쓰인 "Docker builder", "준비 상태 확인", "fixture", "빌드 맥락", "actionlint"가 GLOSSARY.md에 없다 | GLOSSARY.md의 실행 환경·개발 절차 표에 다섯 용어를 더한다 | |
| ARC-8 | minor | `README.md:60`, `compose.yaml:21`, `compose.yaml:49` | D-20, CONFIGURATION 머리말 | `API_PORT`·`DB_PORT`의 설명이 README에만 있고, compose 변수가 CONFIGURATION.md의 범위인지가 정해져 있지 않다 (추정) | CONFIGURATION.md에 compose 변수 소절을 둘지, 범위 밖이라고 1절에 적을지 사람이 정한다 | |

#### ARC-1 상세

FastAPI는 본문을 해석하다 JSON 오류가 아닌 예외가 나면(예: UTF-8이 아닌 바이트, 깨진 multipart) 스스로 `HTTPException(status_code=400)`을 던진다. architecture 차원이 임시 경로로 재현했고 응답은 `400 {"code":"BAD_REQUEST"}`였다. 지금 서버에는 본문을 받는 경로가 없어 드러나지 않지만, 본문을 받는 첫 엔드포인트(특히 묶음 업로드 `POST /api/admin/bundles`)부터 나타난다. 그리고 `HTTPException(499)`처럼 `HTTPStatus`에 없는 상태는 `HTTPStatus(status_code)`에서 `ValueError`가 나서 처리기 자체가 터지고 500 `INTERNAL_ERROR`로 바뀐다(COR-3 실측). step2 summary가 400·403의 공백을 메모했지만 500은 적지 않았다. 403은 step2.md가 기능 Epic의 `AppError`로 미뤘으므로 이 결함에서 뺀다. 테스트가 초록인데 step2.md 금지사항("표에 없는 상태만 HTTPStatus의 이름을 쓴다")이 지켜지지 않는 자리라서 major다.

#### ARC-2 상세

API.md 1절은 서버가 `/api/openapi.json`으로 OpenAPI 문서를 제공하고 프론트엔드가 여기서 TypeScript 타입을 만든다고 정했다. 쿼리 파라미터가 있는 경로를 붙이면 OpenAPI에는 응답이 `200`과 `422`로, 본문 스키마가 `{detail:[{loc,msg,type}]}`로 실리지만 실제 응답은 `400 {code, message, detail:[{field, reason}]}`다(architecture·behavioral 두 차원이 실측). 지금은 입력을 받는 엔드포인트가 없어 드러나지 않지만, 다음 Epic의 첫 입력 엔드포인트(로그인 콜백의 `code`·`state`)부터 기준 문서와 실제 응답이 어긋난다. S0.3이 공통 에러 형식의 바탕이므로 이 phase에서 닫는 것이 맞다고 보고 minor에서 major로 올렸다.

### test coverage

| ID | 심각도 | 위치 | 위반 | 문제점 | 해결 제안 | 연관 |
|---|---|---|---|---|---|---|
| TST-1 | major | `scripts/compose-smoke.sh:95-136`, `tests/infra/test_compose_smoke.py:26`, `tests/infra/test_compose_smoke.py:210-219` | TC-0.5.1, DEVELOPMENT §4.4 | 스모크의 다섯 확인을 모두 늘 통과하도록 망가뜨려도 `tests/infra`는 84개 모두 통과한다. "하나라도 어긋나면 0이 아닌 코드"를 실행해 보는 테스트가 없다 | 가짜 `docker`·`curl`이 하위 명령마다 정해진 출력을 내게 해서, 정상이면 0이고 (1)~(5)를 하나씩 어긋나게 하면 0이 아니며 `(N)`이 찍히는지 parametrize로 단언한다 | |
| TST-2 | major | `tests/health/test_router.py:59-69` | TC-0.4.2, step3.md 반증 조건, D-39 | 헬스체크가 `create_engine()`으로 `SELECT 1`을 보내고 예외를 삼켜도 5개 모두 통과한다. 테스트는 DB 오류가 500으로 새는지만 본다 | `create_engine`·`create_async_engine`·`asyncpg.connect`·`get_settings`를 호출을 기록하는 가짜로 바꾸고, 요청 뒤 호출이 0번인지 단언한다 | |
| TST-3 | minor | `tests/test_main.py:39-46` | TC-0.1.5, step0.md 반증 조건 | `sys.modules`에서 `app.main`만 지우고 다시 import해서, 하위 모듈(`app.health.router` 등)이 import할 때 설정을 읽어도 레포에 `.env`가 있는 로컬에서는 초록이다 | `app`과 `app.*`를 모두 지우거나, `DATABASE_URL` 없는 환경과 빈 cwd에서 subprocess로 `import app.main`을 돌린다 | |
| TST-4 | minor | `tests/infra/test_workflow.py:226`, `tests/infra/test_workflow.py:250`, `tests/infra/test_workflow.py:302` | D-36, TC-0.7.1, TC-0.7.2 | `check`·`compose-smoke` job이나 그 스크립트 step에 `if: github.event_name == 'push'`를 붙여 PR에서 건너뛰어도 30개 모두 통과한다 | 두 job과 그 스크립트 step에 `if`가 없는지 단언한다(`image` job에는 이미 같은 테스트가 있다) | |
| TST-5 | minor | `tests/infra/test_workflow.py:41`, `tests/infra/test_workflow.py:243` | TC-0.7.2, DEVELOPMENT §2 | 검사 도구를 직접 부르는지 `run` 줄만 보므로, `check` job에 `uses: astral-sh/ruff-action@v3`를 더해도 통과한다 | `check` job의 `uses`를 허용 목록(`actions/checkout`, `astral-sh/setup-uv`)으로 제한한다 | |
| TST-6 | minor | `tests/conftest.py:17-24`, `tests/support/test_postgres.py:34` | DEVELOPMENT §4.3, TC-0.2.5 | TC-0.2.5는 `start_database()`만 부르므로, 세션 fixture에 `except DockerUnavailableError: pytest.skip(...)`을 더해도 통과한다 (현재 fixture는 올바르다) | `pytester`로 `database_url`을 요청하는 테스트를 Docker 없는 상태에서 돌려 결과가 skip이 아니라 error인지 단언한다 | |

TST-1·TST-2·TST-4·TST-5와 TST-3은 test-coverage 차원이 레포 복사본에서 반증을 실제로 넣고 돌려 확인했다(근거: 실측). TST-6은 코드 판독이다.

### behavioral

| ID | 심각도 | 위치 | 위반 | 문제점 | 해결 제안 | 연관 |
|---|---|---|---|---|---|---|
| BEH-2 | minor | `phases/0-project-setup/MANUAL.md:13`, `phases/0-project-setup/MANUAL.md:19` | HARNESS.md 2.4, TC-0.7.6 | 유일한 MANUAL 항목이 `[x]`인데 "관찰한 값"이 비어 있어 TC-0.7.6이 확인됐다는 증거가 레포에 없고, 체크가 `feat: step 1 — database` 커밋(`e1d5c4f`)에 섞여 들어갔다 | 사람이 `gh secret list`·`gh variable list`로 본 이름을 적어 따로 커밋하고, 확인하지 않았다면 체크를 되돌린다 | TST-7 |
| BEH-5 | minor | `tests/health/test_router.py:46-56`, `tests/health/test_router.py:61` | E0 못 박을 것, step0.md 금지사항 | TC-0.4.2의 fixture가 작업 경로를 옮기지 않은 채 `get_settings()`를 불러, 레포 최상위에 있는 개발자의 `.env`(`PORT`·`LOG_LEVEL`)를 읽는다 | fixture에 `monkeypatch.chdir(tmp_path)`를 더한다(test_config.py의 `isolated_env`와 같은 방식) | |
| BEH-9 | minor | `README.md:14-15`, `docs/DEVELOPMENT.md:10-14` | step5.md 검증 절차 2 | README는 compose 절에서 PowerShell 문법까지 적었지만, bash 스크립트인 `scripts/check.sh`를 Windows에서 돌리는 방법(Git Bash·WSL)은 없다 | DEVELOPMENT.md 1절에 Windows에서 검사를 돌리는 방법을 적고 README에서 그 절로 잇는다 | |
| BEH-10 | minor | `scripts/compose-smoke.sh:132-136`, `docs/backlog/epic-0/testcase.md:50`, `phases/0-project-setup/step4.md:57` | TC-0.5.1 (5) | TC는 "api 이미지 안에 `.env`가 없다"인데, step4.md와 스모크는 작업 폴더(`/app/.env`)만 본다 | TC-0.5.1 (5)를 "작업 폴더에"로 고치거나, 스모크가 이미지 전체에서 `.env`를 찾게 한다 | |

#### BEH-2 상세

누가 체크했는지는 코드로 확정할 수 없지만, step 1 세션의 결과(`step1-output.json`)에는 "MANUAL.md의 항목이 세션 중에 `[x]`로 체크되어 있었습니다. 제가 한 변경이 아니어서 … 제 커밋에서도 뺐습니다"라고 적혀 있고, 실제로 에이전트의 커밋 `5d2ecc2`에는 MANUAL.md가 없다. 체크는 harness가 `git add -A`로 만든 다음 커밋 `e1d5c4f`에 섞였다. 그래서 사람이 실행 도중 체크했을 가능성이 높고(추정), 에이전트의 금지사항 위반으로 보지 않는다. 남은 문제는 관찰한 값이 비어 있다는 기록의 공백이며, 고치는 것은 사람의 몫이다.

## 수정 우선순위

| # | 결함 | ID | 규모 |
|---|---|---|---|
| 1 | 표에 있는 상태(400·500)의 HTTP 예외가 표에 없는 code로 나간다 | ARC-1 | `_HTTP_ERRORS`에 두 줄과 `HTTPStatus` 실패 대체 분기, 재현 테스트 3~4개 |
| 2 | OpenAPI가 422와 FastAPI 기본 오류 스키마를 문서화한다 | ARC-2 | `create_app()`에 OpenAPI 생성 덮어쓰기 한 함수와 테스트 1~2개 |
| 3 | TC-0.4.2가 예외를 삼키는 DB 질의를 잡지 못한다 | TST-2 | 테스트 하나에 호출 기록용 가짜 몇 개 |
| 4 | db healthcheck가 소켓만 봐서 첫 초기화 중 migrate가 실패할 수 있다 | COR-1 | `compose.yaml` 한 줄과 test_compose.py 단언 하나 |
| 5 | 스모크의 다섯 확인이 실패하는 경우를 확인하는 테스트가 없다 | TST-1 | test_compose_smoke.py의 가짜 docker 확장과 parametrize 6개 |
| 6 | 이미지 push 가드의 우회 형태와 문자열 오탐 | SEC-1, COR-10 | bash-guard.sh 정규식과 bash-guard.test.sh 사례 |
| 7 | `/docs/oauth2-redirect`가 `/api` 밖에 열려 있다 | ARC-3 | `create_app()` 인자 하나와 TC-0.1.5 parametrize 한 줄 |
| 8 | 검증 오류의 `field`가 문자 번호나 빈 문자열로 나간다 | COR-4 | `_field_name` 분기와 API.md 2.3절 한 줄, 테스트 2개 |
| 9 | 리비전 템플릿이 검사를 통과하지 못하는 파일을 만든다 | COR-11 | `alembic.ini`의 post_write_hooks 또는 템플릿 수정 |
| 10 | 나머지 minor(테스트 보강·문서 정합) | COR-2, COR-5, COR-7, COR-8, ARC-4~8, TST-3~6, BEH-5, BEH-9, BEH-10 | 각각 몇 줄. 문서 항목(ARC-4~8, BEH-9, BEH-10)은 결정을 맡은 문서를 고치는 일이라 사람이 정한다(D-33) |
| — | MANUAL의 관찰한 값 | BEH-2 | 사람만 할 수 있다 |

## 이전 라운드 대조

1차라 해당 없음.

## 잘 된 것 (재검증 불필요)

- RED 커밋 순서: step2(`95b3f58`→`854c5e5`), step3(`be1d09a`→`d48d0e4`), step4(`4902bf5`→`32191f0`), step6(`1103b3f`→`0cfe90a`) 모두 테스트가 먼저다. step4 구현 커밋의 test_compose.py 변경은 단언을 지우지 않고 테스트 하나를 더한 강화다
- 반증 조건의 대부분이 실제로 빨개진다(test-coverage 차원이 복사본에서 실측): `database_url` 기본값, `extra="forbid"`, `.env` 우선, OpenAPI 기본 경로, 422, `body.` 접두사, 500의 예외 내용, `"detail": null`, 처리기 미등록, 헬스체크의 키 추가·접두사 없음, `.dockerignore`의 `.env` 삭제, `.python-version`만 올림, migrate의 `localhost`, 프로젝트 이름을 바깥에서 받음, `docker build`, `pull_request_target`, `uv run pytest` 추가, uv 버전 차이, `needs` 삭제, PR에서 push, arm64, 이미지 이름·사용자 이름 리터럴, `contents: write`, `continue-on-error`
- 에러 형식의 정상 경로: 404·405의 본문 키가 정확히 `{code, message}`이고 405는 `Allow: GET`을 유지한다. 409는 `CONFLICT`, 검증 실패는 400과 `item.price` 꼴의 `field`, 500은 `INTERNAL_ERROR`이며 응답에 예외 내용이 없고 스택은 로그에만 남는다. 검증 오류의 `input`·`ctx`는 응답에 실리지 않는다
- 설정: 세 값만 있고, `DATABASE_URL`은 필수, `extra="ignore"`, 환경변수가 `.env`보다 우선한다. `app/`·`migrations/`에 `os.environ`·`getenv`가 없다
- DB 이미지는 `compose.yaml`의 `db` 한 곳에만 있고, TC-0.2.4는 compose.yaml을 직접 읽어 Docker의 실제 이미지와 비교한다(자기 단언이 아니다). Docker가 없으면 skip이 아니라 오류가 난다. TC-0.2.2 픽스처는 코사인과 유클리드를 실제로 가른다
- `migrations/env.py`는 넘겨받은 `sqlalchemy.url`을 먼저 쓰고 alembic.ini에 주소가 없다. 마이그레이션은 vector 확장 하나뿐이고 upgrade와 downgrade가 대칭이다
- CI: 트리거는 main을 향한 `pull_request`와 main `push`뿐이고, 권한은 `contents: read`, checkout은 `persist-credentials: false`, `run:` 안에 `${{ }}` 직접 삽입이 없다. 로그인과 push는 `push && refs/heads/main`일 때만 돌고, PR의 step에는 secrets·vars 참조가 없다. actionlint 종료 코드 0
- 이미지: 멀티 스테이지, `--locked --no-dev`, `app/`·`migrations/`·`alembic.ini`만 복사, `USER 10001:10001`, 셸 스크립트 진입점 없음, `.env`·비밀값 없음
- 스모크: 프로젝트 이름이 readonly 상수이고 인자를 거부하며 `-p`로 고정, `--env-file /dev/null`, 빈 포트, compose로만 빌드, trap으로 이 프로젝트만 볼륨까지 내린다. orchestrator 실측 통과
- index.json summary의 테스트 개수 주장(step0 25, step1 6, step2 18, step3 5, step4 54, step6 30, 합계 226)이 실측과 모두 맞는다
- diff 전체에 Docker Hub 사용자 이름·이미지 전체 이름·토큰이 없다. `# type: ignore`·`# noqa`가 새로 들어오지 않았고 ruff·pyright·pytest 설정이 느슨해지지 않았다

## 이 리뷰가 판정하지 않은 것

- 로그인·허용 목록·CORS, 기능 테이블, 선곡·평가 기록·묶음 적재·서명된 주소 — 이 phase의 범위 밖(E0 "범위 밖"). 각 차원은 "표면 없음"으로 확인했다
- GitHub Actions의 실제 실행 결과, 배포 환경에서의 실행, 이미지 크기와 빌드 시간, arm64 이미지가 없는 것 — `testcase.md` "이 Epic에서 판정하지 않는 것"
- MANUAL 항목(TC-0.7.6)의 실제 등록 여부(`gh secret list`·`gh variable list`) — 사람의 몫. 기록의 공백만 BEH-2로 올렸다
- phase가 리뷰보다 먼저 `completed`로 기록된 것(`phases/index.json`, `6398f3f`) — `scripts/execute.py`의 `_finalize` 설계에서 오는 것이고 harness는 이 diff에 없다. harness를 고치는 작업에서 볼 것
- 기각한 sub-agent 지적 11건 (근거 불일치 0 · 범위 밖 1 · 중복 10)
  - 범위 밖: SEC-2(`/api/docs`·`/api/openapi.json`이 로그인 없이 열린 것 — 관문은 로그인 Epic이 정한다. API.md에 `/api/docs`가 없는 문서 공백은 ARC-3에 남겼다)
  - 중복: COR-3·BEH-1 → ARC-1, BEH-4 → ARC-2, COR-6·BEH-3 → ARC-3, BEH-8 → ARC-4, COR-9 → SEC-1, BEH-6 → COR-4, BEH-7 → COR-5, TST-7 → BEH-2
- 심각도를 다시 정한 것: COR-1(minor→major), ARC-2(minor→major). ARC-1은 차원마다 major·minor로 갈렸고 major로 통일했다

<!-- verdict: critical=0 major=5 minor=22 -->
