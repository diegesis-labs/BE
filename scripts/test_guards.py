"""셸로 쓴 가드와 래퍼의 테스트를 pytest에서 함께 돌린다.

`scripts/check.sh` 하나로 전부 덮이게 하려는 것이다. 따로 돌려야 하는 테스트는 잊힌다.
새 `*.test.sh`를 `scripts/` 아래에 두면 자동으로 포함된다.
"""

import os
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
        "harness-pr.test.sh",
        "execute-smoke.test.sh",
    } <= names


@pytest.mark.parametrize("script", SHELL_TESTS, ids=lambda p: p.name)
def test_shell_test_passes(script: Path):
    # 무인 세션의 변수를 일부러 흘려 넣는다. 셸 테스트는 이 변수들을 스스로 지워야 한다.
    # 지우지 않으면 무인 세션 안에서만 검사가 빨개져, 모든 step이 이유 없이 되돌려진다.
    env = os.environ | {
        "HARNESS_RUN": "1",
        "HARNESS_REVIEW": "1",
        "HARNESS_FIX": "1",
        "HARNESS_MODEL": "leaked-model",
        "HARNESS_MAX_REVIEW_ROUNDS": "9",
        "HARNESS_CHECK_CMD": "exit 1",
    }
    result = subprocess.run(
        ["bash", str(script)], capture_output=True, text=True, timeout=300, env=env
    )
    assert result.returncode == 0, result.stdout[-4000:] + result.stderr[-2000:]
