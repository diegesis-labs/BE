"""`scripts/compose-smoke.sh`와 `.gitattributes`의 테스트 (TC-0.5.5, TC-0.5.1의 판정).

스크립트를 실제로 돌려서 다섯 가지를 확인하는 것(TC-0.5.1)은 스크립트 자신이 한다.
이 파일은 Docker 없이 돈다. 스크립트의 내용을 읽고(주석 줄은 뺀다), 가짜 `docker`를 앞세워
스크립트를 실행해서 어떤 docker 명령을 부르는지를 본다. 그리고 정상인 스택을 흉내 내는 가짜
`docker`와 `curl`로, 다섯 확인이 하나씩 어긋날 때 스크립트가 0이 아닌 코드로 끝나는지 본다.
"""

import os
import re
import subprocess
import sys
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
    return run_script(tmp_path, bin_dir, *args, env=env)


def run_script(tmp_path: Path, bin_dir: Path, *args: str, env: dict[str, str] | None = None) -> Run:
    """bin_dir의 가짜 명령을 앞세워 스크립트를 돌린다. 임시 폴더(TMPDIR)도 이 테스트의 것을 쓴다."""
    log = tmp_path / "docker-calls.log"
    temp_dir = tmp_path / "tmp"
    temp_dir.mkdir(exist_ok=True)

    result = subprocess.run(
        [str(SCRIPT), *args],
        env={
            "PATH": os.pathsep.join([str(bin_dir), "/usr/bin", "/bin"]),
            "HOME": str(tmp_path),
            "TMPDIR": str(temp_dir),
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


# 정상인 스택을 흉내 내는 가짜 docker. 스크립트가 부르는 하위 명령마다 정해진 출력을 낸다.
# 환경변수(FAKE_*)로 그 출력을 바꿔서 확인 하나를 어긋나게 한다.
# api 컨테이너에서 도는 파이썬 코드 가운데 uid를 읽는 것 밖의 코드는 가짜 이미지의 파일 시스템
# (FAKE_IMAGE_ROOT)에서 실제로 돌린다. 작업 폴더는 그 아래의 app이고, 인자로 넘긴 "/"는
# 가짜 이미지의 최상위로 바꾼다. 그래서 .env를 만드는 위치로 (5)를 어긋나게 할 수 있다.
FAKE_STACK_PORT = "49153"
FAKE_STACK_DOCKER = f"""#!{sys.executable}
import os
import subprocess
import sys

args = sys.argv[1:]
with open(os.environ["FAKE_DOCKER_LOG"], "a", encoding="utf-8") as log:
    log.write("".join(arg + "\\x1f" for arg in args) + "\\n")


def say(text):
    print(text)
    sys.exit(0)


if args[:1] == ["info"]:
    sys.exit(0)
if args[:1] == ["inspect"]:
    say(os.environ.get("FAKE_MIGRATE_STATE", "exited 0"))
if args[:1] != ["compose"]:
    sys.exit(1)

rest = args[1:]
while rest[:1] in (["-p"], ["-f"], ["--env-file"]):
    rest = rest[2:]
# exec의 실행 사용자(--user, -u)는 가짜 이미지에서 뜻이 없으므로 건너뛴다.
if rest[:1] == ["exec"]:
    words = rest[1:]
    rest = ["exec"]
    while words:
        if words[0] in ("--user", "-u"):
            words = words[2:]
            continue
        rest.append(words.pop(0))
if rest[:1] == ["up"] and os.environ.get("FAKE_LOCK_DIR"):
    # 스택을 띄우는 동안 스크립트가 잠금을 쥐고 있는지 기록한다.
    with open(os.environ["FAKE_LOCK_LOG"], "a", encoding="utf-8") as log:
        log.write(("held" if os.path.isdir(os.environ["FAKE_LOCK_DIR"]) else "free") + "\\n")
if rest[:1] in (["down"], ["up"]):
    sys.exit(0)
if rest[:4] == ["ps", "--all", "--quiet", "migrate"]:
    say("fake-migrate-container")
if rest[:3] == ["port", "api", "8080"]:
    say("0.0.0.0:{FAKE_STACK_PORT}")
if rest[:4] == ["exec", "-T", "db", "psql"]:
    say(os.environ.get("FAKE_VECTOR_VERSION", "0.8.7"))
if rest[:3] == ["exec", "-T", "api"]:
    inner = rest[3:]
    if inner == ["pwd"]:
        say("/app")
    if inner[:2] == ["python", "-c"]:
        code = inner[2]
        if "Uid:" in code:
            say(os.environ.get("FAKE_API_UIDS", "10001 10001 10001 10001"))
        root = os.environ["FAKE_IMAGE_ROOT"]
        extra = [root if arg == "/" else arg for arg in inner[3:]]
        result = subprocess.run(
            [sys.executable, "-c", code, *extra], cwd=os.path.join(root, "app")
        )
        sys.exit(result.returncode)
sys.exit(1)
"""

# 가짜 curl. 받은 주소를 기록하고, 헬스체크의 본문을 낸다.
FAKE_STACK_CURL = f"""#!{sys.executable}
import os
import sys

with open(os.environ["FAKE_CURL_LOG"], "a", encoding="utf-8") as log:
    log.write(sys.argv[-1] + "\\n")
sys.stdout.write(os.environ.get("FAKE_HEALTH_BODY", '{{"status":"ok"}}'))
"""


@dataclass
class StackRun(Run):
    curl_urls: list[str]


def make_fake_image(tmp_path: Path) -> Path:
    """가짜 api 이미지의 파일 시스템. 작업 폴더(/app)와 파이썬이 깔린 폴더가 있다."""
    root = tmp_path / "image"
    (root / "app" / "app").mkdir(parents=True)
    (root / "usr" / "local" / "lib" / "python3").mkdir(parents=True)
    return root


def run_against_fake_stack(
    tmp_path: Path, image_root: Path, env: dict[str, str] | None = None
) -> StackRun:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, content in (("docker", FAKE_STACK_DOCKER), ("curl", FAKE_STACK_CURL)):
        fake = bin_dir / name
        fake.write_text(content, encoding="utf-8")
        fake.chmod(0o755)
    curl_log = tmp_path / "curl-calls.log"
    run = run_script(
        tmp_path,
        bin_dir,
        env={"FAKE_IMAGE_ROOT": str(image_root), "FAKE_CURL_LOG": str(curl_log), **(env or {})},
    )
    urls = curl_log.read_text(encoding="utf-8").splitlines() if curl_log.exists() else []
    return StackRun(run.returncode, run.output, run.calls, urls)


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


# --- TC-0.5.1: 다섯 확인이 실제로 판정하는가 ---------------------------------------


def test_script_passes_when_every_check_holds(tmp_path: Path) -> None:
    run = run_against_fake_stack(tmp_path, make_fake_image(tmp_path))

    assert run.returncode == 0, run.output
    assert "스모크 통과" in run.output
    for number in range(1, 6):
        assert f"확인: ({number})" in run.output, run.output
    # (3)은 compose가 알려 준 호스트 포트로 요청한다.
    assert run.curl_urls == [f"http://127.0.0.1:{FAKE_STACK_PORT}/api/health"]


@pytest.mark.parametrize(
    ("number", "env"),
    [
        pytest.param(1, {"FAKE_MIGRATE_STATE": "exited 1"}, id="1-migrate-failed"),
        pytest.param(1, {"FAKE_MIGRATE_STATE": "running 0"}, id="1-migrate-not-exited"),
        pytest.param(2, {"FAKE_VECTOR_VERSION": ""}, id="2-no-vector-extension"),
        pytest.param(3, {"FAKE_HEALTH_BODY": '{"status":"ok","db":"ok"}'}, id="3-health-body"),
        pytest.param(4, {"FAKE_API_UIDS": "0 0 0 0"}, id="4-runs-as-root"),
        pytest.param(4, {"FAKE_API_UIDS": "10001 10001 0 10001"}, id="4-saved-uid-is-root"),
    ],
)
def test_script_fails_when_one_check_does_not_hold(
    tmp_path: Path, number: int, env: dict[str, str]
) -> None:
    run = run_against_fake_stack(tmp_path, make_fake_image(tmp_path), env)

    assert run.returncode != 0, run.output
    assert f"스모크 실패: ({number})" in run.output, run.output
    assert "스모크 통과" not in run.output


def test_script_fails_when_env_file_is_in_workdir(tmp_path: Path) -> None:
    image_root = make_fake_image(tmp_path)
    (image_root / "app" / ".env").write_text("DATABASE_URL=x\n", encoding="utf-8")

    run = run_against_fake_stack(tmp_path, image_root)

    assert run.returncode != 0, run.output
    assert "스모크 실패: (5)" in run.output, run.output
    assert "스모크 통과" not in run.output


@pytest.mark.parametrize(
    "location",
    [
        "app/app/.env",
        "usr/local/lib/python3/.env",
        "root/.env",
    ],
)
def test_script_fails_when_env_file_is_anywhere_in_image(tmp_path: Path, location: str) -> None:
    # TC-0.5.1 (5)는 작업 폴더가 아니라 api 이미지 전체에 .env가 없는지를 본다.
    image_root = make_fake_image(tmp_path)
    env_file = image_root / location
    env_file.parent.mkdir(parents=True, exist_ok=True)
    env_file.write_text("DATABASE_URL=x\n", encoding="utf-8")

    run = run_against_fake_stack(tmp_path, image_root)

    assert run.returncode != 0, run.output
    assert "스모크 실패: (5)" in run.output, run.output
    assert location in run.output, "어디에서 .env를 찾았는지 알리지 않는다"
    assert "스모크 통과" not in run.output


# --- 스모크 두 개가 겹치지 않는다 ------------------------------------------------
# 모든 worktree가 같은 프로젝트 이름(diegesis-smoke)을 쓰므로, 겹쳐 돌면 서로의 컨테이너와 볼륨을
# 지운다. 스크립트는 임시 폴더(TMPDIR)에 잠금 폴더를 만들어 한 번에 하나만 돌게 한다.


def lock_dir(tmp_path: Path) -> Path:
    return tmp_path / "tmp" / f"{PROJECT}.lock"


def lock_env(tmp_path: Path) -> dict[str, str]:
    return {"FAKE_LOCK_DIR": str(lock_dir(tmp_path)), "FAKE_LOCK_LOG": str(tmp_path / "lock.log")}


def test_script_holds_the_lock_while_running_and_releases_it(tmp_path: Path) -> None:
    run = run_against_fake_stack(tmp_path, make_fake_image(tmp_path), lock_env(tmp_path))

    assert run.returncode == 0, run.output
    assert (tmp_path / "lock.log").read_text(encoding="utf-8").splitlines() == ["held"]
    assert not lock_dir(tmp_path).exists(), "끝난 뒤에도 잠금이 남았다"


def test_script_releases_the_lock_when_a_check_fails(tmp_path: Path) -> None:
    env = {**lock_env(tmp_path), "FAKE_API_UIDS": "0 0 0 0"}

    run = run_against_fake_stack(tmp_path, make_fake_image(tmp_path), env)

    assert run.returncode != 0, run.output
    assert (tmp_path / "lock.log").read_text(encoding="utf-8").splitlines() == ["held"]
    assert not lock_dir(tmp_path).exists(), "실패한 뒤에 잠금이 남았다"


def test_script_refuses_while_another_smoke_holds_the_lock(tmp_path: Path) -> None:
    lock = lock_dir(tmp_path)
    lock.mkdir(parents=True)
    # 살아 있는 프로세스(이 테스트)가 잠금을 쥐고 있다.
    holder = f"{os.getpid()}\n"
    (lock / "pid").write_text(holder, encoding="utf-8")

    run = run_against_fake_stack(tmp_path, make_fake_image(tmp_path), lock_env(tmp_path))

    assert run.returncode != 0, run.output
    assert str(os.getpid()) in run.output, "누가 잠금을 쥐고 있는지 알리지 않는다"
    # 다른 스모크의 컨테이너와 볼륨을 건드리지 않고, 그 잠금도 지우지 않는다.
    assert compose_calls(run.calls) == [], run.calls
    assert (lock / "pid").read_text(encoding="utf-8") == holder


def test_script_takes_over_a_lock_left_by_a_dead_smoke(tmp_path: Path) -> None:
    # kill -9처럼 정리할 틈 없이 끝난 스모크가 남긴 잠금이다. 그 프로세스는 이미 없다.
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    lock = lock_dir(tmp_path)
    lock.mkdir(parents=True)
    (lock / "pid").write_text(f"{dead.pid}\n", encoding="utf-8")

    run = run_against_fake_stack(tmp_path, make_fake_image(tmp_path), lock_env(tmp_path))

    assert run.returncode == 0, run.output
    assert (tmp_path / "lock.log").read_text(encoding="utf-8").splitlines() == ["held"]
    assert not lock.exists()


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
