"""핵심 로직이 바깥 세계에 기대하는 기능의 약속(포트). 구조는 docs/ARCHITECTURE.md 8절에 있다.

이 파일에는 선언만 둔다. 포트는 특정 기술의 이름을 알지 못하며, 실제 구현은 app/adapters/의
어댑터가 맡는다. 그 기능의 Epic이 필요한 포트만 여기에 더한다.
"""

from dataclasses import dataclass
from typing import Protocol


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
    """로그인한 사람의 신원을 확인해 주는 바깥 서비스(docs/ARCHITECTURE.md 8절).

    email_verified가 false인 신원을 거르는 것은 어댑터가 아니라 service의 일이다. 어댑터는 Google이
    준 값을 그대로 돌려준다.
    """

    def authorization_url(self, *, state: str, nonce: str, code_verifier: str) -> str:
        """Google의 인가 주소.

        state와 nonce를 붙이고, code_verifier로 만든 code_challenge(S256)를 붙인다.
        """
        ...

    async def exchange_code(
        self, *, code: str, code_verifier: str, expected_nonce: str
    ) -> Identity:
        """code를 토큰으로 바꾸고 ID 토큰의 클레임을 모두 확인해서 신원을 돌려준다.

        통신 실패, 오류 응답, 형식이 틀린 응답, 클레임이 하나라도 맞지 않는 경우에 모두
        LoginFailedError 하나만 낸다.
        """
        ...
