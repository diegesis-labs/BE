"""FRONTEND_URL의 모양을 판정한다."""


def check_frontend_url(value: str) -> str:
    return value


def uses_https(frontend_url: str) -> bool:
    return False
