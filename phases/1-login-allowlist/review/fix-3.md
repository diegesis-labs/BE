# 1-login-allowlist 리뷰 처분 — 3차

> `review-3.md`의 결함 16건(critical 0 · major 1 · minor 15)에 대한 처분. 2026-11-26.
> 고친 것 16건, 기각 0건, 사람 판단 필요 0건. (ARC-3은 처분 뒤에 사람이 정했다.)

## 고쳤다

| ID | 심각도 | 처분 | 커밋 |
|---|---|---|---|
| TST-1 | major | `tests/infra/test_login_check_run.py`의 가짜 세계가 가짜 시계로 기록마다 다른 시각을 주고, 가짜 사람은 스크립트가 기다리기 시작해야 움직인다. 쿠키 대조·상태 코드·주소의 고장 7가지(`WIRED`)와 `me_renames_user`, 상관없는 요청이 기한을 늘리지 않는지 보는 테스트를 더했다(아래 상세) | `a54b1ac` |
| COR-1 | minor | `_check_denied`가 시작할 때 `_discard_pending`으로 큐에 남은 점검 1의 기록을 버린다. 재현: `test_login_check_run.py::TestStepsOfChecks::test_requests_left_from_the_first_window_are_not_used_by_the_second_check`(로그아웃을 두 번 누름) | `3d1a5f5` `f8ff355` |
| COR-2 | minor | 대역 서버가 요청을 받은 순번(`Exchange.received`)과 기록한 순번(`recorded`)을 한 카운터로 매기고, `BrowserWatch`는 요청을 보낸 때까지 기록된 응답만 반영한 셈과 견준다. 재현: `test_login_check.py::TestRequestsSentTogether::test_two_logouts_sent_together_are_not_reported`(진짜 대역 서버로 겹친 로그아웃 둘) | `3d1a5f5` `f8ff355` |
| COR-3 | minor | `CheckAbortedError.found`에 끝내기 전까지 모은 어긋남(끝내지 못한 시점에 이미 본 쿠키 대조 포함)을 싣고, `main`이 "끝내지 못한 점검의 중간 결과"로 보여 준 뒤 4로 끝난다. 재현: `test_login_check_run.py`의 `test_mismatches_found_before_the_abort_are_kept`(2) · `test_mismatches_found_before_the_timeout_are_kept` · `test_abort_shows_the_mismatches_found_before_it` | `3d1a5f5` `f8ff355` |
| COR-4 | minor | (추정)이었고 재현됐다. `BrowserWatch.observe`가 화면 이동과 `/api` 요청에서만 쿠키를 대조한다. 재현: `test_login_check_observe.py::TestBrowserWatch::test_request_that_is_neither_a_page_nor_api_is_not_compared` | `3d1a5f5` `f8ff355` |
| COR-5 | minor | `parse_dotenv`가 따옴표로 시작하는 값을 닫는 따옴표까지 읽고 그 뒤(주석)를 버린다. 재현: `test_login_check_judge.py::TestSettings::test_parse_dotenv_quoted_value_with_comment`(4가지 중 3가지가 RED) | `3d1a5f5` `f8ff355` |
| SEC-1 | minor | `_is_api`(경로가 `/api`로 시작) 하나를 넘기는 판정(`_handle`), 기록(`request_target`), 주소(`BrowserWatch`·`_is_page`), 출력(`_display_url`)이 함께 쓴다. 재현: `test_login_check.py::TestObservation::test_forwarded_request_is_recorded_without_query`(`/api`·`/apix`)와 `test_login_check_observe.py`의 사례 넷 | `3d1a5f5` `f8ff355` |
| ARC-1 | minor | service의 검사를 허용 목록(표준 라이브러리, `app.core.security`, `app.core.ports`)으로 바꾸고 검출기 사례에 asyncpg·starlette·uvicorn·pydantic을 더했다(`tests/auth/test_service.py`). 검사만 고친 결함이라 RED 대신 돌연변이로 확인했다 | `5dc6043` |
| ARC-4 | minor | README "결과를 읽는 법"이 따로 적던 쿠키 대조 규칙을 testcase.md의 같은 절로 넘기고, 사람이 할 일(심지 않은 쿠키가 보이면 새 게스트 창 확인)만 남겼다. E1과 testcase.md는 고치지 않았다(아래 상세) | `0bca94e` |
| TST-2 | minor | `test_login_check.py::TestRecordBeforeResponse`(5). 기록을 붙잡아 둔 동안 `_forward`·`_page`·`_plain`(411·400·502)이 응답을 보내지 않는지 본다 | `a54b1ac` |
| TST-3 | minor | `test_login_check_run.py::TestWithRealStandIn`(2). 진짜 `FrontendStandIn`과 HTTP로 띄운 가짜 백엔드, 별도 스레드의 사람으로 `run_checks`를 끝까지 돌린다. `test_exchange_that_arrives_after_the_checks_is_ignored`는 `asyncio.run`이 끝난 뒤(루프가 닫힌 뒤)에 기록을 넘긴다 | `a54b1ac` |
| TST-4 | minor | `test_login_check_precheck.py::test_read_state_reads_sessions_of_the_two_accounts_and_counts_all`(integration). A와 다른 사람의 행을 넣고 `sessions_for(A)`(token_hash·expires_at·created_at)와 `session_total`을 단언한다 | `a54b1ac` |
| TST-5 | minor | `test_login_check.py::TestRequestLinesAreNotPrinted`. capfd로 화면·411·400·502에서 쿼리의 code·state가 찍히지 않는지 본다 | `a54b1ac` |
| BEH-1 | minor | `_parser()`의 description과 epilog를 ADR-031과 모듈 독스트링에 맞췄다(브라우저를 열거나 조종하지 않음, 게스트 창, 종료 코드 4의 뜻). 재현: `test_login_check_judge.py::TestSettings::test_help_describes_the_check_of_adr_031` | `3d1a5f5` `f8ff355` |
| BEH-2 | minor | 리포트의 두 선택지 가운데 "사람이 대조한다고 적는다"를 골랐다(아래 상세). `render_report`가 `DISPLAY_NAME_NOTE`를 붙이고, 첫 줄을 "스크립트가 판정하는 칸은 모든 시점에서 표와 같다"로 바꿨다. README·MANUAL·`--help`·모듈 독스트링에도 적었다. 재현: `test_report_says_display_name_is_compared_by_person`과 두 `test_all_match_exits_0` | `3d1a5f5` `f8ff355` `0bca94e` |
| ARC-3 | minor | 사람(백엔드 담당자)이 B를 골랐다(2026-11-26). 기능 폴더 안에서만 쓰는 저장소 포트의 구현체는 그 폴더의 라우터가 FastAPI 의존성으로 넣는다고 ADR-033으로 기록하고, ARCHITECTURE 8절에 포트의 종류마다 구현체를 넣는 곳을 표로 적었다. ADR-029는 바꾸지 않았다(공통 층의 포트에 관한 결정은 그대로다). 코드는 그대로다 | `e655e93` |

### TST-1 상세

- **가짜 시계**: 사람이 안내 하나를 따르는 데 3분, 브라우저의 요청 하나에 1초가 흐른다. 표의 "1분 안"보다 길어서, 로그인 결과 처리가 아닌 요청의 시각(로그인 전의 `GET /api/me`)을 넘기면 created_at·expires_at이 어긋난다.
- **안내를 읽고 나서 움직이는 사람**: `_ask`는 사람의 행동을 이벤트 루프에 예약만 한다. 스크립트가 기다리기 시작해야 사람이 움직이고, 그 전에 다음 안내가 나오면 앞의 안내는 따르지 못한다. 그래서 점검 2에서 결과 처리와 화면을 기다리지 않으면 표와 다른 주소가 찍힌다. `EXPECTED_LOG`는 안내(`ask`), 사람의 행동(`do`), 읽기(`read`)의 순서를 본다.
- **고장**: 리포트의 다섯 가지(로그아웃 뒤 지운 쿠키를 다시 붙임 `browser_keeps_deleted_session`, 점검 2의 새 창에 쿠키가 남음 `stale_cookie_in_denied_window`, 로그인하지 않은 me가 200 `anonymous_me_is_200`, 로그아웃이 403 `logout_is_403`, 점검 2의 결과 처리 중 쿠키 어긋남 `denied_window_drops_state`)를 더했다. 이미 있던 `stale_cookie_in_browser`, `browser_drops_session`도 `WIRED`로 옮겨 보고되는 전부를 순서까지 단언한다. 그래서 여섯 시점의 쿠키 대조 자리마다 그것을 빼면 빨개지는 고장이 있다.
- **기준 스냅숏**: `me_renames_user`(me가 display_name을 바꿈)는 로그아웃 후의 기준이 로그인 후로 바뀌면 하나 더 보고된다.
- **기한**: 리포트의 "기한을 단계마다 새로 잡게 했다"는, 상관없는 기록이 올 때마다 기한을 새로 잡는 변이로 읽었다. `test_other_requests_do_not_extend_the_wait`는 기한(0.3초)보다 짧은 간격(0.1초)으로 상관없는 요청 30개를 보내고, 그것이 끊기기 전에 4로 끝나는지 본다.

### COR-1 상세

리포트의 두 제안 가운데 "큐를 비운다"를 골랐다. 비우는 것은 점검 2가 시작할 때 이미 대역 서버를 지난 기록이다. 그때 아직 처리 중인 점검 1의 요청이나, 사람이 점검 2의 안내를 본 뒤 옛 창에서 누른 버튼은 여전히 점검 2의 대상이 될 수 있다. 다른 제안(안내 전에 기록된 것을 쓰지 않음)도 기록 시각은 응답 직전이라 처리 중인 요청은 막지 못한다.

### COR-2 상세

순번이 없는 기록(대역 서버를 거치지 않고 만든 것)은 기록된 차례대로 보낸 것으로 본다. 기존 단위 테스트가 만드는 기록이 여기에 해당한다. 대역 서버가 응답을 기록한 뒤 브라우저에 보내기 전의 짧은 틈에 같은 창이 보낸 요청은, 그 응답을 받기 전인데도 반영한 셈과 견준다. 이 틈은 처분 전에도 있었다.

### COR-4 상세

리포트의 두 제안 가운데 "화면 이동과 `/api` 요청으로 좁힌다"를 골랐다. 다른 창의 탭이 화면을 옮기거나 `/api`를 부르면 여전히 대조된다. 다른 제안(점검마다 다른 표식)은 로그인 링크와 Google의 리디렉션 같은 화면 이동에 표식을 붙이려면 쿠키나 쿼리를 바꿔야 해서 고르지 않았다. 실제 Vite 탭으로는 확인하지 않았다. 다른 탭의 요청과 같은 꼴(화면 이동이 아닌 `GET /`에 평소 창의 쿠키)의 기록으로 재현했다.

### ARC-4 상세

리포트가 짚은 세 곳 가운데 README만 고쳤다. E1 T1.7.2는 만들 것을, testcase.md는 합격 기준을 적는 자리라 겹침이 어느 정도 생긴다. 리포트도 이 점을 들어 (추정)으로 두었고, 가장 분명한 중복으로 README를 꼽았다.

### BEH-2 상세

리포트의 선택지는 A(A의 Google 이름을 인자로 받아 판정)와 B(결과·MANUAL·README에 사람이 대조한다고 적음)였다. B를 골랐다. A는 E1 T1.7.2가 정한 명령의 인자("점검할 두 계정의 이메일은 명령의 인자로 받습니다")를 넘어서는 인자를 더한다. B는 그 규격을 그대로 두고, 결과가 판정하지 않은 칸을 판정했다고 말하지 않게 한다. MANUAL은 안내 문장 하나만 고쳤고, 두 표와 체크 항목은 건드리지 않았다.

## 기각했다

없음

## 사람 판단 필요

없음

## 커밋

`5dc6043` 테스트(ARC-1) · `a54b1ac` 테스트(TST-1 · TST-2 · TST-3 · TST-4 · TST-5) · `3d1a5f5` RED(COR-1 · COR-2 · COR-3 · COR-4 · COR-5 · SEC-1 · BEH-1 · BEH-2) · `f8ff355` 코드(같은 8건) · `0bca94e` 문서(ARC-4 · BEH-2) · `e655e93` 문서(ARC-3, 사람이 정함)

## 검증

`scripts/check.sh --all`, Docker 켜짐(통합 테스트가 testcontainers의 PostgreSQL에서 돎).

| 명령 | 결과 |
|---|---|
| `ruff check` | exit 0 — 위반 0 |
| `ruff format --check` | exit 0 — 102파일 서식 맞음 |
| `pyright` | exit 0 — 오류 0, 경고 0 |
| `pytest` | exit 0 — 1188개 통과 (처분 전 1145개). 건너뜀 0, xfail 0. 경고 1(Starlette TestClient의 httpx 폐기 예고, 처분 전과 같음) |

- RED의 근거(`3d1a5f5`): 20개가 실패했다. 실패는 모두 결함 그대로의 동작에 걸린 단언이었다.
  - COR-1: 읽기가 `do:reopen` 앞에 왔다. 새 창을 열기 전에 점검 2의 "로그인 전"을 읽었다.
  - COR-2: 앞에 보낸 로그아웃이 "이번 점검에서 심지 않은 diegesis_session"으로 보고됐다.
  - COR-3: `main`의 출력에 앞서 모은 어긋남이 없었다. `found`를 직접 보는 세 테스트는 속성이 없어 AttributeError였다.
  - COR-4: 화면 이동이 아닌 `GET /`의 쿠키가 "값이 다르다"로 보고됐다.
  - COR-5: 따옴표를 벗기지 못한 값이 나왔다.
  - SEC-1: 기록과 출력에 `code`가 남았고, `/apix`가 화면 주소가 됐다.
  - BEH-1: `--help`에 ADR-031이 없었다.
  - BEH-2: 결과에 display_name의 안내가 없었고, "모든 시점의 상태가" 문구를 썼다.
- 돌연변이 반증. 하나씩 넣고 해당 테스트를 돌린 뒤, 복사해 둔 원본으로 되돌렸다. 되돌린 뒤 `git diff`가 비어 있음을 확인했다.
  - ARC-1: `app/auth/service.py`에 `import asyncpg`, `import starlette`, `import uvicorn`, `from pydantic import BaseModel`, `from app.core.config import get_settings`를 하나씩 넣었다. 다섯 번 모두 `test_service_imports_no_framework_database_http_or_adapter`가 빨갰다.
  - TST-1: 리포트가 실측한 진행 층 변이를 넣었다. 모두 빨갰다.
    - `take_problems()` 빼기: 6자리 각각에서 1·2·1·3·1·2개.
    - `logout_status=204`: 1개.
    - me를 401로 고정: 401을 기대하는 세 자리 각각에서 1·2·1개.
    - `login_at=me.at`: 19개.
    - 로그아웃 후의 기준을 `after_login`으로: 1개.
    - 점검 2에서 결과 처리와 화면을 기다리지 않음: 19개.
    - 기한을 기록마다 새로 잡음: 1개.
  - TST-3: `call_soon_threadsafe` 대신 대역 서버의 스레드에서 `put_nowait`를 바로 불렀다. 2개가 빨갰다. 기다리는 시간(5초)이 지나 4로 끝났다. `contextlib.suppress(RuntimeError)`를 뺀 변이도 넣었고 1개가 빨갰다.
  - TST-2: `_record`를 응답 뒤로 옮겼다. `_forward`에서 1개, `_page`에서 1개, `_plain`에서 3개(411·400·502)가 빨갰다. `_forward` 변이에서는 네 번 가운데 한 번 `test_requests_are_recorded_in_order`도 함께 빨갰다. 변이가 기록 순서를 흔들었기 때문이다. 원래 코드에서는 이 파일을 세 번 연속 돌려 모두 통과했다.
  - TST-4: `session_total=0` 고정, 전체 대신 두 계정의 행만 셈, sessions 비움을 넣었다. 셋 다 1개가 빨갰다.
  - TST-5: `log_message` 재정의를 지웠다. 1개가 빨갰다.
- 실행으로 확인한 것: `uv run python scripts/login_check.py --help`의 출력을 읽어 description과 종료 코드가 ADR-031과 같은 것을 확인했다. 실제 Google 계정으로 하는 MANUAL 점검(TC-1.7.3, TC-1.7.4)은 돌리지 않았다. 사람이 하는 일이다.

## 새로 발견한 것

- `browser_keeps_deleted_session`처럼 브라우저가 로그아웃의 지우는 `Set-Cookie`를 무시한 경우에도, 어긋남의 문장이 "이번 점검에서 심지 않은 … 쿠키를 붙였다. 새 게스트 창에서 시작했는지 확인한다"로 나온다. 원인이 새 창이 아닌데도 사람을 새 창 확인으로 안내한다. 고치지 않았다.

<!-- disposition: fixed=16 rejected=0 needs-human=0 -->
