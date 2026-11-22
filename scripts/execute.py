#!/usr/bin/env python3
"""
Harness Step Executor — phase 내 step을 순차 실행하고 자가 교정한다.

Usage:
    python3 scripts/execute.py <phase-dir> [--push]

OnlineFourCut의 scripts/execute.py를 옮긴 것이다. 주석에 남은 사례(Epic 번호, 날짜)는
원본 프로젝트에서 실제로 있었던 일이다. 이 레포에 맞춰 바꾼 곳은 HEADLESS_MODEL,
GUARDRAIL_DOCS, 그리고 프롬프트와 안내 문구의 스택 이름뿐이다.
"""

import argparse
import contextlib
import json
import os
import subprocess
import sys
import threading
import time
import types
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent


@contextlib.contextmanager
def progress_indicator(label: str):
    """터미널 진행 표시기. with 문으로 사용하며 .elapsed 로 경과 시간을 읽는다."""
    frames = "◐◓◑◒"
    stop = threading.Event()
    t0 = time.monotonic()

    def _animate():
        idx = 0
        while not stop.wait(0.12):
            sec = int(time.monotonic() - t0)
            sys.stderr.write(f"\r{frames[idx % len(frames)]} {label} [{sec}s]")
            sys.stderr.flush()
            idx += 1
        sys.stderr.write("\r" + " " * (len(label) + 20) + "\r")
        sys.stderr.flush()

    th = threading.Thread(target=_animate, daemon=True)
    th.start()
    info = types.SimpleNamespace(elapsed=0.0)
    try:
        yield info
    finally:
        stop.set()
        th.join()
        info.elapsed = time.monotonic() - t0


class StepExecutor:
    """Phase 디렉토리 안의 step들을 순차 실행하는 하네스."""

    MAX_RETRIES = 3
    # 헤드리스 step 세션의 모델. 환경 변수 HARNESS_MODEL로 바꾼다(docs/DECISIONS.md D-29).
    # --model을 명시하지 않으면 대화 세션의 기본 모델이 상속되므로 여기서 끊는다.
    # harness-run.sh의 리뷰·처분 세션 --model과 짝이다.
    HEADLESS_MODEL = os.environ.get("HARNESS_MODEL") or "claude-opus-5-5"
    FEAT_MSG = "feat({phase}): step {num} — {name}"
    CHORE_MSG = "chore({phase}): step {num} output"
    TZ = timezone(timedelta(hours=9))

    # 매 step 프롬프트에 주입할 docs/ 문서. 나열한 순서대로 들어간다.
    # docs/*.md 전체를 넣으면 결정의 경위(ADR의 후보 비교)와 특정 step만 쓰는 규격
    # (API, AI_CONTRACT)까지 딸려와 프롬프트가 두 배가 되고, 재시도마다 다시 나간다.
    # 여기에는 거의 모든 step이 전제로 삼는 문서만 둔다. 여기 없는 문서는
    # step 파일의 "읽어야 할 파일"에 경로와 절 번호를 적어 세션이 직접 읽게 한다.
    GUARDRAIL_DOCS = ("DEVELOPMENT.md", "ARCHITECTURE.md", "CONFIGURATION.md", "GLOSSARY.md")

    def __init__(self, phase_dir_name: str, *, auto_push: bool = False):
        self._root = str(ROOT)
        self._phases_dir = ROOT / "phases"
        self._phase_dir = self._phases_dir / phase_dir_name
        self._phase_dir_name = phase_dir_name
        self._top_index_file = self._phases_dir / "index.json"
        self._auto_push = auto_push

        if not self._phase_dir.is_dir():
            print(f"ERROR: {self._phase_dir} not found")
            sys.exit(1)

        self._index_file = self._phase_dir / "index.json"
        if not self._index_file.exists():
            print(f"ERROR: {self._index_file} not found")
            sys.exit(1)

        idx = self._read_json(self._index_file)
        self._project = idx.get("project", "project")
        self._phase_name = idx.get("phase", phase_dir_name)
        self._total = len(idx["steps"])

    def run(self):
        self._print_header()
        self._check_blockers()
        self._check_clean_tree()
        self._checkout_branch()
        guardrails = self._load_guardrails()
        self._ensure_created_at()
        self._execute_all_steps(guardrails)
        self._finalize()

    # --- timestamps ---

    def _stamp(self) -> str:
        return datetime.now(self.TZ).strftime("%Y-%m-%dT%H:%M:%S%z")

    # --- JSON I/O ---

    @staticmethod
    def _read_json(p: Path) -> dict:
        return json.loads(p.read_text(encoding="utf-8"))

    @staticmethod
    def _write_json(p: Path, data: dict):
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    # --- git ---

    def _run_git(self, *args) -> subprocess.CompletedProcess:
        cmd = ["git"] + list(args)
        return subprocess.run(cmd, cwd=self._root, capture_output=True, text=True)

    def _check_clean_tree(self):
        """워킹트리에 관련 없는 변경이 있으면 시작하지 않는다.

        _commit_step과 _finalize가 `git add -A`로 트리 전체를 담기 때문에, 남아 있던
        변경이 step 커밋에 딸려 들어간다. 실제로 하네스 수정본이 'mark phase completed'에
        휩쓸려 커밋을 손으로 쪼개야 했다.

        phases/ 아래는 뺀다 — started_at은 커밋 없이 index.json에 남고 MANUAL.md 체크는
        사람이 손으로 한다. 여기를 안 빼면 정상 흐름에서 매번 울려 곧 무시하게 된다.
        """
        r = self._run_git("status", "--porcelain")
        if r.returncode != 0:
            return
        dirty = []
        for line in r.stdout.splitlines():
            if not line.strip():
                continue
            path = line[3:].split(" -> ")[-1].strip().strip('"')
            if not path.startswith("phases/"):
                dirty.append(path)
        if not dirty:
            return
        print(f"\n  ⏸ 워킹트리에 커밋되지 않은 변경이 있다 ({len(dirty)}개)")
        for path in dirty[:10]:
            print(f"     {path}")
        if len(dirty) > 10:
            print(f"     … 외 {len(dirty) - 10}개")
        print("  하네스는 `git add -A`로 커밋하므로 이 변경들이 step 커밋에 섞인다.")
        print("  커밋하거나 stash한 뒤 다시 돌려라.")
        sys.exit(1)

    def _checkout_branch(self):
        branch = f"feat-{self._phase_name}"

        r = self._run_git("rev-parse", "--abbrev-ref", "HEAD")
        if r.returncode != 0:
            print(f"  ERROR: git을 사용할 수 없거나 git repo가 아닙니다.")
            print(f"  {r.stderr.strip()}")
            sys.exit(1)

        if r.stdout.strip() == branch:
            return

        r = self._run_git("rev-parse", "--verify", branch)
        r = self._run_git("checkout", branch) if r.returncode == 0 else self._run_git("checkout", "-b", branch)

        if r.returncode != 0:
            print(f"  ERROR: 브랜치 '{branch}' checkout 실패.")
            print(f"  {r.stderr.strip()}")
            print(f"  Hint: 변경사항을 stash하거나 commit한 후 다시 시도하세요.")
            sys.exit(1)

        print(f"  Branch: {branch}")

    def _commit_step(self, step_num: int, step_name: str):
        output_rel = f"phases/{self._phase_dir_name}/step{step_num}-output.json"
        index_rel = f"phases/{self._phase_dir_name}/index.json"

        self._run_git("add", "-A")
        self._run_git("reset", "HEAD", "--", output_rel)
        self._run_git("reset", "HEAD", "--", index_rel)

        if self._run_git("diff", "--cached", "--quiet").returncode != 0:
            msg = self.FEAT_MSG.format(phase=self._phase_name, num=step_num, name=step_name)
            r = self._run_git("commit", "-m", msg)
            if r.returncode == 0:
                print(f"  Commit: {msg}")
            else:
                print(f"  WARN: 코드 커밋 실패: {r.stderr.strip()}")

        self._run_git("add", "-A")
        if self._run_git("diff", "--cached", "--quiet").returncode != 0:
            msg = self.CHORE_MSG.format(phase=self._phase_name, num=step_num)
            r = self._run_git("commit", "-m", msg)
            if r.returncode != 0:
                print(f"  WARN: housekeeping 커밋 실패: {r.stderr.strip()}")

    # --- top-level index ---

    def _update_top_index(self, status: str):
        if not self._top_index_file.exists():
            return
        top = self._read_json(self._top_index_file)
        ts = self._stamp()
        for phase in top.get("phases", []):
            if phase.get("dir") == self._phase_dir_name:
                phase["status"] = status
                ts_key = {"completed": "completed_at", "error": "failed_at", "blocked": "blocked_at"}.get(status)
                if ts_key:
                    phase[ts_key] = ts
                break
        self._write_json(self._top_index_file, top)

    # --- guardrails & context ---

    def _load_guardrails(self) -> str:
        sections = []
        claude_md = ROOT / "CLAUDE.md"
        if claude_md.exists():
            sections.append(f"## 문서 색인 (CLAUDE.md)\n\n{claude_md.read_text()}")
        docs_dir = ROOT / "docs"
        for name in self.GUARDRAIL_DOCS:
            doc = docs_dir / name
            if doc.is_file():
                sections.append(f"## {doc.stem}\n\n{doc.read_text()}")
        return "\n\n---\n\n".join(sections) if sections else ""

    @staticmethod
    def _build_step_context(index: dict) -> str:
        lines = [
            f"- Step {s['step']} ({s['name']}): {s['summary']}"
            for s in index["steps"]
            if s["status"] == "completed" and s.get("summary")
        ]
        if not lines:
            return ""
        return "## 이전 Step 산출물\n\n" + "\n".join(lines) + "\n\n"

    def _build_preamble(self, guardrails: str, step_context: str,
                        prev_error: Optional[str] = None) -> str:
        commit_example = self.FEAT_MSG.format(
            phase=self._phase_name, num="N", name="<step-name>"
        )
        retry_section = ""
        if prev_error:
            retry_section = (
                f"\n## ⚠ 이전 시도 실패 — 아래 에러를 반드시 참고하여 수정하라\n\n"
                f"{prev_error}\n\n---\n\n"
            )
        return (
            f"당신은 {self._project} 프로젝트의 개발자입니다. 아래 step을 수행하세요.\n\n"
            f"{guardrails}\n\n---\n\n"
            f"{step_context}{retry_section}"
            f"## 실행 환경 — 헤드리스\n\n"
            f"이 세션은 `claude -p`로 돈다. **턴을 끝내면 세션이 즉시 종료된다.** 명령을 "
            f"백그라운드로 띄우고 완료 알림을 기다리는 마무리는 그 알림을 받을 주체가 없어 "
            f"실패다(가드가 백그라운드 실행 자체를 막는다). 오래 걸리는 명령(통합 테스트 등)도 "
            f"포그라운드로 완주하고, AC 검증·index.json 갱신·커밋까지 한 턴 안에서 끝내라.\n\n"
            f"## 작업 규칙\n\n"
            f"1. 이전 step에서 작성된 코드를 확인하고 일관성을 유지하라.\n"
            f"2. 이 step에 명시된 작업만 수행하라. 추가 기능이나 파일을 만들지 마라.\n"
            f"3. 기존 테스트를 깨뜨리지 마라.\n"
            f"4. AC(Acceptance Criteria) 검증을 직접 실행하라.\n"
            f"5. /phases/{self._phase_dir_name}/index.json의 해당 step status를 업데이트하라:\n"
            f"   - AC 통과 → \"completed\" + \"summary\" 필드에 이 step의 산출물을 한 줄로 요약\n"
            f"   - {self.MAX_RETRIES}회 수정 시도 후에도 실패 → \"error\" + \"error_message\" 기록\n"
            f"   - 사용자 개입이 필요한 경우 (API 키, 인증, 수동 설정 등) → \"blocked\" + \"blocked_reason\" 기록 후 즉시 중단\n"
            f"6. 모든 변경사항을 커밋하라:\n"
            f"   {commit_example}\n\n---\n\n"
        )

    # --- Claude 호출 ---

    @staticmethod
    def _quota_message(output: dict) -> str | None:
        """할당량·요금 한도(HTTP 429)에 걸렸으면 사람에게 보여줄 문구를, 아니면 None을 돌려준다.

        claude -p --output-format json은 한도에 걸려도 종료 코드 1로 끝나서
        '세션이 status를 갱신하지 않았다'와 구별되지 않는다. 본문의 api_error_status로 가른다.
        """
        if output.get("exitCode", 0) == 0:
            return None
        try:
            body = json.loads(output.get("stdout") or "{}")
        except json.JSONDecodeError:
            return None
        if body.get("api_error_status") != 429:
            return None
        return str(body.get("result") or "사용 한도에 걸렸다 (HTTP 429)")

    # 검사 출력에서 다음 시도에 실어 보낼 분량. 실패 원인은 대개 끝에 있다.
    CHECK_TAIL_LINES = 40

    def _check_failure(self) -> Optional[str]:
        """검사를 돌려 통과하면 None, 실패하면 다음 시도에 넘길 에러 문장을 돌려준다.

        명령은 Stop 훅(scripts/hooks/stop-check.sh)과 같다: HARNESS_CHECK_CMD가 있으면 그것,
        없으면 scripts/check.sh. 둘 다 없으면 확인할 수단이 없으므로 경고만 하고 통과시킨다.
        """
        cmd = os.environ.get("HARNESS_CHECK_CMD")
        if cmd:
            argv, shown = ["bash", "-c", cmd], cmd
        elif (Path(self._root) / "scripts" / "check.sh").is_file():
            argv, shown = ["bash", "scripts/check.sh"], "scripts/check.sh"
        else:
            print("  WARN: scripts/check.sh가 없어 completed를 확인하지 못했다 — 세션의 신고를 그대로 믿는다")
            return None

        try:
            r = subprocess.run(argv, cwd=self._root, capture_output=True, text=True, timeout=1800)
            code, out = r.returncode, (r.stdout or "") + (r.stderr or "")
        except subprocess.TimeoutExpired:
            code, out = "timeout", "검사가 30분 안에 끝나지 않았다"
        if code == 0:
            return None

        tail = "\n".join(out.strip().splitlines()[-self.CHECK_TAIL_LINES:])
        return (
            f"세션이 status를 completed로 적었지만 `{shown}`가 실패했다 (exit {code}). "
            "completed는 이 검사가 통과한 뒤에만 인정된다. 아래 출력의 원인을 고치고, "
            "검사가 통과하는 것을 직접 확인한 뒤 completed를 적어라. 이 step이 고칠 수 없는 "
            "원인이면 completed 대신 blocked와 blocked_reason을 적어라.\n"
            f"--- 검사 출력의 끝 ---\n{tail}"
        )

    def _invoke_claude(self, step: dict, preamble: str) -> dict:
        step_num, step_name = step["step"], step["name"]
        step_file = self._phase_dir / f"step{step_num}.md"

        if not step_file.exists():
            print(f"  ERROR: {step_file} not found")
            sys.exit(1)

        prompt = preamble + step_file.read_text()
        try:
            result = subprocess.run(
                ["claude", "-p", "--model", self.HEADLESS_MODEL,
                 "--dangerously-skip-permissions", "--output-format", "json", prompt],
                cwd=self._root, capture_output=True, text=True, timeout=3600,
                # HARNESS_RUN은 훅에게 "사람이 안 보고 있다"를 알린다 — tdd-guard가 이때만
                # 자기 수정을 막는다. 대화형 세션까지 막으면 가드를 손볼 길이 없어진다.
                env={**os.environ, "HARNESS_RUN": "1"},
            )
        except subprocess.TimeoutExpired:
            # 예외 문자열에 cmd가 통째로 들어 있어 그냥 두면 주입 프롬프트 수만 자가
            # 터미널을 덮고 원인 한 줄이 묻힌다. 여기서 잘라 말한다.
            print(f"\n  ⏸ Step {step_num}: {step_name} — 60분 상한을 넘겨 중단했다")
            print(f"    세션이 멈춘 자리는 `git status`와 직전 커밋에서 본다.")
            print(f"    step은 pending 그대로다. 원인을 없앤 뒤 같은 명령으로 이어서 돌려라.")
            print(f"    재시도하지 않는다 — 60분 × 3회는 3시간을 버리는 일이다.")
            print(f"    남은 자식(uvicorn·pytest)이 포트 8080을 물고 있을 수 있다 —")
            print(f"    `lsof -nP -iTCP:8080 -sTCP:LISTEN`으로 보고 걷어낸 뒤 재실행해라.")
            sys.exit(4)

        if result.returncode != 0:
            print(f"\n  WARN: Claude가 비정상 종료됨 (code {result.returncode})")
            if result.stderr:
                print(f"  stderr: {result.stderr[:500]}")

        output = {
            "step": step_num, "name": step_name,
            "exitCode": result.returncode,
            "stdout": result.stdout, "stderr": result.stderr,
        }
        out_path = self._phase_dir / f"step{step_num}-output.json"
        with open(out_path, "w") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        return output

    # --- 헤더 & 검증 ---

    def _print_header(self):
        print(f"\n{'='*60}")
        print(f"  Harness Step Executor")
        print(f"  Phase: {self._phase_name} | Steps: {self._total}")
        if self._auto_push:
            print(f"  Auto-push: enabled")
        print(f"{'='*60}")

    def _check_blockers(self):
        index = self._read_json(self._index_file)
        for s in reversed(index["steps"]):
            if s["status"] == "error":
                print(f"\n  ✗ Step {s['step']} ({s['name']}) failed.")
                print(f"  Error: {s.get('error_message', 'unknown')}")
                print(f"  Fix and reset status to 'pending' to retry.")
                sys.exit(1)
            if s["status"] == "blocked":
                print(f"\n  ⏸ Step {s['step']} ({s['name']}) blocked.")
                print(f"  Reason: {s.get('blocked_reason', 'unknown')}")
                print(f"  Resolve and reset status to 'pending' to retry.")
                sys.exit(2)
            if s["status"] != "pending":
                break

    def _ensure_created_at(self):
        index = self._read_json(self._index_file)
        if "created_at" not in index:
            index["created_at"] = self._stamp()
            self._write_json(self._index_file, index)

    # --- 실행 루프 ---

    def _execute_single_step(self, step: dict, guardrails: str) -> bool:
        """단일 step 실행 (재시도 포함). 완료되면 True, 실패/차단이면 False."""
        step_num, step_name = step["step"], step["name"]
        done = sum(1 for s in self._read_json(self._index_file)["steps"] if s["status"] == "completed")
        prev_error = None

        for attempt in range(1, self.MAX_RETRIES + 1):
            index = self._read_json(self._index_file)
            step_context = self._build_step_context(index)
            preamble = self._build_preamble(guardrails, step_context, prev_error)

            tag = f"Step {step_num}/{self._total - 1} ({done} done): {step_name}"
            if attempt > 1:
                tag += f" [retry {attempt}/{self.MAX_RETRIES}]"

            with progress_indicator(tag) as pi:
                output = self._invoke_claude(step, preamble)
            # elapsed는 with를 빠져나온 뒤에 읽는다 — progress_indicator가 finally에서 채운다
            elapsed = int(pi.elapsed)

            # 할당량 소진은 step의 실패가 아니다. 재시도해도 같은 벽이라 3회를 태울 뿐이고,
            # error로 기록하면 재개할 때 손으로 JSON을 되돌려야 한다. 여기서 즉시 멈춘다.
            limit = self._quota_message(output)
            if limit is not None:
                print(f"\n  ⏸ Step {step_num}: {step_name} — 사용 한도에 걸렸다 [{elapsed}s]")
                print(f"    {limit}")
                print(f"    step은 pending 그대로다. 한도가 풀리면 같은 명령으로 이어서 돌리면 된다.")
                sys.exit(3)

            index = self._read_json(self._index_file)
            status = next((s.get("status", "pending") for s in index["steps"] if s["step"] == step_num), "pending")
            ts = self._stamp()

            # completed는 세션의 자기 신고다. 검사를 여기서 직접 돌려 확인한 뒤에만 인정한다 —
            # Stop 훅은 세 번 되돌린 뒤 놓아주므로, 세션이 빨간 검사 위에 completed를 적고
            # 끝날 수 있다(시험용 phase smoke-harness에서 실제로 그렇게 기록됐다).
            check_failure = None
            if status == "completed":
                check_failure = self._check_failure()
                if check_failure is None:
                    for s in index["steps"]:
                        if s["step"] == step_num:
                            s["completed_at"] = ts
                    self._write_json(self._index_file, index)
                    self._commit_step(step_num, step_name)
                    print(f"  ✓ Step {step_num}: {step_name} [{elapsed}s]")
                    return True

            if status == "blocked":
                for s in index["steps"]:
                    if s["step"] == step_num:
                        s["blocked_at"] = ts
                self._write_json(self._index_file, index)
                reason = next((s.get("blocked_reason", "") for s in index["steps"] if s["step"] == step_num), "")
                print(f"  ⏸ Step {step_num}: {step_name} blocked [{elapsed}s]")
                print(f"    Reason: {reason}")
                self._update_top_index("blocked")
                sys.exit(2)

            err_msg = next(
                (s.get("error_message", "Step did not update status") for s in index["steps"] if s["step"] == step_num),
                "Step did not update status",
            )
            if check_failure is not None:
                err_msg = check_failure
            if err_msg == "Step did not update status":
                # 세션이 status를 안 건드리고 끝난 것 — 다음 시도가 같은 함정을 밟지 않게
                # 흔한 원인과 처방을 에러에 실어 보낸다(Epic 5 step 17: e2e를 백그라운드로
                # 띄우고 알림을 기다리며 턴을 끝내 3회를 태웠다)
                err_msg += (
                    " — 세션이 index.json의 status를 갱신하지 않고 턴을 끝냈다. "
                    "흔한 원인: 명령을 백그라운드로 띄우고 완료를 기다리며 턴을 종료"
                    "(헤드리스에선 알림이 오지 않는다). 모든 명령을 포그라운드로 완주하고 "
                    "같은 턴에서 status 갱신까지 마쳐라."
                )

            if attempt < self.MAX_RETRIES:
                for s in index["steps"]:
                    if s["step"] == step_num:
                        s["status"] = "pending"
                        s.pop("error_message", None)
                self._write_json(self._index_file, index)
                prev_error = err_msg
                print(f"  ↻ Step {step_num}: retry {attempt}/{self.MAX_RETRIES} — {err_msg}")
            else:
                for s in index["steps"]:
                    if s["step"] == step_num:
                        s["status"] = "error"
                        s["error_message"] = f"[{self.MAX_RETRIES}회 시도 후 실패] {err_msg}"
                        s["failed_at"] = ts
                self._write_json(self._index_file, index)
                self._commit_step(step_num, step_name)
                print(f"  ✗ Step {step_num}: {step_name} failed after {self.MAX_RETRIES} attempts [{elapsed}s]")
                print(f"    Error: {err_msg}")
                self._update_top_index("error")
                sys.exit(1)

        return False  # unreachable

    def _execute_all_steps(self, guardrails: str):
        while True:
            index = self._read_json(self._index_file)
            pending = next((s for s in index["steps"] if s["status"] == "pending"), None)
            if pending is None:
                print("\n  All steps completed!")
                return

            step_num = pending["step"]
            for s in index["steps"]:
                if s["step"] == step_num and "started_at" not in s:
                    s["started_at"] = self._stamp()
                    self._write_json(self._index_file, index)
                    break

            self._execute_single_step(pending, guardrails)

    def _unchecked_manual_items(self) -> list[str]:
        """MANUAL.md에 남은 `- [ ]` 항목. 파일이 없으면 빈 목록이다."""
        manual = self._phase_dir / "MANUAL.md"
        if not manual.exists():
            return []
        items = []
        for line in manual.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("- [ ]"):
                items.append(stripped[5:].strip())
        return items

    def _finalize(self):
        index = self._read_json(self._index_file)

        # 자동 AC가 전부 통과해도 요구사항이 깨져 있을 수 있다. Epic 0에서 세 번 그랬고
        # 셋 다 MANUAL.md의 육안 확인에서 잡혔다. 사람이 보기 전에는 완료로 찍지 않는다.
        pending_manual = self._unchecked_manual_items()
        if pending_manual:
            print(f"\n  ⏸ MANUAL.md에 확인 안 된 항목이 {len(pending_manual)}개 남았다")
            for item in pending_manual[:10]:
                print(f"     - {item}")
            if len(pending_manual) > 10:
                print(f"     … 외 {len(pending_manual) - 10}개")
            print(f"  코드는 이미 커밋됐다. 사람이 확인한 뒤 같은 명령을 다시 돌려라.")
            sys.exit(5)

        # 이미 완료된 phase를 다시 돌려도 completed_at을 덮거나 커밋을 또 만들지 않는다
        if "completed_at" in index:
            print(f"\n  Phase '{self._phase_name}'는 이미 완료됐다 ({index['completed_at']}).")
            return

        index["completed_at"] = self._stamp()
        self._write_json(self._index_file, index)
        self._update_top_index("completed")

        self._run_git("add", "-A")
        if self._run_git("diff", "--cached", "--quiet").returncode != 0:
            msg = f"chore({self._phase_name}): mark phase completed"
            r = self._run_git("commit", "-m", msg)
            if r.returncode == 0:
                print(f"  ✓ {msg}")

        if self._auto_push:
            branch = f"feat-{self._phase_name}"
            r = self._run_git("push", "-u", "origin", branch)
            if r.returncode != 0:
                print(f"\n  ERROR: git push 실패: {r.stderr.strip()}")
                sys.exit(1)
            print(f"  ✓ Pushed to origin/{branch}")

        print(f"\n{'='*60}")
        print(f"  Phase '{self._phase_name}' completed!")
        print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(description="Harness Step Executor")
    parser.add_argument("phase_dir", help="Phase directory name (e.g. 0-mvp)")
    parser.add_argument("--push", action="store_true", help="Push branch after completion")
    args = parser.parse_args()

    StepExecutor(args.phase_dir, auto_push=args.push).run()


if __name__ == "__main__":
    main()
