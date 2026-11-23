"""`scripts/compose-smoke.sh`와 `.gitattributes`의 테스트 (TC-0.5.5).

스크립트를 실제로 돌려서 다섯 가지를 확인하는 것(TC-0.5.1)은 스크립트 자신이 한다.
이 파일은 Docker 없이 돈다. 스크립트의 내용을 읽고(주석 줄은 뺀다), 가짜 `docker`를 앞세워
스크립트를 실행해서 어떤 docker 명령을 부르는지를 본다.
"""

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "compose-smoke.sh"
GITATTRIBUTES = REPO_ROOT / ".gitattributes"

PROJECT = "diegesis-smoke"
OTHER_PROJECT = "other-project"

# 가짜 docker. 받은 인자를 한 줄에 하나의 호출로 기록한다. 인자 사이는 \037(단위 구분자)로 나눈다.
# `docker info`만 성공하고 나머지는 모두 실패한다. 그래서 스크립트는 Docker가 있다고 보고 compose를
# 부른 뒤, 그것이 실패하면 정리하고 끝난다. 실제 컨테이너는 하나도 뜨지 않는다.
FAKE_DOCKER = """#!/bin/sh
{ for arg in "$@"; do printf '%s\\037' "$arg"; done; printf '\\n'; } >> "$FAKE_DOCKER_LOG"
case "$1" in
  info) exit 0 ;;
esac
exit 1
"""


def code_lines() -> list[str]:
    """스크립트에서 빈 줄과 주석 줄을 뺀 줄."""
    lines = []
    for raw in SCRIPT.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            lines.append(line)
    return lines


def project_variable() -> str:
    """프로젝트 이름을 담은 변수의 이름.

    그 값이 `diegesis-smoke`인 대입이 정확히 하나 있어야 한다.
    """
    assignment = re.compile(r"^(?:readonly\s+|declare\s+-r\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$")
    found = [
        (match.group(1), match.group(2))
        for line in code_lines()
        if (match := assignment.match(line)) and PROJECT in match.group(2)
    ]
    assert len(found) == 1, f"`{PROJECT}`를 대입하는 줄이 정확히 하나가 아니다: {found}"
    return found[0][0]


@dataclass
class Run:
    returncode: int
    output: str
    calls: list[list[str]]


def run_with_fake_docker(tmp_path: Path, *args: str, env: dict[str, str] | None = None) -> Run:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "docker"
    fake.write_text(FAKE_DOCKER, encoding="utf-8")
    fake.chmod(0o755)
    log = tmp_path / "docker-calls.log"

    result = subprocess.run(
        [str(SCRIPT), *args],
        env={
            "PATH": os.pathsep.join([str(bin_dir), "/usr/bin", "/bin"]),
            "HOME": str(tmp_path),
            "FAKE_DOCKER_LOG": str(log),
            **(env or {}),
        },
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
    )
    calls = []
    if log.exists():
        for line in log.read_text(encoding="utf-8").splitlines():
            calls.append(line.split("\x1f")[:-1])
    return Run(result.returncode, result.stdout + result.stderr, calls)


def compose_calls(calls: list[list[str]]) -> list[list[str]]:
    return [call for call in calls if call[:1] == ["compose"]]


def uses_project(call: list[str], project: str) -> bool:
    for flag, value in zip(call, call[1:], strict=False):
        if flag in {"-p", "--project-name"} and value == project:
            return True
    return f"--project-name={project}" in call


def is_direct_build(call: list[str]) -> bool:
    words = [word for word in call if not word.startswith("-")]
    return words[:1] == ["build"] or words[:2] in (
        ["buildx", "build"],
        ["buildx", "bake"],
        ["image", "build"],
        ["builder", "build"],
    )


# --- 스크립트의 형태 ---------------------------------------------------------


def test_script_is_executable_bash_with_strict_mode() -> None:
    assert os.access(SCRIPT, os.X_OK), "scripts/compose-smoke.sh에 실행 권한이 없다"
    first_line = SCRIPT.read_text(encoding="utf-8").splitlines()[0]
    assert first_line == "#!/usr/bin/env bash"
    assert "set -euo pipefail" in code_lines()


# --- TC-0.5.5: 이미지는 compose로만 빌드한다 ----------------------------------

DIRECT_BUILD = re.compile(
    r"(^|[^\w./-])docker\s+(buildx\s+(build|bake)|image\s+build|builder\s+build|build)\b"
)


def test_script_never_calls_docker_build_directly() -> None:
    offending = [line for line in code_lines() if DIRECT_BUILD.search(line)]
    assert not offending, f"docker build를 직접 부른다(docs/DECISIONS.md의 D-41): {offending}"


def test_script_builds_images_with_compose() -> None:
    builds = [
        line
        for line in code_lines()
        if re.search(r"\bup\b.*\s--build\b", line) or re.search(r"\bcompose\b.*\sbuild\b", line)
    ]
    assert builds, "이미지를 compose로 빌드하는 줄(up --build 또는 compose build)이 없다"


# --- TC-0.5.5: 프로젝트 이름은 고정된 상수다 ----------------------------------


def test_project_name_is_a_readonly_literal() -> None:
    name = project_variable()
    assignments = [line for line in code_lines() if re.match(rf"^(readonly\s+)?{name}=", line)]
    assert len(assignments) == 1, f"{name}에 대입하는 줄이 둘 이상이다: {assignments}"
    value = assignments[0].split("=", 1)[1]
    # `${SMOKE_PROJECT:-diegesis-smoke}`나 `${1:-diegesis-smoke}`처럼
    # 바깥에서 받는 값이면 실패해야 한다.
    assert value.strip("\"'") == PROJECT, f"프로젝트 이름이 상수가 아니다: {assignments[0]}"
    assert any(re.match(rf"^(readonly|declare\s+-r)\s+{name}\b", line) for line in code_lines()), (
        f"{name}이 readonly가 아니다"
    )


def test_every_compose_call_in_script_passes_fixed_project_name() -> None:
    name = project_variable()
    flag = re.compile(rf"(-p|--project-name)[\s=]\"?\$(\{{{name}\}}|{name}\b)\"?")
    calls = [line for line in code_lines() if re.search(r"\bdocker([\s-]+)compose\b", line)]
    assert calls, "docker compose를 부르는 줄이 없다"
    for line in calls:
        assert flag.search(line), f"프로젝트 이름을 {name}으로 넘기지 않는 compose 호출이다: {line}"


def test_script_does_not_read_compose_project_name() -> None:
    assert not any("COMPOSE_PROJECT_NAME" in line for line in code_lines())


def test_script_rejects_arguments(tmp_path: Path) -> None:
    run = run_with_fake_docker(tmp_path, OTHER_PROJECT)

    assert run.returncode != 0, run.output
    assert not any(OTHER_PROJECT in call for call in run.calls), run.calls


def test_compose_calls_use_fixed_project_name_whatever_environment_says(tmp_path: Path) -> None:
    hostile = {
        "COMPOSE_PROJECT_NAME": OTHER_PROJECT,
        "PROJECT": OTHER_PROJECT,
        "PROJECT_NAME": OTHER_PROJECT,
        "SMOKE_PROJECT": OTHER_PROJECT,
    }
    run = run_with_fake_docker(tmp_path, env=hostile)

    # 가짜 docker의 compose는 실패하므로 스크립트도 실패로 끝나야 한다.
    assert run.returncode != 0, run.output
    composes = compose_calls(run.calls)
    assert composes, f"compose를 부르지 않았다: {run.calls}\n{run.output}"
    for call in composes:
        assert uses_project(call, PROJECT), f"-p {PROJECT} 없이 compose를 불렀다: {call}"
        assert OTHER_PROJECT not in call
    # 이미지는 compose가 빌드하고(up --build), 실패해도 마지막에 볼륨까지 내린다.
    assert any("up" in call and "--build" in call for call in composes), composes
    downs = [call for call in composes if "down" in call]
    assert downs, f"실패한 뒤에 내리지 않았다: {composes}"
    assert any("-v" in call or "--volumes" in call for call in downs), downs
    assert not any(is_direct_build(call) for call in run.calls), run.calls


# --- 스크립트가 확인하는 것 (TC-0.5.1, docs/DECISIONS.md의 D-39) ---------------


def test_script_checks_vector_extension_through_db_service() -> None:
    # /api/health만 보면 서버와 데이터베이스의 연결을 확인하지 못한다.
    queries = [line for line in code_lines() if "pg_extension" in line and "vector" in line]
    assert queries, "데이터베이스에 vector 확장이 있는지 확인하지 않는다"
    assert any(re.search(r"\bexec\s+-T\s+db\s+psql\b", line) for line in code_lines())


def test_script_compares_health_body_exactly() -> None:
    assert any("/api/health" in line for line in code_lines())
    assert any('\'{"status":"ok"}\'' in line for line in code_lines())


# --- TC-0.5.5: .gitattributes -----------------------------------------------


def test_gitattributes_pins_shell_scripts_to_lf() -> None:
    rules = [
        line.split()
        for line in GITATTRIBUTES.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    assert ["*.sh", "text", "eol=lf"] in rules, rules


@pytest.mark.parametrize("path", ["scripts/compose-smoke.sh", "some/new/dir/new-script.sh"])
def test_git_applies_lf_to_shell_scripts(path: str) -> None:
    # 뒤에 오는 규칙이 덮어쓰지 않는지 git이 실제로 적용하는 값으로 확인한다.
    result = subprocess.run(
        ["git", "check-attr", "text", "eol", "--", path],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert f"{path}: eol: lf" in result.stdout, result.stdout
    assert f"{path}: text: set" in result.stdout, result.stdout
