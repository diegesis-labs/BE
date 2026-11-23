# Epic 0 코드 리뷰 — 2차

대상 `feat-0-project-setup` · `main...HEAD` (67파일, +5913/-25) · 커밋 `de889eb..0c3e079`
리뷰 일시 2026-11-23 · 차원별 모델 correctness=opus, security=sonnet, architecture=opus, test-coverage=opus, behavioral=opus
근거 문서: `docs/backlog/epic-0/` · `docs/DEVELOPMENT.md` · `docs/ARCHITECTURE.md` · `docs/ADR.md` · `docs/API.md` · `docs/CONFIGURATION.md` · `docs/DECISIONS.md` · `docs/INFRA.md` · `phases/0-project-setup/step*.md` · `phases/0-project-setup/review/review-1.md` · `phases/0-project-setup/review/fix-1.md`

1차 이후 바뀐 것은 처분 커밋 6개(`c5a84f5`·`138217f`·`f5a3a35`·`943a133`·`e9c7286`·`0c3e079`, 19파일 +911/-35)다. 판정 대상은 diff 전체이고, 처분이 새로 넣은 코드는 각 차원이 따로 살폈다. architecture는 `app/main.py`·`app/core/`·`pyproject.toml`이 diff에 있고 diff가 1,000줄을 넘어 opus로 두었다. security는 로그인·본문·음원·묶음·SQL 표면이 이 phase에 없어 기본값(sonnet)으로 두었다.

## 종합 판정

| 차원 | critical | major | minor | 판정 |
|---|---|---|---|---|
| correctness | 0 | 0 | 3 | ✅ |
| security | 0 | 0 | 1 | ✅ |
| architecture | 0 | 0 | 1 | ✅ |
| test coverage | 0 | 0 | 6 | ✅ |
| behavioral | 0 | 0 | 1 | ✅ |
| **합계** | **0** | **0** | **12** | |

판정: critical 있으면 ❌ · major만 있으면 ⚠️ · minor 이하면 ✅ · 차원이 안 돌았으면 `미완`

**phase를 닫아도 되는가**: 가능하다. 1차 major 5건은 모두 닫혔고, critical과 major는 없다. minor 12건은 다음 Epic이 이 위에 쌓이는 것을 막지 않는다. 다만 ARC-1은 본문을 받는 첫 엔드포인트를 만들기 전에 닫는 것이 좋다.

## 실측

| 명령 | 결과 |
|---|---|
| `ruff check` | exit 0 — 위반 0 |
| `ruff format --check` | exit 0 |
| `pyright` | exit 0 — 오류 0 |
| `pytest` | exit 0 — 268개 통과, 건너뜀 0, xfail 0, 경고 1(StarletteDeprecationWarning) (31.93s) |
| `scripts/compose-smoke.sh` | exit 0 — 다섯 확인 통과, vector 0.8.7, api Uid 10001×4 (13.6s) |

`scripts/check.sh --all`과 스모크는 orchestrator가 Docker 28.3.2를 켠 상태에서 직접 돌렸다. pytest 268개에는 통합 테스트(`tests/core/test_database.py`) 4개가 들어 있다. 1차의 226개보다 42개 늘었다.

## 결함

### correctness

| ID | 심각도 | 위치 | 위반 | 문제점 | 해결 제안 | 연관 |
|---|---|---|---|---|---|---|
| COR-1 | minor | `app/core/errors.py:35`, `app/core/errors.py:181-182`, `app/core/errors.py:189-195` | step2.md 작업 1(500 항목) | 코드가 직접 던진 `HTTPException(500)`·`HTTPException(503)`은 응답이 처리되지 않은 예외와 같은 `INTERNAL_ERROR`(503은 `SERVICE_UNAVAILABLE`)인데, 서버 로그에는 원인이 남지 않는다. 499를 500으로 바꾸는 분기도 상태만 남기고 스택은 남기지 않는다 | `_handle_http_exception`에서 상태가 500 이상이거나 이름 없는 상태이면 method·path·status·detail을 `logger.error`(원인 예외가 있으면 `exc_info`)로 남기고, caplog로 단언한다 | BEH-3, TST-2 |
| COR-3 | minor | `scripts/compose-smoke.sh:80-93` | 없음 | 죽은 스모크가 남긴 잠금을 넘겨받는 "pid 읽기 → kill -0 → rm → rmdir → mkdir"가 원자적이지 않다. 두 스모크가 거의 동시에 시작하면 둘 다 잠금을 쥐고 같은 프로젝트의 볼륨을 서로 지울 수 있다 | `mv "$LOCK_DIR" "$LOCK_DIR.stale.$$"`처럼 원자적 rename에 성공한 쪽만 정리하고 mkdir하거나, mkdir 뒤 pid 파일을 다시 읽어 자기 것인지 확인한다 | TST-4 |
| COR-4 | minor | `alembic.ini:25`, `alembic.ini:28` | 없음 | Windows의 네이티브 Python에서는 alembic이 options를 `posix=False`로 나눠 `--config "…"`의 따옴표가 남고, ruff가 exit 2로 끝나는데 alembic은 그 실패를 무시한다. 리비전은 성공으로 끝나고 고쳐지지 않은 파일이 남는다 (Windows에서 리비전을 만드는 팀원이 있다는 것은 추정) | 따옴표를 빼고 `ruff_check.cwd = %(here)s`와 `--config pyproject.toml`처럼 상대 경로로 넘긴다(ruff_format도 같다) | |

#### COR-3 상세

correctness 차원이 `acquire_lock`을 그대로 옮긴 스크립트로 재현했다. 죽은 pid가 든 잠금을 두고 두 프로세스를 0.3초 차이로 띄우고 한쪽의 pid 읽기 뒤에 지연을 넣자, 둘 다 "넘겨받는다"와 잠금 획득을 찍었다. 지연이 없으면 경합 창은 수 ms다. 남은 잠금(kill -9 등)과 동시 시작이 모두 있어야 하고, 지워지는 것은 `diegesis-smoke` 프로젝트의 볼륨뿐이라 개발용 데이터는 안전하다. 그래서 1차 COR-8과 같은 minor로 둔다.

#### COR-4 상세

alembic 1.20.1의 `write_hooks._parse_cmdline_options`는 `shlex.split(…, posix=compat.is_posix)`를 쓰고, `_run_hook`은 `subprocess.run`을 check 없이 부른다. 따옴표가 남은 `--config`에 ruff 0.17.6은 `invalid value … for '--config'`로 exit 2를 냈다(correctness 차원 재현). 고쳐지지 않은 리비전 파일은 다음 `scripts/check.sh`에서 걸리므로 결과는 조용한 실패보다 늦게 알게 되는 것에 가깝다. 1차 COR-11은 POSIX에서는 닫혔다.

### security

| ID | 심각도 | 위치 | 위반 | 문제점 | 해결 제안 | 연관 |
|---|---|---|---|---|---|---|
| SEC-1 | minor | `compose.yaml:21`, `compose.yaml:51` | 없음 | db와 api의 포트가 호스트 주소 없이(`"${DB_PORT:-5432}:5432"`) 열려, 개발자 컴퓨터의 데이터베이스가 compose.yaml에 적힌 고정 계정(diegesis/diegesis)과 함께 같은 네트워크의 다른 기기에 열린다 (외부 기기에서 닿는지는 추정) | `"127.0.0.1:${DB_PORT:-5432}:5432"`와 `"127.0.0.1:${API_PORT:-8080}:8080"`으로 묶고, 그 문자열을 단언하는 `tests/infra/test_compose.py:150`을 함께 고친다 | |

이 형식은 step1.md 작업 2와 step4.md 작업 3이 그대로 지시한 것이라 에이전트의 위반은 아니다. 지금은 기능 테이블이 없어 노출될 데이터도 없지만, 뒤 Epic에서 책을 로컬에 적재하면 그 데이터베이스에 본문이 들어간다. 스모크의 `compose port api 8080` 조회는 127.0.0.1로 묶어도 그대로 동작한다.

### architecture

| ID | 심각도 | 위치 | 위반 | 문제점 | 해결 제안 | 연관 |
|---|---|---|---|---|---|---|
| ARC-1 | minor | `app/core/errors.py:64`, `app/core/errors.py:31`, `app/core/errors.py:198`, `tests/core/test_errors.py:253`, `tests/core/test_errors.py:311` | API §2.3, API §1 | OpenAPI의 400 스키마(`ValidationErrorResponse`)는 `detail`을 필수로 적지만, 같은 400·`VALIDATION_ERROR`로 나가는 HTTP 예외 400(본문 해석 실패, 깨진 multipart)은 `detail` 없이 응답한다. 두 테스트가 이 모순을 그대로 고정한다 | `required`를 `["code", "message"]`로 줄여 API §2.3의 "있을 때에만"과 모듈 docstring(`errors.py:4`)에 맞추고, 311줄을 고치고, HTTP 예외 400의 응답을 400 스키마와 대조하는 단언을 더한다 | COR-2, BEH-1, TST-1 |

#### ARC-1 상세

1차 처분 두 건이 같은 400에 서로 다른 모양을 정했다. ARC-1 처분은 HTTP 예외 400을 `{code, message}`로 내보내고(`errors.py:31`, `:198`), ARC-2 처분은 OpenAPI 400의 `required`에 `detail`을 넣었다(`errors.py:64`). architecture·correctness·behavioral·test-coverage 네 차원이 각자 복사본에 pydantic 본문을 받는 임시 경로를 붙이고 UTF-8이 아닌 본문을 보내 재현했다. 응답은 `400 {"code":"VALIDATION_ERROR","message":"요청 형식이 올바르지 않습니다."}`이고, 같은 operation의 문서는 `required: ["code","message","detail"]`이었다. API.md 머리말은 서버가 구현된 뒤에는 `/api/openapi.json`이 세부 형식의 기준이라고 하므로, 이 문서로 만든 프론트엔드 타입은 `detail`이 늘 있다고 본다. 지금은 본문을 받는 경로가 없어 드러나지 않는다. 브라우저가 보내는 요청에서는 거의 일어나지 않는 경로라 사람이 겪는 결과가 작아서 minor로 두었다. 첫 노출 후보는 multipart인 `POST /api/admin/bundles`(API §4.9)다.

### test coverage

| ID | 심각도 | 위치 | 위반 | 문제점 | 해결 제안 | 연관 |
|---|---|---|---|---|---|---|
| TST-1 | minor | `tests/core/test_errors.py:296-318` | API §1 (ARC-2 처분) | OpenAPI 대조 테스트는 키 집합과 `required`만 보고, `field`·`reason`의 타입과 `code`의 `const`는 보지 않는다. field를 integer로, reason을 object로, const를 `"BAD_REQUEST"`로 바꿔도 32개 모두 통과한다 | `field`·`reason`의 `type == "string"`과 `code.const == "VALIDATION_ERROR"`를 단언한다 | ARC-1 |
| TST-2 | minor | `tests/core/test_errors.py:257-269`, `tests/core/test_errors.py:272-281` | 없음 (ARC-1·COR-2 처분) | 499 분기의 `logger.error`를 지워도, 본문 없는 응답에서 `headers=error.headers`를 지워도 32개 모두 통과한다 | 499 테스트에 caplog로 ERROR 레코드와 `499`를 단언하고, 304에 `ETag`를 실은 예외를 던져 응답 헤더를 단언한다 | COR-1 |
| TST-3 | minor | `tests/test___main__.py:22-42`, `tests/test___main__.py:63-86` | CONFIGURATION §3.1 (COR-5 처분) | `log_config()`가 uvicorn의 기본 설정을 버리고 `app` 로거만 담은 dict를 돌려주게 바꿔도 4개 모두 통과한다. 그 돌연변이에서는 `uvicorn.error`의 INFO와 access 로그가 사라진다 | PROBE에서 `uvicorn.error`의 INFO와 `uvicorn.access`의 한 줄도 남겨 출력에 나오는지 단언한다 | |
| TST-4 | minor | `scripts/compose-smoke.sh:80-83`, `scripts/compose-smoke.sh:91-92`, `tests/infra/test_compose_smoke.py:444-472` | 없음 (COR-8 처분) | 잠금 테스트는 살아 있는 pid와 죽은 pid가 든 잠금만 미리 만든다. pid 파일이 아직 없는 잠금(다른 스모크가 막 mkdir한 순간)의 분기와 넘겨받은 뒤 다시 mkdir하다 실패하는 분기를 무력화해도 28개 모두 통과한다 | pid 파일 없이 잠금 폴더만 둔 상태로 스크립트를 돌려, 0이 아닌 코드·compose 호출 0개·잠금 폴더 유지를 단언한다 | COR-3 |
| TST-5 | minor | `tests/infra/test_compose_smoke.py:136-144`, `tests/infra/test_compose_smoke.py:395`, `scripts/compose-smoke.sh:183` | TC-0.5.1 (5) (BEH-10 처분) | 가짜 docker가 exec의 `--user`·`-u`를 건너뛰고 테스트 사용자 권한으로 모든 폴더를 읽어서, 스크립트에서 `--user 0`을 지워도 28개 모두 통과한다. `root/.env` 사례는 root만 읽는 폴더를 덮는 것처럼 보이지만 반증하지 못한다 | 가짜가 기록한 호출에서 (5)의 exec에 `--user 0`이 있는지 단언하거나, 사용자를 정하지 않은 exec에서는 가짜가 `root/` 아래를 읽지 못하게 한다 | |
| TST-6 | minor | `scripts/compose-smoke.sh:175`, `scripts/compose-smoke.sh:183-184`, `tests/infra/test_compose_smoke.py:358-376` | TC-0.5.1 | (4)의 `[ -n "$api_uids" ] \|\| fail`과 (5)의 exec 실패 `\|\| fail`을 각각 무력화해도 28개 모두 통과한다. 이 둘은 "확인하지 못한 것"이 통과로 읽히는 것을 막는 유일한 방어다 | parametrize에 빈 uid(`FAKE_API_UIDS=""`)와 (5)의 exec가 0이 아닌 코드로 끝나는 경우를 더해 `스모크 실패: (4)`·`(5)`를 단언한다 | |

TST-1~TST-6은 test-coverage 차원이 `git archive`로 만든 복사본에 돌연변이를 넣고 돌려 확인했다(근거: 실측). 여섯 건 모두 지금의 구현은 올바르고, 다음 변경에서 그 성질이 깨질 때 잡지 못하는 자리다. 그래서 1차 TST-3~6과 같은 minor로 둔다. TST-1은 원래 ARC-1의 모순까지 함께 올렸는데, 그 부분은 ARC-1에 합치고 스키마 내용을 단언하지 않는 부분만 남겼다.

### behavioral

| ID | 심각도 | 위치 | 위반 | 문제점 | 해결 제안 | 연관 |
|---|---|---|---|---|---|---|
| BEH-2 | minor | `app/__main__.py:12-20`, `app/__main__.py:32`, `phases/0-project-setup/step0.md:57` | step0.md 작업 4 | COR-5 처분이 TDD 가드의 개별 예외 파일인 `app/__main__.py`에 `log_config()`(uvicorn 기본 설정을 복사해 `app` 로거를 더한다)를 넣고 docstring을 그에 맞춰 고쳤다. step0의 "uvicorn을 실행하는 것 외의 로직을 넣지 마라"와 가드 예외의 전제가 지금 코드와 어긋난다 | 로그 설정의 조립을 가드 예외가 아닌 자리(예: `app/core/` 아래)로 옮겨 `__main__.py`는 그것을 부르기만 하게 하거나, 지금 형태를 받아들일지 사람이 정한다 | |

`log_config()`에는 판정하는 분기가 없어 DEVELOPMENT.md 4.2절("판정하는 로직을 넣지 않는다")은 어기지 않는다. 이번에는 RED 커밋(`138217f`)과 `tests/test___main__.py`도 있다. 남은 문제는 앞으로 이 함수를 고칠 때 TDD 가드가 테스트를 먼저 요구하지 않는다는 것이다.

## 수정 우선순위

| # | 결함 | ID | 규모 |
|---|---|---|---|
| 1 | OpenAPI의 400이 `detail`을 필수로 적어 HTTP 예외 400의 실제 응답과 어긋난다 | ARC-1, TST-1 | `errors.py`의 `required` 한 줄, `test_errors.py:311` 한 줄, 스키마 대조 단언 2~3개 |
| 2 | 코드가 던진 5xx HTTP 예외와 499 분기가 원인을 로그에 남기지 않는다 | COR-1, TST-2 | `_handle_http_exception`에 로그 몇 줄과 caplog 테스트 2개, 304 헤더 단언 1개 |
| 3 | 스모크의 잠금 넘겨받기 경합과 그 분기의 테스트 공백 | COR-3, TST-4 | `acquire_lock`의 넘겨받기 몇 줄과 테스트 1~2개 |
| 4 | 스모크의 `--user 0`과 "읽지 못함" 방어를 테스트가 지키지 않는다 | TST-5, TST-6 | 가짜 docker 몇 줄과 parametrize 2개 |
| 5 | 진입점의 로그 설정이 uvicorn 로거를 남기는지 테스트하지 않고, 그 자리가 가드 예외다 | TST-3, BEH-2 | PROBE 몇 줄. 자리를 옮기면 `app/core/` 아래 파일 하나 |
| 6 | db·api 포트가 모든 인터페이스에 열린다 | SEC-1 | `compose.yaml` 두 줄과 `test_compose.py:150` 한 줄 |
| 7 | Windows에서 리비전 훅이 따옴표 때문에 실패한다 | COR-4 | `alembic.ini` 네 줄. Windows에서 한 번 돌려 봐야 한다 |

## 이전 라운드 대조

1차 27건(major 5 · minor 22). 처분 기록(`fix-1.md`)은 고침 16 · 기각 0 · 사람 판단 11이었다. 처분의 주장을 다섯 차원이 코드와 실측으로 다시 확인했다.

| 1차 ID | 1차 심각도 | 처분 주장 | 2차 판정 | 근거 |
|---|---|---|---|---|
| COR-1 | major | db healthcheck를 TCP로 | 닫힘 | `compose.yaml:28`이 `pg_isready -h 127.0.0.1`로 본다. RED 커밋에서 빨갰고 `-h /var/run/postgresql` 돌연변이도 빨개진다. 스모크 통과 |
| ARC-1 | major | 400·500을 표의 code로, 499는 500 | 닫힘 | API.md 2.3절 표를 행마다 대조했다(`errors.py:31-35`). 실측으로 400·500·499·409·418이 주장대로 나간다. 로그 공백은 COR-1, 스키마 모순은 ARC-1(이번)로 따로 올렸다 |
| ARC-2 | major | OpenAPI의 422를 400 공통 형식으로 | 다르게 터짐 | 모든 operation에서 422·`HTTPValidationError`·`ValidationError`가 사라졌고 입력 없는 `/api/health`에는 400이 붙지 않는다(실측). 새로 실린 400 스키마의 `detail` 필수가 HTTP 예외 400과 어긋난다 → ARC-1(이번) |
| TST-1 | major | 가짜 docker·curl로 정상과 확인별 실패 | 닫힘 | 다섯 판정 줄을 하나씩 무력화하면 모두 빨개진다(실측). 남은 구멍은 TST-5·TST-6(이번) |
| TST-2 | major | 소켓·엔진 연결과 `get_settings` 호출을 기록 | 닫힘 | `asyncpg.connect`를 직접 부르고 삼키는 돌연변이, `create_async_engine`+connect를 삼키는 돌연변이 모두 빨개진다(실측) |
| COR-2 | minor | 1xx·204·205·304는 본문 없는 응답 | 닫힘 | 실제 uvicorn에서 204는 본문 없이, 304는 본문 없이 ETag를 유지한다(실측). 헤더 단언 공백은 TST-2(이번) |
| COR-4 | minor | — | 미해결(사람 판단 대기) | json_invalid의 `field`가 여전히 문자 번호다(실측). 처분이 손대지 않았다 |
| COR-5 | minor | `app` 로거에 LOG_LEVEL과 처리기 | 닫힘 | `LOG_LEVEL=WARNING`이면 uvicorn INFO가 사라지고 DEBUG이면 나온다. 처리되지 않은 예외가 `ERROR:` 서식과 스택으로 남는다(실측). 테스트 공백은 TST-3, 자리는 BEH-2(이번) |
| COR-7 | minor | — | 미해결(사람 판단 대기) | `ci.yml`이 바뀌지 않았다 |
| COR-8 | minor | mkdir 잠금, 죽은 pid는 넘겨받음 | 다르게 터짐 | 주 경로는 맞다. 넘겨받기 경로에 두 실행이 함께 잠금을 쥐는 경합이 생겼다 → COR-3·TST-4(이번) |
| COR-10 | minor | — | 미해결(사람 판단 대기) | `scripts/hooks/`가 바뀌지 않았다 |
| COR-11 | minor | `[post_write_hooks]`에 ruff | 다르게 터짐(POSIX에서는 닫힘) | 리비전을 실제로 만들어 ruff로 검사하는 테스트가 있고, 훅 하나씩을 빼면 빨개진다(실측). Windows에서는 따옴표 때문에 실패한다 → COR-4(이번, 추정) |
| SEC-1 | minor | — | 미해결(사람 판단 대기) | `scripts/hooks/bash-guard.sh`가 바뀌지 않았다 |
| ARC-3 | minor | 코드: `/docs/oauth2-redirect` 닫음 / 문서: 사람 판단 | 코드 닫힘, 문서 미해결 | `swagger_ui_oauth2_redirect_url=None`(`app/main.py:23`), 실측 404. `/api/docs`는 200. API.md는 그대로다 |
| ARC-4 | minor | — | 미해결(사람 판단 대기) | ADR.md·ARCHITECTURE.md가 바뀌지 않았다 |
| ARC-5 | minor | — | 미해결(사람 판단 대기) | ADR.md·DECISIONS.md가 바뀌지 않았다 |
| ARC-6 | minor | — | 미해결(사람 판단 대기) | DEVELOPMENT.md 4.2절이 바뀌지 않았다. 처분이 더한 `tests/infra/test_migration_template.py`의 자리도 같은 규칙의 공백이다 |
| ARC-7 | minor | GLOSSARY에 용어 5개 | 닫힘 | `docs/GLOSSARY.md`에 fixture·actionlint·빌드 맥락·Docker builder·준비 상태 확인이 있다. GLOSSARY는 결정 문서가 아니고 D-17대로 정의를 더한 것이라 D-33에 걸리지 않는다 |
| ARC-8 | minor | — | 미해결(사람 판단 대기) | CONFIGURATION.md가 바뀌지 않았다 |
| TST-3 | minor | 빈 cwd의 새 프로세스에서 import | 닫힘 | router가 import될 때 `get_settings()`를 부르는 돌연변이가 빨개진다(실측) |
| TST-4 | minor | check·smoke에 `if` 없음 | 닫힘 | compose-smoke step에 `if`를 붙이면 빨개진다(실측) |
| TST-5 | minor | check job의 `uses` 허용 목록 | 닫힘 | `ruff-action`을 더하면 빨개진다(실측) |
| TST-6 | minor | pytester로 error 1·skip 0 | 닫힘 | fixture가 `pytest.skip`하게 바꾸면 빨개진다(실측) |
| BEH-2 | minor | — | 미해결(사람 판단 대기) | MANUAL.md의 "관찰한 값"이 여전히 비어 있다 |
| BEH-5 | minor | fixture에 `monkeypatch.chdir` | 닫힘 | `tests/health/test_router.py:56` |
| BEH-9 | minor | — | 미해결(사람 판단 대기) | DEVELOPMENT.md 1절·README가 바뀌지 않았다 |
| BEH-10 | minor | `--user 0`으로 이미지 전체에서 `.env` | 닫힘 | `compose-smoke.sh:183`이 `/` 전체(최상위 proc·sys·dev 제외)를 root로 찾고 스모크가 통과한다. TC 문구를 바꾸지 않고 코드를 TC에 맞췄다. 테스트 공백은 TST-5(이번) |

요약: 고쳤다는 16건 가운데 13건이 닫혔고, 3건(ARC-2·COR-8·COR-11)은 원래 지적은 닫혔지만 고친 코드에서 새 minor가 하나씩 생겼다. 사람 판단 11건은 처분이 손대지 않아 그대로이며, 이번 표에 다시 올리지 않았다.

## 잘 된 것 (재검증 불필요)

- 처분의 RED 순서: test-coverage 차원이 RED 커밋 `138217f`를 꺼내 돌리자 26개가 기대한 이유로 실패했다(400 `BAD_REQUEST`, 500 `INTERNAL_SERVER_ERROR`, 499에서 `ValueError`, 304·204의 본문, OpenAPI의 422, `pg_isready`에 호스트 없음, 작업 폴더만 찾는 `.env`, 잠금 없음, 리비전의 ruff 위반, 서식 없는 app 로그, oauth2-redirect 200). 처분 9건마다 빨간 테스트가 있었고 `f5a3a35`에서 초록이 됐다
- 처분의 테스트 diff에 지워진 단언이 없다. 지워진 줄은 약한 구현을 강한 구현으로 바꾼 자리뿐이다
- `fix-1.md`가 적은 돌연변이 반증(TST-1~6)을 test-coverage 차원이 다시 돌려 모두 재현했다
- `_openapi_with_error_format`은 FastAPI의 문서 캐시 위에서 여러 번 불려도 결과가 같고, 경로가 바뀌어 문서가 다시 만들어져도 422를 다시 지운다. 남는 `$ref`가 없다
- `_handle_http_exception`의 분기 순서(본문 불가 → 표 → HTTPStatus 이름 → 이름 없음)가 맞고, 401·405의 헤더(`WWW-Authenticate`, `Allow`)를 유지한다
- `app/__main__.py`는 `deepcopy`로 uvicorn 기본 설정을 건드리지 않고, `disable_existing_loggers: False`라서 이미 만들어진 `app.core.errors` 로거도 설정을 받는다
- 스모크의 잠금 주 경로: 잠금을 얻지 못하면 trap을 걸기 전에 끝나 다른 스모크의 컨테이너를 건드리지 않고, 정리 뒤에 잠금을 푼다. (5)의 `os.walk`는 심볼릭 링크를 따라가지 않고 깨진 링크 `.env`도 잡는다
- 처분이 결정 문서(API·CONFIGURATION·DECISIONS·ADR·ARCHITECTURE)와 `scripts/hooks/`·`ci.yml`·`Dockerfile`·`pyproject.toml`·`uv.lock`을 고치지 않았다. `# type: ignore`·`# noqa`가 없고 검사 설정이 느슨해지지 않았다
- 처분이 더한 테스트(`tests/test___main__.py`, `tests/test_main.py`의 새 프로세스, `tests/infra/test_migration_template.py`)는 모두 빈 임시 폴더에서 돌아 개발자의 `.env`와 데이터베이스에 닿지 않는다
- 의존 방향과 설정 규칙: 거꾸로 가는 import가 없고, `app/`·`migrations/`에 `os.environ`·`getenv`가 없다. 처분은 설정값을 더하지 않았다
- 1차 "잘 된 것"(RED 순서, 반증 조건, CI 권한과 자격 증명, 이미지 구성, 스모크의 프로젝트 이름 고정)은 처분 뒤에도 그대로다

## 이 리뷰가 판정하지 않은 것

- 로그인·허용 목록·CORS, 기능 테이블, 선곡·평가 기록·묶음 적재·서명된 주소 — E0 "범위 밖". 다섯 차원이 "표면 없음"으로 확인했다
- GitHub Actions의 실제 실행 결과, 배포 환경에서의 실행, 이미지 크기와 빌드 시간, arm64 이미지가 없는 것 — `testcase.md` "이 Epic에서 판정하지 않는 것"
- MANUAL 항목(TC-0.7.6)의 실제 등록 여부 — 사람의 몫(1차 BEH-2로 기록되어 있다)
- 1차에서 사람 판단으로 넘어간 11건 — 위 "이전 라운드 대조"에 상태만 적었다
- `fix-1.md` "새로 발견한 것"의 둘째(ruff가 없는 환경에서 `alembic revision`이 실패한다) — 리비전은 개발 환경에서만 만들므로 올리지 않았다. 셋째(`tests/infra/test_migration_template.py`·`tests/test___main__.py`의 자리)는 1차 ARC-6과 같은 규칙 공백이다. 첫째(코드가 던진 HTTPException(500)의 로그)는 COR-1로 올렸다
- `index.json`의 step2·step4 summary가 처분 전의 동작을 적고 있는 것 — summary는 같은 phase의 뒤 step에만 넘어가고 이 phase는 끝났으므로 뒤 step을 오도하지 않는다. 바뀐 내용은 `fix-1.md`에 있다
- 동시에 돈 두 번째 스모크가 기다리지 않고 1로 끝나는 것 — `fix-1.md` COR-8 상세가 밝힌 맞바꿈이다
- 기각한 sub-agent 지적 3건 (근거 불일치 0 · 범위 밖 0 · 중복 3)
  - 중복: COR-2·BEH-1 → ARC-1, BEH-3 → COR-1
  - 문구를 바로잡은 것: SEC-1(인용 줄 `compose.yaml:19-20`·`55-56` → 실제 `21`·`51`), TST-1(ARC-1과 겹치는 모순 부분을 ARC-1로 옮기고 스키마 내용 단언 공백만 남김)
- 심각도를 다시 정한 것: 없음. ARC-1은 네 차원이 독립으로 재현했고 major 후보로 다시 따져 봤다. 하지만 그 경로(UTF-8이 아닌 본문, 깨진 multipart)는 브라우저가 보내는 요청에서 거의 일어나지 않고 지금은 본문을 받는 경로가 없어, 사람이 겪는 결과가 작은 문서와 코드의 어긋남(minor)으로 두었다

<!-- verdict: critical=0 major=0 minor=12 -->
