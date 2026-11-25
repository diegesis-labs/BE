"""로그인에 쓰는 임의의 값, 해시, 비교(ADR-027).

app/ 아래에서 secrets와 random을 import하는 파일은 이 모듈 하나뿐이다. 임의의 값을 만드는 곳이
둘 이상이면 TC-1.3.17이 모든 값을 이 모듈의 함수로 만들었는지 확인할 수 없다.
"""

import hashlib
import hmac
import secrets


def new_token() -> str:
    """secrets.token_urlsafe(32).

    로그인 상태의 쿠키 값, state, nonce, code_verifier를 모두 이것으로 만든다.
    256비트의 무작위 값이며 base64url 문자 43자다. random 모듈, uuid, 시각으로 만들지 않는다.
    추측할 수 있는 값이면 로그인 상태를 가로챌 수 있기 때문이다(ADR-027).

    이 함수를 부르는 쪽은 `from app.core.security import new_token`으로 이름을 가져오지 않고
    `security.new_token()`처럼 모듈을 거쳐 부른다. TC-1.3.17은 `app.core.security.new_token`을
    가짜로 바꾸고 로그인 응답의 값이 모두 가짜가 낸 값인지 보는데, 이름을 가져온 모듈에는 그 바꿈이
    반영되지 않는다. 같은 이유로 이 함수도 `secrets.token_urlsafe`를 모듈을 거쳐 부른다.
    """
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """SHA-256의 16진수 소문자 문자열. login_sessions.token_hash에 넣는 값이다.

    쿠키의 값을 데이터베이스에 그대로 저장하지 않기 위해서다(docs/ARCHITECTURE.md 6절).
    """
    return hashlib.sha256(token.encode()).hexdigest()


def secure_equals(left: str, right: str) -> bool:
    """hmac.compare_digest로 비교한다. 어느 한쪽이라도 빈 문자열이면 False다.

    state와 nonce의 비교에 쓴다. 빈 값끼리 같다고 판정하면 state의 확인이 무력해진다(ADR-027).
    compare_digest는 str을 ASCII로만 받으므로, 바이트로 바꿔서 넘긴다. 그래야 쿼리에 ASCII가 아닌
    문자가 와도 예외가 아니라 False가 된다.
    """
    if not left or not right:
        return False
    return hmac.compare_digest(left.encode(), right.encode())
