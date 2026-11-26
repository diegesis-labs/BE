"""포트의 자리 (docs/ARCHITECTURE.md 8절, ADR-029).

핵심 로직이 바깥 세계나 저장소에 기대하는 약속(Protocol)은 모두 app/core/ports.py에 둔다.
기능 폴더의 service가 저장소에 기대하는 AuthStore도 여기에 있다. 포트가 여러 파일에 흩어지면
무엇이 갈아 끼울 수 있는 자리인지 한눈에 보이지 않기 때문이다.
"""

import ast
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.repository import AuthRepository
from app.core.ports import AuthStore, LoginLookup

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_DIR = REPO_ROOT / "app"
PORTS_PATH = APP_DIR / "core" / "ports.py"


def protocol_classes(source: str) -> list[str]:
    """Protocol을 상속하는 클래스의 이름. `Protocol`, `typing.Protocol`, `Protocol[T]`를 센다."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.ClassDef):
            continue
        for base in node.bases:
            target = base.value if isinstance(base, ast.Subscript) else base
            if (isinstance(target, ast.Name) and target.id == "Protocol") or (
                isinstance(target, ast.Attribute) and target.attr == "Protocol"
            ):
                found.append(node.name)
                break
    return found


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("class A(Protocol):\n    pass", ["A"]),
        ("class A(typing.Protocol):\n    pass", ["A"]),
        ("class A(Protocol[T]):\n    pass", ["A"]),
        ("class A(Base, Protocol):\n    pass", ["A"]),
        ("def f():\n    class A(Protocol):\n        pass\n    return A", ["A"]),
        ("class A(Base):\n    pass", []),
        ("class Protocolish(Base):\n    pass", []),
    ],
)
def test_protocol_class_detector(source: str, expected: list[str]) -> None:
    # 아래 검사가 Protocol을 놓치면 포트를 다른 파일에 선언해도 초록이 된다.
    assert protocol_classes(source) == expected


def test_ports_module_declares_store_ports() -> None:
    # 전제: 검출기가 ports.py의 포트를 실제로 찾는다.
    assert {"AuthStore", "LoginLookup", "IdentityProvider"} <= set(
        protocol_classes(PORTS_PATH.read_text(encoding="utf-8"))
    )


def test_protocols_are_declared_only_in_ports_module() -> None:
    elsewhere = {
        str(path.relative_to(REPO_ROOT)): names
        for path in sorted(APP_DIR.rglob("*.py"))
        if path != PORTS_PATH and (names := protocol_classes(path.read_text(encoding="utf-8")))
    }
    assert elsewhere == {}


def test_auth_repository_satisfies_both_store_ports() -> None:
    """AuthRepository는 service의 AuthStore와 관문의 LoginLookup을 함께 만족한다.

    두 대입은 pyright가 구조적으로 확인한다. 메서드의 이름이나 시그니처가 어긋나면 검사가 실패한다.
    """
    repository = AuthRepository(cast(AsyncSession, object()))
    store: AuthStore = repository
    lookup: LoginLookup = repository

    assert store is lookup
