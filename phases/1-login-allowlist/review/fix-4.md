# 1-login-allowlist 리뷰 처분 — 4차

> `review-4.md`의 결함 10건(critical 0 · major 0 · minor 10)에 대한 처분. 2026-11-26.
> 고친 것 9건, 기각 0건, 사람 판단 필요 1건.

## 고쳤다

| ID | 심각도 | 처분 | 커밋 |
|---|---|---|---|
| COR-1 | minor | 점검 2의 "로그인 전"은 새 창의 화면 이동을 먼저 기다린 뒤에 온 `GET /api/me`로 판정한다(아래 상세). 재현: `test_login_check_run.py::TestStepsOfChecks::test_requests_of_the_first_window_after_the_second_check_starts_are_not_its[late_second_logout_click]` | `4fadff5` `a915c80` |
| COR-2 | minor | `run_checks`가 점검 2를 시작할 때 `FrontendStandIn.tick()`으로 순번을 받고, `_wait_for`는 그보다 먼저 받은 요청을 셈에도 대상에도 넣지 않는다(`BrowserWatch.belongs`). 재현: 같은 테스트의 `[logouts_cross_the_checks]`와 `test_login_check.py::TestObservation::test_tick_is_after_requests_received_before_it` | `4fadff5` `a915c80` |
| BEH-1 | minor | `CookieJar`가 지운 쿠키를 기억하고, 그 쿠키가 같은 값으로 다시 붙으면 `kept`로 보고해 지우는 `Set-Cookie`의 속성을 확인하라고 안내한다. `WIRED`와 README도 고쳤다. 재현: `test_login_check_observe.py::TestCookieJar`의 새 테스트 다섯 개 | `4fadff5` `a915c80` `a95a155` |
| TST-1 | minor | `test_login_check.py::TestRequestsSentTogether::test_two_logouts_sent_together_are_not_reported`를 두 순서로 나누었다. 반대 순서(먼저 보낸 것이 먼저 기록되고, 뒤의 것은 그 전에 이미 받음)를 더하고, 두 순번의 관계로 순서를 확인한다 | `6cc5d18` |
| TST-2 | minor | 가짜 세계가 몇 번째 안내에서 멈출지(`idle_at`) 정하고, Google이 로그인을 막는 경우(`google_blocks_login`)를 더했다. 점검 1과 점검 2의 시간 초과, 점검 2의 DB 오류에서 그 시점의 쿠키 어긋남이 `found`에 남는지 본다 | `6cc5d18` |
| TST-3 | minor | 가짜 사람이 Google 화면에서 계정을 고르는 데 2분(`GOOGLE_GAP`)이 흐른다. 로그인 시작의 시각을 `login_at`으로 넘기면 created_at과 expires_at이 어긋난다 | `6cc5d18` |
| TST-4 | minor | `test_login_check_judge.py::TestNoSecretsInOutput::test_render_snapshot_shows_display_name_for_the_person`. "로그인 후"의 A의 users 줄과 "로그아웃 전"의 `GET /api/me` 줄에 `display_name`과 그 값(`독자 A`)이 있는지 본다 | `6cc5d18` |
| TST-5 | minor | `world` 픽스처가 `LOGIN_WAIT_SECONDS`를 2초로 줄인다. 배선이 고장 나도 테스트가 300초씩 멈추지 않고 2초 뒤에 빨개진다 | `aa0b343` |
| ARC-1 | minor | service의 검사가 표준 라이브러리도 이름을 적은 것(`SERVICE_STANDARD_LIBRARY`)만 허용하고, `builtins.__import__`와 `importlib.__import__`를 문자열로 가져오는 함수로 센다. 검출기 사례에 `sqlite3`·`urllib.request`·`http.client`·`socket`·`builtins.__import__`·`importlib.__import__`를 더했다 | `8d8f1c7` |

### COR-1 · COR-2 상세

- 3차 COR-1의 `_discard_pending`은 그 순간 큐에 든 것만 버렸다. 이것을 없애고 두 가지로 바꿨다.
  - 순번의 경계(COR-2): 점검 2를 시작할 때 대역 서버의 카운터에서 순번 하나를 받는다. `received`가 그보다 작은 요청은 점검 1의 창이 보낸 것이다. 응답이 늦게 끝나 점검 2가 시작한 뒤에 기록되어도 셈과 대상에서 뺀다. 큐에 남아 있던 것도 모두 여기에 걸리므로 `_discard_pending`은 필요 없다.
  - 화면 이동 먼저(COR-1): 경계 뒤에 온 점검 1의 창의 요청(사람의 간격으로 늦게 누른 [로그아웃])은 화면 이동이 아니다. 그래서 점검 2는 새 창이 화면을 연 뒤의 `GET /api/me`로 "로그인 전"을 판정한다. 그 사이의 요청은 셈에는 넣는다.
- 재현을 위해 가짜 대역 서버도 진짜처럼 요청을 받을 때와 기록할 때 순번을 매기게 했다(`FakeWorld.tick`, `_send`). 처분 전의 실패는 다음과 같았다.
  - `late_second_logout_click`: 두 번째 누름은 점검 2가 기다리기 시작한 뒤에 오고, 사람은 0.05초 뒤에 새 창을 연다. 처분 전에는 로그에서 `read`가 `do:reopen`보다 앞에 왔다. 새 창을 열기 전에 "로그인 전"을 읽은 것이다.
  - `logouts_cross_the_checks`: 겹쳐 누른 두 로그아웃 가운데 먼저 보낸 것이 점검 2가 시작한 뒤에 기록된다. 처분 전에는 "[점검 2 · 로그인 전] … POST /api/auth/logout에 이번 점검에서 심지 않은 diegesis_session 쿠키를 붙였다"가 나왔다.
- `test_tick_is_after_requests_received_before_it`는 RED에서 `FrontendStandIn`에 `tick`이 없어 AttributeError로 실패했다. 이 테스트는 진짜 대역 서버의 순번 관계를 보는 받침이고, 결함의 재현은 위의 run 층 테스트다.

### BEH-1 상세

- 지운 쿠키는 (이름, 경로)와 값의 SHA-256으로 기억한다. 셈의 복사본(`BrowserWatch`가 보낸 때의 셈으로 쓰는 것)에도 함께 복사한다.
- 같은 이름과 값이고 경로가 맞는 요청에 다시 붙었을 때만 `kept`다. 값이 다르거나 경로가 맞지 않으면 다른 창의 쿠키일 수 있으므로 그대로 `unexpected`(새 게스트 창 확인)로 둔다.
- 리포트의 실측 (b)(앱이 `SameSite=None`을 붙이고 Chrome처럼 거부하는 브라우저)는 다시 돌리지 않았다. (a)와 같은 꼴, 즉 브라우저가 지우는 `Set-Cookie`를 무시하는 경우를 가짜 세계와 진짜 대역 서버(`TestWithRealStandIn`)로 확인했다.

### TST-2 상세

- `idle_step`(안내의 이름)을 `idle_at`(몇 번째 안내)으로 바꿨다. 점검 1과 점검 2에 같은 이름의 안내(로그인, 내 정보 확인)가 있어서 이름으로는 점검 2를 고를 수 없다. 이 이름을 쓰던 두 테스트는 `idle_at = 1`로 옮겼다.
- 점검 1의 시간 초과는 Google이 로그인을 막는 경우로 만들었다. 그래야 끝내지 못한 시점에 이미 본 어긋남(로그인 시작에 붙은 쿠키)이 생긴다. 사람이 아무것도 하지 않는 안내에서는 끝내지 못한 시점의 어긋남이 생기지 않아서, F8이 초록이었다.
- 시간 초과 사례의 기다림은 0.5초다. 처음 0.05초로 썼더니 점검 2까지 가는 사례가 7번 가운데 한 번 앞의 안내에서 끝났다.

### ARC-1 상세

- 허용하는 표준 라이브러리는 abc, collections, dataclasses, datetime, enum, functools, itertools, logging, math, re, typing이다. 지금 service가 쓰는 것은 logging, dataclasses, datetime, typing이다.
- importlib와 builtins도 목록에 없다. 그래서 importlib를 쓰는 기존 사례 다섯 개의 기대값에 `importlib`(또는 `importlib.import_module`)를 더했다. 동적 import의 대상은 그대로 센다. `importlib.import_module('json')`이 금지가 아님을 보던 사례는 `__import__('logging')`으로 바꿨다. json도 목록에 없기 때문이다.

## 기각했다

없음

## 사람 판단 필요

| ID | 심각도 | 무엇을 정해야 하는가 | 선택지 |
|---|---|---|---|
| BEH-2 | minor | 3차 COR-4 처분이 쿠키 대조를 게스트 창의 화면 이동과 `/api` 요청으로 좁혔다(`scripts/login_check.py`의 `BrowserWatch.observe`). 그런데 ADR-031의 결정, E1 T1.7.2, testcase.md의 안내, 모듈 독스트링은 요청에 붙은 `Cookie`를 모두 대조한다고 적는다. 좁힌 범위를 결정으로 받아들이면 그 경위는 ADR-031에 남아야 하는데, 무인 처분은 ADR.md의 규칙을 코드에 맞춰 고치지 않는다 | A: 좁힌 범위를 받아들인다. ADR-031에 경위(다른 창의 탭이 보낸 요청에 붙은 평소 창의 쿠키를 거짓 보고하던 것)를 남기고, E1 T1.7.2와 testcase.md의 브라우저 안내, 모듈 독스트링에 대조 범위를 적는다. 코드는 그대로다 / B: 문서대로 모든 요청을 대조한다. `observe`의 조건을 없애 3차 COR-4 이전으로 되돌린다. 다른 창의 탭(끈 Vite의 재연결, 아이콘)이 평소 창의 쿠키를 붙이면 거짓 어긋남(종료 코드 1)이 다시 난다. 문서는 그대로다 |

## 커밋

`aa0b343` 테스트(TST-5) · `4fadff5` RED(COR-1 · COR-2 · BEH-1) · `a915c80` 코드(COR-1 · COR-2 · BEH-1) · `6cc5d18` 테스트(TST-1 · TST-2 · TST-3 · TST-4) · `8d8f1c7` 테스트(ARC-1) · `a95a155` 문서(BEH-1)

## 검증

`scripts/check.sh --all`, Docker 켜짐(통합 테스트가 testcontainers의 PostgreSQL에서 돎).

| 명령 | 결과 |
|---|---|
| `ruff check` | exit 0 — 위반 0 |
| `ruff format --check` | exit 0 — 102파일 서식 맞음 |
| `pyright` | exit 0 — 오류 0, 경고 0 |
| `pytest` | exit 0 — 1208개 통과 (처분 전 1188개). 건너뜀 0, xfail 0. 경고 1(Starlette TestClient의 httpx 폐기 예고, 처분 전과 같음) |

- RED의 근거(`4fadff5`): 9개가 실패했다. 실패는 모두 결함 그대로의 동작에 걸린 단언이었다.
  - COR-1: 로그에서 `read`가 `do:reopen`보다 앞에 왔다.
  - COR-2: 점검 2의 "로그인 전"에 앞 창의 로그아웃이 "심지 않은 diegesis_session"으로 보고됐다. 진짜 대역 서버의 순번 테스트는 `tick`이 없어 AttributeError였다.
  - BEH-1: 다시 붙은 지운 쿠키가 `kept`가 아니라 `unexpected`로 나왔다(단위 셋, 문장 하나, `WIRED`의 가짜 세계와 진짜 대역 서버 각 하나).
- 돌연변이 반증. 하나씩 넣고 해당 테스트를 돌린 뒤 복사해 둔 원본으로 되돌렸다. 되돌린 뒤 `cmp`와 `git status`로 원본과 같음을 확인했다.
  - 수정(COR-1 · COR-2 · BEH-1): 새 창의 화면을 기다리지 않음(1개), `belongs` 검사 제거(1개), `since=0`(1개), `received` 대신 `recorded`로 가림(1개), 복사본이 지운 쿠키를 잃음(3개), 지운 쿠키의 값 확인 제거(1개), 경로 확인 제거(1개), `kept`를 `unexpected`로(5개). 모두 빨갰다.
  - TST-1: 히스토리를 `received`로 매김(Mc)은 새 사례 1개가, 기록의 순번을 다른 카운터에서 매김(Md)은 두 사례와 순번 테스트 3개가 빨갰다.
  - TST-2: 점검 2의 `except`에서 `take_problems()` 제거(F2)는 2개(점검 2의 DB 오류, 시간 초과), 점검 1이 DB 오류만 잡음(F8)은 1개(점검 1의 시간 초과)가 빨갰다.
  - TST-3: 결과 처리 대신 로그인 시작의 시각을 `login_at`으로 넘김(T14)은 26개가 빨갰다. 처분 전의 테스트로 같은 변이를 돌리면 시각 판정에 걸리는 테스트가 없었다. 실패 1개는 변이가 더한 대기의 안내 문구 때문이었다.
  - TST-4: users 줄에서 `display_name` 제거(N3), `GET /api/me` 줄에서 본문 제거(N4), 본문을 `ensure_ascii=True`로 찍음(N5). 각 1개가 빨갰다.
  - TST-5: `_is_callback`이 결과 처리를 알아보지 못하게 했다. `test_login_check_run.py` 전체가 72초 만에 끝났다(30 failed). 리포트의 실측은 테스트 하나에 300초였다.
  - ARC-1: `app/auth/service.py`에 `import sqlite3`, `from urllib.request import urlopen`, `import http.client`, `import socket`, `builtins.__import__("sqlalchemy")`, `importlib.__import__("httpx")`를 하나씩 넣었다. 여섯 번 모두 `test_service_imports_no_framework_database_http_or_adapter`가 빨갰다. 처분 전의 테스트 파일로는 여섯 번 모두 초록이었다.
- 흔들림: 실제 스레드를 쓰는 `test_login_check_run.py`와 `test_login_check.py`를 수정 뒤 8번, TST-2를 고친 뒤 `test_login_check_run.py`를 8번, 겹친 로그아웃의 두 사례를 5번 연속 돌렸다. 모두 통과했다.
- 실행으로 확인한 것: 없음. 실제 Google 계정으로 하는 MANUAL 점검(TC-1.7.3, TC-1.7.4)은 돌리지 않았다. 사람이 하는 일이다.

## 새로 발견한 것

- COR-1의 남은 틈: 점검 2가 시작한 뒤 사람이 점검 1의 창을 새로 고치거나 그 창에서 화면을 옮기면, 그 화면 이동을 새 창의 것으로 읽는다. 그 창의 로그인 상태 쿠키는 로그아웃으로 지워졌으므로 판정이 달라지지 않을 것으로 보지만, 확인하지 않았다. 고치지 않았다.

<!-- disposition: fixed=9 rejected=0 needs-human=1 -->
