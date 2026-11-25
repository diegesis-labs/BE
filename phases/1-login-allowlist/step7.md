# Step 7: origin-check

## 읽어야 할 파일

먼저 아래 파일들을 읽고 이 step의 근거와 설계 의도를 파악하라:

- `docs/backlog/epic-1/E1-login-allowlist.md` — "못 박을 것 (Epic 전역)"의 출처 확인 항목, S1.4(T1.4.2와 "못 박을 것")
- `docs/backlog/epic-1/testcase.md` — 맨 위 첫 문단(상태를 바꾸는 요청의 테스트는 `Origin`을 붙인다), TC-1.4.7과 "출처 확인의 경우" 표
- `docs/API.md` 2.4절 — 확인하는 순서, 거절할 때의 응답. 2.3절 — 에러 응답의 형식
- `docs/ADR.md` — ADR-027의 "출처 확인"
- `app/core/errors.py` — 에러 응답을 만드는 방법과, 처리기가 어디에 등록되는지
- `app/main.py` — `create_app()`의 조립
- `app/core/config.py`의 `frontend_url` (step 0), `tests/conftest.py`의 `app_env`, `tests/support/settings.py` (step 0)
- 지금 있는 테스트 가운데 `POST`, `PUT`, `PATCH`, `DELETE`를 보내는 것 — `grep -rn "\.post(\|\.put(\|\.patch(\|\.delete(\|method=" tests` 로 찾아라 (예: `tests/core/test_errors.py`, `tests/health/test_router.py`)

이전 step에서 만들어진 코드를 꼼꼼히 읽고, 설계 의도를 이해한 뒤 작업하라.

## 작업

상태를 바꾸는 모든 요청이 프론트엔드의 화면에서 왔는지 확인하는 미들웨어를 만들고 앱 전체에 건다.

### 1. 출처 확인 — `app/core/origin.py`, `app/main.py`

API.md 2.4절의 순서를 그대로 구현한다.

- `GET`, `HEAD`, `OPTIONS`는 확인하지 않고 통과시킨다. **이 세 메서드에서는 설정도 읽지 않는다.** 이유: 헬스체크와 API 문서는 설정 없이도 응답해야 하고, 설정 없이 도는 기존 단위 테스트(`tests/test_main.py`, `tests/health/test_router.py`의 GET)가 그대로 통과해야 한다.
- 그 밖의 메서드는 `get_settings().frontend_url`과 비교한다.
  1. `Origin` 헤더가 있으면 그 값이 `FRONTEND_URL`과 **정확히** 같아야 한다. `null`이면 거절한다.
  2. `Origin`이 없으면 `Referer`의 출처(스킴과 `호스트[:포트]`, `urllib.parse.urlsplit`로 뽑는다)가 `FRONTEND_URL`과 정확히 같아야 한다.
  3. 둘 다 없으면 거절한다.
  - `Origin`이 있으면 `Origin`만 본다. `Origin`이 맞으면 `Referer`가 달라도 통과다.
  - 문자열의 앞부분이나 포함 여부로 비교하지 마라. `http://localhost:5173.evil.example`이 통과한다. step 0이 `FRONTEND_URL`을 스킴, 호스트, 포트만 담도록 검증하므로 정확한 비교로 충분하다.
- 거절은 `403`과 `{"code": "ORIGIN_MISMATCH", "message": "..."}` 본문이다(API.md 2.3절의 형식). 거절한 요청은 경로의 처리로 넘어가지 않는다.
- **거절 응답은 미들웨어가 직접 만들어 돌려준다. `AppError`를 던지지 마라.** 이유: `add_middleware`로 건 미들웨어는 `register_error_handlers`가 등록한 예외 처리기의 바깥에서 돈다. 거기서 던진 `AppError`는 처리기를 만나지 못하고 500이 된다. 같은 형식을 쓰도록 `app/core/errors.py`에 공개 함수를 두고 함께 써도 된다.
- 거절할 때 메서드, 경로, 받은 `Origin`이나 `Referer`를 로그에 남긴다. `Cookie` 헤더는 남기지 않는다(E1 S1.4 "못 박을 것").
- `create_app()`에서 앱 전체에 한 번 건다. 경로마다 의존성으로 걸지 마라. 이유: 등록된 경로가 없는 요청과 공개 경로(로그아웃 포함), 그리고 이후 Epic이 더하는 경로까지 빠짐없이 걸려야 한다(ADR-027). 끄는 설정이나 예외 경로의 목록을 두지 마라.
- `create_app()`이 설정을 읽지 않는다는 규칙은 그대로다. 미들웨어는 요청을 받았을 때 설정을 읽는다.

### 2. 기존 테스트 고치기

미들웨어를 걸면 `Origin` 없이 `POST` 등을 보내던 기존 테스트가 `403`을 받는다. 그리고 그 요청에서 설정을 읽으므로 설정 환경이 필요하다. 이 테스트들에 **단언은 그대로 두고** 다음 두 가지만 더한다.

- step 0의 `app_env` fixture.
- 요청에 `Origin: TEST_FRONTEND_URL` 헤더. testcase.md의 안내대로 `TestClient(..., headers={"Origin": TEST_FRONTEND_URL})`처럼 테스트 클라이언트의 기본 헤더로 두면 된다.

예를 들어 `tests/health/test_router.py`의 "`POST /api/health`는 `405 METHOD_NOT_ALLOWED`와 `Allow: GET`" 테스트는 여전히 405를 단언해야 한다. 403을 기대하도록 바꾸지 마라.

### 3. 테스트 — `tests/core/test_origin.py`

모두 `unit`이며 `app_env`(`FRONTEND_URL=http://localhost:5173`)를 쓴다. 앱은 `create_app()`으로 만들고, 관문을 걸지 않은 테스트 전용 경로 하나를 `GET`, `POST`, `PUT`, `PATCH`, `DELETE`로 테스트 안에서만 붙인다. 그 경로는 불린 횟수를 기록한다.

- TC-1.4.7: testcase.md "출처 확인의 경우" 표의 열두 줄을 그대로 매개변수화한다. 통과면 그 경로의 응답이 나오고 경로가 불렸으며, 거절이면 `403`, 본문의 `code`가 `ORIGIN_MISMATCH`이고 본문의 키가 `{"code", "message"}`이며 경로가 불리지 않았다.
- 등록되지 않은 경로에 `POST`를 `Origin: https://evil.example`로 보내도 `403 ORIGIN_MISMATCH`다(404가 아니다).
- `HEAD`와 `OPTIONS`는 `Origin: https://evil.example`이어도 거절되지 않는다.
- `app_env` 없이(설정이 없는 상태) `GET /api/health`가 `200`이다.
- 거절한 요청의 로그(`caplog`)에 메서드, 경로, 받은 `Origin`이 있고, 요청에 붙인 `Cookie` 값(예: `diegesis_session=cookie-marker-1234`)은 없다.

### 4. 순서 — RED 커밋을 남긴다

1. `tests/core/test_origin.py`를 먼저 쓰고, 미들웨어는 아무것도 확인하지 않는 빈 껍데기로 `create_app()`에 건다.
2. 거절해야 하는 경우의 테스트가 실패하는 것을 눈으로 확인한다.
3. `test(1-login-allowlist): RED — 상태를 바꾸는 요청의 출처를 확인한다`로 커밋한다.
4. 구현하고, 2번대로 기존 테스트를 고쳐서 초록으로 만든다.

## Acceptance Criteria

```bash
uv run pytest tests/core/test_origin.py tests/core/test_errors.py tests/health/test_router.py tests/test_main.py -v
scripts/check.sh
```

**반증 조건** — 아래의 틀린 구현으로도 초록이면 그 테스트가 틀린 것이다.

- `Origin`을 `startswith(FRONTEND_URL)`로 비교해도 초록이면 TC-1.4.7이 틀렸다(`http://localhost:5173.evil.example` 줄).
- `Origin`과 `Referer`가 모두 없을 때 통과시켜도, `Origin: null`을 통과시켜도 초록이면 TC-1.4.7이 틀렸다.
- `GET`까지 확인해서 막아도 초록이면 TC-1.4.7이 틀렸다(`GET`에 `https://evil.example` 줄).
- `Origin`이 있는데 `Referer`도 함께 봐서 거절해도 초록이면 TC-1.4.7이 틀렸다(둘째 줄).
- 출처 확인을 경로의 의존성으로 걸어 없는 경로의 `POST`가 404로 나가도 초록이면 그 테스트가 틀렸다.
- 거절 응답이 500이나 FastAPI 기본 형식이어도 초록이면 TC-1.4.7이 틀렸다.
- 기존 테스트의 단언을 403으로 바꿔서 통과시켰다면 2번을 어긴 것이다.

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

- 허용할 출처의 목록이나 와일드카드를 두지 마라. 비교 기준은 `FRONTEND_URL` 하나다. 이유: E1 S1.4 "못 박을 것".
- 출처 확인을 끄는 설정, 예외로 두는 경로를 만들지 마라. 이유: 공개 경로도 예외가 아니다(ADR-027).
- CORS 미들웨어를 더하지 마라. 이유: 프론트엔드와 백엔드가 같은 주소를 쓴다(CONFIGURATION.md 3.1절). CORS는 이 확인과 다른 것이다.
- `Sec-Fetch-Site`나 CSRF 토큰을 더하지 마라. 이유: ADR-027이 `Origin` 확인(B안)을 골랐다.
- 기존 테스트의 단언을 바꾸거나 지우지 마라. `app_env`와 `Origin` 헤더만 더한다. 이유: 위 2번.
- 로그인 경로나 로그아웃을 만들지 마라. 이유: 뒤의 step이 한다.
- `MANUAL.md`의 항목을 체크하지 마라. 이유: 그 항목은 사람이 직접 본 것만 체크한다.
