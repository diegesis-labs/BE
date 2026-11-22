#!/usr/bin/env bash
# Stop Check — Stop 훅
# 세션이 턴을 끝내려 할 때 scripts/check.sh를 돌린다. 실패하면 세션을 되돌려 고치게 한다.
#
# OnlineFourCut은 이 자리에 `npm run lint && npm run build && npm run test`를 settings.json에
# 직접 적었다. 그 명령은 실패하면 1로 끝나는데, Stop 훅에서 1은 차단이 아니라 '비차단 오류'라
# 세션이 그대로 끝났다. 세션을 되돌리는 것은 종료 코드 2다(표준 오류의 내용이 세션에 전달된다).
#
# 되돌리는 횟수에는 상한을 둔다. 훅이 되돌린 뒤 다시 끝내려는 턴에는 입력의 stop_hook_active가
# true로 온다. 그때마다 세션별 카운터를 올리고, MAX_BLOCKS번을 넘으면 경고만 남기고 놓아준다.
# 상한이 없으면 고칠 수 없는 실패(예: DB가 꺼져 있다)에서 세션이 영원히 돈다.
#
# 알려진 한계: 놓아준 뒤에는 검사가 빨간 채로 세션이 끝난다. 무인 step이라면 그 상태로
# completed가 커밋될 수 있다. 리뷰의 실측(scripts/check.sh --all)이 이것을 잡는다.

INPUT=$(cat)

MAX_BLOCKS=3

# 리뷰 세션은 코드를 고치지 않는다. 매 턴 검사를 돌리면 시간만 쓰고, 실패해도 고칠 수 없다.
[ -z "${HARNESS_REVIEW:-}" ] || exit 0

ROOT="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"

# 아직 스캐폴딩 전이면 검사할 것이 없다.
[ -f "$ROOT/pyproject.toml" ] || exit 0

# --- 입력 파싱. jq → python3 순으로 쓴다. 둘 다 없으면 첫 시도로 본다 ---
SESSION_ID=""
ACTIVE="false"
if command -v jq >/dev/null 2>&1; then
  SESSION_ID=$(printf '%s' "$INPUT" | jq -r '.session_id // empty' 2>/dev/null)
  ACTIVE=$(printf '%s' "$INPUT" | jq -r '.stop_hook_active // false' 2>/dev/null)
elif command -v python3 >/dev/null 2>&1; then
  SESSION_ID=$(printf '%s' "$INPUT" | python3 -c '
import json, sys
try:
    sys.stdout.write(str(json.load(sys.stdin).get("session_id") or ""))
except Exception:
    pass
')
  ACTIVE=$(printf '%s' "$INPUT" | python3 -c '
import json, sys
try:
    active = json.load(sys.stdin).get("stop_hook_active") is True
except Exception:
    active = False
sys.stdout.write("true" if active else "false")
')
fi

# 파일 이름으로 쓸 수 있는 글자만 남긴다.
SAFE_ID=$(printf '%s' "${SESSION_ID:-unknown}" | tr -c 'A-Za-z0-9_-' '_')
COUNTER="${TMPDIR:-/tmp}/diegesis-stop-check-${SAFE_ID}"

# 테스트가 검사 명령을 바꿀 수 있게 한다. 평소에는 scripts/check.sh다.
if [ -n "${HARNESS_CHECK_CMD:-}" ]; then
  OUTPUT=$(cd "$ROOT" && bash -c "$HARNESS_CHECK_CMD" 2>&1)
else
  OUTPUT=$(cd "$ROOT" && bash scripts/check.sh 2>&1)
fi
CODE=$?

if [ "$CODE" -eq 0 ]; then
  rm -f "$COUNTER"
  exit 0
fi

# 훅이 되돌려서 이어진 턴이 아니면 새로 센다.
COUNT=0
if [ "$ACTIVE" = "true" ] && [ -f "$COUNTER" ]; then
  COUNT=$(cat "$COUNTER" 2>/dev/null)
  case "$COUNT" in
    '' | *[!0-9]*) COUNT=0 ;;
  esac
fi
COUNT=$((COUNT + 1))

if [ "$COUNT" -gt "$MAX_BLOCKS" ]; then
  rm -f "$COUNTER"
  # 표준 출력의 JSON은 사용자에게 보이는 경고가 된다. 세션은 그대로 끝난다.
  cat <<EOF
{
  "systemMessage": "STOP CHECK: scripts/check.sh가 실패한 채로 세션을 끝낸다 (종료 코드 ${CODE}, ${MAX_BLOCKS}번 되돌렸지만 고쳐지지 않았다). 검사가 통과하지 않은 상태다 — scripts/check.sh --all 로 확인해라."
}
EOF
  exit 0
fi

echo "$COUNT" >"$COUNTER"

{
  echo "STOP CHECK: scripts/check.sh가 실패했다 (종료 코드 ${CODE}, ${COUNT}/${MAX_BLOCKS}번째 되돌림)."
  echo "턴을 끝내기 전에 고쳐라. 검사를 끄거나 느슨하게 만들어서 통과시키지 마라 — 테스트를 지우거나 건너뛰게 하는 것, ruff·pyright 설정을 완화하는 것, 무시 주석을 다는 것이 그것이다."
  echo "네가 고칠 수 없는 원인(DB가 꺼져 있다, 인증이 필요하다)이면 그 사실을 말하고 끝내라."
  echo
  echo "--- 출력의 끝 60줄 ---"
  printf '%s\n' "$OUTPUT" | tail -n 60
} >&2
exit 2
