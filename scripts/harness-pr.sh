#!/usr/bin/env bash
# harness-pr.sh — 완료된 phase의 PR을 준비한다.
#
#   사용법: scripts/harness-pr.sh {task} [--create] [--base <브랜치>]
#
#   기본은 드라이런이다. 관문을 검사하고 PR의 제목과 본문을 표준 출력에 찍기만 한다.
#   --create를 줘야 브랜치를 push하고 PR을 연다. --base는 PR이 향할 브랜치다(기본 main).
#
# PR은 레포 밖에 보이는 행동이다. 사람이 본문을 보고 승인한 뒤에만 --create를 붙인다.
# 헤드리스 세션은 이 길로도 PR을 열 수 없다 — bash-guard가 그 세션의 push와 gh pr create를 막는다.
#
# OnlineFourCut은 PR 없이 로컬에서 main에 합쳤다. 이 레포는 main에 합쳐지면 배포되므로
# (docs/DECISIONS.md D-23) PR이 배포의 관문이고, 이 스크립트가 그 관문 앞의 점검이다.
#
#   종료 코드: 0 준비됨(또는 PR을 열었다) · 1 관문에 걸렸다 · 64 사용법 오류
#   테스트: bash scripts/harness-pr.test.sh
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# 관문을 검사한다. 걸린 것을 한 줄씩 찍고, 하나라도 걸리면 1로 끝난다.
# 검사 명령(scripts/check.sh)은 여기서 돌리지 않는다 — 본문을 만들 때 돌려 결과를 싣는다.
pr_gates() { # pr_gates <레포 루트> <task>
  python3 - "$1" "$2" <<'PY'
import json
import re
import subprocess
import sys
from pathlib import Path

root, task = Path(sys.argv[1]), sys.argv[2]
phase = root / "phases" / task
problems: list[str] = []


def bad(message: str) -> None:
    problems.append(message)
    print(message)


def marker(path: Path, kind: str, key: str) -> int | None:
    """리포트 끝의 기계 판독용 줄에서 값을 읽는다. harness-run.sh의 read_marker와 같은 규칙이다."""
    lines = [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if re.fullmatch(rf"<!-- {kind}: .*-->\s*", line)
    ]
    if not lines:
        return None
    found = re.findall(rf"(?:^|\s){re.escape(key)}=(\d+)", lines[-1])
    return int(found[-1]) if found else None


def round_of(path: Path) -> int:
    return int(path.stem.split("-")[1])


try:
    index = json.loads((phase / "index.json").read_text(encoding="utf-8"))
    steps = index["steps"]
    assert isinstance(steps, list) and steps
except (OSError, ValueError, KeyError, TypeError, AssertionError):
    bad(f"phases/{task}/index.json을 읽을 수 없거나 step이 없다")
    sys.exit(1)

pending = [s.get("name", "?") for s in steps if not isinstance(s, dict) or s.get("status") != "completed"]
if pending:
    bad(f"completed가 아닌 step이 있다: {', '.join(map(str, pending))}")

manual = phase / "MANUAL.md"
if manual.exists():
    unchecked = [
        line for line in manual.read_text(encoding="utf-8").splitlines() if line.strip().startswith("- [ ]")
    ]
    if unchecked:
        bad(f"MANUAL.md에 확인 안 된 항목이 {len(unchecked)}개 남았다")

if "completed_at" not in index:
    bad("phase가 완료로 찍히지 않았다 — scripts/harness-run.sh를 다시 돌려 종료 코드 0을 봐라")

branch = subprocess.run(
    ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=root, capture_output=True, text=True
).stdout.strip()
if branch != f"feat-{task}":
    bad(f"지금 브랜치가 feat-{task}가 아니다 (현재: {branch or '알 수 없음'})")

dirty = subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True).stdout
if dirty.strip():
    bad("커밋되지 않은 변경이 있다 — PR에 실리지 않는다")

review_dir = phase / "review"
reviews = sorted(
    (p for p in review_dir.glob("review-*.md") if re.fullmatch(r"review-\d+", p.stem)), key=round_of
)
if not reviews:
    bad("리뷰 리포트가 없다 — 리뷰를 거치지 않은 phase는 PR로 올리지 않는다")
else:
    last = reviews[-1]
    n = round_of(last)
    counts = {key: marker(last, "verdict", key) for key in ("critical", "major", "minor")}
    if None in counts.values():
        bad(f"{last.name} 끝에 verdict 줄이 없다")
    else:
        if counts["critical"] or counts["major"]:
            bad(
                f"마지막 리뷰({last.name})에 critical {counts['critical']} · major {counts['major']}가 있다"
                " — 고친 결과가 재리뷰로 확인되지 않았다"
            )
        elif counts["minor"] and not (review_dir / f"fix-{n}.md").exists():
            bad(f"마지막 리뷰({last.name})의 minor {counts['minor']}건에 대한 처분 기록(fix-{n}.md)이 없다")

# 최종 요약(scripts/harness-summary.sh). PR 본문의 "만든 것"이 이 파일이다. step의 summary는
# 처분 전에 쓴 것이라 싣지 않는다. 요약이 다룬 커밋 뒤로 코드가 바뀌었으면 낡은 요약이다 —
# harness-summary.sh의 summary_is_current와 같은 규칙이다. 커밋하지 않은 변경은 위의 관문이 잡는다.
summary_rel = f"phases/{task}/summary.md"
summary_path = root / summary_rel


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)


summary_text = summary_path.read_text(encoding="utf-8") if summary_path.exists() else ""
summary_marks = re.findall(r"^<!-- summary-of: ([0-9a-f]{40}) -->\s*$", summary_text, re.MULTILINE)
summary_body = "\n".join(line for line in summary_text.splitlines() if not line.lstrip().startswith("<!-- summary-of:"))
if not summary_body.strip():
    bad(f"최종 요약({summary_rel})이 없다 — scripts/harness-summary.sh {task}로 쓴다")
elif (
    not summary_marks
    or git("ls-files", "--error-unmatch", "--", summary_rel).returncode != 0
    or git("rev-parse", "--verify", "--quiet", f"{summary_marks[-1]}^{{commit}}").returncode != 0
):
    bad(f"최종 요약({summary_rel})이 다룬 커밋을 읽을 수 없다 — scripts/harness-summary.sh {task} --force로 다시 쓴다")
elif git("diff", "--quiet", summary_marks[-1], "HEAD", "--", ".", ":(exclude)phases").returncode != 0:
    bad(f"최종 요약을 쓴 뒤로 코드가 바뀌었다 — scripts/harness-summary.sh {task}로 다시 쓴다")

for fix in sorted(review_dir.glob("fix-*.md")):
    waiting = marker(fix, "disposition", "needs-human")
    if waiting is None:
        bad(f"{fix.name} 끝에 disposition 줄이 없다")
    elif waiting:
        bad(
            f"{fix.name}에 사람 판단 필요가 {waiting}건 남았다"
            " — 정한 뒤 그 항목을 '고쳤다'나 '기각했다'로 옮기고 disposition 줄의 숫자를 고쳐라"
        )

sys.exit(1 if problems else 0)
PY
}

# PR의 제목을 첫 줄에, 본문을 그 뒤에 찍는다. 셋째 인자는 검사 결과의 요약이다.
pr_text() { # pr_text <레포 루트> <task> <검사 요약>
  python3 - "$1" "$2" "$3" <<'PY'
import json
import re
import sys
from pathlib import Path

root, task, check_summary = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
phase = root / "phases" / task
review_dir = phase / "review"
index = json.loads((phase / "index.json").read_text(encoding="utf-8"))

# Epic 문서: phases/3-books ↔ docs/backlog/epic-3/E3-*.md, phases/bugfix-1 ↔ docs/backlog/bugfix-1/*.md
epic_doc = None
m = re.match(r"(\d+)-", task)
if m:
    found = sorted((root / "docs" / "backlog" / f"epic-{m.group(1)}").glob(f"E{m.group(1)}-*.md"))
    epic_doc = found[0] if found else None
elif (root / "docs" / "backlog" / task).is_dir():
    found = sorted(p for p in (root / "docs" / "backlog" / task).glob("*.md") if p.name != "testcase.md")
    epic_doc = found[0] if found else None

title = task
issue = None
if epic_doc:
    text = epic_doc.read_text(encoding="utf-8")
    t = re.search(r"^title:\s*(.+)$", text, re.MULTILINE)
    if t:
        title = t.group(1).strip().strip("\"'")
    for line in text.splitlines():
        if "GitHub 이슈" in line:
            num = re.search(r"#(\d+)", line)
            if num:
                issue = num.group(1)
                break

print(f"feat({task}): {title}")

out: list[str] = []
if issue:
    out += [f"Closes #{issue}", ""]
if epic_doc:
    out += [f"Epic 문서: `{epic_doc.relative_to(root)}`", ""]

# 처분까지 끝난 코드를 다시 읽고 쓴 최종 요약이다(scripts/harness-summary.sh). 관문이 있는지와
# 최신인지를 이미 확인했다. 판독용 줄은 싣지 않는다.
out += ["## 만든 것", ""]
summary = (phase / "summary.md").read_text(encoding="utf-8")
out += "\n".join(
    line for line in summary.splitlines() if not line.lstrip().startswith("<!-- summary-of:")
).strip().splitlines()
out.append("")


def round_of(path: Path) -> int:
    return int(path.stem.split("-")[1])


def marker(path: Path, kind: str, key: str) -> int | None:
    """파일 끝의 판독용 줄에서 값을 읽는다. 관문의 marker와 같은 규칙이다."""
    lines = [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if re.fullmatch(rf"<!-- {kind}: .*-->\s*", line)
    ]
    found = re.findall(rf"(?:^|\s){re.escape(key)}=(\d+)", lines[-1]) if lines else []
    return int(found[-1]) if found else None


def shown(value: int | None) -> str:
    return "?" if value is None else str(value)


# 라운드마다 리뷰가 찾은 결함과 그 처분을 한 줄에 싣는다. 리뷰 리포트의 판정표를 그대로 옮기지
# 않는다 — 그 표는 처분 전의 상태라서, 처분으로 닫힌 결함이 남아 있는 것처럼 읽힌다.
reviews = sorted(
    (p for p in review_dir.glob("review-*.md") if re.fullmatch(r"review-\d+", p.stem)), key=round_of
)
out += ["## 리뷰와 처분", ""]
if reviews:
    rows: list[str] = []
    quotes: list[str] = []
    rejected_total = 0
    for review in reviews:
        n = round_of(review)
        found = " · ".join(shown(marker(review, "verdict", k)) for k in ("critical", "major", "minor"))
        fix = review_dir / f"fix-{n}.md"
        if fix.exists():
            fixed, rejected, waiting = (marker(fix, "disposition", k) for k in ("fixed", "rejected", "needs-human"))
            rejected_total += rejected or 0
            rows.append(f"| {n}차 | {found} | {shown(fixed)} | {shown(rejected)} | {shown(waiting)} |")
            quote = [line[1:].strip() for line in fix.read_text(encoding="utf-8").splitlines() if line.startswith(">")]
            quotes.append(f"- {n}차 `{fix.relative_to(root)}`: {' '.join(quote) or '(머리 요약 없음)'}")
        else:
            rows.append(f"| {n}차 | {found} | — | — | — |")
    out += [
        f"리뷰를 {len(reviews)}라운드 돌았습니다. 라운드마다 별도 세션이 리뷰하고, 또 다른 세션이 처분했습니다.",
        "",
        "| 라운드 | 리뷰가 찾은 결함 (critical · major · minor) | 고침 | 기각 | 사람 판단 필요 |",
        "|---|---|---|---|---|",
        *rows,
        "",
    ]
    # 관문이 확인한 것: 마지막 리뷰에 critical·major가 없고, 모든 처분 기록의 사람 판단 필요가 0이다.
    closing = ["남은 결함은 없습니다. 리뷰가 찾은 결함은 모두 고쳤거나, 근거를 들어 기각했습니다."]
    if rejected_total:
        closing.append(f"기각한 {rejected_total}건의 근거는 각 라운드의 처분 기록에 있습니다.")
    last = reviews[-1]
    n = round_of(last)
    if (review_dir / f"fix-{n}.md").exists():
        closing.append(f"마지막 라운드({n}차)는 minor만 있어서, 처분한 결과를 다시 리뷰하지 않았습니다.")
    else:
        closing.append(f"마지막 리뷰({n}차)는 결함을 찾지 못했습니다.")
    out += [" ".join(closing), ""]
    if quotes:
        out += quotes + [""]

out += ["## 사람이 확인한 것", ""]
manual = phase / "MANUAL.md"
checked = (
    [line.strip() for line in manual.read_text(encoding="utf-8").splitlines() if line.strip().startswith("- [x]")]
    if manual.exists()
    else []
)
out += checked or ["이 phase에는 사람이 따로 확인할 항목이 없습니다."]
if checked:
    out += ["", f"관찰한 값은 `{manual.relative_to(root)}`에 있습니다."]
out.append("")

out += ["## 검사", "", "`scripts/check.sh --all`의 결과입니다.", "", "```", check_summary.strip(), "```", ""]
out += ["🤖 Generated with [Claude Code](https://claude.com/claude-code)"]
print("\n".join(out))
PY
}

# 테스트가 함수만 가져갈 때는 여기서 멈춘다.
[ -n "${HARNESS_PR_LIB:-}" ] && return 0

say() { echo "harness-pr: $*" >&2; }

task="${1:-}"
if [ -z "$task" ] || [ "${task#-}" != "$task" ]; then
  echo "usage: scripts/harness-pr.sh {task} [--create] [--base <브랜치>]" >&2
  exit 64
fi
shift

create=""
base="main"
while [ $# -gt 0 ]; do
  case "$1" in
    --create)
      create=1
      shift
      ;;
    --base)
      base="${2:-}"
      [ -n "$base" ] || {
        say "--base 뒤에 브랜치가 없다"
        exit 64
      }
      shift 2
      ;;
    --base=*)
      base="${1#*=}"
      shift
      ;;
    *)
      say "모르는 인자: $1"
      exit 64
      ;;
  esac
done

if [ ! -d "$ROOT/phases/$task" ]; then
  say "phases/$task 가 없다"
  exit 64
fi

say "관문을 검사한다"
problems="$(pr_gates "$ROOT" "$task")"
if [ -n "$problems" ]; then
  say "⏸ PR로 올릴 수 없다:"
  printf '%s\n' "$problems" | sed 's/^/  - /' >&2
  exit 1
fi

# 검사를 지금 다시 돌린다. 리뷰 때의 결과가 아니라 PR에 실릴 코드의 결과여야 한다.
say "검사를 돌린다 (scripts/check.sh --all)"
if [ -n "${HARNESS_CHECK_CMD:-}" ]; then
  check_out="$(cd "$ROOT" && bash -c "$HARNESS_CHECK_CMD" 2>&1)"
else
  check_out="$(cd "$ROOT" && bash scripts/check.sh --all 2>&1)"
fi
check_code=$?
# 요약 줄만 싣는다. 요약이 없으면(검사 명령을 바꿔 끼운 경우) 끝의 몇 줄을 싣는다.
check_summary="$(printf '%s\n' "$check_out" | sed -n '/^=== 요약$/,$p' | sed '1d')"
[ -n "$check_summary" ] || check_summary="$(printf '%s\n' "$check_out" | tail -n 8)"
if [ "$check_code" -ne 0 ]; then
  say "⏸ 검사가 실패했다 (종료 코드 $check_code) — 빨간 코드는 PR로 올리지 않는다:"
  printf '%s\n' "$check_summary" | sed 's/^/  /' >&2
  exit 1
fi

text="$(pr_text "$ROOT" "$task" "$check_summary")" || {
  say "PR 본문을 만들지 못했다"
  exit 1
}
title="$(printf '%s\n' "$text" | sed -n '1p')"
body="$(printf '%s\n' "$text" | sed '1d')"
branch="feat-$task"

if [ -z "$create" ]; then
  echo "제목: $title"
  echo "대상: $branch → $base"
  echo
  printf '%s\n' "$body"
  echo
  say "관문을 통과했다. 위 내용으로 PR을 열려면 사람의 승인을 받은 뒤 --create를 붙여 다시 실행해라."
  exit 0
fi

command -v gh >/dev/null 2>&1 || {
  say "gh 명령이 없다"
  exit 1
}

say "브랜치를 push한다 ($branch)"
git -C "$ROOT" push -u origin "$branch" >&2 || {
  say "push가 실패했다"
  exit 1
}

body_file="$(mktemp "${TMPDIR:-/tmp}/harness-pr-body.XXXXXX")"
trap 'rm -f "$body_file"' EXIT
printf '%s\n' "$body" >"$body_file"

say "PR을 연다 ($branch → $base)"
(cd "$ROOT" && gh pr create --base "$base" --head "$branch" --title "$title" --body-file "$body_file") || {
  say "gh pr create가 실패했다 — 브랜치는 이미 push됐다"
  exit 1
}
