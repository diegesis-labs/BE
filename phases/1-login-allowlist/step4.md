# Step 4: google-adapter

## 읽어야 할 파일

먼저 아래 파일들을 읽고 이 step의 근거와 설계 의도를 파악하라:

- `docs/backlog/epic-1/E1-login-allowlist.md` — "못 박을 것 (Epic 전역)", S1.2(T1.2.2와 그 "못 박을 것")
- `docs/backlog/epic-1/testcase.md` — 맨 위의 "정상 ID 토큰" 정의, TC-1.2.1 ~ TC-1.2.8
- `docs/API.md` 4.2절 — `GET /api/auth/google/login`의 Response Header 예시(인가 주소의 매개변수)와 **설명**, `GET /api/auth/google/callback`의 **설명**(ID 토큰에서 확인할 클레임)
- `docs/ADR.md` — ADR-025, ADR-027의 "로그인 흐름", **ADR-028**(httpx로 직접 통신한다)
- `docs/INFRA.md` 3.5절 — Google 콘솔에 등록하는 돌아올 주소
- `app/core/ports.py`, `app/core/security.py` (step 3)
- `app/core/config.py`의 `frontend_url`, `google_client_id`, `google_client_secret` (step 0)
- `pyproject.toml`의 `dependencies`와 `[dependency-groups]`, `Dockerfile`(개발 의존성을 설치하지 않는다)

이전 step에서 만들어진 코드를 꼼꼼히 읽고, 설계 의도를 이해한 뒤 작업하라.

## 작업

`IdentityProvider` 포트의 Google 구현을 만든다. ADR-028에 따라 httpx로 토큰 엔드포인트와 통신하고, 인가 주소와 PKCE와 ID 토큰의 클레임 확인은 표준 라이브러리로 직접 구현한다.

### 1. 의존성

httpx를 개발 의존성에서 런타임 의존성으로 옮긴다(`uv remove --dev httpx` 뒤 `uv add httpx`). 이유: 서버의 이미지는 개발 의존성을 설치하지 않는다. 개발 의존성에 남겨 두면 테스트는 초록인데 운영 서버는 import에서 죽는다.

`tests/infra/test_dependencies.py`를 만들어 `pyproject.toml`의 `[project].dependencies`에 `httpx`가 있는지 확인한다. Authlib을 더하지 마라(ADR-028).

### 2. 어댑터 — `app/adapters/google.py`

```python
AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
CALLBACK_PATH = "/api/auth/google/callback"


class GoogleIdentityProvider:   # IdentityProvider를 구조적으로 만족한다
    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        transport: httpx.AsyncBaseTransport | None = None,   # 테스트가 MockTransport를 넣는다
    ) -> None: ...

    @classmethod
    def from_settings(
        cls, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> "GoogleIdentityProvider": ...   # redirect_uri = settings.frontend_url + CALLBACK_PATH

    def authorization_url(self, *, state: str, nonce: str, code_verifier: str) -> str: ...
    async def exchange_code(self, *, code: str, code_verifier: str, expected_nonce: str) -> Identity: ...
```

**인가 주소** (`authorization_url`):

- 매개변수는 API.md 4.2절의 예시에 있는 것만 붙인다. `client_id`, `redirect_uri`, `response_type=code`, `scope=openid email profile`, `state`, `nonce`, `code_challenge`, `code_challenge_method=S256`.
- `code_challenge`는 `code_verifier`의 SHA-256을 패딩(`=`) 없는 base64url로 바꾼 값이다. 주소에 `code_verifier`를 넣지 마라.
- 돌아올 주소는 `FRONTEND_URL`로만 만든다. 어댑터는 요청을 받지 않으므로 요청의 Host를 볼 수 없다. 이 구조를 유지하라(E1 "못 박을 것": 돌아올 주소를 요청의 Host로 만들지 않는다).

**토큰 교환과 ID 토큰의 확인** (`exchange_code`):

- `TOKEN_ENDPOINT`에 폼 본문으로 `grant_type=authorization_code`, `code`, `code_verifier`, `redirect_uri`(인가 주소와 같은 값), `client_id`, `client_secret`을 보낸다. 토큰 엔드포인트의 주소는 코드의 상수이며, 설정값이나 요청에서 받지 않는다(E1 S1.2 "못 박을 것").
- 타임아웃을 명시한다. 이유: Google이 응답하지 않을 때 로그인 요청이 끝없이 붙들려 있으면 안 된다.
- 응답의 `id_token`을 `.`으로 나눠 가운데 부분(payload)을 base64url로 풀어 JSON 객체로 읽는다. **서명은 확인하지 않는다.** 대신 아래 클레임을 모두 확인한다(API.md 4.2절 설명, ADR-027). 하나라도 어긋나면 `LoginFailedError`다.

  | 클레임 | 조건 |
  | --- | --- |
  | `iss` | `https://accounts.google.com` 또는 `accounts.google.com` |
  | `aud` | 문자열이면 우리의 `client_id`와 같다. 목록이면 원소가 우리의 `client_id` 하나뿐이다. |
  | `azp` | 있으면 우리의 `client_id`와 같다. |
  | `exp` | 숫자이고 지금보다 뒤다. 없거나 숫자가 아니면 실패다. |
  | `nonce` | 있고, `security.secure_equals(nonce, expected_nonce)`가 참이다. |
  | `sub` | 비어 있지 않은 문자열이다. |
  | `email` | 비어 있지 않은 문자열이다. |

- `email_verified`는 확인 조건이 아니라 신원에 담아 돌려주는 값이다. 불리언 `true`나 문자열 `"true"`일 때만 `True`이고, 없거나 그 밖의 값이면 `False`다. 거르는 것은 service의 일이다.
- `name`은 문자열이면 그대로, 없으면 `None`이다.
- **어떤 실패든 `LoginFailedError` 하나로 바꾼다.** 통신 오류(httpx의 예외, 타임아웃), 200이 아닌 응답, JSON이 아닌 본문, `id_token`이 없거나 세 부분이 아닌 것, payload를 풀 수 없는 것, 클레임이 맞지 않는 것이 모두 여기에 해당한다. httpx나 `json`, `binascii`의 예외가 밖으로 나가면 안 된다(E1 S1.2 "못 박을 것").
- **예외의 메시지에 비밀을 넣지 마라.** `code`, `code_verifier`, `client_secret`, 응답 본문, `id_token`과 `access_token`의 값이 `LoginFailedError`의 문자열에 들어가면 안 된다. 원인만 적는다(예: "ID 토큰의 aud가 클라이언트 ID와 다름"). 이유: service가 이 메시지를 로그에 남긴다.

### 3. 테스트 — `tests/adapters/test_google.py`

모두 `unit`이며, 네트워크를 쓰지 않는다. `httpx.MockTransport`로 토큰 엔드포인트를 흉내 낸다. ID 토큰은 테스트 안에서 클레임을 base64url로 인코딩해 `header.payload.signature` 모양으로 만든다(서명 부분은 아무 문자열이어도 된다). "정상 ID 토큰"은 testcase.md 맨 위의 정의를 그대로 쓰고, 각 케이스는 적힌 클레임만 바꾼다.

- TC-1.2.1: `FRONTEND_URL=http://localhost:5173`인 설정으로 `from_settings`를 써서 어댑터를 만들고, 정해진 `state`, `nonce`, `code_verifier`로 인가 주소를 만든다. 주소를 `urllib.parse`로 풀어서 각 매개변수를 정확히 비교한다. 문자열에 부분 문자열이 있는지만 보지 마라. `scope`는 정확히 `openid email profile`이고, 매개변수의 집합이 위의 여덟 개와 정확히 같아야 한다. (요청의 Host가 `localhost:8080`일 때의 확인은 로그인 경로를 만드는 step에서 다시 한다.)
- TC-1.2.2: 토큰 교환이 400 오류 응답을 받을 때, JSON이 아닌 본문을 받을 때, `id_token`이 없는 JSON을 받을 때, 그리고 전송이 `httpx.ConnectError`를 낼 때 모두 `LoginFailedError`이고 다른 예외가 아니다.
- TC-1.2.3: 정상 ID 토큰과 `iss`만 `accounts.google.com`인 토큰에서 신원의 네 값이 토큰과 같다. `email_verified`가 없는 토큰은 `False`로 돌아오는 것도 확인한다.
- TC-1.2.4 ~ TC-1.2.7: testcase.md의 각 토큰에서 `LoginFailedError`.
- TC-1.2.8: `MockTransport`의 처리기가 받은 요청을 기록해서, 주소가 `TOKEN_ENDPOINT`이고 메서드가 POST이며, 폼 본문을 풀었을 때 `grant_type`, `code`, `code_verifier`, `redirect_uri`, `client_id`, `client_secret`이 넘긴 값과 같은지 본다.
- 비밀이 새지 않음: 위 실패 케이스마다 `str(예외)`에 `code`, `code_verifier`, 클라이언트 비밀값, 그리고 응답 본문에 넣어 둔 표식 문자열(예: `"access-token-marker"`)이 없는지 본다.
- 형식이 틀린 `id_token`(세 부분이 아님, payload가 base64가 아님, payload가 JSON 배열)에서도 `LoginFailedError`.

### 4. 순서 — RED 커밋을 남긴다

1. 위 테스트를 먼저 쓰고, 어댑터는 시그니처만 있는 빈 껍데기로 둔다.
2. 테스트가 실패하는 것을 눈으로 확인한다.
3. `test(1-login-allowlist): RED — Google 어댑터의 인가 주소와 ID 토큰 확인`으로 커밋한다.
4. 구현해서 초록으로 만든다.

## Acceptance Criteria

```bash
uv run pytest tests/adapters/test_google.py tests/infra/test_dependencies.py -v
scripts/check.sh
```

**반증 조건** — 아래의 틀린 구현으로도 초록이면 그 테스트가 틀린 것이다.

- `scope`에 `offline_access`를 더하거나, `code_challenge_method=plain`으로 `code_verifier`를 그대로 넣거나, `nonce`를 빼도 초록이면 TC-1.2.1이 틀렸다.
- 주소에 `code_verifier`를 함께 넣어도 초록이면 TC-1.2.1이 틀렸다.
- `aud`가 목록일 때 우리 ID가 **들어 있기만 하면** 통과시켜도 초록이면 TC-1.2.4가 틀렸다.
- `azp`를 보지 않아도, `iss`를 보지 않아도, `exp`를 보지 않아도 초록이면 TC-1.2.4~1.2.6이 틀렸다.
- `nonce`가 없는 토큰을 통과시켜도 초록이면 TC-1.2.7이 틀렸다.
- 토큰 교환에서 `code_verifier`를 보내지 않아도 초록이면 TC-1.2.8이 틀렸다.
- httpx의 `ConnectError`가 그대로 나가도 초록이면 TC-1.2.2가 틀렸다.
- httpx를 개발 의존성에 남겨 두어도 초록이면 `test_dependencies.py`가 틀렸다.

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

- 테스트에서 실제 Google에 요청하지 마라. Google의 공개키(JWKS)를 받아 오는 코드도 두지 마라. 이유: 검사가 네트워크와 Google 계정에 기대면 CI에서 돌 수 없다(E1 "못 박을 것", ADR-027).
- Authlib이나 JWT 라이브러리를 더하지 마라. 이유: ADR-028.
- ID 토큰을 쿼리나 브라우저에서 받는 경로나 메서드를 만들지 마라. 이유: 서명을 확인하지 않는 근거가 "토큰 엔드포인트에서 TLS로 직접 받는다"는 것이다(ADR-027).
- 클레임 확인을 줄이거나 선택 사항으로 만드는 설정을 두지 마라. 이유: E1 "못 박을 것"의 보안 항목. 테스트가 실패하면 규칙이 아니라 구현을 고친다.
- 어댑터 안에서 로그에 `code`, 토큰, 클라이언트 비밀값을 남기지 마라. 이유: 위 2번.
- 어댑터를 `app/main.py`에 조립하거나 로그인 경로를 만들지 마라. 이유: 로그인 경로를 만드는 step의 일이다.
- 기존 테스트를 깨뜨리지 마라
- `MANUAL.md`의 항목을 체크하지 마라. 이유: 그 항목은 사람이 직접 본 것만 체크한다.
