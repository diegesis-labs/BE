"""공통 층(app/core/)의 의존 방향 (docs/ARCHITECTURE.md 8절, ADR-029).

app/core/는 기능 폴더(app/auth/, app/health/ 등)와 어댑터(app/adapters/)를 import하지 않는다.
관문처럼 기능 폴더의 저장소가 필요한 것은 app/core/ports.py에 포트로 선언하고, 구현체는
app/main.py의 create_app()이 넣는다. core가 기능 폴더를 가져오면 앞으로 더할 기능 폴더들이 모두
core를 거쳐 auth에 묶이기 때문이다.
"""

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CORE_DIR = REPO_ROOT / "app" / "core"
CORE_PACKAGE = "app.core"


def imported_modules(source: str, package: str) -> set[str]:
    """import 구문이 가져오는 모듈과 이름의 전체 이름. `from a.b import c`는 `a.b.c`로 센다.

    상대 경로의 import는 package를 기준으로 절대 이름으로 바꾼다. 함수 안의 import도 센다.
    """
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                parts = package.split(".")
                base = parts[: len(parts) - (node.level - 1)]
                module = ".".join([*base, *([node.module] if node.module else [])])
            else:
                module = node.module or ""
            found.update(f"{module}.{alias.name}" for alias in node.names)
    return found


def is_outside_core(name: str) -> bool:
    """app/ 아래에서 app/core/ 밖의 것인가."""
    if name != "app" and not name.startswith("app."):
        return False
    return name not in {"app.core"} and not name.startswith("app.core.")


@pytest.mark.parametrize(
    ("source", "outside"),
    [
        ("from app.auth.repository import AuthRepository", {"app.auth.repository.AuthRepository"}),
        ("import app.auth.repository", {"app.auth.repository"}),
        ("from app import auth", {"app.auth"}),
        ("from ..auth import repository", {"app.auth.repository"}),
        (
            "from ..adapters.google import GoogleIdentityProvider",
            {"app.adapters.google.GoogleIdentityProvider"},
        ),
        ("def f():\n    from app.health import router\n    return router", {"app.health.router"}),
        ("from app.core.ports import LoginLookup", set()),
        ("from . import security", set()),
        ("from app.corex import thing", {"app.corex.thing"}),
        ("import appdirs", set()),
    ],
)
def test_outside_core_detector(source: str, outside: set[str]) -> None:
    # 아래 검사가 import를 놓치면 core가 기능 폴더를 가져와도 초록이 된다.
    names = imported_modules(source, CORE_PACKAGE)
    assert {name for name in names if is_outside_core(name)} == outside


def core_modules() -> list[Path]:
    return sorted(CORE_DIR.glob("*.py"))


def test_core_has_modules_to_check() -> None:
    # 경로가 틀려 아무 파일도 보지 않고 초록이 되는 것을 막는다.
    names = {path.name for path in core_modules()}
    assert {"gate.py", "ports.py", "database.py"} <= names


@pytest.mark.parametrize("path", core_modules(), ids=lambda path: path.name)
def test_core_module_imports_nothing_outside_core(path: Path) -> None:
    names = imported_modules(path.read_text(encoding="utf-8"), CORE_PACKAGE)
    assert {name for name in names if is_outside_core(name)} == set()
