#!/usr/bin/env bash
# execute-smoke.test.sh — 실제 execute.py를 가짜 claude로 끝까지 돌려, 세션이 빨간 검사 위에
# completed를 적는 경우를 재현한다.
#
#   bash scripts/execute-smoke.test.sh
#
# 시험용 phase smoke-harness에서 실제로 일어난 일이다: Stop 훅이 세 번 되돌린 뒤 놓아주자
# 세션이 적어 둔 completed가 그대로 기록됐다. 이제는 execute.py가 검사를 직접 돌린다.
set -u

# 이 테스트가 무인 세션 안에서 돌면 그 세션의 HARNESS_* 변수를 물려받는다. 그러면 가드가
# "헤드리스다"로 판정해 테스트의 기대와 어긋난다. 필요한 변수는 경우마다 직접 넣는다.
unset HARNESS_RUN HARNESS_REVIEW HARNESS_FIX HARNESS_MODEL HARNESS_MAX_REVIEW_ROUNDS HARNESS_CHECK_CMD

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
PASS=0
FAIL=0

check() { # check <설명> <기대> <실제>
  if [ "$2" = "$3" ]; then
    PASS=$((PASS + 1))
    printf '  ok    %s\n' "$1"
  else
    FAIL=$((FAIL + 1))
    printf '  FAIL  %s — want=[%s] got=[%s]\n' "$1" "$2" "$3"
  fi
}

# 가짜 claude: 호출 횟수를 세고, 지금 pending인 step에 completed를 적는다.
# FIX_ON이 n이면 n번째 호출에서 $REPO/fixed를 만들어 검사를 초록으로 바꾼다.
mkdir -p "$TMP/bin"
cat >"$TMP/bin/claude" <<'FAKE'
#!/usr/bin/env bash
n=$(($(cat "$REPO/.calls" 2>/dev/null || echo 0) + 1))
echo "$n" >"$REPO/.calls"
[ "${FIX_ON:-0}" = "$n" ] && : >"$REPO/fixed"
python3 - "$REPO/phases/demo/index.json" <<'PY'
import json, sys
p = sys.argv[1]
d = json.load(open(p))
for s in d["steps"]:
    if s["status"] == "pending":
        s["status"] = "completed"
        s["summary"] = "다 됐다고 신고한다"
        break
json.dump(d, open(p, "w"))
PY
echo '{}'
FAKE
chmod +x "$TMP/bin/claude"

make_repo() { # make_repo <이름> → 경로를 찍는다
  local r="$TMP/$1"
  mkdir -p "$r/scripts" "$r/phases/demo"
  cp "$SRC/execute.py" "$r/scripts/execute.py"
  printf '.calls\n.out\nfixed\n' >"$r/.gitignore"
  printf '{"phases": [{"dir": "demo", "status": "pending"}]}\n' >"$r/phases/index.json"
  printf '{"project": "T", "phase": "demo", "steps": [{"step": 0, "name": "only", "status": "pending"}]}\n' \
    >"$r/phases/demo/index.json"
  printf '# Step 0\n' >"$r/phases/demo/step0.md"
  (
    cd "$r" && git init -q -b main && git add -A &&
      git -c user.name=t -c user.email=t@t commit -qm init && git checkout -q -b feat-demo
  )
  echo "$r"
}

run() { # run <레포> <검사 명령> [FIX_ON] → 종료 코드를 RC에 둔다
  REPO="$1" FIX_ON="${3:-0}" HARNESS_CHECK_CMD="$2" PATH="$TMP/bin:$PATH" \
    GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t \
    python3 "$1/scripts/execute.py" demo >"$1/.out" 2>&1
  RC=$?
}

field() { # field <레포> <키> → step 0의 값
  python3 -c '
import json, sys
s = json.load(open(sys.argv[1] + "/phases/demo/index.json"))["steps"][0]
print(s.get(sys.argv[2], ""))' "$1" "$2"
}

top() {
  python3 -c '
import json, sys
print(json.load(open(sys.argv[1] + "/phases/index.json"))["phases"][0]["status"])' "$1"
}

echo "검사가 끝까지 빨갛다"
R="$(make_repo red)"
run "$R" 'echo RED-MARKER; exit 1'
check "종료 코드 1" 1 "$RC"
check "세 번 시도한다" 3 "$(cat "$R/.calls")"
check "step은 error로 남는다" error "$(field "$R" status)"
check "completed_at이 없다" "" "$(field "$R" completed_at)"
check "에러에 검사 출력이 실린다" yes "$(field "$R" error_message | grep -q '^RED-MARKER$' && echo yes)"
check "상위 인덱스도 error다" error "$(top "$R")"
check "phase 완료 커밋이 없다" 0 "$(git -C "$R" log --oneline | grep -c 'mark phase completed')"

echo "검사가 초록이다"
R="$(make_repo green)"
run "$R" 'true'
check "종료 코드 0" 0 "$RC"
check "한 번만 시도한다" 1 "$(cat "$R/.calls")"
check "step은 completed다" completed "$(field "$R" status)"
check "상위 인덱스도 completed다" completed "$(top "$R")"

echo "두 번째 시도에서 고친다"
R="$(make_repo fixed)"
run "$R" "test -f '$R/fixed'" 2
check "종료 코드 0" 0 "$RC"
check "두 번 시도한다" 2 "$(cat "$R/.calls")"
check "step은 completed다" completed "$(field "$R" status)"

printf '\n통과 %d · 실패 %d\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
