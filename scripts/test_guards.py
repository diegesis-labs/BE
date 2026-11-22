"""셸로 쓴 가드와 래퍼의 테스트를 pytest에서 함께 돌린다.

`scripts/check.sh` 하나로 전부 덮이게 하려는 것이다. 따로 돌려야 하는 테스트는 잊힌다.
새 `*.test.sh`를 `scripts/` 아래에 두면 자동으로 포함된다.
"""

import subprocess
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent
SHELL_TESTS = sorted(SCRIPTS.rglob("*.test.sh"))


def test_shell_tests_are_collected():
    """glob이 비면 아래 테스트가 0개로 통과한다. 그 구멍을 막는다."""
    names = {p.name for p in SHELL_TESTS}
    assert {
        "bash-guard.test.sh",
        "tdd-guard.test.sh",
        "stop-check.test.sh",
        "harness-run.test.sh",
    } <= names


@pytest.mark.parametrize("script", SHELL_TESTS, ids=lambda p: p.name)
def test_shell_test_passes(script: Path):
    result = subprocess.run(["bash", str(script)], capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, result.stdout[-4000:] + result.stderr[-2000:]
