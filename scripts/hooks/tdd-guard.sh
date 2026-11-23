#!/usr/bin/env bash
# TDD Guard — PreToolUse[Edit|Write|MultiEdit]
# 구현 코드를 쓰려 할 때 그 모듈의 테스트가 먼저 있는지 본다. 없으면 막는다.
#
# 원본: jha0313/finsight — scripts/hooks/tdd-guard.sh, 그것을 고쳐 쓴 OnlineFourCut의 같은 파일.
# 골격(자기 방어, deny JSON, "blocked로 세워라" 문구, 가장 가까운 프로젝트 루트)은 그대로 두고
# 규칙을 이 레포의 Python 구조에 맞춰 다시 썼다. 주석의 Epic 번호는 원본 프로젝트의 사례다.
#
#   1. 프로젝트 루트는 편집 파일에서 위로 올라가며 만나는 가장 가까운 pyproject.toml이다.
#      못 찾으면 막지 않는다.
#   2. 검사 대상은 app/ 아래의 .py뿐이다. tests/, scripts/, migrations/, 문서와 설정은 통과한다.
#   3. 대응 테스트는 이름이 아니라 경로로 찾는다. app/books/service.py의 테스트는
#      tests/books/test_service.py 또는 tests/books/test_service_*.py다(docs/ARCHITECTURE.md 8절:
#      tests/는 app/과 같은 구조). 기능 폴더마다 service.py가 있어서 이름만으로 찾으면
#      다른 기능의 test_service.py가 대신 통과시킨다.
#   4. 통과 규칙은 절대경로가 아니라 프로젝트 루트 기준 상대 경로에 맞춘다. worktree의
#      절대경로에는 무엇이든 들어갈 수 있다.
#
# 규칙의 설명은 docs/DEVELOPMENT.md에 있고, 규칙의 실체는 이 파일이다.

INPUT=$(cat)

# --- 입력 파싱. jq → python3 순으로 쓰고, 둘 다 없으면 막지 않는다(fail-open) ---
if command -v jq >/dev/null 2>&1; then
  FILE_PATH=$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // empty')
elif command -v python3 >/dev/null 2>&1; then
  FILE_PATH=$(printf '%s' "$INPUT" | python3 -c '
import json, sys
try:
    sys.stdout.write((json.load(sys.stdin).get("tool_input") or {}).get("file_path") or "")
except Exception:
    pass
')
else
  exit 0
fi

[ -n "$FILE_PATH" ] || exit 0
case "$FILE_PATH" in /*) ;; *) FILE_PATH="$PWD/$FILE_PATH" ;; esac

deny() {
  cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "TDD GUARD: $1"
  }
}
EOF
  exit 0
}

# --- 자기 방어 ---
# 아래 통과 규칙보다 먼저 본다. scripts/ 는 검사 대상이 아니라서, 막힌 세션이 가드에
# 자기 예외를 추가하고 그대로 커밋하는 길이 열려 있었다.
# Epic 0의 8 step 중 3개가 실제로 그 길을 지났다 — deny 문구가 그렇게 하라고 시켰다.
#
# 검사 스크립트와 훅 배선도 같은 자리다. Stop 훅이 부르는 scripts/check.sh를 비우거나
# .claude/settings.json에서 훅을 빼면 가드를 고치지 않고도 같은 결과가 난다.
#
# 무인 실행(HARNESS_RUN=1, execute.py와 harness-run.sh의 처분 세션이 넣는다)에서만 막는다.
# 사람이 붙어 있는 세션까지 막으면 가드를 손볼 때 훅을 꺼야 한다 — deny는 승인으로 뚫리지 않는다.
if [ -n "${HARNESS_RUN:-}" ]; then
  case "$FILE_PATH" in
    */scripts/hooks/* | */scripts/check.sh | */.claude/settings.json | */.claude/settings.local.json)
      deny "가드와 검사 설정(${FILE_PATH##*/})은 무인 실행에서 고칠 수 없다. 제약받는 쪽이 제약을 넓히면 가드가 아니다. 예외가 필요하면 index.json의 status를 'blocked'로, blocked_reason에 어떤 파일에 왜 예외가 필요한지 적고 즉시 중단해라. 사람이 판단한다."
      ;;
  esac
fi

# --- 프로젝트 루트 찾기 ---
# 가장 가까운 pyproject.toml이 프로젝트 루트다. 못 찾으면 아직 스캐폴딩 전이라 막지 않는다.
PROJ_ROOT=""
probe=$(dirname "$FILE_PATH")
while [ -n "$probe" ] && [ "$probe" != "/" ]; do
  if [ -f "$probe/pyproject.toml" ]; then
    PROJ_ROOT="$probe"
    break
  fi
  probe=$(dirname "$probe")
done
[ -n "$PROJ_ROOT" ] || exit 0

REL=${FILE_PATH#"$PROJ_ROOT"/}

# --- 통과 규칙 ---

# app/ 밖은 검사하지 않는다 — 테스트, 스크립트, 마이그레이션, 문서, 설정
case "$REL" in
  app/*) ;;
  *) exit 0 ;;
esac

# .py가 아닌 것은 로직이 아니다
case "$REL" in
  *.py) ;;
  *) exit 0 ;;
esac

# 선언과 조립만 하는 파일.
#   __init__.py — 패키지 표시. 여기에 로직을 쓰면 테스트 없이 통과한다. 쓰지 마라.
#   app/main.py — 라우터와 어댑터를 조립한다. 부팅 검증은 통합 테스트의 일이다.
#   models.py   — 테이블 선언. schemas.py — 요청과 응답의 형식 선언.
#                 여기에 판정 함수를 쓰면 테스트 없이 통과한다. 판정은 service.py에 둬라.
#   app/core/config.py   — 설정 클래스(docs/CONFIGURATION.md).
#   app/core/ports.py, app/core/ports/ — 포트의 Protocol 선언(docs/ARCHITECTURE.md 8절).
#   app/core/database.py — 엔진과 연결의 조립.
# router.py는 여기에 없다. 로그인 상태와 허용 목록의 관문, 에러 형식이 라우터 층의 성질이고,
# 저작권이 있는 본문이 새는 자리가 바로 여기다(docs/ARCHITECTURE.md 1절). 가짜 어댑터를 끼우면
# DB 없이 테스트할 수 있다.
case "$REL" in
  */__init__.py | app/main.py | */models.py | */schemas.py) exit 0 ;;
  app/core/config.py | app/core/ports.py | app/core/ports/* | app/core/database.py) exit 0 ;;
esac

# --- 개별 파일 예외 ---
# 위 규칙으로 덮이지 않는데 단위 테스트를 먼저 쓸 수 없는 파일을 여기에 한 줄씩 더한다.
# 줄마다 이유를 주석으로 단다. 무인 실행은 이 파일을 고칠 수 없으므로, step을 설계하는
# 사람이 step 파일과 같은 커밋에 넣는다(.claude/commands/harness.md 원칙 9).
#
#   app/__main__.py — `python -m app`으로 uvicorn을 띄우기만 하는 진입점이다. 설정 클래스에서
#                     포트와 로그 레벨을 읽어 넘길 뿐 판정하는 로직이 없고, 서버가 실제로 뜨는지는
#                     compose 스모크가 확인한다(Epic 0, phases/0-project-setup/step0.md).
case "$REL" in
  app/__main__.py) exit 0 ;;
esac

# --- 대응 테스트 찾기 ---
# app/<경로>/<이름>.py → tests/<경로>/test_<이름>.py 또는 tests/<경로>/test_<이름>_*.py
SUB=${REL#app/}
SUB_DIR=$(dirname "$SUB")
NAME=$(basename "$SUB" .py)
if [ "$SUB_DIR" = "." ]; then
  TEST_REL_DIR="tests"
else
  TEST_REL_DIR="tests/$SUB_DIR"
fi
TEST_DIR="$PROJ_ROOT/$TEST_REL_DIR"

if [ -f "$TEST_DIR/test_${NAME}.py" ]; then
  exit 0
fi
for candidate in "$TEST_DIR/test_${NAME}_"*.py; do
  [ -f "$candidate" ] && exit 0
done

# --- 차단 ---
deny "'${REL}'에 대응하는 테스트가 없다. 구현보다 테스트를 먼저 써라. 기대 위치: ${TEST_REL_DIR}/test_${NAME}.py (같은 폴더의 test_${NAME}_*.py 도 인정한다). 다른 폴더에 있는 같은 이름의 테스트는 세지 않는다. 이 파일이 TDD 대상이 아니라고 판단되면 가드를 고치지 마라 — index.json의 status를 'blocked'로, blocked_reason에 '${REL}: 예외가 필요한 이유'를 적고 즉시 중단해라. 예외를 넓힐지는 사람이 정한다."
