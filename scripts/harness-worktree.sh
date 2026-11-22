#!/usr/bin/env bash
# harness-worktree.sh — phase 하나를 돌릴 worktree를 Orca로 만들고 그 경로를 찍는다.
#
#   사용법: scripts/harness-worktree.sh {task} [--base <ref>]
#
#   {task}는 phases/ 아래 폴더 이름이다 (예: 0-project-setup). 브랜치는 feat-{task}가 된다 —
#   execute.py가 기대하는 이름이라 바꾸면 execute.py가 다른 브랜치를 새로 딴다.
#   --base — worktree를 딸 기준점. 생략하면 main이다.
#
#   표준 출력의 마지막 줄은 worktree의 절대 경로 하나뿐이다. 안내는 전부 표준 오류로 나간다.
#   그래서 `cd "$(scripts/harness-worktree.sh 0-project-setup)"`처럼 쓸 수 있다.
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

# 테스트가 함수만 가져갈 때는 여기서 멈춘다.
[ -n "${HARNESS_WORKTREE_LIB:-}" ] && return 0

task="${1:-}"
if [ -z "$task" ] || [ "${task#-}" != "$task" ]; then
  echo "usage: scripts/harness-worktree.sh {task} [--base <ref>]" >&2
  exit 64
fi
shift

base="main"
while [ $# -gt 0 ]; do
  case "$1" in
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
echo "$path"
