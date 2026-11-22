#!/usr/bin/env bash
# harness-run.sh 검증. 통과/실패 수를 찍고 하나라도 실패하면 1로 끝난다.
#   1부: phase_complete 게이트 (원본 그대로)
#   2부: 리포트 판독 함수와 worktree 판정
#   3부: 리뷰 → 처분 루프. 가짜 claude와 가짜 execute.py로 스크립트 전체를 돌린다.
#   실행: bash scripts/harness-run.test.sh
#
# 이 게이트가 리뷰 세션을 띄울지 말지를 혼자 정한다. 여기가 틀리면 미완성 phase에
# 리뷰가 붙거나(오판), 끝난 phase가 리뷰 없이 지나간다(누락).
set -u

HARNESS_RUN_LIB=1 source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/harness-run.sh"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

PASS=0
FAIL=0
N=0

ALL_DONE='{"steps":[{"step":0,"status":"completed"},{"step":1,"status":"completed"}]}'

expect() { # expect <0|1> <task-index|NONE> <top-index|NONE> <설명>
  local want="$1" task_json="$2" top_json="$3" label="$4" root got
  N=$((N + 1))
  root="$TMP/case$N"
  mkdir -p "$root/phases/demo"
  [ "$task_json" = "NONE" ] || printf '%s' "$task_json" >"$root/phases/demo/index.json"
  [ "$top_json" = "NONE" ] || printf '%s' "$top_json" >"$root/phases/index.json"

  if phase_complete "$root" demo; then got=0; else got=1; fi

  if [ "$got" = "$want" ]; then
    PASS=$((PASS + 1))
    printf '  ok    %s  %s\n' "$want" "$label"
  else
    FAIL=$((FAIL + 1))
    printf '  FAIL  want=%s got=%s  %s\n' "$want" "$got" "$label"
  fi
}

# 상위 phases/index.json은 보지 않는다. MANUAL.md에 미확인 항목이 남으면 execute.py는
# _finalize()에서 exit 5로 끝나며 상위 인덱스도, task 인덱스의 completed_at도 쓰지 않는다.
# 그때도 코드는 전부 커밋돼 있으므로 리뷰 대상이다. 상위를 게이트에 넣으면 사람이
# MANUAL을 체크할 때까지 리뷰가 영원히 안 뜬다.
echo "상위 인덱스 비참조"
expect 0 "$ALL_DONE" '{"phases":[{"dir":"demo","status":"pending"}]}'   "상위가 pending이어도 통과 (MANUAL 미체크 모양)"
expect 0 "$ALL_DONE" '{"phases":[{"dir":"demo","status":"error"}]}'     "상위가 error여도 통과"
expect 0 "$ALL_DONE" NONE                                              "상위 인덱스 파일이 없어도 통과"
expect 0 "$ALL_DONE" '{"phases":[]}'                                   "상위에 항목이 없어도 통과"

echo "steps 판정"
expect 0 '{"steps":[{"step":0,"status":"completed"}]}' NONE            "step 하나, completed"
expect 1 '{"steps":[{"step":0,"status":"completed"},{"step":1,"status":"pending"}]}' NONE  "마지막 step이 pending"
expect 1 '{"steps":[{"step":0,"status":"pending"},{"step":1,"status":"completed"}]}' NONE  "첫 step이 pending"
expect 1 '{"steps":[{"step":0,"status":"completed"},{"step":1,"status":"error"}]}'   NONE  "step 하나가 error"
expect 1 '{"steps":[{"step":0,"status":"completed"},{"step":1,"status":"blocked"}]}' NONE  "step 하나가 blocked"
expect 1 '{"steps":[]}'                                                NONE            "steps가 빈 배열"
expect 1 '{"steps":[{"step":0}]}'                                      NONE            "status 키가 없는 step"

echo "입력"
expect 1 NONE                    NONE  "task 인덱스 파일이 없다"
expect 1 '{"steps": [' NONE            "깨진 JSON"
expect 1 '{}'                    NONE  "steps 키가 없다"
expect 1 '{"steps":"completed"}' NONE  "steps가 배열이 아니다"


# ---------------------------------------------------------------------------
# 2부: 리포트 판독 함수와 worktree 판정
# ---------------------------------------------------------------------------

check() { # check <설명> <기대> <실제>
  if [ "$2" = "$3" ]; then
    PASS=$((PASS + 1))
    printf '  ok    %s\n' "$1"
  else
    FAIL=$((FAIL + 1))
    printf '  FAIL  %s — want=[%s] got=[%s]\n' "$1" "$2" "$3"
  fi
}

echo "latest_round"
R="$TMP/rounds"
mkdir -p "$R/phases/demo/review"
check "리포트가 없으면 0" 0 "$(latest_round "$R" demo)"
touch "$R/phases/demo/review/review-1.md" "$R/phases/demo/review/review-2.md" "$R/phases/demo/review/fix-9.md"
check "가장 큰 번호 (fix 파일은 세지 않는다)" 2 "$(latest_round "$R" demo)"
touch "$R/phases/demo/review/review-10.md" "$R/phases/demo/review/review-draft.md"
check "문자열이 아니라 수로 비교한다 (10 > 2), 번호가 아닌 것은 무시" 10 "$(latest_round "$R" demo)"
check "review 폴더가 없어도 0" 0 "$(latest_round "$R" nope)"

echo "read_marker"
M="$TMP/marker.md"
printf '# 리포트\n\n| major | 3 |\n\n<!-- verdict: critical=0 major=2 minor=15 -->\n' >"$M"
check "critical" 0 "$(read_marker "$M" verdict critical)"
check "major" 2 "$(read_marker "$M" verdict major)"
check "minor (두 자리)" 15 "$(read_marker "$M" verdict minor)"
check "없는 키는 빈 값" "" "$(read_marker "$M" verdict blocker)"
read_marker "$M" verdict blocker >/dev/null
check "없는 키는 종료 코드 1" 1 "$?"
read_marker "$M" disposition fixed >/dev/null
check "다른 종류의 줄은 읽지 않는다" 1 "$?"
read_marker "$TMP/none.md" verdict major >/dev/null
check "파일이 없으면 1" 1 "$?"
printf '본문에 표만 있다\n| major | 3 |\n' >"$M"
read_marker "$M" verdict major >/dev/null
check "표를 세어 추정하지 않는다 — 줄이 없으면 1" 1 "$?"
printf '<!-- disposition: fixed=6 rejected=1 needs-human=2 -->\n' >"$M"
check "needs-human" 2 "$(read_marker "$M" disposition needs-human)"
check "fixed" 6 "$(read_marker "$M" disposition fixed)"
printf '<!-- verdict: critical=9 major=9 minor=9 -->\n고쳐 쓴 뒤\n<!-- verdict: critical=0 major=1 minor=0 -->\n' >"$M"
check "줄이 여럿이면 마지막 것" 1 "$(read_marker "$M" verdict major)"

# ---------------------------------------------------------------------------
# 3부: 리뷰 → 처분 루프
# ---------------------------------------------------------------------------
#
# 가짜 claude는 HARNESS_REVIEW가 있으면 리뷰, HARNESS_FIX가 있으면 처분으로 행동한다.
#   $SCENARIO/verdicts      — 라운드별 "critical major minor" 한 줄씩. 다 쓰면 마지막 줄을 되풀이한다.
#   $SCENARIO/needs_human   — 처분이 적을 needs-human 값 (없으면 0)
#   $SCENARIO/review_mode   — noreport | nomarker
#   $SCENARIO/fix_mode      — nofile | nomarker | dirty | uncommitted
#   $SCENARIO/calls         — 호출 기록 ("review" / "fix", 그리고 --model 값)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STUB_BIN="$TMP/bin"
mkdir -p "$STUB_BIN"
cat >"$STUB_BIN/claude" <<'STUB'
#!/usr/bin/env bash
# 인자에서 --model 값을 꺼낸다.
model=""
prev=""
for a in "$@"; do
  [ "$prev" = "--model" ] && model="$a"
  prev="$a"
done
dir="phases/demo/review"
if [ -n "${HARNESS_REVIEW:-}" ]; then
  echo "review model=$model run=${HARNESS_RUN:-}" >>"$SCENARIO/calls"
  mode="$(cat "$SCENARIO/review_mode" 2>/dev/null)"
  [ "$mode" = "noreport" ] && exit 1
  n=$(($(ls "$dir" 2>/dev/null | grep -c '^review-[0-9]*\.md$') + 1))
  line="$(sed -n "${n}p" "$SCENARIO/verdicts")"
  [ -n "$line" ] || line="$(tail -n 1 "$SCENARIO/verdicts")"
  set -- $line
  echo "# ${n}차 리뷰" >"$dir/review-$n.md"
  [ "$mode" = "nomarker" ] || echo "<!-- verdict: critical=$1 major=$2 minor=$3 -->" >>"$dir/review-$n.md"
  exit 0
fi
if [ -n "${HARNESS_FIX:-}" ]; then
  echo "fix model=$model run=${HARNESS_RUN:-}" >>"$SCENARIO/calls"
  mode="$(cat "$SCENARIO/fix_mode" 2>/dev/null)"
  [ "$mode" = "nofile" ] && exit 0
  n=$(ls "$dir" | grep -c '^review-[0-9]*\.md$')
  echo "fixed $n" >>code.txt
  git add code.txt && git commit --quiet -m "fix(demo): ${n}차 리뷰"
  echo "# ${n}차 처분" >"$dir/fix-$n.md"
  nh="$(cat "$SCENARIO/needs_human" 2>/dev/null || echo 0)"
  [ "$mode" = "nomarker" ] || echo "<!-- disposition: fixed=1 rejected=0 needs-human=$nh -->" >>"$dir/fix-$n.md"
  [ "$mode" = "uncommitted" ] || { git add "$dir/fix-$n.md" && git commit --quiet -m "docs(demo): 처분"; }
  [ "$mode" = "dirty" ] && echo "남긴 변경" >>code.txt
  exit 0
fi
echo "other" >>"$SCENARIO/calls"
STUB
chmod +x "$STUB_BIN/claude"

# 메인 체크아웃 하나와 거기서 딴 worktree 하나를 만든다. harness-run.sh는 worktree 쪽에서 돈다.
make_repo() { # make_repo <이름> <execute.py 종료 코드> → worktree 경로를 찍는다
  local base="$TMP/$1" wt="$TMP/$1-wt"
  mkdir -p "$base/scripts" "$base/phases/demo"
  cp "$SCRIPT_DIR/harness-run.sh" "$base/scripts/"
  printf 'import sys\nsys.exit(%s)\n' "$2" >"$base/scripts/execute.py"
  printf '%s' "$ALL_DONE" >"$base/phases/demo/index.json"
  printf 'phases/**/review/session.log\n' >"$base/.gitignore"
  (
    cd "$base" && git init --quiet -b main &&
      git -c user.name=t -c user.email=t@t add -A &&
      git -c user.name=t -c user.email=t@t commit --quiet -m init &&
      git worktree add --quiet -b feat-demo "$wt"
  ) >/dev/null 2>&1
  echo "$wt"
}

run_loop() { # run_loop <worktree> <인자...> → 종료 코드를 RC에 둔다
  local wt="$1"
  shift
  (
    cd "$wt" &&
      PATH="$STUB_BIN:$PATH" SCENARIO="$SCENARIO" \
        GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t \
        bash scripts/harness-run.sh demo "$@"
  ) >"$TMP/out.log" 2>&1
  RC=$?
}

scenario() { # scenario <이름> <verdict 줄...>
  SCENARIO="$TMP/scn-$1"
  mkdir -p "$SCENARIO"
  shift
  printf '%s\n' "$@" >"$SCENARIO/verdicts"
  : >"$SCENARIO/calls"
}

calls() { tr '\n' ' ' <"$SCENARIO/calls" | sed -E 's/ model=[^ ]*//g; s/ run=[^ ]*//g; s/ $//'; }
subjects() { git -C "$1" log --format=%s main..HEAD | tr '\n' '|'; }

echo "worktree 판정"
WT="$(make_repo gate 0)"
if in_linked_worktree "$WT"; then got=0; else got=1; fi
check "따로 만든 worktree는 통과" 0 "$got"
if in_linked_worktree "$TMP/gate"; then got=0; else got=1; fi
check "메인 체크아웃은 거부" 1 "$got"
scenario gate "0 0 0"
run_loop "$TMP/gate"
check "메인 체크아웃에서 부르면 64로 끝나고 아무 세션도 띄우지 않는다" "64:" "$RC:$(calls)"

echo "루프: 결함 없음"
WT="$(make_repo clean 0)"
scenario clean "0 0 0"
run_loop "$WT"
check "리뷰 한 번, 처분 없음, 종료 0" "0:review" "$RC:$(calls)"
check "리포트가 커밋된다" "docs(demo): 1차 리뷰 리포트 — critical 0 · major 0 · minor 0|" "$(subjects "$WT")"

echo "루프: minor만"
WT="$(make_repo minor 0)"
scenario minor "0 0 3"
run_loop "$WT"
check "처분은 하되 다시 리뷰하지 않는다" "0:review fix" "$RC:$(calls)"

echo "루프: major → 처분 → 재리뷰에서 닫힘"
WT="$(make_repo major 0)"
scenario major "0 2 1" "0 0 0"
run_loop "$WT"
check "리뷰, 처분, 재리뷰" "0:review fix review" "$RC:$(calls)"
check "리포트 둘과 처분 기록이 있다" "review-1.md review-2.md fix-1.md" \
  "$(cd "$WT/phases/demo/review" && echo review-*.md fix-*.md)"
check "작업 트리가 깨끗하다" "" "$(git -C "$WT" status --porcelain)"

echo "루프: 끝까지 major가 남는다"
WT="$(make_repo stuck 0)"
scenario stuck "0 1 0"
run_loop "$WT"
check "기본 3라운드를 돌고 종료 6" "6:review fix review fix review fix" "$RC:$(calls)"
WT="$(make_repo stuck2 0)"
scenario stuck2 "1 0 0"
HARNESS_MAX_REVIEW_ROUNDS=1 run_loop "$WT"
check "HARNESS_MAX_REVIEW_ROUNDS=1이면 한 라운드" "6:review fix" "$RC:$(calls)"

echo "루프: 사람 판단으로 넘긴 항목"
WT="$(make_repo human 0)"
scenario human "0 0 2"
echo 1 >"$SCENARIO/needs_human"
run_loop "$WT"
check "needs-human이 있으면 종료 6" "6:review fix" "$RC:$(calls)"

echo "루프: --no-fix"
WT="$(make_repo nofix 0)"
scenario nofix "0 2 0"
run_loop "$WT" --no-fix
check "리뷰까지만 하고 execute.py의 코드로 끝난다" "0:review" "$RC:$(calls)"

echo "루프: execute.py의 종료 코드"
WT="$(make_repo manual 5)"
scenario manual "0 0 0"
run_loop "$WT"
check "MANUAL 미확인(5)이어도 리뷰는 돌고 5로 끝난다" "5:review" "$RC:$(calls)"
WT="$(make_repo manual6 5)"
scenario manual6 "0 1 0"
run_loop "$WT"
check "닫히지 않은 리뷰(6)가 5보다 앞선다" 6 "$RC"

echo "루프: 세션이 약속을 어긴다"
WT="$(make_repo noreport 0)"
scenario noreport "0 0 0"
echo noreport >"$SCENARIO/review_mode"
run_loop "$WT"
check "리포트가 없으면 6" "6:review" "$RC:$(calls)"
WT="$(make_repo nomarker 0)"
scenario nomarker "0 2 0"
echo nomarker >"$SCENARIO/review_mode"
run_loop "$WT"
check "verdict 줄이 없으면 처분하지 않고 6" "6:review" "$RC:$(calls)"
check "그래도 리포트는 커밋한다" "docs(demo): 1차 리뷰 리포트|" "$(subjects "$WT")"
WT="$(make_repo nofile 0)"
scenario nofile "0 2 0"
echo nofile >"$SCENARIO/fix_mode"
run_loop "$WT"
check "처분 기록이 없으면 6" "6:review fix" "$RC:$(calls)"
WT="$(make_repo fixnomarker 0)"
scenario fixnomarker "0 0 1"
echo nomarker >"$SCENARIO/fix_mode"
run_loop "$WT"
check "disposition 줄이 없으면 6" 6 "$RC"
WT="$(make_repo dirty 0)"
scenario dirty "0 0 1"
echo dirty >"$SCENARIO/fix_mode"
run_loop "$WT"
check "처분이 커밋하지 않은 변경을 남기면 6" 6 "$RC"
WT="$(make_repo uncommitted 0)"
scenario uncommitted "0 0 1"
echo uncommitted >"$SCENARIO/fix_mode"
run_loop "$WT"
check "처분 기록만 안 커밋했으면 대신 커밋하고 통과" "0:" "$RC:$(git -C "$WT" status --porcelain)"

echo "세션 환경"
WT="$(make_repo env 0)"
scenario env "0 1 0" "0 0 0"
run_loop "$WT"
check "기본 모델, 처분 세션에만 HARNESS_RUN" \
  "review model=claude-opus-5-5 run=|fix model=claude-opus-5-5 run=1|review model=claude-opus-5-5 run=|" \
  "$(tr '\n' '|' <"$SCENARIO/calls")"
WT="$(make_repo env2 0)"
scenario env2 "0 0 0"
HARNESS_MODEL=other-model run_loop "$WT"
check "HARNESS_MODEL로 바꾼다" "review model=other-model run=|" "$(tr '\n' '|' <"$SCENARIO/calls")"

printf '\n통과 %d · 실패 %d\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
