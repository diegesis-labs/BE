# Epic 1 코드 리뷰 — 4차

대상 `feat-1-login-allowlist` · `main...HEAD` (97파일, +18593/-112) · 커밋 `3daea97..1fce2c7` (3차 이후 `5dc6043..1fce2c7`, 12파일 +1273/-209: 3차 처분 6커밋)
리뷰 일시 2026-11-26 · 차원별 모델 correctness=opus, security=opus, architecture=opus, test-coverage=opus, behavioral=opus (diff가 1,000줄을 넘고 로그인·SQL·`app/core/ports.py`·`app/main.py`·`pyproject.toml`을 건드려 security와 architecture도 opus로 올림)
근거 문서: `docs/backlog/epic-1/` · `docs/DEVELOPMENT.md` · `docs/ARCHITECTURE.md` 1·8절 · `docs/ADR.md`(ADR-024~031) · `docs/API.md` 2~4.3절 · `docs/CONFIGURATION.md` · `phases/1-login-allowlist/step*.md` · `phases/1-login-allowlist/MANUAL.md` · `phases/1-login-allowlist/review/review-3.md` · `fix-3.md`

## 종합 판정

| 차원 | critical | major | minor | 판정 |
|---|---|---|---|---|
| correctness | 0 | 0 | 2 | ✅ |
| security | 0 | 0 | 0 | ✅ |
| architecture | 0 | 0 | 1 | ✅ |
| test coverage | 0 | 0 | 5 | ✅ |
| behavioral | 0 | 0 | 2 | ✅ |
| **합계** | **0** | **0** | **10** | |

판정: critical 있으면 ❌ · major만 있으면 ⚠️ · minor 이하면 ✅ · 차원이 안 돌았으면 `미완`

**phase를 닫아도 되는가**: 리뷰 기준으로는 가능하다. critical과 major가 없다.

- 3차의 16건 가운데 12건이 닫혔다. COR-1은 미해결이고, COR-2와 ARC-1은 다르게 터졌다. ARC-3은 사람의 판단을 기다린다.
- 새로 나온 10건은 모두 minor다. 대부분 3차 처분이 새로 넣은 코드와 그 재현 테스트의 빈 곳이다.
- 3차 이후 `app/`, `docs/`, `migrations/`, `pyproject.toml`, `compose.yaml`은 바뀌지 않았다. 바뀐 것은 점검 스크립트와 그 테스트, README와 MANUAL의 몇 줄이다.
- 리뷰 밖에 남은 일이 둘 있다.
  - E1이 끝나는 조건인 MANUAL 점검표(TC-1.7.3, TC-1.7.4)가 아직 체크되지 않았다. 사람이 실제 Google 계정으로 돌려야 한다.
  - 3차 ARC-3(`AuthStore`의 구현체를 넣는 자리)을 사람이 정해야 한다.

## 실측

`scripts/check.sh --all`, Docker 켜짐(통합 테스트가 testcontainers의 PostgreSQL에서 실제로 돎), 전체 51초.

| 명령 | 결과 |
|---|---|
| `ruff check` | exit 0 — 위반 0 |
| `ruff format --check` | exit 0 — 102파일 서식 맞음 |
| `pyright` | exit 0 — 오류 0, 경고 0 |
| `pytest` | exit 0 — 1188개 통과, 건너뜀 0, xfail 0, 경고 1(Starlette TestClient의 httpx 폐기 예고, 1~3차와 같음) (46.38s) |

차원별로 따로 실측한 것이 있다. 모두 레포 밖 복사본(`git archive HEAD`)이나 스크래치 컨테이너에서 했다. 레포의 작업 트리는 바뀌지 않았다.

- **점검 흐름을 끝까지 돌림 (correctness, behavioral)**
  - 실제 `create_app()`에 신원 제공자(correctness는 저장소도)만 가짜로 끼웠다. 그리고 실제 `FrontendStandIn`과, RFC 6265식 쿠키 저장소를 가진 흉내 브라우저로 `run_checks`와 `main`을 돌렸다. behavioral은 스크래치 PostgreSQL에 마이그레이션까지 했다.
  - 정상 흐름: 두 점검의 여섯 시점 모두 표와 같았고, 종료 코드 0이었다.
  - 세션 쿠키를 거부하는 브라우저: 어긋남 5개, 종료 코드 1.
  - 점검 2의 창에 쿠키가 남음: 어긋남 2개, 종료 코드 1이며 안내가 맞다.
  - 시간 초과 2종과 점검 중 DB 중단: 중간 결과를 보여 주고 4로 끝났다(3차 COR-3 닫힘).
  - 더러운 DB에서 다시 실행: 종료 코드 3과 SQL 두 묶음이 나왔다.
  - 지우는 `Set-Cookie`를 브라우저가 무시함, 그리고 그것을 `SameSite=None` 변이로 일으킴: 둘 다 "새 게스트 창에서 시작했는지 확인한다"로 안내했다(BEH-1).
  - [로그아웃]을 사람의 간격(0.15초)으로 두 번 누름: 2회 중 2회, 점검 2 "로그인 전"이 새 창이 생기기 전에 판정됐다(COR-1). 간격이 0이면 2회 모두 비워졌다.
  - 점검 경계에 걸친 로그아웃 둘(50ms 간격, 앞의 것을 0.3초 늦춤): 4회 중 4회 거짓 어긋남이 나왔다(COR-2).
- **보안 표면 (security)**
  - 진짜 대역 서버에 대상 14가지를 GET과 POST로 보냈다. 411·400·깨진 요청줄·64KB를 넘는 요청줄도 보냈다.
    - 넘긴 기록에 `code`·`state`가 0건, 쿠키 값이 0건이었다.
    - stdout과 stderr는 모두 0바이트였다.
  - `main`을 시간 초과로 끝내게 했다. 중간 결과와 stderr에서 비밀값 8가지(그 SHA-256 포함)가 0건이었다.
  - 듣는 주소는 127.0.0.1이었다. 화면의 이스케이프도 그대로였다.
  - `.env`의 `FRONTEND_URL=${GOOGLE_CLIENT_SECRET}`을 치환하지 않고 거부했다.
- **돌연변이 (test-coverage)**
  - 기준선은 login_check 테스트 6파일 283개다. 3차 처분 코드에 변이 약 80가지를 넣었다.
  - 3차 TST-1의 진행 층 변이는 모두 빨갰다. TST-2~5의 변이도 빨갰다.
  - 초록으로 남은 것: Mc·Md(TST-1), F2·F8(TST-2), T14(TST-3), N3~N5(TST-4).
  - `_is_callback` 변이와 S7은 테스트가 300초씩 멈췄다(TST-5).
  - 흔들림: 실제 스레드를 쓰는 두 파일을 최대 16개 병렬로 52번 돌렸다. 모두 통과했다.
- **검출기 (architecture)**
  - service의 import 검출기에 44가지 소스를 넣었다.
    - `sqlite3`·`urllib.request`·`http.client`·`socket`, 그리고 `builtins.__import__`·`importlib.__import__`는 초록이었다(ARC-1).
    - `asyncpg`와 상대 import, `import_module`은 빨갰다.
- **TDD 순서 (test-coverage, behavioral)**
  - RED `3d1a5f5`를 풀어 돌리자 20개가 실패했다. fix-3.md가 적은 수와 같다. 그 뒤 `tests/`는 바뀌지 않았다.
  - fix-3.md가 인용한 테스트 이름 20개는 모두 실제로 있다.

## 결함

### correctness

| ID | 심각도 | 위치 | 위반 | 문제점 | 해결 제안 | 연관 |
|---|---|---|---|---|---|---|
| COR-1 | minor | `scripts/login_check.py:1872-1876`, `scripts/login_check.py:1973`, `scripts/login_check.py:1982`, `tests/infra/test_login_check_run.py:419-421` | E1 S1.7 T1.7.2 · 3차 COR-1 | `_discard_pending`은 점검 1의 마지막 DB 읽기 직후까지 큐에 든 것만 버린다. 그래서 사람이 [로그아웃]을 0.15초 간격으로 두 번 누르면, 점검 2 "로그인 전"이 옛 창의 `GET /api/me`로 판정되고 안내가 앞서 나간다 | 점검 2의 "로그인 전"은 새 창의 화면 이동을 먼저 기다린 뒤에 온 `GET /api/me`로만 판정한다. 회귀 테스트는 두 번째 누름을 다음 `_wait_for`가 시작된 뒤에 보낸다 | COR-2 |
| COR-2 | minor | `scripts/login_check.py:1973`, `scripts/login_check.py:1283-1295`, `scripts/login_check.py:1248-1252` | E1 S1.7 못 박을 것(심지 않은 쿠키) · 3차 COR-2 | 점검 2를 시작하기 전에 대역 서버가 받았지만 응답은 그 뒤에 기록된 점검 1 창의 요청이 있다. 이 요청은 새 `BrowserWatch`에서 `_jar_when_sent`가 돌려주는 빈 셈과 견주어져, "심지 않은 쿠키"로 거짓 보고된다 (빈도는 추정) | 점검 2를 시작할 때 대역 서버의 지금 순번을 잠금 아래에서 받아 둔다. `received`가 그보다 작은 기록은 점검 2의 셈과 대상에서 뺀다 | COR-1, TST-1 |

- **COR-1·COR-2를 minor로 두는 이유**: 둘 다 사람이 버튼을 겹쳐 누를 때 점검의 경계에서 생기고, 조용히 통과하는 경로는 없다.
  - COR-1: 점검 2의 판정은 계속된다. 새 창의 요청은 뒤의 대기에서 셈과 대조되므로, 새 창에 남은 쿠키는 다음 요청에서 잡힌다(behavioral 실측).
  - COR-2: 거짓 어긋남이라 종료 코드 1로 드러난다. 사람이 다시 돌리면 된다.
  - correctness는 COR-2에 대해 실제 PostgreSQL에서는 드물다고 적었다. 두 번째 로그아웃이 행 잠금을 기다렸다가 곧 끝나기 때문이다.
- **COR-1의 실측이 behavioral과 다른 이유**: behavioral의 "로그아웃 두 번"은 두 누름이 점검 1의 마지막 DB 읽기 전에 모두 기록되는 간격이었다. 그래서 비워졌다. correctness는 두 번째 누름을 0.15초 뒤에 보냈고, 2회 모두 재현됐다. 코드(`_discard_pending`은 그 순간의 큐만 비움)로도 확인했다.
- **COR-3**: behavioral의 BEH-1과 같은 결함이라 BEH-1에 합쳤다.

### security

결함 없음.

### architecture

| ID | 심각도 | 위치 | 위반 | 문제점 | 해결 제안 | 연관 |
|---|---|---|---|---|---|---|
| ARC-1 | minor | `tests/auth/test_service.py:695-696`, `tests/auth/test_service.py:703-708`, `tests/auth/test_service.py:608-612`, `tests/auth/test_service.py:640` | ARCHITECTURE §8 · DEVELOPMENT 반드시 지킬 규칙 | service의 허용 목록 검출기가 표준 라이브러리를 통째로 허용한다(`sys.stdlib_module_names`). 그래서 `sqlite3`·`urllib.request`·`http.client`·`socket`과 `builtins.__import__`·`importlib.__import__`가 초록이다 | service가 쓸 표준 라이브러리 모듈만 명시해 허용하거나 바깥과 닿는 모듈을 금지한다. 검출기 사례에 `sqlite3`·`urllib.request`·`builtins.__import__`를 더한다 | |

- **ARC-1의 근거**
  - 주석(:610 "그 밖의 것은 모두 특정 기술")과 테스트 이름("no … database, http")이 실제 판정보다 넓게 말한다.
  - 지금의 `app/auth/service.py`는 logging·dataclasses·datetime·typing만 쓴다. 실제 위반은 없으니 검사의 빈틈이다.
- **3차 처분과의 관계**: 3차 ARC-1의 해결 제안("표준 라이브러리와 …만 허용")이 이 빈틈을 함께 남겼다. 그래서 처분 자체의 잘못으로 보지 않고, 이전 라운드 대조에 "다르게 터짐"으로 적었다.
- **보류한 부분과의 관계**: `builtins.__import__`·`importlib.__import__` 부분은 1~3차가 보류한 "검출기의 정적 한계"에 가깝다. 다만 이미 있는 별칭 풀이로 잡을 수 있는 정적 형태라서 함께 적었다.

### test coverage

| ID | 심각도 | 위치 | 위반 | 문제점 | 해결 제안 | 연관 |
|---|---|---|---|---|---|---|
| TST-1 | minor | `tests/infra/test_login_check.py:533-560`, `scripts/login_check.py:378-388`, `scripts/login_check.py:1283-1295` | E1 S1.7 못 박을 것(반영 전 대조) · 3차 COR-2 | COR-2의 재현 테스트는 "먼저 온 로그아웃이 나중에 끝나는" 순서 하나만 만든다. 그래서 히스토리를 `received`로 매기거나(Mc) 두 순번을 다른 카운터에서 매겨도(Md) 283개가 초록이다 | 반대 순서(먼저 온 것이 먼저 기록되고, 뒤에 온 것은 그 전에 이미 받음)의 사례를 더한다. 두 사례 모두 어긋남이 없음을 단언한다 | COR-2 |
| TST-2 | minor | `scripts/login_check.py:1955-1957`, `scripts/login_check.py:2006-2008`, `tests/infra/test_login_check_run.py:766-776` | fix-3 COR-3 · 모듈 독스트링 종료 코드 4 | 끝내지 못한 시점의 쿠키 어긋남을 싣는 `except`는 "점검 1 + DB 오류"에서만 테스트된다. 점검 2의 `except`에서 `take_problems()`를 빼도(F2), 점검 1이 DB 오류만 잡게 해도(F8) 초록이다 | 가짜 세계가 몇 번째 안내에서 멈출지 정하게 한다. 그리고 점검 2의 시간 초과와 DB 오류에서, 그 시점의 쿠키 어긋남이 `found`에 남는지 단언한다 | |
| TST-3 | minor | `tests/infra/test_login_check_run.py:107-108`, `tests/infra/test_login_check_run.py:411-414`, `scripts/login_check.py:1908-1921` | TC-1.7.3 · 3차 TST-1 | 가짜 시계가 로그인 시작과 결과 처리 사이에 1초(HOP)만 흘린다. 그래서 결과 처리 대신 로그인 시작의 시각을 `login_at`으로 넘겨도(T14) 초록이다 | `STEP_LOG_IN`에서 Google 화면에 머무는 시간을 `TIME_TOLERANCE`보다 길게(예: 2분) 흘린다 | |
| TST-4 | minor | `scripts/login_check.py:1348`, `scripts/login_check.py:1656-1658`, `tests/infra/test_login_check_judge.py:444-448` | .claude/commands/harness.md D-4 · 3차 BEH-2 처분 | 3차 BEH-2를 "display_name은 사람이 출력을 보고 대조한다"로 처분했다. 그런데 출력에 `display_name`과 `GET /api/me`의 본문이 찍히는지 보는 테스트가 없다. 둘을 빼도(N3~N5) 초록이다 | "로그인 후"의 users 줄과 "로그아웃 전"의 `GET /api/me` 줄에 `display_name` 값이 있는지 단언한다 | |
| TST-5 | minor | `tests/infra/test_login_check_run.py:538-551`, `scripts/login_check.py:585` | 없음 (테스트 자체의 결함) | `world` 픽스처가 `LOGIN_WAIT_SECONDS`(300)를 줄이지 않는다. 그래서 기다리는 요청을 알아보지 못하는 변이에서는 테스트가 빨개지는 대신 하나에 300초씩 멈춘다(실측: 40초 안에 안 끝남, 묶음은 10분 넘게) | `world` 픽스처에서 `LOGIN_WAIT_SECONDS`를 짧게(예: 2초) 둔다. 사람의 시간은 가짜 시계로 흐르므로 판정은 같다 | |

- **TST-4가 범위 밖의 "출력 형식"이 아닌 이유**: testcase.md가 판정하지 않는 것은 표의 모양과 문구다. 이 항목은 사람이 대조할 값이 출력에 있느냐의 문제다. 3차 BEH-2 처분 뒤로 TC-1.7.3의 `display_name` 두 칸은 그 값에 전부 기댄다.
- **TST-5를 minor로 두는 이유**: 지금 코드에서는 일어나지 않는다. 하지만 고치는 세션이 실수하면 `scripts/check.sh`와 Stop 훅이 출력 없이 몇 시간 멈춘다. 이 파일의 34개 가운데 대기 시간을 직접 줄이지 않는 31개가 그렇다.

### behavioral

| ID | 심각도 | 위치 | 위반 | 문제점 | 해결 제안 | 연관 |
|---|---|---|---|---|---|---|
| BEH-1 | minor | `scripts/login_check.py:1175-1179`, `scripts/login_check.py:1211-1212`, `scripts/login_check.py:1248-1252`, `README.md:191`, `tests/infra/test_login_check_run.py:226` | E1 S1.7 못 박을 것(이번 점검에서 심지 않은 쿠키) · ADR-031 | 셈은 지우는 `Set-Cookie`를 받으면 키를 버리기만 한다. 그래서 브라우저가 로그아웃의 삭제를 받아들이지 않아도 "이번 점검에서 심지 않은 쿠키 … 새 게스트 창에서 시작했는지 확인한다"로 나와, 사람을 엉뚱한 원인으로 안내한다 | 셈이 이번 점검에서 지운 (이름, 경로)를 기억하게 한다. 그 쿠키가 다시 붙으면 다른 종류로 보고하고 지우는 `Set-Cookie`의 속성을 확인하라고 안내한다. README:191과 `WIRED`도 함께 고친다 | COR-3(병합) |
| BEH-2 | minor | `scripts/login_check.py:1269-1276`, `scripts/login_check.py:33-35`, `docs/backlog/epic-1/E1-login-allowlist.md:207`, `docs/backlog/epic-1/testcase.md:128`, `docs/ADR.md:1317` | E1 S1.7 T1.7.2 · ADR-031 · testcase.md S1.7 | 3차 COR-4 처분이 쿠키 대조를 화면 이동과 `/api` 요청으로 좁혔다. 그런데 T1.7.2, testcase.md:128, ADR-031, 모듈 독스트링은 요청에 붙은 쿠키를 모두 대조한다고 적고 있다. 이 범위를 적은 곳은 처분 기록뿐이다 (실질 차이는 추정상 없음) | T1.7.2와 testcase.md의 안내, 모듈 독스트링에 대조 범위(게스트 창의 화면 이동과 `/api` 요청)를 적는다. 바뀐 경위는 기술적 결정이므로 ADR-031에만 남긴다 | |

- **BEH-1의 실측**: behavioral이 두 가지로 재현했다.
  - (a) 흉내 브라우저가 지우는 `Set-Cookie`를 무시한다.
  - (b) 앱 변이로 지우는 `Set-Cookie`에 `SameSite=None`을 붙이고, 브라우저가 Chrome처럼 `Secure` 없는 `SameSite=None`을 거부한다.
  - 두 경우 모두 그 시점의 스냅숏은 "쿠키: 없음"이었다. 어긋남은 위 문장 하나뿐이었고, 종료 코드는 1이었다.
- **BEH-1의 범위와 출처**
  - 원인이 백엔드가 보낸 지우는 `Set-Cookie`의 속성이면, 새 창으로 다시 돌려도 같은 결과가 나온다. 사람은 원인을 찾지 못한다.
  - 3차 BEH-1과 같은 기준을 적용했다. 사람을 틀린 행동으로 안내하는 것은 범위 밖의 "문구"가 아니다.
  - fix-3.md가 "새로 발견한 것"으로 적고 고치지 않은 자리다. correctness의 COR-3도 같은 것을 짚었다.
- **BEH-2를 고칠 곳**: 코드와 문서 가운데 어느 쪽을 고칠지는 처분 세션이 정한다. 문서를 고치면 CLAUDE.md의 "결정을 기록하는 규칙"을 따른다. 최신 내용은 E1과 testcase에 적고, 경위는 ADR.md 하나에만 남긴다.

## 수정 우선순위

| # | 결함 | ID | 규모 |
|---|---|---|---|
| 1 | 점검 2가 시작할 때 점검 1 창의 요청이 대상이 되거나 거짓 어긋남이 된다 | COR-1, COR-2 | 순번 경계와 "새 창의 화면 이동 먼저", 몇 줄. 사람의 간격으로 누르는 회귀 테스트 |
| 2 | 지운 쿠키가 다시 붙으면 새 게스트 창 확인으로 안내한다 | BEH-1 | `CookieJar`의 기억과 새 종류의 보고, README 한 줄, `WIRED` 한 줄 |
| 3 | 배선이 망가지면 run 층 테스트가 300초씩 멈춘다 | TST-5 | 픽스처 한 줄 |
| 4 | 3차 처분 코드의 재현 테스트가 한 사례만 본다 | TST-1, TST-2, TST-3, TST-4 | 사례 몇 개, 가짜 시계 한 줄, 출력 단언 몇 줄 |
| 5 | 쿠키 대조 범위를 문서가 다르게 적는다 | BEH-2 | 문서 몇 줄 |
| 6 | service 검출기가 표준 라이브러리를 통째로 허용한다 | ARC-1 | 허용 목록 몇 줄과 검출기 사례 셋 |

## 이전 라운드 대조

3차 처분 기록(`fix-3.md`)은 15건을 "고쳤다", 1건을 "사람 판단 필요"로 적었다. 각 항목을 코드와 실측으로 다시 확인했다.

| 3차 ID | 심각도 | 판정 | 확인한 것 |
|---|---|---|---|
| TST-1 | major | 닫힘 | 3차가 실측한 진행 층 변이를 다시 넣었더니 모두 빨갰다. 여섯 자리의 `take_problems`, 상태 코드 상수, `login_at=me.at`, 기준 스냅숏, 점검 2의 대기, 기한이다. 가짜 세계는 기록마다 다른 시각을 주고, 사람은 스크립트가 기다리기 시작한 뒤에 움직인다. 같은 안내 안의 로그인 시작 시각은 여전히 반증하지 못한다(새 TST-3) |
| COR-1 | minor | 미해결 | `_discard_pending`이 비우는 것은 점검 2가 시작하는 순간 큐에 든 것뿐이다. 사람의 간격(0.15초)으로 두 번 누르면 재현된다(새 COR-1, 실측 2/2). 회귀 테스트가 초록인 것은 두 누름을 간격 0으로 보내기 때문이다 |
| COR-2 | minor | 다르게 터짐 | `BrowserWatch` 하나 안에서는 닫혔다. 같은 쿠키의 동시 로그아웃 둘이 거짓 보고 없이 끝났다(behavioral 2/2). 순번은 한 잠금 아래 한 카운터에서 매긴다. 하지만 점검의 경계를 넘는 요청은 빈 셈과 견주어진다(새 COR-2) |
| COR-3 | minor | 닫힘 | 시간 초과 2종과 점검 중 DB 중단에서, `found`에 앞 시점의 어긋남과 그 시점의 쿠키 대조가 실렸다(correctness, behavioral 실측). 다만 `except` 분기의 테스트는 한 조합뿐이다(새 TST-2) |
| COR-4 | minor | 닫힘 | 화면 이동도 `/api`도 아닌 요청은 대조하지 않는다(실측). 좁힌 범위가 문서에 없는 것은 새 BEH-2로 올렸다 |
| COR-5 | minor | 닫힘 | `docker compose config`와 여섯 가지 값을 견주었다. 따옴표 뒤 주석, 홑따옴표, 탭 뒤 `#`, 빈 따옴표가 같았다(correctness, behavioral 실측) |
| SEC-1 | minor | 닫힘 | 넘김(`_handle`)·기록(`request_target`)·대조(`observe`)·화면(`_is_page`)·출력(`_display_url`)이 `_is_api` 하나를 쓴다. 대상 14가지로 실측했고, 술어를 다시 가르는 변이 둘은 각각 4개가 빨갰다 |
| ARC-1 | minor | 다르게 터짐 | 서드파티는 닫혔다. `asyncpg`·`pydantic`·`starlette`·`app.core.config`를 넣으면 빨갰다. 하지만 표준 라이브러리 전체를 허용해서, 그 안의 DB·HTTP·소켓과 `builtins.__import__`가 초록이다(새 ARC-1) |
| ARC-3 | minor | 미해결 (사람 판단 대기) | `app/auth/router.py:34`가 `AuthRepository`를 import하고, `get_auth_service`(:72-73)가 구현체를 고른다. ARCHITECTURE 8절과 ADR-029는 바뀌지 않았고 결정 커밋이 없다. 새 근거가 없어 새 ID로 올리지 않았고, 이번 표에도 세지 않았다 |
| ARC-4 | minor | 닫힘 | README "결과를 읽는 법"이 쿠키 대조 규칙을 testcase.md의 같은 절로 넘긴다. 남은 것은 "보낸 쿠키"의 뜻과 사람이 할 일이다. 그 안내 문장이 틀리는 경우는 새 BEH-1로 올렸다 |
| TST-2 | minor | 닫힘 | 기록을 응답 뒤로 옮기는 변이가 빨갰다. `_forward` 1개, `_page` 1개, `_plain` 3개다 |
| TST-3 | minor | 닫힘 | 진짜 `FrontendStandIn`을 지나는 테스트가 있다. 대역 서버의 스레드에서 `put_nowait`를 바로 부르는 변이는 2개가, `suppress` 제거는 1개가 빨갰다 |
| TST-4 | minor | 닫힘 | 실제 PostgreSQL integration 테스트가 있다. `session_total=0`, 두 계정만 셈, sessions 비움, expires_at과 created_at 뒤바꿈, 모든 사람의 행, 소문자로 바꾸지 않음이 각 1개씩 빨갰다 |
| TST-5 | minor | 닫힘 | `log_message` 재정의를 지우는 변이가 1개 빨갰다. 실측으로 stderr는 0바이트였다 |
| BEH-1 | minor | 닫힘 | `--help`의 설명이 ADR-031과 같다. 브라우저를 열거나 조종하지 않고, 게스트 창을 쓰고, 종료 코드 4의 뜻이 맞다(실측). README:189가 가리키는 대상이 맞다 |
| BEH-2 | minor | 닫힘 (선택지 B) | 결과 첫 줄이 "스크립트가 판정하는 칸은 모든 시점에서 …"이고, 결과마다 `DISPLAY_NAME_NOTE`가 붙는다(실측). README, MANUAL, `--help`, 독스트링에도 적혀 있다. 출력에 그 값이 찍히는지의 테스트는 새 TST-4로 올렸다 |

fix-3.md의 "새로 발견한 것"(지운 쿠키를 다시 붙여도 새 게스트 창 확인으로 안내함)은 실측으로 재현했고, 새 BEH-1로 올렸다.

처분 커밋의 TDD 순서도 확인했다.

- RED `3d1a5f5`(20 failed)가 수정 `f8ff355`보다 앞선다. COR-1~5, SEC-1, BEH-1, BEH-2마다 실패가 있다.
- `f8ff355`는 `scripts/login_check.py`만 고쳤다. RED 뒤로 `tests/`는 바뀌지 않아, 테스트가 약해지지 않았다.
- `a54b1ac`·`5dc6043`는 RED 없이 테스트만 더한 커밋이다. 이미 맞게 동작하는 코드를 반증하는 테스트라 RED가 될 수 없다. DEVELOPMENT.md 4.1절은 `app/`의 로직을 쓸 때의 규칙이다.
- `a54b1ac`에서 지운 단언 넷은 더 강한 단언으로 바뀌었다. `WIRED` 전체를 순서까지, `do:` 로그, state가 없으면 `LOGIN_FAILED`로 보냄이다.

## 잘 된 것 (재검증 불필요)

- **3차 처분의 대부분**: 15건 가운데 12건이 실측으로 닫혔다. 처분 기록이 주장한 테스트 함수와 커밋은 모두 실제로 있다.
- **순번과 셈**
  - `tick`과 `record`가 같은 잠금을 쓴다. 순번은 겹치지 않고 커지기만 한다.
  - `observe`를 잠금 아래에서 부르므로, `recorded`의 차례, 큐의 차례, 히스토리의 차례가 같다.
  - `_jar_when_sent`의 오차는 거짓 어긋남 쪽으로만 난다. 거짓 통과는 생기지 않는다.
  - 셈과 큐는 이벤트 루프 스레드에서만 만진다.
- **보안 표면**
  - `_is_api` 단일 술어 뒤로 넘김·기록·출력이 갈라지지 않는다.
  - `CheckAbortedError.found`와 중간 결과 출력에 비밀값이 없다.
  - `parse_dotenv`가 바뀌었어도 쓰는 값은 세 값뿐이다.
  - 대역 서버의 stderr는 어떤 실패 응답에서도 비어 있다.
- **앱 코드(3차 이후 바뀌지 않음)**
  - security와 architecture가 관문·출처 확인·쿠키·로그·SQL·의존 방향·설정·API 공통 규칙을 다시 읽었다. 새 결함은 없었다.
  - 보호된 경로는 `/api/me` 하나이며 요청마다 허용 목록을 읽는다.
- **점검 스크립트의 정상 흐름과 주요 고장**
  - 두 차원이 따로, 실제 앱과 실제 대역 서버로 끝까지 돌렸다.
  - 정상 흐름은 종료 코드 0이었다.
  - 쿠키 거부와 남은 쿠키는 1, 시간 초과와 DB 중단은 중간 결과를 보여 주고 4, 더러운 DB는 3으로 끝났다.
- **안내 일치**: 안내 `>>>` 일곱 줄이 README와 MANUAL의 표와 순서·내용이 같다. 안내마다 "(최대 5분 기다립니다)"가 붙는다.
- **문서 규칙**
  - 3차 이후의 README·MANUAL 변경에 경위나 리뷰 ID가 없다. "세션"을 단독으로 쓴 곳도 없다.
  - `docs/`는 바뀌지 않아 결정 기록 규칙을 어긴 곳이 없다.
- **검사 후퇴 없음**: 3차 이후 새 `# type: ignore`·`# noqa`·`cast`·`skip`·`xfail`·`os.environ`이 없다. 새 의존성도 없다.

## 이 리뷰가 판정하지 않은 것

- `docs/backlog/epic-1/testcase.md` "이 Epic에서 판정하지 않는 것"
  - 프론트엔드 화면
  - 운영 주소의 Google 로그인과 `Secure` 쿠키, 운영 호스팅의 `Origin` 전달(E2)
  - 허용 목록 관리 API가 없는 것, 관리자의 실제 경로(E3·E9)
  - 점검 스크립트가 시점마다 내는 출력의 형식과 문구
  - ID 토큰 서명 미확인, `__Host-` 접두사 없음, 유휴 만료 없음(ADR-027)
- `MANUAL.md`의 TC-1.7.3, TC-1.7.4: 실제 Google 계정으로 하는 점검이며, 이 리뷰는 실행하지 않았다. 단언으로 옮길 수 있는 부분은 TST-4로 올렸다.
- 3차 ARC-3: 사람의 판단을 기다린다(위 대조 표).
- `phases/1-login-allowlist/step10.md`·`step11.md`와 `index.json`의 summary가 ADR-031 이전의 Playwright 설계를 적고 있는 것: harness의 실행 기록이다.
- 1~3차가 보류한 것(새 근거 없음)
  - `/api/me`의 401·403과 로그아웃의 403이 OpenAPI에 없는 것
  - 이메일의 Python `lower()`와 PostgreSQL `lower()`가 비ASCII에서 다를 수 있는 것
  - REPEATABLE READ에서는 경합이 500이 되는 것
  - DB 장애·커밋 실패 때 결과 처리가 `500`으로 끝나는 것 자체(ADR-030)
  - core와 service의 검출기가 두 벌인 것
  - 점검 스크립트가 쿠키 이름과 TTL을 상수로 두는 것
  - `hide_parameters`가 가리지 못하는 asyncpg `DataError`의 값 repr과 고유 제약 위반의 `DETAIL`
- 차원이 결함으로 올리지 않은 것
  - test-coverage가 실제 동작에서 원래 코드와 같거나 생길 일이 드물다고 본 초록 변이
    - D2(`sleep(0)` 제거), D4(비우기를 안내 뒤로)
    - C4(앞선 기록이 없으면 지금의 셈), C6(`observe`를 잠금 밖에서)
    - S2(`_handle`만 옛 판정), S5(`_is_page`가 `/api/`만 뺌)
    - T4b(`login_at=landing.at`), T6b·T6c(점검 2의 대기 하나만 제거)
    - P2(`rfind`), P3(닫히지 않은 따옴표)
  - TC-1.7.5에 테스트의 TC 번호가 달리지 않은 것: 굵은 글씨의 세 조건은 모두 변이로 반증된다. 번호를 달라는 규칙도 없다.
  - architecture의 메모 둘
    - `is_allowed_app_import`가 `from app.core.security import hash_token`을 금지로 판정하는 오탐. 허용 쪽을 넓히지는 않는다.
    - MANUAL.md:33의 "Playwright는 따로 설치하지 않는다". 지금 시제의 안내다.
  - security의 메모: 의존성에 websockets나 wsproto가 들어오면, uvicorn의 WebSocket 거절 로그에 쿼리가 남을 수 있다. 지금은 lock에 없다. 그런 의존성을 더하는 Epic에서 다시 본다.
  - behavioral이 재현한 COR-1의 자가 공개 잔여: 옛 창에서 [내 정보 확인]을 누르는 경우다. 조용히 통과하지 않아 올리지 않았다. 같은 자리의 사람 간격 재현은 COR-1에 있다.
- 기각한 sub-agent 지적 1건 (근거 불일치 0 · 범위 밖 0 · 중복 1)
  - COR-3을 BEH-1에 합쳤다. correctness 표에 COR-3이 없는 것은 이 병합 때문이다.
- 심각도를 바꾼 것 0건. 올라온 11건을 모두 다시 판정했다.
  - COR-1, COR-2, TST-3, TST-4, BEH-1은 올릴지 검토했다.
  - 조용히 틀린 판정을 내는 경로가 없거나(COR-1·COR-2·BEH-1은 어긋남이나 종료 코드 1로 드러남), 지금의 코드에서는 요구가 지켜져서(TST-3·TST-4) minor로 두었다.

<!-- verdict: critical=0 major=0 minor=10 -->
