"""`.dockerignore`의 테스트 (TC-0.5.2).

`.env`가 빌드 맥락에 들어가면 공개 저장소의 이미지로 나갈 수 있다(docs/DECISIONS.md의 D-37).
"""

from fnmatch import fnmatch
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCKERIGNORE = REPO_ROOT / ".dockerignore"


def patterns() -> list[str]:
    """`.dockerignore`의 패턴. 빈 줄과 주석 줄은 뺀다. 앞뒤의 `/`는 Docker처럼 무시한다."""
    result: list[str] = []
    for raw in DOCKERIGNORE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        negated = line.startswith("!")
        body = line.removeprefix("!").strip().strip("/")
        result.append(f"!{body}" if negated else body)
    return result


def excluded(path: str) -> bool:
    """Docker의 규칙대로, 마지막으로 맞는 패턴이 그 경로를 빼는지 본다."""
    verdict = False
    for pattern in patterns():
        negated = pattern.startswith("!")
        body = pattern.removeprefix("!")
        # `**/`는 0개 이상의 폴더다. 최상위의 파일에도 맞게 앞부분을 떼어 한 번 더 본다.
        candidates = [body, body.removeprefix("**/")]
        if any(fnmatch(path, candidate) for candidate in candidates):
            verdict = not negated
    return verdict


# --- TC-0.5.2 ---------------------------------------------------------------


def test_dockerignore_lists_env_and_env_variants() -> None:
    # `.env.*`는 `.env`에 맞지 않으므로 둘이 각각 있어야 한다.
    # `.env`를 지우면 `.env.*`가 남아 있어도 이 테스트는 실패해야 한다.
    assert ".env" in patterns()
    assert ".env.*" in patterns()


@pytest.mark.parametrize("path", [".env", ".env.local", ".env.production"])
def test_env_files_are_excluded_from_build_context(path: str) -> None:
    # 뒤에 오는 `!` 패턴이 다시 넣으면 목록에 `.env`가 있어도 빌드 맥락에 들어간다.
    assert excluded(path), f"{path}가 빌드 맥락에 들어간다"


@pytest.mark.parametrize(
    "path",
    [".venv", ".git", "phases", "docs", "tests", "var", ".pytest_cache", ".ruff_cache"],
)
def test_local_only_folders_are_excluded_from_build_context(path: str) -> None:
    assert excluded(path), f"{path}가 빌드 맥락에 들어간다"


@pytest.mark.parametrize("path", ["app", "migrations", "alembic.ini", "pyproject.toml", "uv.lock"])
def test_files_needed_for_the_image_stay_in_build_context(path: str) -> None:
    # 이미지에 필요한 것까지 빼면 빌드가 실패한다. 무엇이든 빼는 `*` 하나로 초록이 되지 않게 한다.
    assert not excluded(path), f"{path}가 빌드 맥락에서 빠진다"
