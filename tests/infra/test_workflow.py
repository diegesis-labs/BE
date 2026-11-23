"""`.github/workflows/ci.yml`의 테스트 (TC-0.7.1 ~ TC-0.7.5).

workflow가 GitHub에서 실제로 도는지는 여기서 판정하지 않는다. phase가 끝난 뒤 첫 PR에서
확인한다(docs/backlog/epic-0/E0-project-setup.md의 "끝나는 조건"). 이 파일은 workflow를 읽어서
단언할 수 있는 것을 본다.

버전 문자열을 이 파일에 적지 않는다. uv의 버전은 `Dockerfile`과 workflow를 둘 다 읽어서 비교한다.
버전은 docs/DEVELOPMENT.md 1절이 정한 파일에만 있어야 하기 때문이다.
"""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
DOCKERFILE = REPO_ROOT / "Dockerfile"

UV_IMAGE = "ghcr.io/astral-sh/uv"
SETUP_UV = "astral-sh/setup-uv"
LOGIN = "docker/login-action"
BUILD_PUSH = "docker/build-push-action"

ALLOWED_SECRETS = {"DOCKERHUB_USERNAME", "DOCKERHUB_TOKEN"}
ALLOWED_VARS = {"DOCKERHUB_IMAGE"}
USERNAME_EXPR = "${{ secrets.DOCKERHUB_USERNAME }}"
TOKEN_EXPR = "${{ secrets.DOCKERHUB_TOKEN }}"
IMAGE_EXPR = "${{ vars.DOCKERHUB_IMAGE }}"

# 로그인과 push를 거는 조건. `&&`로 이은 아래 두 항만 있어야 한다. 순서는 따지지 않는다.
MAIN_PUSH_TERMS = {"github.event_name == 'push'", "github.ref == 'refs/heads/main'"}

# 검사 명령은 scripts/check.sh 한 곳에만 둔다(docs/DEVELOPMENT.md 2절).
CHECK_TOOLS = re.compile(r"(^|[^\w./-])(ruff|pyright|pytest)([^\w-]|$)")


# --- workflow 읽기 ------------------------------------------------------------


def workflow_text() -> str:
    assert WORKFLOW.is_file(), f"{WORKFLOW.relative_to(REPO_ROOT)}가 없다"
    return WORKFLOW.read_text(encoding="utf-8")


def workflow() -> dict[Any, Any]:
    data = yaml.safe_load(workflow_text())
    assert isinstance(data, dict), "workflow의 최상위가 사전이 아니다"
    return data


def triggers() -> dict[str, Any]:
    """workflow의 `on`. PyYAML은 YAML 1.1을 따라 `on` 키를 문자열이 아니라 True로 읽는다."""
    data = workflow()
    raw = data["on"] if "on" in data else data.get(True)
    assert raw is not None, "workflow에 on(트리거)이 없다"
    # `on: push`와 `on: [push, pull_request]` 형식도 읽는다. 이때 각 트리거에는 설정이 없다.
    if isinstance(raw, str):
        return {raw: None}
    if isinstance(raw, list):
        return {str(name): None for name in raw}
    assert isinstance(raw, dict), f"on의 형식을 알 수 없다: {raw!r}"
    return {str(name): config for name, config in raw.items()}


def jobs() -> dict[str, dict[str, Any]]:
    found = workflow().get("jobs")
    assert isinstance(found, dict) and found, "workflow에 jobs가 없다"
    return found


def job(name: str) -> dict[str, Any]:
    found = jobs().get(name)
    assert isinstance(found, dict), f"workflow에 {name} job이 없다"
    return found


def steps(job_name: str) -> list[dict[str, Any]]:
    found = job(job_name).get("steps")
    assert isinstance(found, list) and found, f"{job_name} job에 steps가 없다"
    return found


def all_steps() -> list[tuple[str, dict[str, Any]]]:
    return [(name, step) for name in jobs() for step in steps(name)]


def uses(step: dict[str, Any], action: str) -> bool:
    return str(step.get("uses", "")).split("@")[0] == action


def run_lines(step: dict[str, Any]) -> list[str]:
    """step의 run에서 빈 줄과 주석 줄을 뺀 줄."""
    lines = []
    for raw in str(step.get("run", "")).splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            lines.append(line)
    return lines


def with_inputs(step: dict[str, Any]) -> dict[str, Any]:
    found = step.get("with") or {}
    assert isinstance(found, dict), f"step의 with가 사전이 아니다: {step!r}"
    return found


def as_list(value: Any) -> list[str]:
    """build-push-action의 목록 입력(platforms, tags). 쉼표나 줄바꿈으로 나뉜다."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in re.split(r"[,\n]", str(value)) if item.strip()]


def is_main_push_condition(condition: Any) -> bool:
    """`if`가 `main`에 push된 경우로만 제한하는지.

    `&&`로 이은 항이 정확히 MAIN_PUSH_TERMS여야 한다. `||`나 `!`가 든 조건은 다른 경우에도
    참이 될 수 있으므로 인정하지 않는다.
    """
    if not isinstance(condition, str):
        return False
    expr = condition.strip()
    if expr.startswith("${{") and expr.endswith("}}"):
        expr = expr[3:-2]
    expr = expr.replace('"', "'")
    if "||" in expr or re.search(r"!(?!=)", expr):
        return False
    terms = {re.sub(r"\s+", " ", term.strip(" ()\t\n")) for term in expr.split("&&")}
    terms = {re.sub(r"\s*==\s*", " == ", term) for term in terms}
    return terms == MAIN_PUSH_TERMS


def pushes(step: dict[str, Any]) -> bool:
    """build-push-action의 step이 레지스트리에 올릴 수 있는지.

    명시적인 false만 올리지 않는다고 본다. 식(`${{ ... }}`)은 참이 될 수 있으므로 올린다고 본다.
    """
    value = with_inputs(step).get("push", False)
    return not (value is False or str(value).strip().lower() == "false")


def build_steps() -> list[dict[str, Any]]:
    return [step for step in steps("image") if uses(step, BUILD_PUSH)]


def login_steps() -> list[dict[str, Any]]:
    return [step for step in steps("image") if uses(step, LOGIN)]


def expressions(text: str) -> list[str]:
    return re.findall(r"\$\{\{(.*?)\}\}", text, flags=re.DOTALL)


def strings(node: Any) -> list[str]:
    """YAML 노드 안의 모든 키와 값을 문자열로 모은다."""
    if isinstance(node, dict):
        return [s for key, value in node.items() for s in [str(key), *strings(value)]]
    if isinstance(node, list):
        return [s for item in node for s in strings(item)]
    return [str(node)]


def dockerfile_uv_version() -> str:
    code = "\n".join(
        line
        for line in DOCKERFILE.read_text(encoding="utf-8").splitlines()
        if not line.strip().startswith("#")
    )
    versions = set(re.findall(rf"{re.escape(UV_IMAGE)}:(\d+\.\d+\.\d+)", code))
    assert len(versions) == 1, f"Dockerfile의 uv 이미지 버전이 하나가 아니다: {versions}"
    return versions.pop()


# --- TC-0.7.1: 트리거 ----------------------------------------------------------


def test_triggers_are_pull_request_and_push_only() -> None:
    # pull_request_target은 PR의 코드를 secrets가 있는 맥락에서 돌린다.
    assert set(triggers()) == {"pull_request", "push"}, f"트리거가 다르다: {sorted(triggers())}"


@pytest.mark.parametrize("event", ["pull_request", "push"])
def test_trigger_is_limited_to_main_branch(event: str) -> None:
    config = triggers()[event]
    assert isinstance(config, dict), f"{event}에 branches가 없어서 모든 브랜치에서 돈다"
    # paths나 tags 같은 거름망이 있으면 어떤 변경에서는 검사가 돌지 않는다.
    assert set(config) == {"branches"}, f"{event}에 branches 밖의 설정이 있다: {sorted(config)}"
    assert as_list(config["branches"]) == ["main"], f"{event}가 main 밖의 브랜치에서도 돈다"


def test_main_push_runs_are_never_cancelled() -> None:
    # 취소된 main 커밋의 이미지는 올라가지 않는다. PR의 이전 실행은 취소해도 된다.
    blocks = [("workflow", workflow().get("concurrency"))]
    blocks += [(name, definition.get("concurrency")) for name, definition in jobs().items()]
    for owner, concurrency in blocks:
        if concurrency is None:
            continue
        if isinstance(concurrency, str):
            group, cancel = concurrency, False
        else:
            assert isinstance(concurrency, dict), f"{owner}의 concurrency 형식을 알 수 없다"
            group = str(concurrency.get("group", ""))
            cancel = concurrency.get("cancel-in-progress", False)
        assert cancel is not True, f"{owner}의 concurrency가 main의 push도 취소한다"
        if isinstance(cancel, str):
            assert "pull_request" in cancel, f"{owner}의 cancel-in-progress가 PR로 제한되지 않는다"
        # 같은 그룹에서 기다리던 실행은 cancel-in-progress가 false여도 새 실행이 오면 취소된다.
        # main의 push는 실행마다 다른 그룹에 두어야 한다.
        assert "github.run_id" in group or "github.sha" in group, (
            f"{owner}의 concurrency 그룹을 main의 push끼리 함께 쓴다: {group}"
        )


# --- TC-0.7.2: 검사 job과 스모크 job ----------------------------------------------


def test_check_job_calls_check_script() -> None:
    lines = [line for step in steps("check") for line in run_lines(step)]
    # `scripts/check.sh || true`처럼 실패를 삼키는 줄은 인정하지 않는다.
    assert any(re.fullmatch(r"(bash\s+)?(\./)?scripts/check\.sh(\s+--all)?", s) for s in lines), (
        f"check job이 scripts/check.sh를 부르지 않는다: {lines}"
    )


def test_check_job_installs_locked_dependencies_before_check_script() -> None:
    lines = [line for step in steps("check") for line in run_lines(step)]
    sync = [i for i, line in enumerate(lines) if line.split()[:2] == ["uv", "sync"]]
    check = [i for i, line in enumerate(lines) if "scripts/check.sh" in line]
    assert sync, "check job이 uv sync를 부르지 않는다"
    assert "--locked" in lines[sync[0]].split(), "check job이 uv.lock대로 설치하지 않는다"
    assert check and sync[0] < check[0], "check job이 의존성을 설치하기 전에 검사한다"


@pytest.mark.parametrize("job_name", ["check", "compose-smoke"])
def test_check_and_smoke_run_on_every_trigger(job_name: str) -> None:
    # 검사와 스모크는 PR과 main의 push에서 모두 돈다(docs/DECISIONS.md의 D-36).
    # job이나 step에 조건을 걸면 PR에서 건너뛰어도 검사가 초록으로 보인다.
    assert "if" not in job(job_name), f"{job_name} job 전체에 조건이 걸려 있다"
    for step in steps(job_name):
        assert "if" not in step, f"{job_name} job의 step에 조건이 걸려 있다: {step}"


def test_check_job_uses_only_checkout_and_setup_uv() -> None:
    # 검사는 scripts/check.sh 한 곳에서 돈다(docs/DEVELOPMENT.md 2절). ruff-action처럼 검사 도구를
    # 부르는 action을 더하면 run 줄을 보지 않고도 기준이 갈라진다.
    allowed = {"actions/checkout", SETUP_UV}
    used = {str(step["uses"]).split("@")[0] for step in steps("check") if "uses" in step}
    assert used <= allowed, f"check job이 허용하지 않은 action을 쓴다: {sorted(used - allowed)}"


def test_workflow_never_calls_check_tools_directly() -> None:
    # 검사 명령을 workflow에 따로 적으면 scripts/check.sh와 기준이 갈라진다.
    for job_name, step in all_steps():
        for line in run_lines(step):
            assert not CHECK_TOOLS.search(line), f"{job_name} job이 검사 명령을 직접 부른다: {line}"


def test_compose_smoke_job_calls_smoke_script() -> None:
    lines = [line for step in steps("compose-smoke") for line in run_lines(step)]
    assert any(re.fullmatch(r"(bash\s+)?(\./)?scripts/compose-smoke\.sh", s) for s in lines), (
        f"compose-smoke job이 scripts/compose-smoke.sh를 부르지 않는다: {lines}"
    )
    # 스모크의 이미지는 compose로만 빌드한다(docs/DECISIONS.md의 D-41).
    for line in lines:
        assert not re.search(r"docker\s+(buildx\s+)?build", line), f"docker build를 쓴다: {line}"
    assert not any(uses(step, BUILD_PUSH) for step in steps("compose-smoke"))


def test_setup_uv_version_matches_dockerfile_uv_image() -> None:
    expected = dockerfile_uv_version()
    assert any(uses(step, SETUP_UV) for step in steps("check")), (
        f"check job이 {SETUP_UV}로 uv를 설치하지 않는다"
    )
    found = [(job_name, step) for job_name, step in all_steps() if uses(step, SETUP_UV)]
    for job_name, step in found:
        version = with_inputs(step).get("version")
        assert version is not None, f"{job_name} job의 {SETUP_UV}가 uv의 버전을 고정하지 않는다"
        assert str(version).strip() == expected, (
            f"{job_name} job의 uv({version})가 Dockerfile의 uv 이미지({expected})와 다르다"
        )


def test_no_continue_on_error() -> None:
    # 실패한 검사가 초록으로 보인다.
    for name, definition in jobs().items():
        assert "continue-on-error" not in definition, f"{name} job에 continue-on-error가 있다"
    for job_name, step in all_steps():
        assert "continue-on-error" not in step, f"{job_name} job의 step에 continue-on-error가 있다"


def test_actions_are_pinned_to_tags() -> None:
    for job_name, step in all_steps():
        if "uses" not in step:
            continue
        action, _, ref = str(step["uses"]).partition("@")
        assert ref, f"{job_name} job의 {action}에 버전이 없다"
        assert ref not in {"main", "master"}, f"{job_name} job의 {action}이 브랜치를 가리킨다"
        assert re.fullmatch(r"v\d+(\.\d+){0,2}", ref), f"{action}@{ref}가 버전 태그가 아니다"


# --- TC-0.7.3: 이미지 job -------------------------------------------------------


def test_image_job_needs_check_and_compose_smoke() -> None:
    needs = job("image").get("needs")
    names = [needs] if isinstance(needs, str) else list(needs or [])
    assert {"check", "compose-smoke"} <= set(names), f"image job의 needs가 모자란다: {names}"


def test_image_job_runs_on_pull_requests_too() -> None:
    # PR에서도 이미지가 빌드되는지까지는 확인한다(docs/INFRA.md 3.7절).
    assert "if" not in job("image"), "image job 전체에 조건이 걸려 있다"


def test_image_is_built_for_linux_amd64_only() -> None:
    assert build_steps(), f"image job이 {BUILD_PUSH}로 빌드하지 않는다"
    for step in build_steps():
        platforms = as_list(with_inputs(step).get("platforms"))
        assert platforms == ["linux/amd64"], f"플랫폼이 linux/amd64 하나가 아니다: {platforms}"
    # arm64 이미지는 배포 환경이 요구할 때 더한다(docs/DECISIONS.md의 D-37).
    assert "arm64" not in workflow_text()
    assert not any(uses(step, "docker/setup-qemu-action") for _, step in all_steps())


def test_pull_request_build_does_not_push() -> None:
    on_pr = [step for step in build_steps() if not is_main_push_condition(step.get("if"))]
    assert on_pr, "PR에서 이미지를 빌드하는 step이 없다"
    for step in on_pr:
        assert not pushes(step), f"main의 push가 아닌 경우에도 이미지를 올린다: {step}"


def test_registry_push_only_on_main_push() -> None:
    pushing = [step for step in build_steps() if pushes(step)]
    assert pushing, "main의 push에서 이미지를 올리는 step이 없다"
    for step in pushing:
        assert is_main_push_condition(step.get("if")), (
            f"이미지를 올리는 step이 main의 push로 제한되지 않는다: if={step.get('if')!r}"
        )


def test_registry_login_only_on_main_push() -> None:
    assert login_steps(), f"image job이 {LOGIN}로 로그인하지 않는다"
    for step in login_steps():
        assert is_main_push_condition(step.get("if")), (
            f"로그인하는 step이 main의 push로 제한되지 않는다: if={step.get('if')!r}"
        )
    # 로그인과 push는 위의 공식 action으로만 한다. run에서 직접 하면 조건을 확인할 수 없다.
    for job_name, step in all_steps():
        for line in run_lines(step):
            assert not re.search(r"docker\s+((image\s+)?push|login)|--push", line), (
                f"{job_name} job이 run에서 로그인하거나 올린다: {line}"
            )


def test_login_comes_before_push() -> None:
    image_steps = steps("image")
    login = min(image_steps.index(step) for step in login_steps())
    for step in build_steps():
        if pushes(step):
            assert login < image_steps.index(step), "로그인하기 전에 이미지를 올린다"


def test_pushed_image_is_tagged_latest_and_commit_sha() -> None:
    for step in build_steps():
        if not pushes(step):
            continue
        tags = as_list(with_inputs(step).get("tags"))
        assert f"{IMAGE_EXPR}:latest" in tags, f"latest 태그가 없다: {tags}"
        sha = [tag for tag in tags if tag.startswith(f"{IMAGE_EXPR}:sha-")]
        assert sha and all("github.sha" in tag for tag in sha), f"sha-<커밋> 태그가 없다: {tags}"


# --- TC-0.7.4: 자격 증명, 이미지 이름, 권한 -------------------------------------------


def test_top_level_permissions_are_contents_read_only() -> None:
    assert workflow().get("permissions") == {"contents": "read"}
    # job에서 권한을 넓히면 최상위의 권한이 뜻을 잃는다.
    for name, definition in jobs().items():
        assert "permissions" not in definition, f"{name} job이 권한을 따로 정한다"


def test_only_registered_secrets_and_vars_are_referenced() -> None:
    for expr in expressions(workflow_text()):
        for context, allowed in (("secrets", ALLOWED_SECRETS), ("vars", ALLOWED_VARS)):
            for match in re.finditer(rf"\b{context}\b(\.(\w+))?", expr):
                name = match.group(2)
                # secrets[...]나 toJSON(secrets)처럼 이름을 감추는 참조도 인정하지 않는다.
                assert name in allowed, f"허용하지 않는 {context} 참조: ${{{{{expr}}}}}"


def test_registry_credentials_come_from_secrets() -> None:
    for step in login_steps():
        inputs = with_inputs(step)
        assert inputs.get("username") == USERNAME_EXPR, f"사용자 이름: {inputs.get('username')!r}"
        assert inputs.get("password") == TOKEN_EXPR, f"토큰: {inputs.get('password')!r}"
        # 비워 두면 Docker Hub(docker.io)다. 다른 레지스트리로 올리지 않는다.
        assert inputs.get("registry") in {None, "docker.io"}
    # Docker Hub의 개인 액세스 토큰은 dckr_pat_로 시작한다.
    assert "dckr_pat_" not in workflow_text()


def test_names_of_registered_values_are_never_assigned_literals() -> None:
    # 예: env의 DOCKERHUB_IMAGE: someone/diegesis-be
    expected = {
        "DOCKERHUB_USERNAME": USERNAME_EXPR,
        "DOCKERHUB_TOKEN": TOKEN_EXPR,
        "DOCKERHUB_IMAGE": IMAGE_EXPR,
    }

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in expected:
                    assert value == expected[key], f"{key}에 {value!r}를 넣는다"
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(workflow())


def test_image_name_comes_only_from_variable() -> None:
    for step in build_steps():
        for tag in as_list(with_inputs(step).get("tags")):
            assert tag.startswith(f"{IMAGE_EXPR}:"), (
                f"이미지 이름을 {IMAGE_EXPR}에서 읽지 않는다: {tag}"
            )


def test_pull_request_steps_do_not_depend_on_secrets_or_vars() -> None:
    # secrets와 variable을 등록하기 전에도, secrets를 받지 못하는 PR(Dependabot 등)에서도
    # 빌드 확인은 초록이어야 한다.
    for job_name, step in all_steps():
        if is_main_push_condition(step.get("if")):
            continue
        for expr in expressions("\n".join(strings(step))):
            assert not re.search(r"\b(secrets|vars)\b", expr), (
                f"PR에서도 도는 {job_name} job의 step이 secrets나 vars에 기댄다: {step}"
            )


def image_name_guard() -> dict[str, Any]:
    """로그인 전에 DOCKERHUB_IMAGE가 비어 있지 않은지 확인하는 step."""
    image_steps = steps("image")
    login = min(image_steps.index(step) for step in login_steps())
    guards = [
        step
        for step in image_steps[:login]
        if "run" in step and (step.get("env") or {}).get("DOCKERHUB_IMAGE") == IMAGE_EXPR
    ]
    assert guards, "로그인하기 전에 DOCKERHUB_IMAGE를 확인하는 step이 없다"
    assert len(guards) == 1
    return guards[0]


def test_image_name_guard_runs_only_on_main_push() -> None:
    assert is_main_push_condition(image_name_guard().get("if"))


def run_guard(value: str) -> subprocess.CompletedProcess[str]:
    script = str(image_name_guard()["run"])
    assert "${{" not in script, "확인 스크립트가 식(${{ }})을 직접 쓴다. env로 넘겨라"
    return subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", script],
        env={"PATH": os.environ.get("PATH", ""), "DOCKERHUB_IMAGE": value},
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_image_name_guard_fails_with_instructions_when_variable_is_empty() -> None:
    result = run_guard("")
    assert result.returncode != 0, "DOCKERHUB_IMAGE가 비어 있는데도 다음 단계로 넘어간다"
    output = result.stdout + result.stderr
    assert "DOCKERHUB_IMAGE" in output, f"무엇을 등록해야 하는지 알리지 않는다: {output}"


def test_image_name_guard_passes_when_variable_is_set() -> None:
    result = run_guard("example/image")
    assert result.returncode == 0, result.stdout + result.stderr


# --- TC-0.7.5: actionlint -------------------------------------------------------


def actionlint() -> str:
    """dev 의존성의 actionlint. 찾지 못하면 건너뛰지 않고 실패한다."""
    search = os.pathsep.join([str(Path(sys.executable).parent), os.environ.get("PATH", "")])
    found = shutil.which("actionlint", path=search)
    if found is None:
        pytest.fail("actionlint를 찾을 수 없다. `uv sync`로 dev 의존성을 설치해라")
    return found


def run_actionlint(path: Path) -> subprocess.CompletedProcess[str]:
    # shellcheck와 pyflakes는 끈다. ubuntu 실행기에는 shellcheck가 있고 개발자의 컴퓨터에는 없을 수
    # 있어서, 켜 두면 같은 파일이 CI에서만 실패한다.
    return subprocess.run(
        [actionlint(), "-shellcheck=", "-pyflakes=", "-no-color", str(path)],
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_actionlint_passes() -> None:
    workflow_text()
    result = run_actionlint(WORKFLOW)
    assert result.returncode == 0, result.stdout + result.stderr


def test_actionlint_rejects_broken_workflow(tmp_path: Path) -> None:
    # actionlint가 아무것도 검사하지 않고 0으로 끝나는 것은 아닌지 확인한다.
    broken = tmp_path / ".github" / "workflows" / "broken.yml"
    broken.parent.mkdir(parents=True)
    broken.write_text(
        "on: push\njobs:\n  a:\n    runs-on: ubuntu-latest\n"
        "    steps:\n      - run: echo ${{ github.no_such_context }}\n"
        "    needs: missing-job\n",
        encoding="utf-8",
    )
    assert run_actionlint(broken).returncode != 0
