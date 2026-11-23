# 0-project-setup 리뷰 처분 — 2차

> `review-2.md`의 결함 12건(critical 0 · major 0 · minor 12)에 대한 처분. 2026-11-23.
> 고친 것 12건, 기각 0건, 사람 판단 필요 0건.

## 고쳤다

| ID | 심각도 | 처분 | 커밋 |
|---|---|---|---|
| COR-1 | minor | 5xx로 응답하는 HTTP 예외와 이름 없는 상태(499)를 `logger.error`로 method·path·상태·detail과 함께, `exc_info`로 스택을 붙여 남긴다. 4xx는 남기지 않는다. 재현: `tests/core/test_errors.py::test_http_exception_answered_as_server_error_is_logged_with_its_stack` | `072bdd9` → `09fec4e` |
| COR-3 | minor | 낡은 잠금은 넘겨받기 잠금(`diegesis-smoke.lock.takeover`, mkdir)을 쥔 쪽만, 그 안에서 pid를 다시 읽어 처음 본 죽은 pid와 같을 때만 넘겨받는다(아래 상세). 재현: `tests/infra/test_compose_smoke.py`의 `test_script_does_not_take_over_a_lock_another_smoke_just_took_over`, `test_script_refuses_while_another_smoke_is_taking_over_the_lock`, `test_script_releases_takeover_lock_when_it_cannot_remove_the_stale_lock` | `072bdd9` → `09fec4e`, `2625a00` → `5f83f3d` |
| COR-4 | minor | 리비전 훅에 `cwd = %(here)s`를 주고 `--config pyproject.toml`을 따옴표 없이 넘긴다. 재현: `tests/infra/test_migration_template.py::test_new_revision_passes_ruff[windows-split-*]` (`compat.is_posix=False`로 Windows의 나누기를 흉내 냄) | `072bdd9` → `09fec4e`, `95bcb0c` |
| SEC-1 | minor | db와 api의 포트를 `127.0.0.1:${DB_PORT:-5432}:5432`, `127.0.0.1:${API_PORT:-8080}:8080`으로 묶는다. 재현: `tests/infra/test_compose.py`의 `test_api_publishes_port_8080_through_api_port_on_loopback_only`, `test_db_publishes_port_5432_through_db_port_on_loopback_only` | `072bdd9` → `09fec4e` |
| ARC-1 | minor | OpenAPI 400 스키마의 `required`를 `["code", "message"]`로 줄였다. 재현: `tests/core/test_errors.py::test_body_parse_failure_matches_documented_400`(UTF-8이 아닌 본문의 실제 응답을 같은 operation의 문서와 대조) | `072bdd9` → `09fec4e` |
| TST-1 | minor | 400 스키마의 `field`·`reason`이 `type: string`이고 `code.const`가 `VALIDATION_ERROR`인지 단언한다. `test_openapi_documents_validation_failure_as_400_in_error_format` | `a87490d` |
| TST-2 | minor | 499 테스트가 caplog로 ERROR 기록 하나와 `499`·경로를 단언하고, 304에 ETag를 실어 응답 헤더를 단언한다(`test_http_exception_without_body_keeps_its_headers`) | `a87490d` |
| TST-3 | minor | PROBE가 `uvicorn.error`의 INFO와 `uvicorn.access` 한 줄을 남기고 출력에 나오는지 단언한다. `tests/test___main__.py::test_uvicorn_logs_are_kept` | `a87490d` |
| TST-4 | minor | pid 파일 없는 잠금(`test_script_refuses_a_lock_without_pid_file`)과 넘겨받는 도중 다른 스모크가 잠금을 얻는 경우(`test_script_gives_up_when_another_smoke_gets_the_lock_during_takeover`, 가짜 rmdir)를 확인한다 | `a87490d` |
| TST-5 | minor | 가짜 docker가 기록한 (5)의 exec 호출에 `--user 0`(또는 root)이 있는지 단언한다(`test_env_file_search_runs_as_root`). 아래 상세 | `a87490d` |
| TST-6 | minor | parametrize에 `4-uid-not-read`(`FAKE_API_UIDS=""`)와 `5-env-search-failed`(가짜 exec가 1로 끝남)를 더해 `스모크 실패: (4)`·`(5)`를 단언한다 | `a87490d` |
| BEH-2 | minor | `log_config()`를 `app/core/log_config.py`로 옮기고 진입점은 그것을 부르기만 한다. 재현: `tests/test___main__.py::test_entrypoint_only_runs_uvicorn`(진입점에 정의가 없는지). 새 자리의 테스트는 `tests/core/test_log_config.py` | `072bdd9` → `09fec4e` |

### COR-1 상세

리포트의 제안대로 상태가 500 이상이거나 이름이 없는 상태에서 로그를 남긴다. `exc_info`에는 처리기가 받은 HTTP 예외를 넘기므로 던진 자리의 스택과 `raise ... from`의 원인 예외가 함께 남는다. detail은 응답에는 여전히 담지 않고 로그에만 남긴다. 4xx를 ERROR로 남기지 않는다는 경계 테스트(`test_http_exception_answered_as_client_error_is_not_logged_as_error`)는 RED 커밋에서도 초록이었다. 고치기 전에도 4xx는 로그를 남기지 않았고, 이 테스트는 "모든 상태를 남긴다"는 틀린 수정을 막으려고 둔 것이다. TST-2의 499 로그 단언은 이 결함과 같은 자리라서, 499 테스트에는 ERROR 기록만 단언하고 스택과 detail은 COR-1의 테스트가 본다.

### COR-3 상세

리포트가 제안한 두 방법은 둘 다 창이 남는다. 첫째, `mv "$LOCK_DIR" "$LOCK_DIR.stale.$$"`처럼 이름을 바꾸는 방법에서는 같은 낡은 잠금을 본 B가 A가 넘겨받아 새로 만든 잠금을 통째로 옮길 수 있다. 그러면 A는 잠금 폴더가 없는 채로 돌고, 셋째 스모크가 들어온다. 이미 있는 폴더 위로는 `mv`로 되돌릴 수도 없다. 둘째, mkdir한 뒤 pid를 다시 읽는 방법에서는 A가 확인을 마친 뒤에 B가 A의 pid 파일을 지울 수 있다. 그래서 넘겨받기 자체를 두 번째 mkdir 잠금으로 직렬화했다.

넘겨받기 잠금 안에서 pid를 다시 읽어 처음 본 죽은 pid와 다르면(누가 먼저 넘겨받았거나 비었으면) 멈춘다. 같으면 지우고 mkdir한다. 낡은 잠금을 지우지 못하거나(권한, 다른 파일) mkdir이 실패하면(그 사이 다른 스모크가 주 경로로 잠금을 얻었으면) 넘겨받기 잠금을 풀고 멈춘다. 주 잠금을 지우는 길은 쥔 스모크의 정리와 넘겨받기 잠금 안의 넘겨받기 둘뿐이다. 처음 고친 `09fec4e`에서는 잠금의 pid 파일을 지우는 `rm -f`가 실패하면 `set -e`로 끝나 넘겨받기 잠금이 남았다. 그 잠금은 이 수정이 새로 만든 것이라 COR-3 안에서 닫았다(RED `2625a00`, 가짜 rm이 권한 오류를 냄 → `5f83f3d`). 맞바꾼 것이 하나 있다. 넘겨받기의 몇 줄 사이에 kill -9로 끝나면 넘겨받기 잠금이 남고, 그 뒤 낡은 잠금을 만난 스모크는 그 폴더를 지우라는 메시지와 함께 멈춘다. 주 경로(낡은 잠금이 없을 때)는 넘겨받기 잠금을 보지 않는다.

### COR-4 상세

alembic 1.20.1의 `_run_hook`은 `options.get("cwd")`를 `subprocess.run(cwd=…)`에 넘기고, 리비전 파일의 경로는 options를 나눈 뒤에 끼워 넣는다. 그래서 레포 경로나 리비전 경로에 공백이 있어도 갈라지지 않는다. 실제 Windows에서는 돌려 보지 못했다. 테스트는 `alembic.util.compat.is_posix`를 False로 바꿔 alembic이 Windows에서 쓰는 `shlex.split(posix=False)`를 흉내 낸다. 고치기 전에는 그 조건에서 ruff가 `invalid value '"…/pyproject.toml"' for '--config'`로 exit 2를 냈고(직접 재현), 리비전 파일이 고쳐지지 않은 채 남았다.

pytest가 레포 최상위에서 돌기 때문에, 처음 쓴 테스트는 `cwd`를 빼도 상대 경로가 찾아져 초록이었다. 그래서 `95bcb0c`에서 레포 밖의 작업 경로로 옮긴 뒤 리비전을 만들게 했고, `cwd` 두 줄을 지우면 4개가 빨개지는 것을 확인했다.

### SEC-1 상세

step1.md 작업 2와 step4.md 작업 3이 호스트 주소 없는 형식(`${DB_PORT:-5432}:5432`)을 지시했다. 그 지시의 이유는 포트를 바꿀 수 있게 하는 것이었고, 그것은 그대로 지켜진다. 닫힌 step 파일은 고치지 않았다. README의 "서버는 8080 포트로, 데이터베이스는 5432 포트로 띄웁니다"는 이 컴퓨터에서 접속하는 경우 그대로 맞다. 같은 네트워크의 다른 기기에서 접속하는 방법은 원래 문서에 없었고, 이번에 막혔다. `docker compose config`에서 두 포트의 `host_ip`가 `127.0.0.1`이고, 스모크의 `compose port api 8080` 조회와 127.0.0.1로의 요청도 그대로 통과했다.

### ARC-1 상세

리포트의 진술은 맞지만 재현 조건이 하나 다르다. "UTF-8이 아닌 본문"이 모두 HTTP 예외 400이 되지는 않는다. `b"\xff\xfe"`는 `json.loads`가 UTF-16으로 읽고 `JSONDecodeError`를 내므로 요청 검증 실패(detail 있음)가 된다. `b'{"price": "\xff"}'`나 `b"\x80"`처럼 UTF-8 디코딩에서 실패하는 본문만 FastAPI 0.165.0의 `HTTPException(400, "There was an error parsing the body")`가 되어 detail 없이 나간다. 테스트는 이 경우를 쓴다.

`test_openapi_documents_validation_failure_as_400_in_error_format`의 `required` 단언을 `{"code", "message", "detail"}`에서 `{"code", "message"}`로 바꿨다. 이것은 단언을 약하게 고친 것이 아니다. 그 단언은 API.md 2.3절("detail은 추가 정보가 있을 때에만")과 실제 HTTP 예외 400의 응답에 어긋나는 값을 고정하고 있었다. 여전히 정확히 같은지를 단언하고, 실제 응답을 문서와 대조하는 테스트를 새로 더했다.

### TST-5 상세

리포트의 둘째 제안(사용자를 정하지 않은 exec에서는 가짜가 `root/`를 읽지 못하게 함)은 권한을 chmod로 흉내 내야 한다. 그러면 테스트가 root로 돌 때 반증하지 못하므로 첫째 제안을 택했다. 이를 위해 가짜 docker의 호출 기록을 고쳤다. 원래는 한 줄에 호출 하나를 적는데, 여러 줄인 (5)의 파이썬 코드 인자가 기록을 여러 줄로 쪼개 (5)의 호출을 찾을 수 없었다. 그래서 인자 안의 줄바꿈을 `\n`으로 적게 했다. 기존 단언은 바꾸지 않았다.

### BEH-2 상세

step0.md 작업 4("uvicorn을 실행하는 것 외의 로직을 넣지 마라")와 DEVELOPMENT.md 4.2절(가드 예외 파일의 "하는 일")이 맞는 형태를 정하고 있어서, 사람 판단 없이 코드를 문서에 맞췄다. `app/core/log_config.py`는 가드 예외가 아니므로 테스트(`tests/core/test_log_config.py`)를 먼저 썼다. RED 커밋에는 `NotImplementedError`를 내는 빈 껍데기를 두었다. 결함 자체의 재현은 `test_entrypoint_only_runs_uvicorn`이 `['log_config']`로 실패한 것이다. 진입점의 PROBE 테스트(`tests/test___main__.py`)는 그대로 진입점이 uvicorn에 넘기는 설정을 본다. ARCHITECTURE.md 8절은 `core/`를 "설정, DB 연결, … 에러 형식, 포트 정의"로 설명하며, 파일 목록을 정하지는 않는다.

## 기각했다

없음

## 사람 판단 필요

없음

## 커밋

`a87490d` 테스트 강화(TST-1 · TST-2 · TST-3 · TST-4 · TST-5 · TST-6) · `072bdd9` RED(COR-1 · COR-3 · COR-4 · SEC-1 · ARC-1 · BEH-2) · `09fec4e` 코드(같은 6건) · `95bcb0c` 테스트(COR-4의 cwd 반증) · `2625a00` RED(COR-3 넘겨받기 잠금의 실패 경로) · `5f83f3d` 코드(같은 것)

테스트 결함 커밋 `a87490d`는 고치기 전 코드에서도 초록이다. 그래서 RED가 아니고, 아래 돌연변이 반증이 증거다. RED 커밋 `072bdd9`에서는 19개가 기대한 이유로 실패했다. 내역은 COR-1 6 · ARC-1 2 · SEC-1 2 · COR-4 2 · COR-3 2 · BEH-2 5이고, 4xx 경계 테스트 6개는 초록이었다. `2625a00`에서는 1개가 실패했다. `rm`의 권한 오류로 메시지 없이 끝나고 넘겨받기 잠금이 남았다.

## 검증

| 명령 | 결과 |
|---|---|
| `ruff check` | exit 0 |
| `ruff format --check` | exit 0 — 52파일 서식 일치 |
| `pyright` | exit 0 — 오류 0 |
| `pytest` | exit 0 — 300개 통과 (처분 전 268개), 경고 1(StarletteDeprecationWarning, 처분 전과 같다) |
| `scripts/compose-smoke.sh` | exit 0 — 다섯 확인 통과(Docker 28.3.2, vector 0.8.7, api Uid 10001×4). 마지막 커밋 `5f83f3d` 뒤에 다시 돌렸다 |

- 돌연변이 반증 (고치기 전 코드, `a87490d`의 테스트):
  - TST-1: `field`를 `integer`로, `reason`을 `object`로, `const`를 `BAD_REQUEST`로 바꾸자 각각 빨개졌다.
  - TST-2: 499 분기의 `logger.error`를 지우자 2개, 본문 없는 응답의 `headers=error.headers`를 지우자 2개가 빨개졌다.
  - TST-3: `log_config()`가 `app` 로거와 `default` 처리기만 담은 dict를 돌려주게 하자 `test_uvicorn_logs_are_kept`가 빨개졌다.
  - TST-4: 빈 pid 분기를 지우자 `test_script_refuses_a_lock_without_pid_file`이, 다시 mkdir하는 줄의 `|| fail`을 `|| true`로 바꾸자 `test_script_gives_up_when_another_smoke_gets_the_lock_during_takeover`가 빨개졌다.
  - TST-5: `--user 0`을 지우자 `test_env_file_search_runs_as_root`가 빨개졌다.
  - TST-6: `[ -n "$api_uids" ] || fail`을 지우자 `4-uid-not-read`가, (5)의 `|| fail`을 `|| true`로 바꾸자 `5-env-search-failed`가 빨개졌다.
- 돌연변이 반증 (고친 뒤 코드):
  - COR-1: 이름 없는 상태의 로그를 지우자, 5xx 로그를 지우자, `exc_info`를 빼자, 조건을 `>= 400`으로 넓히자 각각 빨개졌다.
  - BEH-2·TST-3: 새 자리의 `log_config()`가 uvicorn 설정을 버리게 하자 `test_uvicorn_logs_are_kept`와 `test_uvicorn_logging_config_is_kept`가 빨개졌다. `deepcopy`를 빼자 `test_uvicorn_default_is_not_modified`가 빨개졌다.
  - TST-4: 바뀐 `acquire_lock`에서 빈 pid 분기를 지우자, 다시 mkdir의 실패를 무시하자 각각 빨개졌다.
  - COR-3: 넘겨받기 잠금 안의 pid 재확인을 끄자, 넘겨받기 잠금의 실패를 무시하자, 넘겨받은 뒤 넘겨받기 잠금을 풀지 않자 각각 빨개졌다. `5f83f3d` 뒤에는 `rm -f`의 `|| true`를 빼자, 낡은 잠금을 지우지 못한 분기에서 넘겨받기 잠금을 풀지 않자 각각 빨개졌다.
  - COR-4: `ruff_check.cwd`·`ruff_format.cwd`를 지우자 4개가 빨개졌다.
- 실행으로 확인한 것:
  - COR-3: 죽은 pid가 든 잠금을 만들어 두고 실제 스모크 두 개를 동시에 띄웠다. 하나는 `끝난 스모크(PID …)가 남긴 잠금을 넘겨받는다` 뒤 exit 0으로 통과했다. 다른 하나는 `다른 스모크가 잠금(…)을 넘겨받고 있다`로 exit 1이 되어 compose를 부르지 않았다. 끝난 뒤 잠금 폴더와 넘겨받기 잠금 폴더는 남지 않았다.
  - SEC-1: `docker compose config`에서 db `('127.0.0.1', '5432', 5432)`, api `('127.0.0.1', '8080', 8080)`을 확인했고, 스모크가 통과했다.
  - ARC-1: 고치기 전 `{"price": "\xff"}` 본문의 응답이 `400 {"code":"VALIDATION_ERROR","message":"요청 형식이 올바르지 않습니다."}`이고 문서의 `required`가 `["code","message","detail"]`인 것을 임시 스크립트로 재현했다.
  - COR-4: `shlex.split(…, posix=False)`로 나눈 options를 ruff 0.17.6에 넘겨 exit 2를 재현했다. 실제 Windows에서는 확인하지 못했다.

## 새로 발견한 것

- 스모크의 `kill -0`은 다른 사용자의 프로세스에도 실패하므로(EPERM), 같은 Linux 기계에서 다른 사용자가 쥔 잠금을 죽은 것으로 본다. 그 잠금 폴더는 다른 사용자의 것이라 지우지 못한다. 그래서 `5f83f3d` 뒤로는 "잠금을 지우지 못했다"로 멈추고 잠금을 빼앗지 않는다. 다만 살아 있는 잠금을 낡은 것으로 안내한다. macOS의 `TMPDIR`은 사용자마다 따로이고 CI는 사용자가 하나라서 이 레포의 쓰임에서는 생기지 않는다. 고치지 않았다(처분 전부터 있던 판정이다).

<!-- disposition: fixed=12 rejected=0 needs-human=0 -->
