"""공통 층(app/core/)의 의존 방향 (docs/ARCHITECTURE.md 8절, ADR-029).

app/core/는 기능 폴더(app/auth/, app/health/ 등)와 어댑터(app/adapters/)를 import하지 않는다.
관문처럼 기능 폴더의 저장소가 필요한 것은 app/core/ports.py에 포트로 선언하고, 구현체는
app/main.py의 create_app()이 넣는다. core가 기능 폴더를 가져오면 앞으로 더할 기능 폴더들이 모두
core를 거쳐 auth에 묶이기 때문이다.

이 테스트의 대상은 한 모듈이 아니라 패키지 `app.core` 전체이므로, 그 패키지를 나타내는 파일
`app/core/__init__.py`의 자리에 둔다(docs/DEVELOPMENT.md 4.2절, 2차 리뷰 ARC-2).
"""

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CORE_DIR = REPO_ROOT / "app" / "core"
CORE_PACKAGE = "app.core"


# 문자열로 모듈을 가져오는 함수(2차 리뷰 ARC-1). 인자가 문자열 상수가 아니면 무엇을 가져오는지
# 정적으로 알 수 없으므로, 아래 이름으로 세어 검사가 닫힌 채 실패하게 한다.
DYNAMIC_IMPORT = "importlib.import_module"
DYNAMIC_IMPORT_BUILTIN = "__import__"
UNKNOWN_DYNAMIC_IMPORT = "<문자열 상수가 아닌 동적 import>"


def resolve_relative(module: str, level: int, package: str) -> str:
    """`from ..a import b`처럼 점 level개로 시작하는 이름을 package 기준의 절대 이름으로 바꾼다."""
    parts = package.split(".")
    base = parts[: len(parts) - (level - 1)]
    return ".".join([*base, *([module] if module else [])])


def _dynamic_import_name(node: ast.Call, aliases: dict[str, str], package: str) -> str | None:
    """node가 문자열로 모듈을 가져오는 호출이면 가져오는 모듈의 절대 이름. 아니면 None이다."""
    func = node.func
    if isinstance(func, ast.Name):
        target = aliases.get(func.id, func.id)
    elif isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        target = f"{aliases.get(func.value.id, func.value.id)}.{func.attr}"
    else:
        return None
    if target not in {DYNAMIC_IMPORT, DYNAMIC_IMPORT_BUILTIN}:
        return None
    if not node.args:
        return UNKNOWN_DYNAMIC_IMPORT
    name = node.args[0]
    if not (isinstance(name, ast.Constant) and isinstance(name.value, str)):
        return UNKNOWN_DYNAMIC_IMPORT
    module = name.value
    if target == DYNAMIC_IMPORT and module.startswith("."):
        # import_module(".x", "a.b")처럼 둘째 인자(package)를 기준으로 푼다. 없으면 이 모듈의
        # 패키지를 기준으로 푼다.
        anchor = node.args[1] if len(node.args) > 1 else None
        for keyword in node.keywords:
            if keyword.arg == "package":
                anchor = keyword.value
        if anchor is not None and not (
            isinstance(anchor, ast.Constant) and isinstance(anchor.value, str)
        ):
            return UNKNOWN_DYNAMIC_IMPORT
        base = anchor.value if isinstance(anchor, ast.Constant) else package
        level = len(module) - len(module.lstrip("."))
        return resolve_relative(module.lstrip("."), level, str(base))
    return module


def imported_modules(source: str, package: str) -> set[str]:
    """소스가 가져오는 모듈과 이름의 전체 이름. `from a.b import c`는 `a.b.c`로 센다.

    상대 경로의 import는 package를 기준으로 절대 이름으로 바꾼다. 함수 안의 import도 센다.
    `importlib.import_module("a.b")`와 `__import__("a.b")`처럼 문자열로 가져오는 것도 `a.b`로 센다.
    `import importlib as il`이나 `from importlib import import_module as load`로 이름을 바꿔도 센다.
    """
    tree = ast.parse(source)
    # import한 이름이 가리키는 전체 이름. `from importlib import import_module as load`면
    # load → importlib.import_module.
    aliases: dict[str, str] = {}
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name)
                if alias.asname:
                    aliases[alias.asname] = alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                module = resolve_relative(node.module or "", node.level, package)
            else:
                module = node.module or ""
            for alias in node.names:
                found.add(f"{module}.{alias.name}")
                aliases[alias.asname or alias.name] = f"{module}.{alias.name}"
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _dynamic_import_name(node, aliases, package)
            if name is not None:
                found.add(name)
    return found


def is_outside_core(name: str) -> bool:
    """app/ 아래에서 app/core/ 밖의 것인가. 무엇을 가져오는지 모르는 동적 import도 밖으로 본다."""
    if name == UNKNOWN_DYNAMIC_IMPORT:
        return True
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
        # 문자열로 가져오기(2차 리뷰 ARC-1)
        (
            "import importlib\ndef f():\n    return importlib.import_module('app.auth.repository')",
            {"app.auth.repository"},
        ),
        ("import importlib as il\nil.import_module('app.health')", {"app.health"}),
        (
            "from importlib import import_module as load\nload('app.adapters.google')",
            {"app.adapters.google"},
        ),
        ("__import__('app.auth.repository', fromlist=['x'])", {"app.auth.repository"}),
        ("import importlib\nimportlib.import_module('..auth', 'app.core')", {"app.auth"}),
        (
            "import importlib\nimportlib.import_module('.repository', package='app.auth')",
            {"app.auth.repository"},
        ),
        ("import importlib\nimportlib.import_module(NAME)", {UNKNOWN_DYNAMIC_IMPORT}),
        ("__import__(NAME)", {UNKNOWN_DYNAMIC_IMPORT}),
        ("import importlib\nimportlib.import_module('app.core.ports')", set()),
        ("import importlib\nimportlib.import_module('json')", set()),
        ("def import_module(name):\n    return name\nimport_module('app.auth')", set()),
    ],
)
def test_outside_core_detector(source: str, outside: set[str]) -> None:
    # 아래 검사가 import를 놓치면 core가 기능 폴더를 가져와도 초록이 된다.
    names = imported_modules(source, CORE_PACKAGE)
    assert {name for name in names if is_outside_core(name)} == outside


def test_relative_import_in_core_subpackage_is_resolved_from_that_subpackage() -> None:
    # app/core/sub/x.py의 `from ..auth`는 app.core.auth이고 `from ...auth`가 app.auth다.
    names = imported_modules("from ..auth import a\nfrom ...auth import b", "app.core.sub")
    assert {name for name in names if is_outside_core(name)} == {"app.auth.b"}


def core_modules(root: Path = CORE_DIR) -> list[Path]:
    """root 아래의 모든 모듈. 하위 패키지의 모듈도 포함한다(2차 리뷰 ARC-1)."""
    return sorted(root.rglob("*.py"))


def module_package(path: Path) -> str:
    """모듈이 속한 패키지의 이름. 상대 경로의 import를 풀 때 기준이 된다.

    `app/core/gate.py`와 `app/core/__init__.py`는 `app.core`이고, `app/core/sub/x.py`는
    `app.core.sub`다.
    """
    return ".".join(path.relative_to(REPO_ROOT).parts[:-1])


def test_core_modules_include_modules_of_subpackages(tmp_path: Path) -> None:
    for name in ("gate.py", "sub/__init__.py", "sub/lookup.py", "sub/deeper/x.py"):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text("", encoding="utf-8")

    found = [path.relative_to(tmp_path).as_posix() for path in core_modules(tmp_path)]

    assert found == ["gate.py", "sub/__init__.py", "sub/deeper/x.py", "sub/lookup.py"]


@pytest.mark.parametrize(
    ("path", "package"),
    [
        ("app/core/gate.py", "app.core"),
        ("app/core/__init__.py", "app.core"),
        ("app/core/sub/lookup.py", "app.core.sub"),
        ("app/core/sub/__init__.py", "app.core.sub"),
    ],
)
def test_module_package(path: str, package: str) -> None:
    assert module_package(REPO_ROOT / path) == package


def test_core_has_modules_to_check() -> None:
    # 경로가 틀려 아무 파일도 보지 않고 초록이 되는 것을 막는다.
    names = {path.name for path in core_modules()}
    assert {"gate.py", "ports.py", "database.py"} <= names


@pytest.mark.parametrize(
    "path", core_modules(), ids=lambda path: path.relative_to(CORE_DIR).as_posix()
)
def test_core_module_imports_nothing_outside_core(path: Path) -> None:
    names = imported_modules(path.read_text(encoding="utf-8"), module_package(path))
    assert {name for name in names if is_outside_core(name)} == set()
