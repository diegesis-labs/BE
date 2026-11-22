#!/usr/bin/env bash
# tdd-guard.sh 검증. 통과/실패 수를 찍고 하나라도 실패하면 1로 끝난다.
#   실행: bash scripts/hooks/tdd-guard.test.sh
set -u

# 이 테스트가 무인 세션 안에서 돌면 그 세션의 HARNESS_* 변수를 물려받는다. 그러면 가드가
# "헤드리스다"로 판정해 테스트의 기대와 어긋난다. 필요한 변수는 경우마다 직접 넣는다.
unset HARNESS_RUN HARNESS_REVIEW HARNESS_FIX HARNESS_MODEL HARNESS_MAX_REVIEW_ROUNDS HARNESS_CHECK_CMD

GUARD="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/tdd-guard.sh"
PASS=0
FAIL=0

expect() { # expect <allow|deny> <file_path> <설명> [1=무인 실행]
  # 무인 여부는 인자로 받는다. `HARNESS_RUN=1 expect ...`로 부르면 bash에서 함수 호출
  # 뒤까지 변수가 새어 다음 케이스들을 오염시킨다.
  local want="$1" path="$2" label="$3" unattended="${4:-}" got
  if printf '{"tool_input":{"file_path":"%s"}}' "$path" \
    | HARNESS_RUN="$unattended" bash "$GUARD" | grep -q '"deny"'; then
    got=deny
  else
    got=allow
  fi
  if [ "$got" = "$want" ]; then
    PASS=$((PASS + 1))
    printf '  ok    %-5s  %s\n' "$want" "$label"
  else
    FAIL=$((FAIL + 1))
    printf '  FAIL  want=%s got=%s  %s\n' "$want" "$got" "$label"
  fi
}

# --- 픽스처 ---
# proj: pyproject.toml이 있는 프로젝트. noproj: 아직 스캐폴딩 전.
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
P="$TMP/proj"
mkdir -p "$P/app/books" "$P/app/music" "$P/app/recommendation" "$P/app/adapters" "$P/app/core/ports" \
  "$P/tests/books" "$P/tests/music" "$P/tests/recommendation" "$P/tests/adapters" "$P/tests/core" \
  "$P/scripts/hooks" "$P/migrations/versions" "$P/.claude" "$P/docs" "$TMP/noproj/app/books"
: >"$P/pyproject.toml"
: >"$P/tests/books/test_service.py"
: >"$P/tests/books/test_router.py"
: >"$P/tests/books/test_repository.py"
: >"$P/tests/recommendation/test_service_sampling.py"
: >"$P/tests/adapters/test_pgvector.py"
: >"$P/tests/core/test_errors.py"
: >"$P/tests/test_toplevel.py"

echo "테스트 유무"
expect deny  "$P/app/music/service.py"            "테스트 없는 service"
expect deny  "$P/app/music/repository.py"         "테스트 없는 repository"
expect deny  "$P/app/music/router.py"             "router도 검사한다 — 접근 관문이 여기 있다"
expect deny  "$P/app/adapters/storage.py"         "테스트 없는 어댑터"
expect deny  "$P/app/core/security.py"            "테스트 없는 core 모듈"
expect allow "$P/app/books/service.py"            "tests/books/test_service.py가 있다"
expect allow "$P/app/books/router.py"             "tests/books/test_router.py가 있다"
expect allow "$P/app/books/repository.py"         "tests/books/test_repository.py가 있다"
expect allow "$P/app/adapters/pgvector.py"        "tests/adapters/test_pgvector.py가 있다"
expect allow "$P/app/core/errors.py"              "tests/core/test_errors.py가 있다"
expect allow "$P/app/recommendation/service.py"   "test_service_*.py도 인정한다"
expect allow "$P/app/toplevel.py"                 "app/ 바로 아래 파일은 tests/ 바로 아래에서 찾는다"

echo "경로로 대응시킨다"
# tests/books/test_service.py는 있지만 tests/music/에는 없다. 이름만 보면 통과해 버린다.
expect deny  "$P/app/music/service.py"            "다른 기능 폴더의 test_service.py는 세지 않는다"
expect deny  "$P/app/books/serv.py"               "test_service.py는 serv.py의 테스트가 아니다"
: >"$P/tests/music/test_services.py"
expect deny  "$P/app/music/service.py"            "test_services.py는 service.py의 테스트가 아니다"
: >"$P/tests/music/test_service.py"
expect allow "$P/app/music/service.py"            "테스트를 만들면 통과한다"

echo "선언과 조립"
expect allow "$P/app/books/__init__.py"           "__init__.py"
expect allow "$P/app/__init__.py"                 "app/__init__.py"
expect allow "$P/app/main.py"                     "조립 지점"
expect allow "$P/app/music/models.py"             "테이블 선언"
expect allow "$P/app/music/schemas.py"            "요청·응답 형식 선언"
expect allow "$P/app/core/config.py"              "설정 클래스"
expect allow "$P/app/core/ports.py"               "포트 선언"
expect allow "$P/app/core/ports/storage.py"       "포트 선언 폴더"
expect allow "$P/app/core/database.py"            "엔진 조립"
expect deny  "$P/app/music/main.py"               "main.py 예외는 app/main.py뿐이다"
expect deny  "$P/app/music/config.py"             "config.py 예외는 app/core/config.py뿐이다"

echo "app/ 밖"
expect allow "$P/tests/music/test_router.py"      "테스트 파일 자신"
expect allow "$P/tests/conftest.py"               "conftest"
expect allow "$P/scripts/execute.py"              "scripts/"
expect allow "$P/migrations/versions/0001_init.py" "마이그레이션"
expect allow "$P/migrations/env.py"               "alembic env"
expect allow "$P/pyproject.toml"                  "설정 파일"
expect allow "$P/docs/API.md"                     "문서"
expect allow "$P/app/books/README.md"             "app/ 안이라도 .py가 아니면 통과"
expect allow "$P/app/books/queries.sql"           "app/ 안의 SQL 파일"

echo "프로젝트 루트"
expect allow "$TMP/noproj/app/books/service.py"   "pyproject.toml이 없으면 막지 않는다"

echo "상대 경로"
if (cd "$P" && printf '{"tool_input":{"file_path":"app/music/router.py"}}' | bash "$GUARD" | grep -q '"deny"'); then
  PASS=$((PASS + 1)); printf '  ok    deny   상대 경로는 현재 폴더 기준으로 푼다\n'
else
  FAIL=$((FAIL + 1)); printf '  FAIL  want=deny got=allow  상대 경로는 현재 폴더 기준으로 푼다\n'
fi

echo "자기 방어 (무인 실행)"
expect deny  "$P/scripts/hooks/tdd-guard.sh"      "무인 실행은 가드를 고칠 수 없다" 1
expect deny  "$P/scripts/hooks/bash-guard.sh"     "다른 가드도" 1
expect deny  "$P/scripts/hooks/stop-check.sh"     "Stop 훅도" 1
expect deny  "$P/scripts/check.sh"                "검사 스크립트도" 1
expect deny  "$P/.claude/settings.json"           "훅 배선도" 1
expect deny  "$P/.claude/settings.local.json"     "개인 설정으로 훅을 끄는 길도" 1
expect allow "$P/scripts/execute.py"              "무인 실행이라도 다른 스크립트는 통과" 1
expect allow "$P/pyproject.toml"                  "의존성을 넣어야 하므로 pyproject.toml은 통과" 1
expect allow "$P/scripts/hooks/tdd-guard.sh"      "대화형 세션은 가드를 고칠 수 있다"
expect allow "$P/.claude/settings.json"           "대화형 세션은 훅 배선을 고칠 수 있다"
expect allow "$P/app/books/service.py"            "무인 실행이라도 테스트가 있으면 통과" 1
expect deny  "$P/app/adapters/storage.py"         "무인 실행에서도 테스트 없는 로직은 막는다" 1

echo "차단 문구"
MSG=$(printf '{"tool_input":{"file_path":"%s"}}' "$P/app/adapters/storage.py" | bash "$GUARD")
case "$MSG" in
  *"tests/adapters/test_storage.py"*) PASS=$((PASS + 1)); printf '  ok           기대 위치를 알려 준다\n' ;;
  *) FAIL=$((FAIL + 1)); printf '  FAIL  기대 위치가 문구에 없다\n' ;;
esac
case "$MSG" in
  *"가드를 고치지 마라"*"blocked"*) PASS=$((PASS + 1)); printf '  ok           가드를 고치라고 시키지 않는다\n' ;;
  *) FAIL=$((FAIL + 1)); printf '  FAIL  blocked로 세우라는 문구가 없다\n' ;;
esac
if printf '%s' "$MSG" | python3 -c 'import json,sys; json.load(sys.stdin)' 2>/dev/null; then
  PASS=$((PASS + 1)); printf '  ok           출력이 올바른 JSON이다\n'
else
  FAIL=$((FAIL + 1)); printf '  FAIL  출력이 JSON으로 읽히지 않는다\n'
fi

echo "입력"
if echo '{}' | bash "$GUARD" | grep -q '"deny"'; then
  FAIL=$((FAIL + 1)); printf '  FAIL  want=allow got=deny  file_path 없는 입력\n'
else
  PASS=$((PASS + 1)); printf '  ok    allow  file_path 없는 입력\n'
fi
if printf '' | bash "$GUARD" | grep -q '"deny"'; then
  FAIL=$((FAIL + 1)); printf '  FAIL  want=allow got=deny  빈 입력\n'
else
  PASS=$((PASS + 1)); printf '  ok    allow  빈 입력\n'
fi

printf '\n통과 %d · 실패 %d\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
