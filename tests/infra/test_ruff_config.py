"""레포의 ruff 설정이 `random` 모듈로 만든 값을 잡는지의 테스트 (ADR-027의 `S311`).

설정 파일에 `S311`이라는 글자가 있는지만 보면, `select`가 아닌 곳에 적거나 `ignore`에 함께 적어도
통과한다. 그래서 `random`을 쓰는 파일을 임시 폴더에 만들고 레포의 설정으로 ruff를 실제로 돌린다.
"""

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = REPO_ROOT / "pyproject.toml"


def ruff_codes(path: Path) -> list[str]:
    """레포의 ruff 설정으로 그 파일을 검사해서 보고된 규칙 코드를 돌려준다."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--no-cache",
            "--output-format",
            "json",
            "--config",
            str(PYPROJECT),
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=path.parent,
    )
    # 위반이 있으면 1, 없으면 0이다. 그 밖의 코드는 ruff가 설정을 읽지 못한 것이다.
    assert result.returncode in (0, 1), result.stdout + result.stderr
    return [diagnostic["code"] for diagnostic in json.loads(result.stdout)]


def test_ruff_reports_s311_for_random_usage(tmp_path: Path) -> None:
    path = tmp_path / "uses_random.py"
    path.write_text("import random\n\nvalue = random.random()\n", encoding="utf-8")

    assert "S311" in ruff_codes(path)
