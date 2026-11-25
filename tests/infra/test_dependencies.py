"""의존성의 테스트 (ADR-028, ADR-031).

서버의 이미지는 `uv sync --locked --no-dev`로 운영 의존성만 설치한다(Dockerfile). 그래서 서버가
import하는 패키지가 개발 의존성에만 있으면, 테스트는 초록인데 운영 서버는 import에서 죽는다.
Google 어댑터(app/adapters/google.py)는 httpx로 Google과 통신하므로 httpx가 운영 의존성이어야 한다.

로컬 로그인 점검은 브라우저를 자동화하지 않는다(ADR-031). 그래서 브라우저 자동화 도구는 어느
의존성에도 두지 않는다.
"""

import re
import tomllib
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PROJECT_NAME = "diegesis-be"

# Google과의 통신을 맡길 수 있는 라이브러리. ADR-028은 이것들을 쓰지 않고 httpx와 표준 라이브러리로
# 직접 구현하기로 했다. 라이브러리의 기본값(서명 확인을 위한 공개키 받아 오기 등)에 클레임 확인을
# 맡기지 않기 위해서다.
OAUTH_OR_JWT_LIBRARIES = frozenset(
    {
        "authlib",
        "pyjwt",
        "python-jose",
        "jwcrypto",
        "joserfc",
        "google-auth",
        "oauthlib",
        "requests-oauthlib",
    }
)


def normalize(name: str) -> str:
    """패키지 이름을 PEP 503의 방식으로 맞춘다. `Py_JWT`와 `py-jwt`는 같은 패키지다."""
    return re.sub(r"[-_.]+", "-", name).lower()


def requirement_name(requirement: str) -> str:
    """`sqlalchemy[asyncio]>=2.1.9` 같은 요구 사항에서 패키지 이름만 꺼낸다."""
    match = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)", requirement)
    assert match, requirement
    return normalize(match.group(1))


def load_toml(name: str) -> dict[str, Any]:
    return tomllib.loads((REPO_ROOT / name).read_text(encoding="utf-8"))


def runtime_dependencies() -> set[str]:
    return {
        requirement_name(item) for item in load_toml("pyproject.toml")["project"]["dependencies"]
    }


def dev_dependencies() -> set[str]:
    group = load_toml("pyproject.toml").get("dependency-groups", {}).get("dev", [])
    # `{include-group = ...}` 같은 표는 패키지가 아니므로 건너뛴다.
    return {requirement_name(item) for item in group if isinstance(item, str)}


def locked_runtime_dependencies() -> set[str]:
    """uv.lock이 이 프로젝트의 운영 의존성으로 적어 둔 패키지. `--no-dev`가 설치하는 것이다."""
    packages = [
        package for package in load_toml("uv.lock")["package"] if package["name"] == PROJECT_NAME
    ]
    assert len(packages) == 1, packages
    return {normalize(dependency["name"]) for dependency in packages[0].get("dependencies", [])}


@pytest.mark.parametrize(
    ("requirement", "name"),
    [
        ("httpx>=0.28.1", "httpx"),
        ("sqlalchemy[asyncio]>=2.1.9", "sqlalchemy"),
        ("Py_JWT==2.0", "py-jwt"),
        # 이름에 httpx가 들어 있을 뿐인 다른 패키지를 httpx로 세지 않는다.
        ("httpx-sse>=0.4", "httpx-sse"),
    ],
)
def test_requirement_name_extracts_the_normalized_package_name(requirement: str, name: str) -> None:
    assert requirement_name(requirement) == name


def test_httpx_is_a_runtime_dependency() -> None:
    assert "httpx" in runtime_dependencies()
    # 버전의 하한은 pyproject.toml의 한 곳에만 적는다(docs/DEVELOPMENT.md 1절).
    assert "httpx" not in dev_dependencies()


def test_lockfile_installs_httpx_without_dev_dependencies() -> None:
    # pyproject.toml만 고치고 uv.lock을 다시 만들지 않으면 이미지의 `uv sync --locked`가 실패한다.
    # 이 테스트는 이미지가 실제로 설치하는 목록(uv.lock의 운영 의존성)에 httpx가 있는지 본다.
    assert "httpx" in locked_runtime_dependencies()


def test_no_oauth_or_jwt_library_is_a_dependency() -> None:
    dependencies = runtime_dependencies() | dev_dependencies() | locked_runtime_dependencies()

    assert OAUTH_OR_JWT_LIBRARIES.isdisjoint(dependencies), OAUTH_OR_JWT_LIBRARIES & dependencies


# 브라우저를 열거나 조종하는 도구. Google은 자동화로 조종되는 브라우저의 로그인을 막는다(ADR-031).
BROWSER_AUTOMATION = frozenset({"playwright", "selenium", "pyppeteer", "undetected-chromedriver"})


def test_no_browser_automation_tool_is_a_dependency() -> None:
    dependencies = runtime_dependencies() | dev_dependencies() | locked_runtime_dependencies()

    assert BROWSER_AUTOMATION.isdisjoint(dependencies), BROWSER_AUTOMATION & dependencies
