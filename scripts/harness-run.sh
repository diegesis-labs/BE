#!/usr/bin/env bash
# harness-run.sh — execute.py를 돌리고, 모든 step이 완료되면 리뷰와 리뷰 처분을 이어서 돌린다.
#
#   사용법: scripts/harness-run.sh {task} [--push] [--review-base <ref>] [--no-fix]
#
#   OnlineFourCut의 scripts/harness-run.sh를 옮긴 것이다. 원본은 리뷰까지만 띄웠고 처분은
#   사람이 대화형 세션에서 했다. 여기서는 처분까지 무인으로 돌린다.
#
#   흐름: execute.py → 리뷰(review-N.md) → 처분(fix-N.md) → critical·major가 있었으면 재리뷰 …
#   최대 HARNESS_MAX_REVIEW_ROUNDS(기본 3) 라운드. --no-fix를 주면 원본처럼 리뷰까지만 한다.
#
#   종료 코드: execute.py의 코드(0~5)를 그대로 낸다. 6은 이 스크립트가 더한 것이다 —
#   리뷰와 처분이 닫히지 않아 사람이 봐야 한다(.claude/commands/harness.md의 종료 코드표).
#
#   --review-base — 리뷰 세션의 diff 기준점. 생략하면 스킬 기본값(main...HEAD)이다.
#   직전 phase가 아직 main에 들어가지 않았을 때 필요하다 — 그 상태에서 main...HEAD는
#   이미 리뷰가 끝난 변경분을 통째로 떠안아 판정 대상이 실제 변경과 어긋난다.
#   테스트: bash scripts/harness-run.test.sh
#
# 리뷰는 `claude -p`로 뜨는 별도 세션이다. 구현 세션의 컨텍스트를 물려받지 않는 것이
# 요점이므로 같은 세션에서 이어 부르면 안 된다. 처분 세션도 같은 이유로 리뷰 세션과 따로 뜬다 —
# 판정한 세션이 고치면 "고쳤으니 없는 문제"가 된다.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# phase의 모든 step이 completed인지 판정한다.
#
# 상위 phases/index.json은 보지 않는다. MANUAL.md에 확인 안 된 항목이 남으면
# execute.py의 _finalize()가 exit 5로 끝나면서 상위 인덱스도, task 인덱스의
# completed_at도 쓰지 않는다. 그래도 코드는 전부 커밋된 뒤다 — 리뷰 대상이 맞다.
# 상위를 조건에 넣으면 사람이 MANUAL을 체크할 때까지 리뷰가 뜨지 않는다.
phase_complete() {
  local root="$1" task="$2"
  python3 - "$root" "$task" <<'PY'
import json, sys
from pathlib import Path

root, task = Path(sys.argv[1]), sys.argv[2]
try:
    index = json.loads((root / "phases" / task / "index.json").read_text(encoding="utf-8"))
    steps = index["steps"]
except (OSError, ValueError, KeyError, TypeError):
    sys.exit(1)

if not isinstance(steps, list) or not steps:
    sys.exit(1)
if any(not isinstance(s, dict) or s.get("status") != "completed" for s in steps):
    sys.exit(1)
PY
}

# phase의 리뷰 리포트 가운데 가장 큰 라운드 번호를 찍는다. 없으면 0.
latest_round() {
  local root="$1" task="$2" f n max=0
  for f in "$root/phases/$task/review"/review-*.md; do
    [ -e "$f" ] || continue
    n="${f##*/review-}"
    n="${n%.md}"
    case "$n" in
      '' | *[!0-9]*) continue ;;
    esac
    [ "$n" -gt "$max" ] && max="$n"
  done
  echo "$max"
}

# 리포트 끝의 기계 판독용 줄에서 값 하나를 읽는다.
#   <!-- verdict: critical=0 major=2 minor=5 -->            (review-N.md, phase-review 스킬이 쓴다)
#   <!-- disposition: fixed=6 rejected=1 needs-human=0 -->  (fix-N.md, review-fix 스킬이 쓴다)
# 줄이나 키가 없으면 아무것도 찍지 않고 1로 끝난다. 표를 세어 추정하지 않는다 —
# 본문 형식이 조금만 달라져도 조용히 0건으로 읽혀 처분이 건너뛰어진다.
read_marker() { # read_marker <파일> <verdict|disposition> <키>
  local file="$1" kind="$2" key="$3" line value
  [ -f "$file" ] || return 1
  line="$(grep -E "^<!-- ${kind}: .*-->[[:space:]]*$" "$file" | tail -n 1)"
  [ -n "$line" ] || return 1
  value="$(printf '%s\n' "$line" | grep -oE "(^|[[:space:]])${key}=[0-9]+" | tail -n 1)"
  [ -n "$value" ] || return 1
  echo "${value##*=}"
}

# 이 체크아웃이 메인 체크아웃이 아니라 따로 만든 worktree인지 본다.
# 작업은 scripts/harness-worktree.sh가 만든 worktree에서만 돌린다(docs/HARNESS.md).
in_linked_worktree() {
  local root="$1" git_dir common_dir
  git_dir="$(cd "$root" && cd "$(git rev-parse --git-dir 2>/dev/null)" 2>/dev/null && pwd -P)" || return 1
  common_dir="$(cd "$root" && cd "$(git rev-parse --git-common-dir 2>/dev/null)" 2>/dev/null && pwd -P)" || return 1
  [ -n "$git_dir" ] && [ "$git_dir" != "$common_dir" ]
}

# 테스트가 함수만 가져갈 때는 여기서 멈춘다.
[ -n "${HARNESS_RUN_LIB:-}" ] && return 0

task="${1:-}"
if [ -z "$task" ]; then
  echo "usage: scripts/harness-run.sh {task} [--push] [--review-base <ref>] [--no-fix]" >&2
  exit 64
fi
shift

# --review-base는 리뷰 세션만 쓴다 — execute.py에 넘기면 모르는 인자로 죽는다.
review_base=""
no_fix=""
exec_args=()
while [ $# -gt 0 ]; do
  case "$1" in
    --review-base)
      review_base="${2:-}"
      if [ -z "$review_base" ]; then
        echo "harness-run: --review-base 뒤에 ref가 없다" >&2
        exit 64
      fi
      shift 2
      ;;
    --review-base=*)
      review_base="${1#*=}"
      shift
      ;;
    --no-fix)
      no_fix=1
      shift
      ;;
    *)
      exec_args+=("$1")
      shift
      ;;
  esac
done

# 오타를 리뷰 세션까지 끌고 가지 않는다 — 없는 ref로 범위를 적으면 sub-agent가
# 빈 diff를 보고 "변경 없음"으로 판정한다.
if [ -n "$review_base" ] && ! git -C "$ROOT" rev-parse --verify --quiet "$review_base" >/dev/null; then
  echo "harness-run: --review-base '$review_base'를 이 저장소에서 찾을 수 없다" >&2
  exit 64
fi

if ! in_linked_worktree "$ROOT"; then
  echo "harness-run: 여기($ROOT)는 메인 체크아웃이다. 작업은 따로 만든 worktree에서만 돌린다." >&2
  echo "harness-run: scripts/harness-worktree.sh ${task} 로 worktree를 만들고 그 안에서 다시 실행해라." >&2
  exit 64
fi

max_rounds="${HARNESS_MAX_REVIEW_ROUNDS:-3}"
case "$max_rounds" in
  '' | *[!0-9]* | 0)
    echo "harness-run: HARNESS_MAX_REVIEW_ROUNDS는 1 이상의 정수여야 한다 (받은 값: '$max_rounds')" >&2
    exit 64
    ;;
esac

# bash 3.2에서 빈 배열을 ${arr[@]}로 펴면 set -u가 죽는다 — +"..." 형태가 필수다.
python3 "$ROOT/scripts/execute.py" "$task" ${exec_args[@]+"${exec_args[@]}"}
code=$?

# 종료 코드는 게이트에 넣지 않는다. 실패 코드 1·2·3·4는 반드시 어떤 step을
# completed가 아닌 상태로 남기므로 phase_complete가 알아서 막고, 5(MANUAL 미확인)는
# 막으면 안 되는 정상 리뷰 대상이다.
if ! phase_complete "$ROOT" "$task"; then
  # ${task}의 중괄호는 장식이 아니다 — bash가 한글을 식별자에 붙여 읽어 $task의가
  # unbound variable로 죽는다(set -u). 변수 뒤에 한글이 바로 오면 중괄호가 필수다.
  echo "harness-run: ${task}의 step이 전부 completed가 아니다 (execute.py 종료 코드 $code) — 리뷰를 띄우지 않는다." >&2
  exit "$code"
fi

review_dir="$ROOT/phases/$task/review"
mkdir -p "$review_dir"
log="$review_dir/session.log"
model="${HARNESS_MODEL:-claude-opus-5-5}"
echo "harness-run: $task step 전원 completed (execute.py 종료 코드 $code) — 리뷰 세션을 띄운다"
echo "harness-run: 세션 로그 → $log"

# 슬래시 커맨드 대신 스킬 호출 문장을 직접 넘긴다. 헤드리스 모드의 커스텀 커맨드
# 확장에 기대지 않기 위해서다. 내용은 .claude/commands/review.md, review-fix.md와 같다.
headless_note="**되묻지 말고 그대로 진행하라** — 이 세션은 헤드리스라 질문에 답이 오지 않는다."
review_prompt="phase-review 스킬을 Skill 도구로 호출해 리뷰를 진행하라. 인자: $task"
if [ -n "$review_base" ]; then
  # 헤드리스라 되물으면 답이 오지 않는다 — 앞선 실행이 범위를 묻다가 리포트 없이 끝났다.
  review_prompt="$review_prompt

**diff 범위를 갈아라.** 스킬 본문은 \`main...HEAD\`라고 적지만 이 리뷰의 범위는 \`${review_base}...HEAD\`다 — main이 아직 직전 phase의 브랜치를 흡수하지 않아 \`main...HEAD\`에는 이미 리뷰·수정이 끝난 변경분이 섞인다. 스킬에 적힌 모든 \`main...HEAD\`를 \`${review_base}...HEAD\`로 읽고, sub-agent 브리프의 범위에도 그것을 적어라."
fi
review_prompt="$review_prompt

$headless_note"
fix_prompt="review-fix 스킬을 Skill 도구로 호출해 마지막 리뷰 리포트의 처분을 진행하라. 인자: $task

$headless_note"

# 사람이 봐야 하는 채로 끝낸다. 코드와 리포트는 커밋된 뒤다.
needs_human() {
  echo "harness-run: ⏸ $1" >&2
  echo "harness-run: 리뷰와 처분이 닫히지 않았다 — $review_dir 의 리포트를 보고 사람이 정해라 (종료 코드 6)." >&2
  exit 6
}

# 리포트 한 장만 커밋한다. `git add -A`를 쓰지 않는 것은 세션이 남긴 다른 변경을
# 리포트 커밋에 휩쓸지 않기 위해서다. 이미 커밋돼 있으면 아무 일도 하지 않는다.
commit_report() { # commit_report <파일> <메시지>
  local rel="${1#"$ROOT"/}"
  git -C "$ROOT" add -- "$rel" || return 1
  git -C "$ROOT" diff --cached --quiet -- "$rel" && return 0
  git -C "$ROOT" commit --quiet -m "$2" -- "$rel" && echo "harness-run: Commit: $2"
}

# 처분 세션이 커밋하지 않고 남긴 변경이 있는지 본다. session.log는 gitignore라 잡히지 않는다.
tree_dirty() {
  [ -n "$(git -C "$ROOT" status --porcelain)" ]
}

round=0
needs_human_total=0
while :; do
  round=$((round + 1))
  before="$(latest_round "$ROOT" "$task")"

  # HARNESS_REVIEW는 훅에게 "이 세션은 리뷰다"를 알린다 — 코드를 고치지 않는 세션에서
  # Stop 훅의 검사가 매 턴 도는 것을 막는다. execute.py가 HARNESS_RUN으로
  # tdd-guard에 무인 실행을 알리는 것과 같은 방식이다.
  # --model을 명시하지 않으면 대화 세션의 기본 모델이 상속된다. execute.py의 HEADLESS_MODEL과 짝.
  echo "harness-run: 리뷰 세션 ($round/$max_rounds)"
  HARNESS_REVIEW=1 claude -p --model "$model" --dangerously-skip-permissions "$review_prompt" 2>&1 | tee -a "$log"
  review_code="${PIPESTATUS[0]}"

  n="$(latest_round "$ROOT" "$task")"
  if [ "$n" -le "$before" ]; then
    needs_human "리뷰 세션이 새 리포트를 남기지 않았다 (claude 종료 코드 $review_code). 로그: $log"
  fi
  report="$review_dir/review-$n.md"

  critical="$(read_marker "$report" verdict critical)" &&
    major="$(read_marker "$report" verdict major)" &&
    minor="$(read_marker "$report" verdict minor)" || {
    commit_report "$report" "docs($task): ${n}차 리뷰 리포트"
    needs_human "review-$n.md 끝에 verdict 줄이 없어 결함 수를 읽을 수 없다."
  }
  commit_report "$report" "docs($task): ${n}차 리뷰 리포트 — critical $critical · major $major · minor $minor" ||
    needs_human "review-$n.md를 커밋하지 못했다."
  echo "harness-run: ${n}차 리뷰 — critical $critical · major $major · minor $minor"

  if [ $((critical + major + minor)) -eq 0 ]; then
    echo "harness-run: 결함이 없다 — 처분할 것이 없다."
    break
  fi

  if [ -n "$no_fix" ]; then
    echo "harness-run: --no-fix — 처분하지 않고 끝낸다. 처분은 /review-fix 로 한다."
    exit "$code"
  fi

  # 처분 세션은 코드를 고치므로 HARNESS_REVIEW를 주지 않는다 — Stop 훅의 검사가 돈다.
  # HARNESS_RUN은 무인 실행의 제약(가드 자기 수정 금지, 백그라운드 금지, push 금지)을 건다.
  echo "harness-run: 처분 세션 (${n}차 리뷰)"
  HARNESS_RUN=1 HARNESS_FIX=1 claude -p --model "$model" --dangerously-skip-permissions "$fix_prompt" 2>&1 | tee -a "$log"
  fix_code="${PIPESTATUS[0]}"

  fix_file="$review_dir/fix-$n.md"
  if [ ! -f "$fix_file" ]; then
    needs_human "처분 세션이 fix-$n.md를 남기지 않았다 (claude 종료 코드 $fix_code). 로그: $log"
  fi
  commit_report "$fix_file" "docs($task): ${n}차 리뷰 처분 기록" ||
    needs_human "fix-$n.md를 커밋하지 못했다."
  if tree_dirty; then
    needs_human "처분 세션이 커밋하지 않은 변경을 남겼다 — \`git status\`로 보고 정리해라."
  fi

  unresolved="$(read_marker "$fix_file" disposition needs-human)" ||
    needs_human "fix-$n.md 끝에 disposition 줄이 없어 처분 결과를 읽을 수 없다."
  needs_human_total=$((needs_human_total + unresolved))

  # minor만 있던 라운드는 처분으로 닫는다. 다시 리뷰하지 않는다.
  if [ $((critical + major)) -eq 0 ]; then
    break
  fi

  if [ "$round" -ge "$max_rounds" ]; then
    needs_human "${max_rounds}라운드를 돌았지만 ${n}차 리뷰의 critical $critical · major $major 를 고친 결과가 재리뷰로 확인되지 않았다."
  fi
  echo "harness-run: critical·major를 처분했다 — 다시 리뷰한다."
done

if [ "$needs_human_total" -gt 0 ]; then
  needs_human "처분이 사람의 판단으로 넘긴 항목이 ${needs_human_total}건 있다."
fi

echo "harness-run: 리뷰와 처분이 닫혔다 (execute.py 종료 코드 $code)."
exit "$code"
