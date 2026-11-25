# 1-login-allowlist 리뷰 처분 — 2차

> `review-2.md`의 결함 11건(critical 0 · major 0 · minor 11)에 대한 처분. 2026-11-25.
> 고친 것 11건, 기각 0건, 사람 판단 필요 0건.
> 처음 처분에서는 8건을 고치고 BEH-1·BEH-2·ARC-4를 사람 판단으로 넘겼다. 사람이 정한 뒤(2026-11-25) 세 건을 고쳐 "고쳤다"로 옮겼다.

## 고쳤다

| ID | 심각도 | 처분 | 커밋 |
|---|---|---|---|
| COR-1 | minor | `scripts/login_check.py`에 `DATABASE_ERRORS`(OSError, PostgresError, InterfaceError, InternalClientError)를 두고 `preflight`와 `run_checks`가 이 묶음을 잡는다. 재현 테스트는 `tests/infra/test_login_check_main.py`의 `BROKEN["database_auth_unsupported"]`·`["database_protocol_broken"]`(3)와 `tests/infra/test_login_check_run.py`의 `ABORTS`의 같은 두 이름(4) | `23be896` `231ca08` |
| SEC-1 | minor | `create_engine`이 `hide_parameters=True`로 엔진을 만든다. 재현 테스트는 `tests/core/test_database.py::test_statement_error_from_engine_carries_no_bound_values`와 `::test_server_error_log_of_failed_statement_has_no_bound_values`(500의 로그에 이메일과 token_hash가 없음) | `23be896` `231ca08` |
| ARC-1 | minor | core의 의존 방향 검사가 `rglob`으로 하위 패키지까지 보고, 상대 import를 그 모듈의 패키지 기준으로 푼다. `importlib.import_module`·`__import__`의 문자열 인자도 세며, 인자가 문자열 상수가 아니면 닫힌 채 실패한다. 검출기 단위 테스트에 동적 import 11가지와 하위 패키지 형태를 더했다. 리포트가 가리킨 service의 검출기(`tests/auth/test_service.py`)도 같게 고쳤다 | `4ed0616` |
| ARC-2 | minor | `tests/core/test_dependency_direction.py`를 `tests/core/test___init__.py`로 옮겼다(대상: 패키지 `app.core`를 나타내는 `app/core/__init__.py`). ADR-029가 가리키는 경로도 맞췄다 | `26ab3cc` `eda2dd5` |
| ARC-3 | minor | TC-1.2.9의 두 값 목록을 `tests/support/frontend_urls.py`로 옮기고 두 테스트가 거기서 가져다 쓴다. 목록의 약속은 `tests/support/test_frontend_urls.py`가 본다 | `26ab3cc` |
| ARC-5 | minor | ARCHITECTURE 8절의 포트 표와 ADR-029의 재검토 조건에서 "전용 세션 저장소"를 "로그인 상태 전용 저장소"로 고쳤다. 낱말만 고쳤고 결정의 내용은 그대로다 | `eda2dd5` |
| TST-1 | minor | `tests/infra/test_login_check_run.py`(18개). 표대로 움직이는 가짜 서버·DB·브라우저로 진짜 `run_checks`를 불러, 시점별 기준 스냅숏, 제목을 붙여 모으기, 실패를 `CheckAbortedError`로 바꾸기, 연 것을 닫기를 본다. `main`이 진짜 층의 결과로 0·1·4를 고르는지도 본다 | `4ed0616` `23be896` |
| TST-2 | minor | `tests/auth/test_service.py::test_first_login_whose_raced_row_is_gone_is_login_failed`. 결과는 `LOGIN_FAILED`이고, 쓰기는 `create_user`뿐이며, 옛 쿠키의 행을 지우지 않는다 | `4ed0616` |
| BEH-1 | minor | 사람이 A안(문서만)을 골랐다. API.md 4.2절의 동작 순서에 겹친 첫 로그인의 재확인 분기(`opt`)와 500 예외의 노트를 더하고, 마지막 노트를 "302 응답은 모두 `diegesis_oauth_state` 쿠키를 지웁니다"로 좁혔다. 코드는 그대로다. ADR-030의 비교와 결정에 "500에서는 쿠키를 심지도 지우지도 않는다"를 더했다. API.md의 mermaid 다섯 개가 모두 렌더링되는 것을 확인했다. API.md가 바뀌었으므로 PR에 프론트엔드의 리뷰가 필요하다 | `e803998` |
| BEH-2 | minor | 사람이 B안(빈 값 거부)을 골랐다. `database_url: str = Field(min_length=1)`. 재현 테스트 `tests/core/test_config.py::test_empty_database_url_fails_validation`(RED에서 검증 오류 없이 통과함을 확인). CONFIGURATION 3.2절의 `DATABASE_URL` 행에 "빈 값이면 서버가 시작되지 않습니다"를 적었다. CONFIGURATION 1절의 기존 규칙을 따른 것이라 ADR은 더하지 않았다 | `9b19f03` `27a849f` `e803998` |
| ARC-4 | minor | 사람이 A안(`core/ports.py`로 옮김)을 골랐다. `AuthStore`를 `app/core/ports.py`로 옮기고 service는 포트에서 가져온다. `tests/core/test_ports.py`가 app/ 아래의 Protocol이 `ports.py`에만 있는지(검출기의 자기 확인 포함)와 `AuthRepository`가 `AuthStore`·`LoginLookup`을 함께 만족하는지(pyright가 구조적으로 확인)를 본다. RED에서 `service.py`의 `AuthStore`를 잡는 것을 확인했다. ARCHITECTURE 8절의 포트 표와 설명, ADR-029의 비교·결정·재검토 조건에 더했다 | `9b19f03` `27a849f` `e803998` |

### ARC-1 상세

- **리포트보다 넓힌 것**: 인자가 문자열 상수가 아닌 동적 import(`importlib.import_module(name)`)를 `UNKNOWN_DYNAMIC_IMPORT`로 센다. 이것은 core 밖의 것이자 service의 금지 항목으로 판정한다. 리포트는 문자열 인자를 세라고만 했다. 하지만 인자가 상수가 아니면 무엇을 가져오는지 정적으로 알 수 없어서, 세지 않으면 검사가 그대로 초록이 된다. 지금 `app/core/`와 `app/auth/service.py`에는 동적 import가 하나도 없으므로, 이 판정으로 빨개진 파일은 없다.
- **남은 한계**: `getattr(importlib, "import_module")`이나 `importlib.util`로 파일에서 모듈을 읽는 경우는 세지 않는다. 정적 검사로는 닿지 않는 자리이며, 1차의 TST-5 검출기와 같은 선에서 멈췄다.
- **중복**: core와 service의 검출기가 같은 코드를 따로 들고 있다. 1차 처분 때부터 두 벌이었고, 리포트에 없는 리팩터링이라 `tests/support/`로 합치지 않았다.

### ARC-2 상세

리포트의 두 해결 제안 가운데 "대상이 있는 이름으로 옮긴다"를 골랐다. 다른 제안은 DEVELOPMENT 4.2에 패키지 단위 구조 테스트의 자리를 새로 정하는 것인데, 이것은 새 규칙이라 결정 기록이 필요하다. 그래서 무인 처분이 하지 않았다. 옮길 이름으로 `test_ports_dependency_direction.py`도 생각했다. 하지만 이 테스트는 `ports.py` 하나가 아니라 `app/core/`의 모든 모듈을 보므로, 패키지를 나타내는 `__init__.py`의 자리(`tests/test___main__.py`와 같은 꼴)를 골랐다. 사람이 다른 자리를 원하면 파일 이름만 바꾸면 된다.

### TST-1 상세

- `_log_in`(Google 화면으로 보내고 돌아오기를 기다림)은 가짜로 바꿨으므로 이 파일이 보지 않는다. 그 함수의 판정(`returned_to_frontend`)은 `test_login_check_judge.py`가 본다.
- COR-1의 재현 테스트 둘은 이 파일의 `ABORTS`에 RED 커밋(`23be896`)으로 더했다. 18개 가운데 16개는 `4ed0616`에서, 2개는 `23be896`에서 생겼다.

## 기각했다

없음

## 사람 판단 필요

없음. 처음 처분에서 넘긴 BEH-1, BEH-2, ARC-4는 사람이 정한 뒤 고쳐 "고쳤다"로 옮겼다. 그때 비교한 선택지와 고른 이유는 ADR-029(ARC-4), ADR-030(BEH-1), CONFIGURATION 1절(BEH-2)에 있다.

## 커밋

`4ed0616` 테스트(TST-1 · TST-2 · ARC-1) · `26ab3cc` 테스트 구조(ARC-2 · ARC-3) · `23be896` RED(COR-1 · SEC-1) · `231ca08` 코드(COR-1 · SEC-1) · `eda2dd5` 문서(ARC-5 · ARC-2의 ADR-029 경로) · `9b19f03` RED(BEH-2 · ARC-4) · `27a849f` 코드(BEH-2 · ARC-4) · `e803998` 문서(BEH-1 · BEH-2 · ARC-4, ADR-029 · ADR-030)

## 검증

`scripts/check.sh --all`, Docker 켜짐(통합 테스트가 testcontainers의 PostgreSQL에서 돎).

| 명령 | 결과 |
|---|---|
| `ruff check` | exit 0 — 위반 0 |
| `ruff format --check` | exit 0 — 100파일 서식 맞음 |
| `pyright` | exit 0 — 오류 0, 경고 0 |
| `pytest` | exit 0 — 1075개 통과, 건너뜀 0, xfail 0 (처분 전 1021개). 경고 1(Starlette TestClient의 httpx 폐기 예고, 처분 전과 같음) |

- RED의 근거(`23be896`): COR-1의 4개는 `asyncpg.InterfaceError`·`InternalClientError`가 잡히지 않고 테스트 밖으로 나가서 실패했다. SEC-1의 2개는 전제(예외에 `no_such_table`이 있음, `처리되지 않은 예외` 기록이 있음)를 통과한 뒤 `[parameters: ('victim.pii@example.com', '7734…')]` 때문에 실패했다. 문장은 없는 테이블을 읽으므로, PostgreSQL의 오류 문장은 바인딩 값을 되풀이하지 않는다.
- 돌연변이 반증 (넣은 뒤 빨개진 것을 확인하고 되돌렸다. 되돌린 뒤 `git diff`가 비어 있음을 확인했다):
  - TST-1: 14가지를 넣었고 모두 빨갰다.
    - 리뷰가 실측한 것: `judge_allowed_after_logout`에 `before_logout=after_logout`을 넘김(3개 빨감).
    - 다른 기준 스냅숏을 넘김: 로그인 후의 기준을 `after_login`으로(1개), 로그아웃 전의 기준을 `before_logout`으로(2개), 점검 2의 기준을 `after`로(2개).
    - 모으기와 시각: `+=` 대신 `=`(2개), 점검 2의 결과를 버림(2개), `login_at` 대신 지금 시각(9개), 제목을 틀리게 붙임(5개).
    - 실패 처리: DB 오류를 4로 바꾸지 않음(2개), Playwright 메시지를 그대로 노출(1개).
    - 닫기: 브라우저를 닫지 않음(5개), 점검 1의 컨텍스트를 닫지 않음(5개), 대역 서버를 멈추지 않음(6개).
    - 로그아웃 전 `me`를 넘기지 않음(9개).
  - TST-2: 리뷰가 실측한 것, 즉 이 분기의 `_LOGIN_FAILED`를 `_NOT_ALLOWED`로 바꾸자 빨갰다. 분기를 지우자(`user.id`에서 터짐) 빨갰고, 재조회 대신 `create_user`를 다시 부르자 빨갰다.
  - ARC-1: 리뷰가 실측한 두 형태를 넣자 모두 빨갰다. `app/core/gate.py`에 `importlib.import_module("app.auth.repository")`를 넣은 것과 `__import__("app.auth.repository")`를 넣은 것, 그리고 `app/core/mutantsub/lookup.py`에 `from app.auth.repository import …`를 둔 것과 `from ...auth.repository import …`를 둔 것이다. `app/auth/service.py`에 `importlib.import_module("app.auth.repository")`를 넣은 것과 `__import__("httpx")`를 넣은 것도 빨갰다.
  - ARC-3: 목록에서 TC-1.2.9의 `https://diegesis.example/app`을 빼자, 그리고 `http://localhost:5173`을 거부할 값에도 넣자 `test_frontend_urls.py`가 각각 빨갰다.
- 실행으로 확인한 것: COR-1은 실제 asyncpg 연결로 확인했다. SSL을 거절하고 인증 방식 99를 요구하는 가짜 서버를 띄운 뒤 `precheck`를 불렀다. 그러자 `asyncpg.exceptions._base.InterfaceError: unsupported authentication method requested by the server: 99`가 났고, 이 예외가 `DATABASE_ERRORS`에 걸림을 확인했다. BEH-2의 선택지에 적은 지금 동작도 직접 실행해 확인했다. 빈 `DATABASE_URL`로 앱을 띄우자 `/api/health`는 200이었고, 쿠키를 붙인 `/api/me`는 500이었다. SEC-1은 `python -m app`의 uvicorn 출력까지는 다시 확인하지 않았다. 다만 uvicorn의 `Exception in ASGI application`은 같은 예외 객체를 남기고, 그 예외의 문장은 위 통합 테스트가 본다.

## 새로 발견한 것

없음

<!-- disposition: fixed=11 rejected=0 needs-human=0 -->
