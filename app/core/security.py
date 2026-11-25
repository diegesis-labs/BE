"""로그인에 쓰는 임의의 값, 해시, 비교(ADR-027)."""


def new_token() -> str:
    raise NotImplementedError


def hash_token(token: str) -> str:
    raise NotImplementedError


def secure_equals(left: str, right: str) -> bool:
    raise NotImplementedError
