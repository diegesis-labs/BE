# Step 3: ports-and-tokens

## 읽어야 할 파일

먼저 아래 파일들을 읽고 이 step의 근거와 설계 의도를 파악하라:

- `docs/backlog/epic-1/E1-login-allowlist.md` — "못 박을 것 (Epic 전역)"의 보안 항목, S1.2의 T1.2.1과 "못 박을 것", S1.3의 T1.3.2
- `docs/backlog/epic-1/testcase.md` — TC-1.3.17(앞부분: 함수를 1000번 부르는 것과 `secrets.token_urlsafe`를 `32`로 부르는 것), TC-1.3.3(빈 `state`끼리 같다고 판정하면 안 된다)
- `docs/API.md` 4.2절의 **설명** — `state`, `nonce`, `code_verifier`, 쿠키 값의 형식과 비교 방법
- `docs/ADR.md` — ADR-027의 "로그인 흐름"과 "임의의 값"
- `pyproject.toml`의 `[tool.ruff.lint]`
- `app/core/config.py` (step 0), `app/auth/repository.py` (step 2)

이전 step에서 만들어진 코드를 꼼꼼히 읽고, 설계 의도를 이해한 뒤 작업하라.

## 작업

Google 로그인의 포트를 선언하고, 로그인에 쓰는 임의의 값과 해시와 비교를 맡는 함수를 한 곳에 만든다. 다음 step의 Google 어댑터, 그다음의 service와 관문이 이것을 쓴다.

### 1. 포트 — `app/core/ports.py`

```python
@dataclass(frozen=True)
class Identity:
    """Google이 확인해 준 신원. 이메일은 Google이 준 그대로다(소문자로 바꾸는 것은 service의 일)."""
    sub: str
    email: str
    email_verified: bool
    name: str | None


class LoginFailedError(Exception):
    """Google과의 로그인이 끝나지 못했다.

    메시지에는 원인(예: "토큰 교환이 400으로 실패", "ID 토큰의 aud가 다름")만 적는다.
    code, code_verifier, 토큰, 클라이언트 비밀값은 메시지에 넣지 않는다.
    """


class IdentityProvider(Protocol):
    def authorization_url(self, *, state: str, nonce: str, code_verifier: str) -> str:
        """Google의 인가 주소. state와 nonce를 붙이고, code_verifier로 만든 code_challenge(S256)를 붙인다."""

    async def exchange_code(self, *, code: str, code_verifier: str, expected_nonce: str) -> Identity:
        """code를 토큰으로 바꾸고 ID 토큰의 클레임을 모두 확인해서 신원을 돌려준다.

        통신 실패, 오류 응답, 형식이 틀린 응답, 클레임이 하나라도 맞지 않는 경우에 모두
        LoginFailedError 하나만 낸다.
        """
```

이 파일에는 선언만 둔다(TDD 가드가 테스트를 요구하지 않는 파일이다). `email_verified`가 false인 신원을 거르는 것은 어댑터가 아니라 service의 일이다. 어댑터는 Google이 준 값을 그대로 돌려준다.

### 2. 임의의 값, 해시, 비교 — `app/core/security.py`

```python
def new_token() -> str:
    """secrets.token_urlsafe(32). 로그인 상태의 쿠키 값, state, nonce, code_verifier를 모두 이것으로 만든다."""

def hash_token(token: str) -> str:
    """SHA-256의 16진수 소문자 문자열. login_sessions.token_hash에 넣는 값이다."""

def secure_equals(left: str, right: str) -> bool:
    """hmac.compare_digest로 비교한다. 어느 한쪽이라도 빈 문자열이면 False다."""
```

- **임의의 값을 만드는 곳은 `new_token()` 하나뿐이다.** 이후 step의 service는 이 함수를 `security.new_token()`처럼 모듈을 거쳐 부른다(`from app.core.security import new_token`으로 이름을 가져오지 않는다). 이유: TC-1.3.17의 뒷부분은 `app.core.security.new_token`을 가짜로 바꾸고 로그인 응답의 값이 모두 가짜가 낸 값인지 본다. 이름을 가져와 버리면 가짜로 바꿔도 반영되지 않는다. 이 이유를 함수의 독스트링에 적어 둬라.
- `secure_equals`는 `state`와 `nonce`의 비교에 쓴다. 빈 값끼리 같다고 판정하면 `state`의 확인이 무력해진다(ADR-027).

### 3. ruff 규칙 — `pyproject.toml`

`[tool.ruff.lint]`의 `select`에 `S311`을 더한다(ADR-027). 다른 규칙은 바꾸지 마라.

### 4. 테스트

- `tests/core/test_security.py`
  - TC-1.3.17 앞부분: `new_token()`을 1000번 불러 모두 `^[A-Za-z0-9_-]{43}$`에 맞고 서로 다른지. 그리고 `secrets.token_urlsafe`를 부른 인자를 기록하는 가짜로 바꾼 뒤 한 번 더 불러, `32`로 불렀는지와 그 반환값을 그대로 돌려주는지.
  - `hash_token`이 `hashlib.sha256(token.encode()).hexdigest()`와 같고, 입력과 다른지.
  - `secure_equals`: 같은 값은 True, 다른 값은 False, `("", "")`, `("abc", "")`, `("", "abc")`는 모두 False.
  - `app/` 아래에서 `secrets`나 `random` 모듈을 import하는 파일이 `app/core/security.py` 하나뿐인지를 소스의 import 구문(AST)으로 확인한다. 이유: 다른 파일이 따로 임의의 값을 만들면 TC-1.3.17의 "만드는 곳이 둘 이상이면 실패"를 지킬 수 없다.
- `tests/infra/test_ruff_config.py`: 임시 폴더에 `random.random()`을 쓰는 파이썬 파일을 만들고, 이 레포의 `pyproject.toml` 설정으로 `ruff check`를 돌려 `S311`이 보고되는지 확인한다. 설정 파일에 문자열이 있는지만 보지 말고 실제로 ruff를 돌려라. 이유: `select`가 아닌 곳에 적거나 `ignore`에 함께 적어도 문자열 검사는 통과한다.

### 5. 순서 — RED 커밋을 남긴다

1. 위 테스트를 먼저 쓰고, `security.py`의 세 함수는 시그니처만 두고 `NotImplementedError`를 내게 한다(`ports.py`는 선언이므로 처음부터 완성해도 된다).
2. 테스트가 실패하는 것을 눈으로 확인한다.
3. `test(1-login-allowlist): RED — 로그인의 임의의 값과 해시와 비교`로 커밋한다.
4. 구현해서 초록으로 만든다.

## Acceptance Criteria

```bash
uv run pytest tests/core/test_security.py tests/infra/test_ruff_config.py -v
scripts/check.sh
```

**반증 조건** — 아래의 틀린 구현으로도 초록이면 그 테스트가 틀린 것이다.

- `new_token()`이 `secrets.token_urlsafe(16)`(22자)이나 `uuid4().hex`를 써도 초록이면 TC-1.3.17의 앞부분이 틀렸다.
- `secure_equals("", "")`가 True여도 초록이면 그 테스트가 틀렸다.
- `secure_equals`가 `==`로 비교해도 초록인 것은 피할 수 없다. 대신 `hmac.compare_digest`를 쓰는지는 리뷰가 본다.
- `app/auth/` 아래의 파일이 `import secrets`를 해도 초록이면 import 검사 테스트가 틀렸다.
- `S311`을 `select`가 아니라 `ignore`에 넣어도 초록이면 ruff 설정 테스트가 틀렸다.

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

- 임의의 값을 `random`, `uuid`, 시각으로 만들지 마라. 이유: 추측할 수 있는 값이면 로그인 상태를 가로챌 수 있다(ADR-027).
- `ports.py`에 Google의 주소, httpx, 설정 클래스를 넣지 마라. 이유: 포트는 기술의 이름을 모르는 약속이다(ARCHITECTURE.md 8절). Google에 관한 것은 다음 step의 어댑터에 둔다.
- `ports.py`에 다른 포트(`VectorSearch`, `ObjectStorage`, `BundleReader`)를 미리 만들지 마라. 이유: 그 기능의 Epic이 필요한 모양으로 만든다.
- ruff의 다른 규칙을 더하거나 빼지 마라. 이유: 이 step이 정한 범위는 `S311` 하나다.
- 기존 테스트를 깨뜨리지 마라
- `MANUAL.md`의 항목을 체크하지 마라. 이유: 그 항목은 사람이 직접 본 것만 체크한다.
