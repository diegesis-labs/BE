#!/usr/bin/env bash
# harness-worktree.sh 검증. 통과/실패 수를 찍고 하나라도 실패하면 1로 끝난다.
#   실행: bash scripts/harness-worktree.test.sh
#
# 여기서 보는 것은 --handoff, 곧 설계하던 대화를 worktree의 새 Orca 탭으로 옮기는 부분이다.
# 이것이 틀리면 두 가지로 샌다. 따옴표가 깨지면 새 탭의 claude가 엉뚱한 인자를 받아 대화를
# 이어받지 못한다. 세션 ID 없이 탭을 열면 빈 세션이 떠서, 사람은 대화가 옮겨진 줄 안다.
set -u

# 이 테스트는 Claude 세션과 Orca 터미널 안에서 돈다. 그 세션의 변수를 물려받으면 스크립트가
# 진짜 세션 ID와 진짜 claude 프로세스를 읽는다. 필요한 변수는 경우마다 직접 넣는다.
unset HARNESS_RUN HARNESS_REVIEW HARNESS_FIX HARNESS_MODEL HARNESS_MAX_REVIEW_ROUNDS HARNESS_CHECK_CMD
unset CLAUDE_CODE_SESSION_ID CLAUDE_PID
for v in $(env | sed -n 's/^\(ORCA_[A-Za-z0-9_]*\)=.*/\1/p'); do unset "$v"; done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PASS=0
FAIL=0

# git은 worktree 경로를 실제 경로로 적는다. macOS의 /var는 /private/var의 링크라서,
# 링크를 풀어 두지 않으면 같은 경로를 다르다고 판정한다.
TMP="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "$TMP"' EXIT

check() { # check <설명> <기대> <실제>
  if [ "$2" = "$3" ]; then
    PASS=$((PASS + 1))
    printf '  ok    %s\n' "$1"
  else
    FAIL=$((FAIL + 1))
    printf '  FAIL  %s — want=[%s] got=[%s]\n' "$1" "$2" "$3"
  fi
}

contains() { # contains <설명> <찾을 문구> <본문>
  case "$3" in
    *"$2"*) PASS=$((PASS + 1)); printf '  ok    %s\n' "$1" ;;
    *) FAIL=$((FAIL + 1)); printf '  FAIL  %s — [%s]가 없다\n' "$1" "$2" ;;
  esac
}

lacks() { # lacks <설명> <없어야 할 문구> <본문>
  case "$3" in
    *"$2"*) FAIL=$((FAIL + 1)); printf '  FAIL  %s — [%s]가 있다\n' "$1" "$2" ;;
    *) PASS=$((PASS + 1)); printf '  ok    %s\n' "$1" ;;
  esac
}

STUB_BIN="$TMP/bin"
mkdir -p "$STUB_BIN"

# 가짜 claude. 받은 인자를 한 줄에 하나씩 [ ]로 감싸 찍는다. 인자가 어떻게 갈렸는지 보려는 것이다.
cat >"$STUB_BIN/claude" <<'STUB'
#!/usr/bin/env bash
for a in "$@"; do printf '[%s]\n' "$a"; done
STUB

# 가짜 orca. 받은 명령을 한 줄로 기록하고, terminal create의 --command 값은 따로 남긴다.
# worktree current는 실패한다(Orca가 관리하지 않는 worktree). ORCA_TERMINAL_FAIL=1이면
# terminal create가 실패한다.
cat >"$STUB_BIN/orca" <<'STUB'
#!/usr/bin/env bash
echo "orca $*" >>"$ORCA_LOG"
case "$1 $2" in
  "worktree current") exit 1 ;;
  "terminal create")
    prev=""
    for a in "$@"; do
      [ "$prev" = "--command" ] && printf '%s' "$a" >"$ORCA_LOG.cmd"
      prev="$a"
    done
    if [ "${ORCA_TERMINAL_FAIL:-}" = "1" ]; then
      echo "runtime unreachable" >&2
      exit 1
    fi
    echo '{"ok":true}'
    exit 0
    ;;
esac
exit 0
STUB

# 가짜 ps. claude 프로세스의 인자를 흉내 낸다. ps는 따옴표를 잃으므로 공백 든 경로가 쪼개져 나온다.
cat >"$STUB_BIN/ps" <<'STUB'
#!/usr/bin/env bash
echo "claude --plugin-dir /Users/x/Library/Application Support/orca/agent-view --dangerously-skip-permissions --model claude-opus-5-5"
STUB
chmod +x "$STUB_BIN/claude" "$STUB_BIN/orca" "$STUB_BIN/ps"

# ---------------------------------------------------------------------------
echo "carry_flags"
# shellcheck source=harness-worktree.sh
HARNESS_WORKTREE_LIB=1 . "$SCRIPT_DIR/harness-worktree.sh"

check "허용한 플래그만 옮기고 쪼개진 --plugin-dir 값은 버린다" \
  "--dangerously-skip-permissions --model claude-opus-5-5" \
  "$(carry_flags "claude --plugin-dir /Users/x/Library/Application Support/orca --dangerously-skip-permissions --model claude-opus-5-5")"
check "--permission-mode, --x=v 형태, --effort를 옮긴다" \
  "--permission-mode plan --model=claude-sonnet-5-5 --effort high" \
  "$(carry_flags "claude --permission-mode plan --model=claude-sonnet-5-5 --effort high")"
check "--resume, -c, positional prompt는 버린다" \
  "--model m" \
  "$(carry_flags "claude --resume old-id -c --model m hello world")"
check "--allow-dangerously-skip-permissions를 옮긴다" \
  "--allow-dangerously-skip-permissions" \
  "$(carry_flags "claude --allow-dangerously-skip-permissions")"
check "옮길 것이 없으면 빈 줄" "" "$(carry_flags "claude")"

# ---------------------------------------------------------------------------
echo "sq"
check "작은따옴표로 감싼다" "'a b'" "$(sq "a b")"
# shellcheck disable=SC2016
check "작은따옴표가 들어 있어도 셸이 원래 문자열로 되돌린다" "it's \$HOME \`x\`" \
  "$(bash -c "printf '%s' $(sq "it's \$HOME \`x\`")")"

# ---------------------------------------------------------------------------
echo "handoff_command"
ODD_PATH="/tmp/it's a dir/wt"
CMD="$(handoff_command abc-123 "$ODD_PATH" feat-demo --dangerously-skip-permissions --model claude-opus-5-5)"
OUT="$(PATH="$STUB_BIN:$PATH" bash -c "$CMD")"
check "인자가 정확히 일곱 개로 갈린다" 7 "$(printf '%s\n' "$OUT" | wc -l | tr -d ' ')"
check "1: --resume" "[--resume]" "$(printf '%s\n' "$OUT" | sed -n 1p)"
check "2: 세션 ID" "[abc-123]" "$(printf '%s\n' "$OUT" | sed -n 2p)"
check "3: --fork-session" "[--fork-session]" "$(printf '%s\n' "$OUT" | sed -n 3p)"
check "4: 옮긴 플래그" "[--dangerously-skip-permissions]" "$(printf '%s\n' "$OUT" | sed -n 4p)"
check "5: 값을 받는 플래그" "[--model]" "$(printf '%s\n' "$OUT" | sed -n 5p)"
check "6: 그 값" "[claude-opus-5-5]" "$(printf '%s\n' "$OUT" | sed -n 6p)"
PROMPT_LINE="$(printf '%s\n' "$OUT" | sed -n 7p)"
contains "7: 프롬프트가 한 인자로 들어오고 공백·따옴표 든 경로를 그대로 담는다" "$ODD_PATH" "$PROMPT_LINE"
contains "7: 프롬프트가 브랜치를 알려 준다" "feat-demo" "$PROMPT_LINE"
case "$CMD" in
  claude\ *) PASS=$((PASS + 1)); printf '  ok    %s\n' "명령은 claude로 시작한다" ;;
  *) FAIL=$((FAIL + 1)); printf '  FAIL  %s — [%s]\n' "명령은 claude로 시작한다" "$CMD" ;;
esac
CMD2="$(handoff_command abc-123 /tmp/wt feat-demo)"
OUT2="$(PATH="$STUB_BIN:$PATH" bash -c "$CMD2")"
check "옮길 플래그가 없으면 인자는 넷" 4 "$(printf '%s\n' "$OUT2" | wc -l | tr -d ' ')"

# ---------------------------------------------------------------------------
# 메인 체크아웃 하나와 거기서 딴 feat-demo worktree 하나를 만든다. 이미 있는 worktree를 쓰는
# 경로로 가므로 orca worktree create를 부르지 않는다. pyproject.toml이 없어 uv sync도 건너뛴다.
make_repo() { # make_repo <이름> → worktree 경로를 찍는다
  local base="$TMP/$1" wt="$TMP/$1-wt"
  mkdir -p "$base/scripts"
  cp "$SCRIPT_DIR/harness-worktree.sh" "$base/scripts/"
  (
    cd "$base" && git init --quiet -b main &&
      git -c user.name=t -c user.email=t@t add -A &&
      git -c user.name=t -c user.email=t@t commit --quiet -m init &&
      git worktree add --quiet -b feat-demo "$wt"
  ) >/dev/null 2>&1
  echo "$wt"
}

run() { # run <이름> <인자...> → 종료 코드는 RC, 표준 출력은 OUT, 표준 오류는 ERR
  local name="$1"
  shift
  : >"$ORCA_LOG"
  rm -f "$ORCA_LOG.cmd"
  PATH="$STUB_BIN:$PATH" bash "$TMP/$name/scripts/harness-worktree.sh" "$@" \
    >"$TMP/out.log" 2>"$TMP/err.log"
  RC=$?
  OUT="$(cat "$TMP/out.log")"
  ERR="$(cat "$TMP/err.log")"
}

export ORCA_LOG="$TMP/orca.log"

echo "--handoff: 세션 안에서"
WT="$(make_repo ok)"
CLAUDE_CODE_SESSION_ID=abc CLAUDE_PID=4242 run ok demo --handoff
check "종료 코드 0" 0 "$RC"
check "표준 출력의 마지막 줄은 worktree 경로" "$WT" "$(printf '%s\n' "$OUT" | tail -1)"
LOG="$(cat "$ORCA_LOG")"
contains "그 worktree에 터미널을 연다" "terminal create --worktree path:$WT" "$LOG"
contains "새 탭으로 포커스를 옮긴다" "--focus" "$LOG"
contains "탭 이름은 task" "--title demo" "$LOG"
SENT="$(cat "$ORCA_LOG.cmd" 2>/dev/null)"
contains "지금 대화를 fork해서 이어받는다" "claude --resume 'abc' --fork-session" "$SENT"
contains "원래 세션의 권한 모드를 옮긴다" "'--dangerously-skip-permissions'" "$SENT"
contains "원래 세션의 모델을 옮긴다" "'--model' 'claude-opus-5-5'" "$SENT"
lacks "쪼개진 --plugin-dir는 옮기지 않는다" "plugin-dir" "$SENT"
contains "원래 탭을 닫으라고 알린다" "닫아라" "$ERR"

echo "--handoff: CLAUDE_PID가 없을 때"
CLAUDE_CODE_SESSION_ID=abc run ok demo --handoff
check "그래도 옮긴다" 0 "$RC"
SENT="$(cat "$ORCA_LOG.cmd" 2>/dev/null)"
contains "fork해서 이어받는다" "claude --resume 'abc' --fork-session" "$SENT"
lacks "플래그는 옮기지 않는다" "--model" "$SENT"

echo "--handoff: 세션 밖에서"
run ok demo --handoff
check "0이 아닌 코드로 끝난다" 1 "$RC"
contains "준비된 worktree 경로를 알려 준다" "$WT" "$ERR"
lacks "터미널을 열지 않는다" "terminal create" "$(cat "$ORCA_LOG")"
check "표준 출력에 경로를 찍지 않는다" "" "$OUT"

echo "--handoff: 탭을 열지 못했을 때"
CLAUDE_CODE_SESSION_ID=abc ORCA_TERMINAL_FAIL=1 run ok demo --handoff
check "0이 아닌 코드로 끝난다" 1 "$RC"
contains "사람이 직접 칠 명령을 알려 준다" "claude --resume 'abc' --fork-session" "$ERR"
contains "그 명령은 worktree로 들어가서 친다" "cd '$WT' &&" "$ERR"
contains "Orca의 오류를 보여 준다" "runtime unreachable" "$ERR"

echo "--handoff 없이"
CLAUDE_CODE_SESSION_ID=abc run ok demo
check "종료 코드 0" 0 "$RC"
check "표준 출력의 마지막 줄은 worktree 경로" "$WT" "$(printf '%s\n' "$OUT" | tail -1)"
lacks "터미널을 열지 않는다" "terminal create" "$(cat "$ORCA_LOG")"

echo "입력"
run ok
check "task가 없으면 64" 64 "$RC"
run ok demo --bogus
check "모르는 인자면 64" 64 "$RC"

printf '\n통과 %d · 실패 %d\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
