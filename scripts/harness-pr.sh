#!/usr/bin/env bash
# harness-pr.sh — 완료된 phase의 PR을 준비한다.
#
#   사용법: scripts/harness-pr.sh {task} [--create] [--base <브랜치>]
#
#   기본은 드라이런이다. 관문을 검사하고 PR의 제목과 본문을 표준 출력에 찍기만 한다.
#   --create를 줘야 브랜치를 push하고 PR을 연다. 그 브랜치의 PR이 이미 열려 있으면 새로 열지
#   않고 그 PR의 제목과 본문을 지금의 내용으로 바꾼다. --base는 PR이 향할 브랜치다(기본 main).
#
#   흐름: 관문 → 검사(scripts/check.sh --all) → 최종 요약 → 본문. 본문은 언제나 지금의 코드로
#   만든다. "만든 것"은 별도 세션이 지금의 코드를 읽고 쓴 요약이고(pr_summary), "리뷰와 처분"은
#   리뷰와 처분 기록을 그때 읽는다. PR을 연 뒤에 코드가 바뀌면 --create로 다시 돌려 본문을 맞춘다.
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

# PR의 제목을 첫 줄에, 본문을 그 뒤에 찍는다. 셋째 인자는 검사 결과의 요약, 넷째는 pr_summary가 찍은 최종 요약이다.
pr_text() { # pr_text <레포 루트> <task> <검사 요약> <최종 요약>
  python3 - "$1" "$2" "$3" "$4" <<'PY'
import json
import re
import sys
from pathlib import Path

root, task, check_summary, summary = Path(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4]
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

# step의 summary는 처분 전에 쓴 것이라 싣지 않는다. pr_summary를 보라.
out += ["## 만든 것", "", *summary.strip().splitlines(), ""]


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

# PR 본문의 "만든 것"을 표준 출력에 찍는다. 별도 헤드리스 세션이 지금의 코드를 읽고 쓴 요약이다.
# step의 summary는 각 step이 끝날 때 쓴 것이라 리뷰 처분과 사람의 수정이 빠져 있다.
#
# 요약은 레포에 남기지 않고 PR 본문에만 싣는다. 같은 코드로 다시 쓰지 않으려고 git 디렉터리
# (git rev-parse --git-path harness-pr/{task}.summary.md)에 둔다. 첫 줄이 요약이 다룬 코드 커밋 —
# phases/ 밖을 마지막으로 바꾼 커밋 — 이고, 그 커밋이 그대로면 세션을 띄우지 않는다. 그래서
# 드라이런에서 사람이 승인한 본문이 --create에서 그대로 나간다. phases/ 아래(MANUAL 체크, 처분
# 기록)는 코드가 아니므로 세지 않는다. 그 내용은 본문의 다른 절이 매번 새로 읽는다.
pr_summary() { # pr_summary <레포 루트> <task> <base>
  local root="$1" task="$2" base="$3" code cache draft_dir draft prompt model log head_before session_code
  code="$(git -C "$root" log -1 --format=%H -- . ':(exclude)phases')"
  [ -n "$code" ] || code="$(git -C "$root" rev-parse HEAD)"
  cache="$(git -C "$root" rev-parse --path-format=absolute --git-path "harness-pr/$task.summary.md")"
  if [ "$(head -n 1 "$cache" 2>/dev/null)" = "<!-- summary-of: $code -->" ]; then
    say "최종 요약이 지금의 코드를 다룬다 — 다시 쓰지 않는다"
    sed '1d' "$cache"
    return 0
  fi
  rm -f "$cache"

  # 범위의 기준은 PR이 향할 브랜치다. 로컬에 없으면 원격의 것을 쓴다. 둘 다 없으면 세션이 빈
  # diff를 보고 "만든 것이 없다"고 쓰므로 멈춘다.
  if ! git -C "$root" rev-parse --verify --quiet "$base^{commit}" >/dev/null; then
    if git -C "$root" rev-parse --verify --quiet "origin/$base^{commit}" >/dev/null; then
      base="origin/$base"
    else
      say "요약할 범위의 기준($base)을 이 저장소에서 찾을 수 없다"
      return 1
    fi
  fi

  # 세션은 레포 밖의 임시 파일에 쓴다. 그래야 세션이 레포를 바꿨는지를 git status로 가를 수 있다.
  draft_dir="$(mktemp -d "${TMPDIR:-/tmp}/harness-pr-summary.XXXXXX")" || return 1
  draft="$draft_dir/summary.md"
  prompt="phase \`$task\`의 PR 본문에 실을 최종 요약을 \`$draft\`에 써라.

이 phase는 step 실행, 리뷰, 리뷰 처분을 모두 거쳤다. 요약은 그 과정이 아니라 지금 브랜치에 있는 최종 결과를 설명한다. PR을 검토하는 사람이 이 요약만 읽고 이 phase가 무엇을 만들었는지 알 수 있어야 한다.

## 읽을 것

- \`phases/$task/index.json\`의 step별 \`name\`과 \`summary\`. step이 끝날 때 쓴 것이라 뒤의 처분과 사람의 수정이 빠져 있다. 요약의 뼈대로만 쓴다.
- \`phases/$task/review/fix-*.md\`의 \"고쳤다\"와 \"기각했다\". 리뷰 뒤에 무엇이 바뀌었는지 알려 준다.
- \`git diff --stat $base...HEAD\`와 바뀐 파일의 지금 내용. 요약의 근거는 코드다. 기록과 코드가 다르면 코드를 따른다.

## 형식

- 제목 없이 목록만 쓴다. PR 본문이 \"## 만든 것\" 아래에 이 파일을 그대로 싣는다.
- step마다 첫 단계 항목을 하나 둔다. 꼴은 \"- step N \`이름\`: 이 step이 만든 것을 한 문장으로\"이다.
- 그 아래에 두 칸 들여 쓴 둘째 단계 항목을 2~5개 둔다. 최종 코드의 동작이나 규칙을 한 항목에 한 가지씩 한 줄로 적는다. 리뷰 처분으로 바뀐 것은 바뀐 뒤의 모습으로 적는다.
- 어느 step에도 속하지 않는 변경(가드, 문서, harness 스크립트 등)은 마지막의 \`- 그 밖에\` 아래에 같은 방식으로 적는다. 없으면 그 항목을 두지 않는다.
- 테스트의 개수, 커밋 해시, 세션의 시행착오, 리뷰와 처분의 경과는 적지 않는다. 그것은 PR 본문의 다른 절이 싣는다.
- \`docs/DECISIONS.md\`의 문서 작성 규칙을 따른다. 명사만 나열하지 말고 완성된 문장으로 쓴다.

## 금지

- 레포 안의 파일을 만들거나 고치지 마라. 이유: 요약은 레포에 남기지 않고 PR 본문에만 싣는다. 레포가 바뀌면 스크립트가 요약을 버리고 멈춘다.
- 커밋하지 마라.
- 비밀값, 토큰, Docker Hub의 사용자 이름이나 이미지의 전체 이름을 적지 마라. 이유: 레포와 PR이 공개다(docs/DECISIONS.md의 D-37).

**되묻지 말고 그대로 진행하라** — 이 세션은 헤드리스라 질문에 답이 오지 않는다."

  model="${HARNESS_MODEL:-claude-opus-5-5}"
  log="$root/phases/$task/review/session.log"
  mkdir -p "$(dirname "$log")"
  say "최종 요약 세션 ($task, $base...HEAD) — 로그 → $log"
  head_before="$(git -C "$root" rev-parse HEAD)"
  # HARNESS_REVIEW는 리뷰 세션과 같은 제약을 건다: 종료 검사를 건너뛰고, 백그라운드 실행과 push를 막는다.
  # 세션의 출력은 본문이 아니므로 표준 오류로 보낸다.
  (cd "$root" && HARNESS_REVIEW=1 claude -p --model "$model" --dangerously-skip-permissions "$prompt") 2>&1 | tee -a "$log" >&2
  session_code="${PIPESTATUS[0]}"

  local ok=""
  if [ "$(git -C "$root" rev-parse HEAD)" != "$head_before" ]; then
    say "요약 세션이 커밋했다 — \`git log\`로 보고 정리해라."
  elif [ -n "$(git -C "$root" status --porcelain)" ]; then
    say "요약 세션이 레포를 바꿨다 — \`git status\`로 보고 정리해라."
  elif ! grep -q '[^[:space:]]' "$draft" 2>/dev/null; then
    say "요약 세션이 요약을 남기지 않았다 (claude 종료 코드 $session_code). 로그: $log"
  else
    mkdir -p "$(dirname "$cache")"
    { echo "<!-- summary-of: $code -->"; grep -v '^<!-- summary-of:' "$draft"; } >"$cache"
    ok=1
  fi
  rm -f "$draft"
  rmdir "$draft_dir" 2>/dev/null
  [ -n "$ok" ] || return 1
  sed '1d' "$cache"
}

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

# 요약은 검사가 통과한 뒤에 쓴다. 빨간 코드에 요약 세션을 쓰지 않는다. 리뷰와 처분이 닫힐 때
# 쓰지 않고 여기서 쓰는 것은, 그 뒤의 처분이나 사람의 수정이 본문에서 빠지지 않게 하려는 것이다.
summary="$(pr_summary "$ROOT" "$task" "$base")" || {
  say "⏸ 최종 요약을 쓰지 못했다 — 위의 이유를 고친 뒤 다시 실행해라."
  exit 1
}

text="$(pr_text "$ROOT" "$task" "$check_summary" "$summary")" || {
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
  say "관문을 통과했다. 위 내용으로 PR을 열려면 사람의 승인을 받은 뒤 --create를 붙여 다시 실행해라. 이 브랜치의 PR이 이미 열려 있으면 그 제목과 본문을 위 내용으로 바꾼다."
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

# 이미 열린 PR이 있으면 새로 열지 않고 그 PR의 제목과 본문을 바꾼다. PR을 연 뒤에 처분이나
# 사람의 수정이 들어와도 본문이 코드와 어긋나지 않게 하려는 것이다. 찾지 못했으면(네트워크,
# 인증) PR을 새로 열지 않고 멈춘다 — 열린 PR이 있는데 하나 더 열면 되돌려도 흔적이 남는다.
existing="$(cd "$ROOT" && gh pr list --head "$branch" --base "$base" --state open --json number --jq '.[0].number // empty')" || {
  say "열린 PR을 찾지 못했다 (gh pr list) — 브랜치는 이미 push됐다"
  exit 1
}
if [ -n "$existing" ]; then
  say "열린 PR #$existing 의 제목과 본문을 바꾼다 ($branch → $base)"
  (cd "$ROOT" && gh pr edit "$existing" --title "$title" --body-file "$body_file") || {
    say "gh pr edit가 실패했다 — 브랜치는 이미 push됐다"
    exit 1
  }
  exit 0
fi

say "PR을 연다 ($branch → $base)"
(cd "$ROOT" && gh pr create --base "$base" --head "$branch" --title "$title" --body-file "$body_file") || {
  say "gh pr create가 실패했다 — 브랜치는 이미 push됐다"
  exit 1
}
