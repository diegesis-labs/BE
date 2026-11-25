"""로그인의 임의의 값, 해시, 비교의 테스트 (TC-1.3.17의 앞부분, ADR-027).

TC-1.3.17의 뒷부분(new_token을 가짜로 바꾸고 로그인 응답의 값이 모두 가짜가 낸 값인지 보는 것)은
로그인 경로가 생기는 step에서 확인한다.
"""

import ast
import hashlib
import re
import secrets
from pathlib import Path

import pytest

from app.core import security

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_DIR = REPO_ROOT / "app"

# secrets.token_urlsafe(32)는 32바이트를 패딩 없는 base64url로 바꾼 43자다.
TOKEN = re.compile(r"[A-Za-z0-9_-]{43}")

# 임의의 값을 만들 수 있는 모듈. 이 모듈을 import하는 곳이 security.py 하나뿐이어야 한다.
RANDOM_MODULES = frozenset({"secrets", "random"})


# --- TC-1.3.17 (앞부분) --------------------------------------------------------


def test_new_token_values_are_43_base64url_chars_and_distinct() -> None:
    # token_urlsafe(16)은 22자, uuid4().hex는 32자의 16진수라 걸러진다.
    values = [security.new_token() for _ in range(1000)]

    for value in values:
        assert TOKEN.fullmatch(value), value
    assert len(set(values)) == len(values)


def test_new_token_calls_token_urlsafe_with_32_and_returns_its_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int | None] = []
    fake_value = "fake-token-from-token-urlsafe"

    def fake_token_urlsafe(nbytes: int | None = None) -> str:
        calls.append(nbytes)
        return fake_value

    # 모듈의 속성을 바꾼다. security.py가 `from secrets import token_urlsafe`로 이름을 가져왔거나
    # secrets가 아닌 것으로 만들면 가짜가 불리지 않아 실패한다.
    monkeypatch.setattr(secrets, "token_urlsafe", fake_token_urlsafe)

    assert security.new_token() == fake_value
    # 인자 없이 부르면 기본 길이에 기대게 된다. 32를 명시해서 불러야 한다.
    assert calls == [32]


# --- hash_token -----------------------------------------------------------------


@pytest.mark.parametrize(
    "token",
    ["EViRNy6gNGLqNHYCTW4x_31HEbe5gZOm1Uf02Q0SiQM", "a", "로그인-상태"],
)
def test_hash_token_is_sha256_hexdigest(token: str) -> None:
    hashed = security.hash_token(token)

    assert hashed == hashlib.sha256(token.encode()).hexdigest()
    assert re.fullmatch(r"[0-9a-f]{64}", hashed), hashed
    assert hashed != token


def test_hash_token_differs_for_different_tokens() -> None:
    assert security.hash_token("token-a") != security.hash_token("token-b")


# --- secure_equals --------------------------------------------------------------


def test_secure_equals_true_for_same_value() -> None:
    value = "EViRNy6gNGLqNHYCTW4x_31HEbe5gZOm1Uf02Q0SiQM"

    # 같은 객체가 아니라 같은 내용의 다른 문자열로도 같다고 판정해야 한다.
    assert security.secure_equals(value, "".join(value)) is True


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("abc", "abd"),
        ("abc", "abcd"),
        ("abc", "ABC"),
        # 빈 값끼리 같다고 판정하면 state의 확인이 무력해진다(TC-1.3.3, ADR-027).
        ("", ""),
        ("abc", ""),
        ("", "abc"),
    ],
)
def test_secure_equals_false(left: str, right: str) -> None:
    assert security.secure_equals(left, right) is False


# --- 임의의 값을 만드는 곳은 하나뿐 ---------------------------------------------


def imported_random_modules(source: str) -> set[str]:
    """소스의 import 구문 가운데 secrets나 random을 가져오는 것의 최상위 모듈 이름."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            # `from . import random`처럼 상대 경로로 가져온 것은 이 레포의 모듈이다.
            names = [node.module]
        else:
            continue
        found.update(top for top in (name.split(".")[0] for name in names) if top in RANDOM_MODULES)
    return found


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("import secrets", {"secrets"}),
        ("import random", {"random"}),
        ("import os, secrets as s", {"secrets"}),
        ("from secrets import token_urlsafe", {"secrets"}),
        ("from random import choice", {"random"}),
        ("def f():\n    import random\n    return random.random()", {"random"}),
        ("from . import random", set()),
        ("import secretstorage, randomname", set()),
        ("from uuid import UUID", set()),
    ],
)
def test_imported_random_modules_detects_imports(source: str, expected: set[str]) -> None:
    # 아래 검사가 import를 놓치면 다른 파일이 따로 임의의 값을 만들어도 초록이 된다.
    assert imported_random_modules(source) == expected


def test_only_security_module_imports_secrets_or_random() -> None:
    importers = {
        path.relative_to(REPO_ROOT).as_posix()
        for path in APP_DIR.rglob("*.py")
        if imported_random_modules(path.read_text(encoding="utf-8"))
    }

    # 만드는 곳이 둘 이상이면 TC-1.3.17의 뒷부분이 가짜로 바꾼 함수를 거치지 않는 값을 놓친다.
    assert importers == {"app/core/security.py"}
