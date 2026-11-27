#!/usr/bin/env bash
# harness-worktree.sh — phase 하나를 돌릴 worktree를 Orca로 만들고 그 경로를 찍는다.
#
#   사용법: scripts/harness-worktree.sh {task} [--base <ref>] [--handoff]
#
#   {task}는 phases/ 아래 폴더 이름이다 (예: 0-project-setup). 브랜치는 feat-{task}가 된다 —
#   execute.py가 기대하는 이름이라 바꾸면 execute.py가 다른 브랜치를 새로 딴다.
#   --base — worktree를 딸 기준점. 생략하면 main이다.
#   --handoff — worktree를 준비한 뒤 그 worktree에 새 Orca 탭을 열고, 이 명령을 부른 Claude
#     세션의 대화를 거기서 이어받게 한다(claude --resume <세션> --fork-session). Orca는 대화
#     탭을 그것을 처음 연 worktree에 묶어 둔다. 그래서 EnterWorktree로 cwd만 옮기면 탭은
#     원래 worktree에 남고, 대화와 변경사항을 한 화면에서 볼 수 없다. 원래 탭은 닫지 않는다 —
#     응답 중인 턴이 끊기고, 새 탭이 뜨지 않았을 때 돌아갈 곳이 없어지기 때문이다. 사람이 닫는다.
#
#   표준 출력의 마지막 줄은 worktree의 절대 경로 하나뿐이다. 안내는 전부 표준 오류로 나간다.
#   그래서 `cd "$(scripts/harness-worktree.sh 0-project-setup)"`처럼 쓸 수 있다.
#
#   테스트: bash scripts/harness-worktree.test.sh
#
# worktree를 `git worktree add`로 만들지 않는다. Orca 왼쪽 사이드패널에는 Orca가 만든
# worktree만 보인다. Orca에 닿지 않으면 대신 만들지 않고 실패로 끝낸다 — 보이지 않는
# 곳에서 무인 실행이 도는 것을 막기 위해서다.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

say() { echo "harness-worktree: $*" >&2; }
die() {
  say "$*"
  exit 1
}

# `git worktree list --porcelain`에서 주어진 브랜치를 체크아웃한 worktree의 경로를 찍는다.
worktree_for_branch() { # worktree_for_branch <레포> <브랜치>
  git -C "$1" worktree list --porcelain | awk -v want="branch refs/heads/$2" '
    /^worktree / { path = substr($0, 10) }
    $0 == want { print path; exit }
  '
}

# 메인 체크아웃의 경로. 목록의 첫 항목이 항상 메인이다.
main_checkout() {
  git -C "$1" worktree list --porcelain | awk '/^worktree / { print substr($0, 10); exit }'
}

# Orca가 돌려준 JSON에서 worktree 경로를 꺼낸다.
path_from_json() {
  python3 -c '
import json, sys
try:
    print(json.load(sys.stdin)["result"]["worktree"]["path"])
except (ValueError, KeyError, TypeError):
    sys.exit(1)
'
}

prepare_env() { # prepare_env <worktree 경로>
  [ -f "$1/pyproject.toml" ] || return 0
  command -v uv >/dev/null 2>&1 || die "uv가 없다 — worktree는 만들었지만 .venv를 준비하지 못했다: $1"
  say "의존성을 맞춘다 (uv sync --locked)"
  (cd "$1" && uv sync --locked >&2) || die "uv sync가 실패했다: $1"
}

# 작은따옴표로 감싸 찍는다. 터미널에 그대로 쳐 넣을 명령을 만들 때 쓴다. 사람의 로그인 셸은
# zsh이고 테스트는 bash로 돌리므로, 두 셸이 같게 읽는 POSIX 작은따옴표만 쓴다.
sq() { # sq <문자열>
  printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"
}

# claude 프로세스의 인자 가운데 새 탭에서도 같아야 하는 것만 골라 공백으로 이어 찍는다.
# ps는 따옴표를 잃어서 공백 든 값(--plugin-dir의 경로 같은 것)이 쪼개져 나온다. 그래서 값에
# 공백이 없는 플래그만 허용 목록으로 옮기고, 나머지 낱말은 모두 버린다.
carry_flags() { # carry_flags <claude 프로세스의 인자 문자열>
  local out="" pending="" word
  set -f
  for word in $1; do
    if [ -n "$pending" ]; then
      out="$out $pending $word"
      pending=""
      continue
    fi
    case "$word" in
      --dangerously-skip-permissions | --allow-dangerously-skip-permissions) out="$out $word" ;;
      --permission-mode=* | --model=* | --effort=*) out="$out $word" ;;
      --permission-mode | --model | --effort) pending="$word" ;;
    esac
  done
  set +f
  printf '%s\n' "${out# }"
}

# 새 탭에서 칠 명령을 한 줄로 만든다. 원래 세션은 이 스크립트를 부른 턴을 마칠 때까지 살아
# 있으므로, 두 프로세스가 한 트랜스크립트에 쓰지 않도록 --fork-session으로 갈라서 이어받는다.
handoff_command() { # handoff_command <세션 ID> <worktree 경로> <브랜치> [옮길 플래그...]
  local session="$1" wt="$2" branch="$3" cmd flag prompt
  shift 3
  prompt="이 대화를 worktree $wt (브랜치 $branch)의 새 Orca 탭으로 옮겨 왔다. 이제부터 파일은 모두 이 worktree 안에서 쓰고 커밋한다. pwd와 git branch --show-current로 위치를 확인해 한 줄로 보고하고, 사람의 다음 지시를 기다려라."
  cmd="claude --resume $(sq "$session") --fork-session"
  for flag in "$@"; do
    cmd="$cmd $(sq "$flag")"
  done
  printf '%s\n' "$cmd $(sq "$prompt")"
}

# 이 스크립트를 부른 Claude 세션의 대화를 worktree의 새 Orca 탭으로 옮긴다.
# CLAUDE_CODE_SESSION_ID와 CLAUDE_PID는 Claude Code가 Bash 도구에 넣는 값이다.
handoff() { # handoff <worktree 경로> <task> <브랜치>
  local wt="$1" task="$2" branch="$3" flags="" cmd out
  [ -n "${CLAUDE_CODE_SESSION_ID:-}" ] ||
    die "--handoff는 대화형 Claude 세션 안에서만 쓸 수 있다(CLAUDE_CODE_SESSION_ID가 없다). worktree는 준비됐다: $wt"
  if [ -n "${CLAUDE_PID:-}" ]; then
    flags="$(carry_flags "$(ps -o args= -p "$CLAUDE_PID" 2>/dev/null)")"
  else
    say "CLAUDE_PID가 없어 권한 모드와 모델을 옮기지 않는다. 새 탭은 기본 설정으로 뜬다."
  fi
  # $flags는 공백 없는 낱말들이라 일부러 쪼개서 넘긴다.
  # shellcheck disable=SC2086
  cmd="$(handoff_command "$CLAUDE_CODE_SESSION_ID" "$wt" "$branch" $flags)"
  out="$(orca terminal create --worktree "path:$wt" --title "$task" --command "$cmd" --focus --json 2>&1)" ||
    die "worktree는 준비됐지만 새 탭을 열지 못했다: $wt
$out
Orca에서 그 worktree를 열고 아래를 직접 실행해라.
  cd $(sq "$wt") && $cmd"
  say "대화를 '$task' worktree의 새 탭으로 옮겼다. 이 탭의 세션에서는 더 작업하지 말고 닫아라."
}

# 테스트가 함수만 가져갈 때는 여기서 멈춘다.
[ -n "${HARNESS_WORKTREE_LIB:-}" ] && return 0

task="${1:-}"
if [ -z "$task" ] || [ "${task#-}" != "$task" ]; then
  echo "usage: scripts/harness-worktree.sh {task} [--base <ref>] [--handoff]" >&2
  exit 64
fi
shift

base="main"
do_handoff=""
while [ $# -gt 0 ]; do
  case "$1" in
    --handoff)
      do_handoff=1
      shift
      ;;
    --base)
      base="${2:-}"
      [ -n "$base" ] || {
        say "--base 뒤에 ref가 없다"
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

branch="feat-$task"
main="$(main_checkout "$ROOT")"
[ -n "$main" ] || die "git 저장소를 찾을 수 없다: $ROOT"

# 이미 있으면 새로 만들지 않는다. 같은 명령을 다시 불러도 같은 경로가 나와야
# 설계 세션과 실행 세션이 서로 다른 worktree로 갈라지지 않는다.
existing="$(worktree_for_branch "$main" "$branch")"
if [ -n "$existing" ]; then
  if [ "$existing" = "$main" ]; then
    die "메인 체크아웃이 $branch 를 물고 있다. 메인을 main으로 되돌린 뒤 다시 실행해라."
  fi
  say "$branch 의 worktree가 이미 있다 — 그것을 쓴다"
  if command -v orca >/dev/null 2>&1 && ! (cd "$existing" && orca worktree current --json >/dev/null 2>&1); then
    say "주의: 이 worktree는 Orca가 관리하지 않아 사이드패널에 보이지 않을 수 있다."
  fi
  prepare_env "$existing"
  if [ -n "$do_handoff" ]; then handoff "$existing" "$task" "$branch"; fi
  echo "$existing"
  exit 0
fi

# 브랜치만 남아 있으면 Orca가 이름 끝에 숫자를 붙인 새 브랜치를 만든다.
# 그러면 execute.py가 기대하는 feat-{task}와 어긋나므로 여기서 멈춘다.
if git -C "$main" rev-parse --verify --quiet "refs/heads/$branch" >/dev/null; then
  die "브랜치 $branch 가 worktree 없이 남아 있다. 필요 없으면 지우고(git branch -d $branch), 이어서 쓸 것이면 사람이 Orca에서 그 브랜치로 worktree를 열어라."
fi

git -C "$main" rev-parse --verify --quiet "$base" >/dev/null || die "기준점 '$base'를 이 저장소에서 찾을 수 없다"

command -v orca >/dev/null 2>&1 || die "orca 명령이 없다. Orca를 설치하거나 PATH에 넣어라. git worktree add로 대신 만들지 않는다 — 사이드패널에 보이지 않는다."

say "Orca로 worktree를 만든다 (브랜치 $branch, 기준 $base)"
json="$(orca worktree create --repo "path:$main" --name "$task" --branch "$branch" \
  --base-branch "$base" --setup skip --json 2>&1)" ||
  die "orca worktree create가 실패했다. Orca가 켜져 있는지 \`orca status\`로 확인해라.
$json"

path="$(printf '%s' "$json" | path_from_json)" || die "Orca의 응답에서 경로를 읽지 못했다:
$json"

actual="$(git -C "$path" rev-parse --abbrev-ref HEAD 2>/dev/null)"
if [ "$actual" != "$branch" ]; then
  die "만들어진 worktree의 브랜치가 '$actual'이다 ($branch 를 기대했다). 경로: $path — 이대로 돌리지 말고 정리해라."
fi

prepare_env "$path"
say "준비됐다. Orca 사이드패널에서 '$task'로 보인다."
if [ -n "$do_handoff" ]; then handoff "$path" "$task" "$branch"; fi
echo "$path"
