#!/usr/bin/env bash
# stop-check.sh 검증. 통과/실패 수를 찍고 하나라도 실패하면 1로 끝난다.
#   실행: bash scripts/hooks/stop-check.test.sh
#
# 이 훅이 틀리면 두 가지로 샌다. 실패를 막지 못하면 검사가 빨간 채 세션이 끝나고(원본의 결함),
# 상한이 듣지 않으면 고칠 수 없는 실패에서 세션이 끝나지 못한다.
set -u

# 이 테스트가 무인 세션 안에서 돌면 그 세션의 HARNESS_* 변수를 물려받는다. 그러면 가드가
# "헤드리스다"로 판정해 테스트의 기대와 어긋난다. 필요한 변수는 경우마다 직접 넣는다.
unset HARNESS_RUN HARNESS_REVIEW HARNESS_FIX HARNESS_MODEL HARNESS_MAX_REVIEW_ROUNDS HARNESS_CHECK_CMD

GUARD="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/stop-check.sh"
PASS=0
FAIL=0

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/proj" "$TMP/noproj" "$TMP/counters"
: >"$TMP/proj/pyproject.toml"

# run <세션 id> <stop_hook_active> <검사 명령> [프로젝트 폴더] [추가 환경 "K=V"]
# 종료 코드를 RC에, 표준 출력을 OUT에, 표준 오류를 ERR에 둔다.
run() {
  local sid="$1" active="$2" cmd="$3" proj="${4:-$TMP/proj}" extra="${5:-_UNUSED=}"
  OUT=$(printf '{"session_id":"%s","stop_hook_active":%s}' "$sid" "$active" \
    | env "$extra" TMPDIR="$TMP/counters" CLAUDE_PROJECT_DIR="$proj" HARNESS_CHECK_CMD="$cmd" \
      bash "$GUARD" 2>"$TMP/err")
  RC=$?
  ERR=$(cat "$TMP/err")
}

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

echo "통과"
run s1 false true
check "검사가 통과하면 0" 0 "$RC"
check "아무것도 찍지 않는다" "" "$OUT$ERR"

echo "실패 — 세션을 되돌린다"
run s2 false 'echo 테스트가-깨졌다; exit 1'
check "종료 코드 2 (1이면 세션이 그대로 끝난다)" 2 "$RC"
contains "검사 출력을 세션에 전한다" "테스트가-깨졌다" "$ERR"
contains "검사를 끄지 말라고 알린다" "통과시키지 마라" "$ERR"
check "표준 출력에는 아무것도 없다" "" "$OUT"
run s2b false 'exit 5'
check "pytest의 '수집 0개'(5)도 실패다" 2 "$RC"
contains "원래 종료 코드를 알린다" "종료 코드 5" "$ERR"

echo "상한"
run s3 false 'exit 1'
check "1번째" 2 "$RC"
run s3 true 'exit 1'
check "2번째" 2 "$RC"
run s3 true 'exit 1'
check "3번째" 2 "$RC"
contains "몇 번째인지 알린다" "3/3" "$ERR"
run s3 true 'exit 1'
check "4번째는 놓아준다" 0 "$RC"
contains "놓아줄 때 경고를 남긴다" "systemMessage" "$OUT"
if printf '%s' "$OUT" | python3 -c 'import json,sys; json.load(sys.stdin)' 2>/dev/null; then
  PASS=$((PASS + 1)); printf '  ok    경고가 올바른 JSON이다\n'
else
  FAIL=$((FAIL + 1)); printf '  FAIL  경고가 JSON으로 읽히지 않는다\n'
fi
run s3 false 'exit 1'
check "놓아준 뒤 새 턴은 다시 1번째부터" 2 "$RC"
contains "카운터가 초기화됐다" "1/3" "$ERR"

echo "카운터"
run s4 false 'exit 1'
run s4 true 'exit 1'
run s4 true true
check "중간에 통과하면 0" 0 "$RC"
run s4 true 'exit 1'
contains "통과한 뒤에는 처음부터 센다" "1/3" "$ERR"
run s5 false 'exit 1'
run s5 false 'exit 1'
contains "되돌림이 아닌 새 턴은 이어 세지 않는다" "1/3" "$ERR"
run s6a false 'exit 1'
run s6a true 'exit 1'
run s6b true 'exit 1'
contains "세션마다 따로 센다" "1/3" "$ERR"
run '../../etc/x' false 'exit 1'
check "세션 id에 경로 글자가 있어도 동작한다" 2 "$RC"
check "카운터 파일이 지정한 폴더 밖으로 나가지 않는다" "" "$(find "$TMP" -name 'x' -not -path "$TMP/counters/*")"

echo "건너뛰기"
run s7 false 'exit 1' "$TMP/proj" HARNESS_REVIEW=1
check "리뷰 세션은 검사하지 않는다" 0 "$RC"
run s8 false 'exit 1' "$TMP/noproj"
check "pyproject.toml이 없으면 검사하지 않는다" 0 "$RC"
run s9 false 'exit 1' "$TMP/proj" HARNESS_RUN=1
check "무인 step 세션은 검사한다" 2 "$RC"

echo "입력"
OUT=$(printf '' | TMPDIR="$TMP/counters" CLAUDE_PROJECT_DIR="$TMP/proj" HARNESS_CHECK_CMD='exit 1' bash "$GUARD" 2>/dev/null)
check "빈 입력이어도 실패는 막는다" 2 "$?"
OUT=$(printf 'not json' | TMPDIR="$TMP/counters" CLAUDE_PROJECT_DIR="$TMP/proj" HARNESS_CHECK_CMD=true bash "$GUARD" 2>/dev/null)
check "깨진 입력이어도 통과는 통과다" 0 "$?"

echo "기본 검사 명령"
mkdir -p "$TMP/real/scripts"
: >"$TMP/real/pyproject.toml"
printf '#!/usr/bin/env bash\necho check.sh가-불렸다\nexit 3\n' >"$TMP/real/scripts/check.sh"
ERR=$(printf '{"session_id":"s10","stop_hook_active":false}' \
  | env -u HARNESS_CHECK_CMD TMPDIR="$TMP/counters" CLAUDE_PROJECT_DIR="$TMP/real" bash "$GUARD" 2>&1 >/dev/null)
check "HARNESS_CHECK_CMD가 없으면 scripts/check.sh를 부른다" 2 "$?"
contains "그 출력을 전한다" "check.sh가-불렸다" "$ERR"

printf '\n통과 %d · 실패 %d\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
