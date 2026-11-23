#!/usr/bin/env bash
# harness-summary.sh 검증. 통과/실패 수를 찍고 하나라도 실패하면 1로 끝난다.
#   실행: bash scripts/harness-summary.test.sh
#
# 이 스크립트가 틀리면 PR 본문의 "만든 것"이 최종 코드와 어긋난다. 요약이 낡았는데 최신으로
# 판정하거나, 세션이 요약 밖의 파일을 고친 것을 함께 커밋하는 것이 그 길이다.
set -u

# 이 테스트가 무인 세션 안에서 돌면 그 세션의 HARNESS_* 변수를 물려받는다. 그러면 가짜
# claude의 판정이 기대와 어긋난다. 필요한 변수는 경우마다 직접 넣는다.
unset HARNESS_RUN HARNESS_REVIEW HARNESS_FIX HARNESS_SUMMARY HARNESS_MODEL HARNESS_MAX_REVIEW_ROUNDS HARNESS_CHECK_CMD

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PASS=0
FAIL=0

TMP=$(mktemp -d)
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

# 가짜 claude. 받은 환경과 프롬프트를 기록하고, $SCENARIO/mode에 따라 요약을 쓴다.
#   (없음)  — summary.md에 지금 HEAD를 담은 요약을 쓴다. 다시 쓰면 내용이 달라진다.
#   nofile  — 아무것도 쓰지 않는다.
#   other   — 요약을 쓰고 code.txt도 고친다.
#   same    — 언제나 같은 내용을 쓴다.
#   commit  — 요약을 쓰고 스스로 커밋한다.
STUB_BIN="$TMP/bin"
mkdir -p "$STUB_BIN"
cat >"$STUB_BIN/claude" <<'STUB'
#!/usr/bin/env bash
model=""
prev=""
for a in "$@"; do
  [ "$prev" = "--model" ] && model="$a"
  prev="$a"
done
echo "model=$model review=${HARNESS_REVIEW:-} summary=${HARNESS_SUMMARY:-} run=${HARNESS_RUN:-}" >>"$SCENARIO/calls"
printf '%s' "$prev" >"$SCENARIO/prompt"
mode="$(cat "$SCENARIO/mode" 2>/dev/null)"
[ "$mode" = "nofile" ] && exit 0
if [ "$mode" = "same" ]; then
  printf -- '- step 0 `demo`: 같은 요약\n' >phases/demo/summary.md
else
  printf -- '- step 0 `demo`: 요약 %s\n' "$(git rev-parse --short HEAD)" >phases/demo/summary.md
fi
[ "$mode" = "other" ] && echo "딴 변경" >>code.txt
[ "$mode" = "commit" ] && git add -A && git commit --quiet -m "세션이 커밋했다"
exit 0
STUB
chmod +x "$STUB_BIN/claude"

G() { git -c user.name=t -c user.email=t@t "$@"; }

make_repo() { # make_repo <이름> → 레포 경로를 찍는다. 모든 step이 completed인 phase를 가진다.
  local repo="$TMP/$1"
  mkdir -p "$repo/scripts" "$repo/phases/demo"
  cp "$SCRIPT_DIR/harness-summary.sh" "$repo/scripts/"
  printf '{"steps":[{"step":0,"name":"demo","status":"completed","summary":"step 때의 요약"}]}' \
    >"$repo/phases/demo/index.json"
  printf 'phases/**/review/session.log\n' >"$repo/.gitignore"
  echo "처음 코드" >"$repo/code.txt"
  (cd "$repo" && git init --quiet -b main && G add -A && G commit --quiet -m init &&
    git checkout --quiet -b feat-demo) >/dev/null 2>&1
  echo "$repo"
}

commit_all() { (cd "$1" && G add -A && G commit --quiet -m "$2") >/dev/null 2>&1; }

scenario() { # scenario <이름> [mode]
  SCENARIO="$TMP/scn-$1"
  mkdir -p "$SCENARIO"
  : >"$SCENARIO/calls"
  rm -f "$SCENARIO/prompt"
  if [ -n "${2:-}" ]; then echo "$2" >"$SCENARIO/mode"; else rm -f "$SCENARIO/mode"; fi
}

run() { # run <레포> <인자...> → RC, OUT
  local repo="$1"
  shift
  OUT=$(cd "$repo" && PATH="$STUB_BIN:$PATH" SCENARIO="$SCENARIO" \
    GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t \
    bash scripts/harness-summary.sh "$@" 2>&1)
  RC=$?
}

ncalls() { wc -l <"$SCENARIO/calls" | tr -d ' '; }
subjects() { git -C "$1" log --format=%s main..HEAD | tr '\n' '|'; }

echo "처음 쓸 때"
R="$(make_repo first)"
scenario first
run "$R" demo
check "0으로 끝난다" 0 "$RC"
check "세션을 한 번 띄운다" 1 "$(ncalls)"
check "요약 하나만 커밋한다" "docs(demo): 최종 요약|" "$(subjects "$R")"
check "작업 트리가 깨끗하다" "" "$(git -C "$R" status --porcelain)"
check "기본 모델, 리뷰와 같은 제약, 요약 세션 표시, 무인 실행 표시는 없음" \
  "model=claude-opus-5-5 review=1 summary=1 run=" "$(cat "$SCENARIO/calls")"
contains "프롬프트에 기본 범위 main...HEAD가 있다" "main...HEAD" "$(cat "$SCENARIO/prompt")"
contains "프롬프트에 쓸 파일이 있다" "phases/demo/summary.md" "$(cat "$SCENARIO/prompt")"

echo "다시 부를 때"
: >"$SCENARIO/calls"
run "$R" demo
check "쓴 뒤로 그대로면 세션 없이 0" "0:0" "$RC:$(ncalls)"
contains "최신이라고 알린다" "최신이다" "$OUT"
echo "- [x] 봤다" >"$R/phases/demo/MANUAL.md"
commit_all "$R" "docs(demo): MANUAL"
run "$R" demo
check "phases/ 아래만 바뀌었으면 다시 쓰지 않는다" "0:0" "$RC:$(ncalls)"
echo "고친 코드" >>"$R/code.txt"
commit_all "$R" "fix(demo): 사람이 고쳤다"
run "$R" demo
check "phases/ 밖이 바뀌었으면 다시 쓴다" "0:1" "$RC:$(ncalls)"
check "다시 쓴 요약을 커밋한다" "docs(demo): 최종 요약|fix(demo): 사람이 고쳤다|docs(demo): MANUAL|docs(demo): 최종 요약|" "$(subjects "$R")"
: >"$SCENARIO/calls"
run "$R" demo --force
check "--force면 최신이어도 다시 쓴다" "0:1" "$RC:$(ncalls)"

echo "본문이 그대로일 때"
R="$(make_repo same)"
scenario same same
run "$R" demo
check "판독용 줄에 다룬 커밋을 단다" "<!-- summary-of: $(git -C "$R" rev-parse main) -->" "$(tail -n 1 "$R/phases/demo/summary.md")"
echo "고친 코드" >>"$R/code.txt"
commit_all "$R" "fix(demo): 고쳤다"
code_commit="$(git -C "$R" rev-parse HEAD)"
run "$R" demo
check "코드가 바뀌면 본문이 같아도 다룬 커밋을 고쳐 커밋한다" \
  "0:docs(demo): 최종 요약|fix(demo): 고쳤다|docs(demo): 최종 요약|" "$RC:$(subjects "$R")"
check "새 판독용 줄은 고친 코드의 커밋이다" "<!-- summary-of: $code_commit -->" "$(tail -n 1 "$R/phases/demo/summary.md")"
: >"$SCENARIO/calls"
run "$R" demo
check "그 뒤로는 최신이라 세션을 띄우지 않는다" "0:0" "$RC:$(ncalls)"
run "$R" demo --force
check "--force로 다시 써도 그대로면 커밋하지 않는다" \
  "0:docs(demo): 최종 요약|fix(demo): 고쳤다|docs(demo): 최종 요약|" "$RC:$(subjects "$R")"

echo "세션 앞에서 멈출 때"
R="$(make_repo dirty)"
scenario dirty
echo "커밋 안 한 변경" >>"$R/code.txt"
run "$R" demo
check "커밋하지 않은 변경이 있으면 세션 없이 1" "1:0" "$RC:$(ncalls)"
contains "이유를 알린다" "커밋되지 않은 변경" "$OUT"
R="$(make_repo pending)"
scenario pending
printf '{"steps":[{"step":0,"name":"demo","status":"pending"}]}' >"$R/phases/demo/index.json"
commit_all "$R" "chore: pending"
run "$R" demo
check "끝나지 않은 phase는 세션 없이 1" "1:0" "$RC:$(ncalls)"

echo "세션이 약속을 어길 때"
R="$(make_repo nofile)"
scenario nofile nofile
run "$R" demo
check "요약을 남기지 않으면 1" 1 "$RC"
check "아무것도 커밋하지 않는다" "" "$(subjects "$R")"
R="$(make_repo other)"
scenario other other
run "$R" demo
check "요약 밖을 고치면 1" 1 "$RC"
check "그때 요약을 커밋하지 않는다" "" "$(subjects "$R")"
contains "이유를 알린다" "밖을 바꿨다" "$OUT"
R="$(make_repo commits)"
scenario commits commit
run "$R" demo
check "세션이 커밋하면 1" 1 "$RC"
contains "이유를 알린다" "세션이 커밋했다" "$OUT"

echo "범위"
R="$(make_repo base)"
scenario base
(cd "$R" && G branch --quiet prev main) >/dev/null 2>&1
run "$R" demo --base prev
check "--base를 받는다" 0 "$RC"
contains "프롬프트의 범위가 바뀐다" "prev...HEAD" "$(cat "$SCENARIO/prompt")"
: >"$SCENARIO/calls"
run "$R" demo --base nope --force
check "없는 ref면 세션 없이 64" "64:0" "$RC:$(ncalls)"

echo "입력"
R="$(make_repo input)"
scenario input
run "$R"
check "task가 없으면 64" 64 "$RC"
run "$R" nope
check "없는 phase면 64" 64 "$RC"
run "$R" demo --bogus
check "모르는 인자면 64" 64 "$RC"
check "어느 경우에도 세션을 띄우지 않는다" 0 "$(ncalls)"

echo "summary_is_current"
HARNESS_SUMMARY_LIB=1 source "$SCRIPT_DIR/harness-summary.sh"
R="$(make_repo lib)"
if summary_is_current "$R" demo; then got=0; else got=1; fi
check "요약이 없으면 최신이 아니다" 1 "$got"
init="$(git -C "$R" rev-parse HEAD)"
is_current() { if summary_is_current "$R" demo; then echo 0; else echo 1; fi; }
printf -- '- 요약\n\n<!-- summary-of: %s -->\n' "$init" >"$R/phases/demo/summary.md"
check "커밋하지 않은 요약은 최신이 아니다" 1 "$(is_current)"
commit_all "$R" "docs(demo): 최종 요약"
check "다룬 커밋 뒤로 코드가 그대로면 최신이다" 0 "$(is_current)"
echo "고친 코드" >>"$R/code.txt"
commit_all "$R" "fix(demo): 고쳤다"
check "다룬 커밋 뒤로 코드가 바뀌면 낡았다 — 요약을 나중에 커밋했어도" 1 "$(is_current)"
printf -- '- 요약\n' >"$R/phases/demo/summary.md"
commit_all "$R" "docs(demo): 판독용 줄 없음"
check "판독용 줄이 없으면 최신이 아니다" 1 "$(is_current)"
printf -- '- 요약\n\n<!-- summary-of: %s -->\n' "$(printf '0%.0s' $(seq 40))" >"$R/phases/demo/summary.md"
commit_all "$R" "docs(demo): 없는 커밋"
check "판독용 줄의 커밋이 없으면 최신이 아니다" 1 "$(is_current)"
printf '<!-- summary-of: %s -->\n' "$(git -C "$R" rev-parse HEAD)" >"$R/phases/demo/summary.md"
commit_all "$R" "docs(demo): 본문 없음"
check "판독용 줄만 있는 요약은 최신이 아니다" 1 "$(is_current)"

printf '\n통과 %d · 실패 %d\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
