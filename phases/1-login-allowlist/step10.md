# Step 10: login-check-proxy

## 읽어야 할 파일

먼저 아래 파일들을 읽고 이 step의 근거와 설계 의도를 파악하라:

- `docs/backlog/epic-1/E1-login-allowlist.md` — S1.7 전체(T1.7.1과 "못 박을 것")
- `docs/backlog/epic-1/testcase.md` — TC-1.7.1
- `docs/ADR.md` — ADR-025의 맥락(프론트엔드의 개발 서버가 Host를 바꿔 넘긴다), **ADR-026**(로컬 점검의 방법)
- `docs/API.md` 2.4절 — 프론트엔드의 개발 서버가 `/api` 요청을 넘길 때 `Origin`을 바꾸지 않는다
- `scripts/compose-smoke.sh` — `scripts/`의 다른 도구가 어떻게 쓰였는지(주석의 밀도, 인자 처리)
- `pyproject.toml` — `scripts/`도 ruff와 pyright의 검사 대상이다

이전 step에서 만들어진 코드를 꼼꼼히 읽고, 설계 의도를 이해한 뒤 작업하라.

## 작업

로컬 로그인 점검 스크립트(`scripts/login_check.py`)의 첫 부품인 **프론트엔드 대역 서버**를 만든다. 이 서버는 프론트엔드의 개발 서버(Vite)처럼 `FRONTEND_URL`의 주소에서 `/api` 요청을 백엔드로 넘긴다. Playwright로 브라우저를 모는 부분과 데이터베이스를 읽는 부분은 다음 step이 같은 파일에 더한다.

### 1. 대역 서버 — `scripts/login_check.py`

```python
class FrontendStandIn:
    def __init__(self, *, listen_host: str, listen_port: int, backend_url: str) -> None: ...
    def start(self) -> None: ...      # 백그라운드 스레드에서 요청을 받기 시작한다
    def stop(self) -> None: ...
    @property
    def port(self) -> int: ...        # listen_port=0이면 운영체제가 고른 포트
```

- **`/api`로 시작하는 경로**: 메서드, 경로와 쿼리, 본문, 헤더를 그대로 `backend_url`로 넘긴다.
  - `Host`는 백엔드의 `호스트:포트`로 바꾼다. 프론트엔드의 개발 서버가 `changeOrigin: true`로 하는 일이다(ADR-025). 이유: 이 대역 서버를 거치면 "돌아올 주소를 요청의 Host로 만드는" 결함이 로컬에서도 드러난다(ADR-026).
  - `Origin`, `Referer`, `Cookie`는 **바꾸지도 빼지도 않고** 넘긴다. 이유: 백엔드의 출처 확인과 로그인 상태가 이 값을 본다.
  - 백엔드의 응답은 **리디렉션을 따라가지 않고** 상태 코드, `Location`, 모든 `Set-Cookie`, 본문을 그대로 돌려준다. `Set-Cookie`가 여러 개면 각각 따로 돌려준다. 하나로 합치지 마라. 이유: 로그인 결과 처리는 `diegesis_oauth_state`를 지우는 것과 `diegesis_session`을 심는 것을 함께 보낸다. 합치거나 하나를 빠뜨리면 브라우저의 상태가 실제 프론트엔드와 달라진다.
  - hop-by-hop 헤더(`Connection`, `Transfer-Encoding` 등)는 넘기지 않아도 된다.
- **그 밖의 경로**(`/`, `/login` 등): `200`과 지금의 주소(경로와 쿼리)를 보여 주는 빈 HTML 화면을 낸다. 다음 step의 Playwright가 이 화면에서 `fetch`를 부른다.
- **의존성을 새로 들이지 마라.** 표준 라이브러리(`http.server`, `http.client`, `threading`)로 충분하다. 이미 있는 의존성(httpx, uvicorn, starlette)을 써도 되지만, 그 경우 httpx의 `follow_redirects`가 꺼져 있는지와 여러 `Set-Cookie`를 그대로 보존하는지를 직접 확인하라.
- 이 파일은 `app/`을 import하지 않는다. 이유: 점검 스크립트는 compose로 띄운 서버를 바깥에서 보는 도구다. 서버의 코드를 끌어오면 서버를 거치지 않은 것을 확인하게 된다.
- 파일 맨 위의 독스트링에 이 스크립트가 무엇이며 언제 누가 실행하는지(사람이 MANUAL 점검에서 실행하며, `scripts/check.sh`와 CI에서는 실행하지 않는다, ADR-026)를 적는다. 실행 방법은 다음 step이 채운다.

### 2. 테스트 — `tests/infra/test_login_check.py`

TC-1.7.1. `unit`이며 네트워크는 이 컴퓨터 안(`127.0.0.1`)만 쓴다.

- 받은 요청(메서드, 경로, 모든 헤더, 본문)을 기록하는 **가짜 백엔드**를 무작위 포트에 띄운다. 가짜 백엔드는 `302`, `Location: http://example.invalid/after`, `Set-Cookie` 두 개(`a=1; Path=/`, `b=; Max-Age=0; Path=/api/auth/google`)를 돌려준다.
- `FrontendStandIn(listen_host="127.0.0.1", listen_port=0, backend_url=가짜 백엔드)`를 띄운다.
- 대역 서버로 `Cookie: diegesis_session=c1; diegesis_oauth_state=s.n.v`를 붙여 `GET /api/auth/google/callback?code=x&state=s`를, `Origin`과 `Referer`를 붙여 본문이 있는 `POST /api/auth/logout`을 보낸다. 요청을 보내는 클라이언트도 리디렉션을 따라가지 않게 한다(`http.client`나 `follow_redirects=False`).
- 단언:
  - 가짜 백엔드가 받은 `Host`가 가짜 백엔드의 `127.0.0.1:포트`이고, 대역 서버의 주소가 아니다.
  - 가짜 백엔드가 받은 `Origin`, `Referer`, `Cookie`, 경로와 쿼리, 메서드, 본문이 대역 서버가 받은 것과 정확히 같다.
  - 대역 서버의 응답이 `302`이고, `Location`이 같으며, `Set-Cookie`가 **두 개**이고 각 값이 가짜 백엔드가 보낸 것과 같다.
  - 대역 서버가 리디렉션을 따라가지 않았다(가짜 백엔드가 받은 요청은 보낸 요청의 수와 같다).
- `/`과 `/login?error=NOT_ALLOWED`에 `200`과 HTML이 나오고, 이 요청은 가짜 백엔드로 가지 않는다.

### 3. 순서 — RED 커밋을 남긴다

1. 테스트를 먼저 쓰고, `FrontendStandIn`은 시그니처만 있는 빈 껍데기로 둔다.
2. 테스트가 실패하는 것을 눈으로 확인한다.
3. `test(1-login-allowlist): RED — 프론트엔드 대역 서버가 /api 요청을 넘기는 방식`으로 커밋한다.
4. 구현해서 초록으로 만든다.

## Acceptance Criteria

```bash
uv run pytest tests/infra/test_login_check.py -v
scripts/check.sh
```

**반증 조건** — 아래의 틀린 구현으로도 초록이면 그 테스트가 틀린 것이다.

- 대역 서버가 백엔드의 리디렉션을 따라가도 초록이면 TC-1.7.1이 틀렸다.
- `Set-Cookie` 두 개를 쉼표로 이어 하나로 합치거나, 마지막 하나만 돌려줘도 초록이면 TC-1.7.1이 틀렸다.
- `Host`를 바꾸지 않고 대역 서버의 주소 그대로 넘겨도 초록이면 TC-1.7.1이 틀렸다.
- `Origin`을 백엔드의 주소로 바꾸거나 빼도 초록이면 TC-1.7.1이 틀렸다.
- `POST`의 본문을 버려도 초록이면 TC-1.7.1이 틀렸다.

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. `git log --oneline`에 RED 커밋이 구현 커밋보다 먼저 있는지 확인한다.
3. 아키텍처 체크리스트를 확인한다:
   - `docs/ARCHITECTURE.md` 8절의 코드 구조와 의존 방향을 따르는가?
   - `docs/ADR.md`의 기술 스택을 벗어나지 않았는가?
   - `docs/DEVELOPMENT.md`의 "반드시 지킬 규칙"을 위반하지 않았는가?
4. 결과에 따라 `phases/1-login-allowlist/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"`
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 (API 키, 외부 인증, 수동 설정 등) → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- `scripts/check.sh`나 CI가 이 스크립트의 `main`을 실행하게 만들지 마라. 이유: 다음 step의 점검은 실제 Google 계정과 사람의 입력이 필요하다(ADR-026). 이 step의 테스트는 대역 서버만 확인한다.
- 테스트에서 실제 백엔드나 compose를 띄우지 마라. 이유: 가짜 백엔드로 넘기는 방식만 확인하면 된다.
- 고정 포트(5173, 8080)로 테스트를 띄우지 마라. 이유: 개발자가 프론트엔드의 개발 서버나 compose를 띄워 두었으면 부딪힌다.
- `app/`을 import하지 마라. 이유: 위 1번.
- Playwright를 더하거나 브라우저를 여는 코드를 쓰지 마라. 이유: 다음 step의 일이다.
- 기존 테스트를 깨뜨리지 마라
- `MANUAL.md`의 항목을 체크하지 마라. 이유: 그 항목은 사람이 직접 본 것만 체크한다.
