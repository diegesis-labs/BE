"""새 마이그레이션 파일이 검사를 통과하는지의 테스트 (`alembic.ini`, `migrations/script.py.mako`).

`alembic revision`으로 만든 파일은 그대로 커밋된다. 그 파일이 `scripts/check.sh`의 ruff 검사를
통과하지 못하면, 마이그레이션을 만들 때마다 손으로 고쳐야 한다(docs/DEVELOPMENT.md 2절).
이 테스트는 레포의 alembic.ini로 리비전을 임시 폴더에 만들고, 레포의 ruff 설정으로 검사한다.
데이터베이스에는 접속하지 않는다.
"""

import subprocess
import sys
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import Script

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
PYPROJECT = REPO_ROOT / "pyproject.toml"


def new_revision(tmp_path: Path) -> Path:
    config = Config(str(ALEMBIC_INI))
    # 레포의 migrations/versions가 아니라 임시 폴더에 만든다.
    config.set_main_option("version_locations", str(tmp_path))
    script = command.revision(config, message="add example table", version_path=str(tmp_path))
    assert isinstance(script, Script), script
    return Path(script.path)


@pytest.mark.parametrize("ruff_args", [["check"], ["format", "--check"]], ids=["check", "format"])
def test_new_revision_passes_ruff(tmp_path: Path, ruff_args: list[str]) -> None:
    path = new_revision(tmp_path)

    result = subprocess.run(
        [sys.executable, "-m", "ruff", *ruff_args, "--config", str(PYPROJECT), str(path)],
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_new_revision_keeps_alembic_identifiers(tmp_path: Path) -> None:
    # 검사를 통과시키느라 alembic이 읽는 값을 지우면 안 된다.
    text = new_revision(tmp_path).read_text(encoding="utf-8")

    for name in ("revision", "down_revision", "branch_labels", "depends_on"):
        assert f"\n{name}: " in text, f"{name}이 없다"
    assert "def upgrade() -> None:" in text
    assert "def downgrade() -> None:" in text
