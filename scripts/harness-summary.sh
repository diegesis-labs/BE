#!/usr/bin/env bash
# harness-summary.sh — 리뷰와 처분까지 끝난 phase의 최종 요약을 쓴다.
#
#   사용법: scripts/harness-summary.sh {task} [--base <ref>] [--force]
#
#   phases/{task}/summary.md에 이 phase가 만든 것을 지금의 코드 기준으로 요약하고 커밋한다.
#   harness-pr.sh는 PR 본문의 "만든 것"에 이 파일을 그대로 싣는다.
#
#   step의 summary(phases/{task}/index.json)는 각 step이 끝날 때 쓴 것이다. 그 뒤의 리뷰 처분과
#   사람의 수정이 빠져 있어서, PR 본문에 그대로 실으면 최종 코드와 어긋난다. 그래서 처분까지
#   끝난 코드를 별도 세션이 다시 읽고 요약을 쓴다.
#
#   요약이 다룬 커밋(파일 끝의 판독용 줄) 뒤로 phases/ 밖이 바뀌지 않았으면 세션을 띄우지 않는다. --force를 주면
#   그래도 다시 쓴다. harness-run.sh가 리뷰와 처분이 닫힌 뒤에 이 스크립트를 부르고, 사람이
#   그 뒤에 코드를 고쳤으면 PR 전에 사람이 직접 다시 부른다.
#
#   --base — 요약할 변경의 기준점. 생략하면 main이다(main...HEAD).
#   종료 코드: 0 요약이 최신이다 · 1 쓰지 못했다 · 64 사용법 오류
#   테스트: bash scripts/harness-summary.test.sh
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# summary.md 끝의 판독용 줄에서 요약이 다룬 커밋을 읽는다. 이 줄은 세션이 아니라 이 스크립트가 단다.
#   <!-- summary-of: <40자 커밋> -->
# summary.md를 마지막으로 바꾼 커밋으로 대신하지 않는다. 코드가 바뀌어도 다시 쓴 요약의 내용이
# 그대로면 커밋이 생기지 않아, 그 요약은 영원히 낡은 것으로 판정된다.
summary_of() { # summary_of <파일>
  local line
  [ -f "$1" ] || return 1
  line="$(grep -E '^<!-- summary-of: [0-9a-f]{40} -->[[:space:]]*$' "$1" | tail -n 1)"
  [ -n "$line" ] || return 1
  printf '%s\n' "$line" | sed -E 's/^<!-- summary-of: ([0-9a-f]{40}) -->.*$/\1/'
}

# 요약이 지금의 코드를 다루는지 본다. 요약이 커밋돼 있고, 판독용 줄의 커밋과 HEAD 사이에서
# phases/ 밖이 바뀌지 않았어야 한다. 커밋하지 않은 변경도 바뀐 것으로 친다. phases/ 아래(MANUAL
# 체크, 처분 기록)는 코드가 아니므로 세지 않는다. harness-pr.sh의 관문도 같은 규칙으로 본다.
summary_is_current() { # summary_is_current <레포 루트> <task>
  local root="$1" rel="phases/$2/summary.md" of
  grep -vE '^<!-- summary-of:' "$root/$rel" 2>/dev/null | grep -q '[^[:space:]]' || return 1
  git -C "$root" ls-files --error-unmatch -- "$rel" >/dev/null 2>&1 || return 1
  [ -z "$(git -C "$root" status --porcelain -- "$rel")" ] || return 1
  of="$(summary_of "$root/$rel")" || return 1
  git -C "$root" rev-parse --verify --quiet "$of^{commit}" >/dev/null || return 1
  [ -z "$(git -C "$root" status --porcelain -- . ':(exclude)phases')" ] || return 1
  git -C "$root" diff --quiet "$of" HEAD -- . ':(exclude)phases'
}

# 테스트가 함수만 가져갈 때는 여기서 멈춘다.
[ -n "${HARNESS_SUMMARY_LIB:-}" ] && return 0

fail() {
  echo "harness-summary: ⏸ $1" >&2
  exit 1
}

usage() {
  echo "usage: scripts/harness-summary.sh {task} [--base <ref>] [--force]" >&2
  exit 64
}

task="${1:-}"
if [ -z "$task" ] || [ "${task#-}" != "$task" ]; then
  usage
fi
shift

base="main"
force=""
while [ $# -gt 0 ]; do
  case "$1" in
    --base)
      base="${2:-}"
      [ -n "$base" ] || usage
      shift 2
      ;;
    --base=*)
      base="${1#*=}"
      shift
      ;;
    --force)
      force=1
      shift
      ;;
    *)
      echo "harness-summary: 모르는 인자: $1" >&2
      usage
      ;;
  esac
done

if [ ! -d "$ROOT/phases/$task" ]; then
  echo "harness-summary: phases/$task 가 없다" >&2
  exit 64
fi
# 없는 ref로 범위를 적으면 세션이 빈 diff를 보고 "만든 것이 없다"고 쓴다.
if ! git -C "$ROOT" rev-parse --verify --quiet "$base" >/dev/null; then
  echo "harness-summary: --base '$base'를 이 저장소에서 찾을 수 없다" >&2
  exit 64
fi

rel="phases/$task/summary.md"
summary="$ROOT/$rel"

if [ -z "$force" ] && summary_is_current "$ROOT" "$task"; then
  echo "harness-summary: $rel 이 최신이다 — 쓴 뒤로 코드가 바뀌지 않았다."
  exit 0
fi

if ! python3 - "$ROOT/phases/$task/index.json" <<'PY'; then
import json, sys
try:
    steps = json.load(open(sys.argv[1], encoding="utf-8"))["steps"]
except (OSError, ValueError, KeyError, TypeError):
    sys.exit(1)
ok = isinstance(steps, list) and steps and all(isinstance(s, dict) and s.get("status") == "completed" for s in steps)
sys.exit(0 if ok else 1)
PY
  fail "phases/$task 의 step이 전부 completed가 아니다 — 끝나지 않은 phase는 요약하지 않는다."
fi

# 세션이 남긴 것만 커밋하려면 시작할 때 작업 트리가 깨끗해야 한다.
if [ -n "$(git -C "$ROOT" status --porcelain)" ]; then
  fail "커밋되지 않은 변경이 있다 — 커밋하거나 치운 뒤 다시 실행해라. 요약은 커밋된 코드를 기준으로 쓴다."
fi

prompt="phase \`$task\`의 PR 본문에 실을 최종 요약을 \`$rel\`에 써라.

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

- \`$rel\` 밖의 파일을 만들거나 고치지 마라. 이유: 스크립트가 그 파일 하나만 커밋하며, 다른 변경이 남으면 요약을 커밋하지 않고 멈춘다.
- 커밋하지 마라. 이유: 스크립트가 커밋한다.
- 비밀값, 토큰, Docker Hub의 사용자 이름이나 이미지의 전체 이름을 적지 마라. 이유: 레포와 PR이 공개다(docs/DECISIONS.md의 D-37).

**되묻지 말고 그대로 진행하라** — 이 세션은 헤드리스라 질문에 답이 오지 않는다."

model="${HARNESS_MODEL:-claude-opus-5-5}"
log="$ROOT/phases/$task/review/session.log"
mkdir -p "$(dirname "$log")"
echo "harness-summary: 최종 요약 세션 ($task, $base...HEAD) — 로그 → $log"
# HARNESS_REVIEW는 리뷰 세션과 같은 제약을 건다: 종료 검사를 건너뛰고, 백그라운드 실행과 push를 막는다.
# 이 세션은 코드를 고치지 않는다. HARNESS_SUMMARY는 이 세션이 요약 세션임을 알린다.
head_before="$(git -C "$ROOT" rev-parse HEAD)"
# 판독용 줄에는 HEAD가 아니라 phases/ 밖을 마지막으로 바꾼 커밋을 적는다. HEAD를 적으면 요약
# 커밋이나 MANUAL 체크처럼 코드가 아닌 커밋 뒤에 다시 쓸 때마다 줄이 바뀌어 빈 커밋이 쌓인다.
code_commit="$(git -C "$ROOT" log -1 --format=%H -- . ':(exclude)phases')"
[ -n "$code_commit" ] || code_commit="$head_before"
(cd "$ROOT" && HARNESS_REVIEW=1 HARNESS_SUMMARY=1 claude -p --model "$model" --dangerously-skip-permissions "$prompt") 2>&1 | tee -a "$log"
session_code="${PIPESTATUS[0]}"

if [ "$(git -C "$ROOT" rev-parse HEAD)" != "$head_before" ]; then
  fail "세션이 커밋했다 — 요약은 세션이 시작할 때의 코드를 다뤄야 한다. \`git log\`로 보고 정리해라."
fi
if ! grep -vE '^<!-- summary-of:' "$summary" 2>/dev/null | grep -q '[^[:space:]]'; then
  fail "세션이 $rel 을 남기지 않았다 (claude 종료 코드 $session_code). 로그: $log"
fi
others="$(git -C "$ROOT" status --porcelain -- . ":(exclude)$rel")"
if [ -n "$others" ]; then
  fail "세션이 $rel 밖을 바꿨다 — 요약을 커밋하지 않았다. \`git status\`로 보고 정리해라."
fi

# 판독용 줄을 단다. 세션이 비슷한 줄을 남겼으면 지우고 새로 단다.
python3 - "$summary" "$code_commit" <<'PY' || fail "$rel 에 판독용 줄을 달지 못했다."
import re
import sys
from pathlib import Path

path, head = Path(sys.argv[1]), sys.argv[2]
lines = [line for line in path.read_text(encoding="utf-8").splitlines() if not re.match(r"\s*<!-- summary-of:", line)]
path.write_text("\n".join(lines).strip() + f"\n\n<!-- summary-of: {head} -->\n", encoding="utf-8")
PY

git -C "$ROOT" add -- "$rel" || fail "$rel 을 스테이징하지 못했다."
if git -C "$ROOT" diff --cached --quiet -- "$rel"; then
  echo "harness-summary: 요약이 그대로다 — 커밋할 것이 없다."
else
  git -C "$ROOT" commit --quiet -m "docs($task): 최종 요약" -- "$rel" || fail "$rel 을 커밋하지 못했다."
  echo "harness-summary: Commit: docs($task): 최종 요약"
fi

summary_is_current "$ROOT" "$task" || fail "$rel 을 썼지만 최신으로 판정되지 않는다 — \`git status\`를 봐라."
exit 0
