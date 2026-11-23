"""`Dockerfile`의 테스트 (TC-0.5.3).

버전 문자열을 이 파일에 적지 않는다.
Python의 버전은 `.python-version`에서 읽어 `Dockerfile`과 비교한다.
버전은 docs/DEVELOPMENT.md 1절이 정한 파일에만 있어야 하기 때문이다.
"""

import json
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = REPO_ROOT / "Dockerfile"
PYTHON_VERSION_FILE = REPO_ROOT / ".python-version"

UV_IMAGE = "ghcr.io/astral-sh/uv"


@dataclass
class Instruction:
    keyword: str
    args: str


@dataclass
class Stage:
    image: str
    name: str | None
    instructions: list[Instruction] = field(default_factory=list)


def instructions() -> list[Instruction]:
    """주석과 빈 줄을 빼고, `\\`로 이어진 줄을 합친 명령의 목록."""
    result: list[Instruction] = []
    pending = ""
    for raw in DOCKERFILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.endswith("\\"):
            pending += line[:-1] + " "
            continue
        full = (pending + line).strip()
        pending = ""
        keyword, _, args = full.partition(" ")
        result.append(Instruction(keyword.upper(), args.strip()))
    assert not pending, "Dockerfile이 `\\`로 끝난다"
    return result


def stages() -> list[Stage]:
    result: list[Stage] = []
    for instruction in instructions():
        if instruction.keyword == "FROM":
            words = [w for w in instruction.args.split() if not w.startswith("--")]
            name = words[2] if len(words) >= 3 and words[1].upper() == "AS" else None
            result.append(Stage(image=words[0], name=name))
        else:
            assert result, f"FROM보다 앞에 {instruction.keyword}가 있다"
            result[-1].instructions.append(instruction)
    assert result, "Dockerfile에 FROM이 없다"
    return result


def final_stage() -> Stage:
    return stages()[-1]


def python_major_minor() -> str:
    """`.python-version`의 주 버전과 부 버전. `3.14`이든 `3.14.7`이든 `3.14`를 돌려준다."""
    version = PYTHON_VERSION_FILE.read_text(encoding="utf-8").strip()
    match = re.fullmatch(r"(\d+)\.(\d+)(\.\d+)?", version)
    assert match, f".python-version의 형식을 알 수 없다: {version!r}"
    return f"{match.group(1)}.{match.group(2)}"


def python_base_images() -> list[str]:
    return [stage.image for stage in stages() if stage.image.split(":")[0] == "python"]


def exec_form(args: str) -> list[str]:
    """CMD와 ENTRYPOINT의 exec 형식(JSON 배열)을 읽는다. 셸 형식이면 실패한다."""
    value = json.loads(args)
    assert isinstance(value, list), f"exec 형식(JSON 배열)이 아니다: {args}"
    return [str(item) for item in value]


# --- TC-0.5.3: Python 베이스 이미지 -------------------------------------------


def test_python_base_images_follow_python_version_file() -> None:
    images = python_base_images()
    assert images, "Python 베이스 이미지(python:...)를 쓰는 단계가 없다"

    expected = python_major_minor()
    for image in images:
        _, _, tag = image.partition(":")
        match = re.fullmatch(r"(\d+)\.(\d+)-slim(-[a-z]+)?", tag)
        assert match, f"Python 베이스 이미지가 python:<주>.<부>-slim 계열이 아니다: {image}"
        # `.python-version`만 올리고 Dockerfile을 그대로 두면 여기서 실패해야 한다.
        assert f"{match.group(1)}.{match.group(2)}" == expected, (
            f"{image}의 Python 버전이 .python-version({expected})과 다르다"
        )


def test_final_stage_runs_on_python_base_image() -> None:
    assert final_stage().image in python_base_images()


def test_image_is_multi_stage() -> None:
    # 빌드 도구(uv)와 캐시를 실행 이미지에 남기지 않는다.
    assert len(stages()) >= 2


# --- TC-0.5.3: uv 이미지 ----------------------------------------------------


def uv_image_references() -> list[str]:
    text = DOCKERFILE.read_text(encoding="utf-8")
    code = "\n".join(line for line in text.splitlines() if not line.strip().startswith("#"))
    return re.findall(rf"{re.escape(UV_IMAGE)}(?::[^\s/]*)?", code)


def test_uv_is_copied_from_uv_image() -> None:
    copies = [
        instruction
        for stage in stages()
        for instruction in stage.instructions
        if instruction.keyword == "COPY" and f"--from={UV_IMAGE}:" in instruction.args
    ]
    assert copies, f"uv를 {UV_IMAGE} 이미지에서 복사하지 않는다"


def test_uv_image_is_pinned_to_exact_version() -> None:
    references = uv_image_references()
    assert references, f"{UV_IMAGE} 이미지를 쓰지 않는다"
    for reference in references:
        _, _, tag = reference.partition(":")
        # latest, 주 버전만(0), 주와 부 버전만(0.12) 있는 태그는 시간이 지나면 다른 uv를 가리킨다.
        assert re.fullmatch(r"\d+\.\d+\.\d+", tag), (
            f"uv 이미지가 정확한 버전으로 고정되어 있지 않다: {reference}"
        )


def test_build_stage_installs_only_locked_production_dependencies() -> None:
    syncs = [
        instruction.args
        for stage in stages()[:-1]
        for instruction in stage.instructions
        if instruction.keyword == "RUN" and "uv sync" in instruction.args
    ]
    assert syncs, "빌드 단계에서 uv sync를 부르지 않는다"
    for args in syncs:
        assert "--locked" in args.split(), "uv.lock대로 설치하지 않는다(--locked)"
        assert "--no-dev" in args.split(), "개발 도구까지 설치한다(--no-dev)"


# --- TC-0.5.3: 실행 단계 ----------------------------------------------------


def test_final_stage_runs_as_non_root_user() -> None:
    users = [i.args for i in final_stage().instructions if i.keyword == "USER"]
    assert users, "실행 단계에 USER가 없어서 root로 돈다"
    user = users[-1].split(":")[0].strip()
    assert user not in {"root", "0"}, f"실행 단계가 root로 돈다: USER {users[-1]}"


def test_final_stage_copies_only_what_the_server_needs() -> None:
    allowed = {"app", "migrations", "alembic.ini"}
    for instruction in final_stage().instructions:
        assert instruction.keyword != "ADD", "실행 단계에서 ADD를 쓴다"
        if instruction.keyword != "COPY":
            continue
        words = shlex.split(instruction.args)
        if any(w.startswith("--from=") for w in words):
            continue
        sources = [w for w in words if not w.startswith("--")][:-1]
        for source in sources:
            normalized = source.removeprefix("./").rstrip("/")
            assert normalized in allowed, f"실행 단계가 {source}를 빌드 맥락에서 복사한다"


def test_dockerfile_never_copies_env_file() -> None:
    for instruction in instructions():
        if instruction.keyword in {"COPY", "ADD"}:
            assert ".env" not in instruction.args, f"`.env`를 이미지에 넣는다: {instruction.args}"


def test_final_stage_exposes_8080_and_starts_python_m_app() -> None:
    stage = final_stage()
    exposed = [i.args for i in stage.instructions if i.keyword == "EXPOSE"]
    assert "8080" in " ".join(exposed).split()

    cmds = [i.args for i in stage.instructions if i.keyword == "CMD"]
    assert cmds, "실행 단계에 CMD가 없다"
    assert exec_form(cmds[-1]) == ["python", "-m", "app"]


@pytest.mark.parametrize("keyword", ["ENTRYPOINT", "CMD"])
def test_no_shell_script_entrypoint(keyword: str) -> None:
    # Windows의 git이 CRLF로 받은 셸 스크립트는 리눅스 컨테이너 안에서 깨진다.
    for instruction in instructions():
        if instruction.keyword == keyword:
            assert ".sh" not in instruction.args, (
                f"셸 스크립트를 진입점으로 둔다: {instruction.args}"
            )
