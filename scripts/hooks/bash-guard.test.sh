#!/usr/bin/env bash
# bash-guard.sh 검증. 통과/실패 수를 찍고 하나라도 실패하면 1로 끝난다.
#   실행: bash scripts/hooks/bash-guard.test.sh
set -u

GUARD="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/bash-guard.sh"
PASS=0
FAIL=0

expect() { # expect <allow|deny> <command> <설명>
  local want="$1" cmd="$2" label="$3" got
  if printf '%s' "$cmd" \
    | python3 -c 'import json,sys; print(json.dumps({"tool_input":{"command":sys.stdin.read()}}))' \
    | bash "$GUARD" | grep -q '"deny"'; then
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

echo "rm"
expect deny  'rm -rf /tmp/x'                  "rm -rf"
expect deny  'rm -fr /tmp/x'                  "플래그 순서가 뒤집혀도"
expect deny  'rm -Rf /tmp/x'                  "대문자 R"
expect deny  'rm -r -f /tmp/x'                "플래그가 갈라져도"
expect deny  'rm --recursive --force /tmp/x'  "긴 플래그"
expect deny  'sudo rm -rf ~/Library'          "sudo가 앞에 붙어도"
expect deny  'cd /tmp && rm -rf x'            "다른 명령 뒤에 붙어도"
expect allow 'rm file.txt'                    "그냥 삭제"
expect allow 'rm -f file.txt'                 "강제만"
expect allow 'rm -r build'                    "재귀만"
expect allow 'uv run ruff format .'           "낱말 속의 rm은 rm이 아니다"
expect allow 'grep -rf pattern src/'          "rm 명령이 없다"

echo "git"
expect deny  'git push --force origin main'   "force push"
expect deny  'git push -f'                    "짧은 플래그"
expect deny  'git push --force-with-lease'    "force-with-lease도 이력을 바꾼다"
expect deny  'git reset --hard HEAD~1'        "reset --hard"
expect allow 'git push origin main'           "보통 push"
expect allow 'git push -u origin feat-x'      "-u는 force가 아니다"
expect allow 'git reset --soft HEAD~1'        "reset --soft"
expect allow 'git reset HEAD -- file'         "스테이지 해제"
expect allow 'git status --short'             "읽기"

echo "SQL"
expect deny  'psql -c "DROP TABLE users"'     "DROP TABLE"
expect deny  'sqlite3 f.db "drop table x"'    "소문자"
expect allow 'sqlite3 f.db "select * from x"' "조회"
expect deny  'psql -c "DROP DATABASE diegesis"'        "DROP DATABASE"
expect deny  'psql -c "drop schema public cascade"'    "DROP SCHEMA"
expect deny  'dropdb diegesis'                         "dropdb"
expect deny  'psql -c "TRUNCATE recommendation_logs"'  "psql의 TRUNCATE"
expect deny  'psql -d x -c "truncate table plays"'     "소문자 truncate"
expect allow 'truncate -s 0 app.log'                   "coreutils truncate는 SQL이 아니다"
expect allow 'psql -c "select count(*) from plays"'    "psql 조회"
expect deny  'grep -r "DROP TABLE" migrations/'        "알려진 한계 — 문구가 든 검색도 막힌다"

echo "docker"
expect deny  'docker compose down -v'                  "compose down -v"
expect deny  'docker compose down --volumes'           "긴 플래그"
expect deny  'docker compose -f compose.yml down -v'   "-f가 끼어도"
expect deny  'docker-compose down -v'                  "하이픈 표기"
expect deny  'docker volume rm be_pgdata'              "volume rm"
expect deny  'docker volume prune -f'                  "volume prune"
expect deny  'docker system prune -af'                 "system prune"
expect allow 'docker compose down'                     "볼륨은 남는다"
expect allow 'docker compose up -d'                    "띄우기"
expect allow 'docker compose logs -f db'               "로그"
expect allow 'docker volume ls'                        "목록"
expect allow 'docker compose down && docker compose up -d' "다시 띄우기"

echo "alembic"
expect deny  'uv run alembic downgrade base'           "downgrade base"
expect deny  'alembic -c alembic.ini downgrade base'   "옵션이 끼어도"
expect allow 'uv run alembic downgrade -1'             "한 단계 되돌리기"
expect allow 'uv run alembic upgrade head'             "올리기"
expect allow 'uv run alembic revision -m "base tables"' "메시지에 base가 있을 뿐이다"

echo "git clean"
expect deny  'git clean -fdx'                          "clean -fdx"
expect deny  'git clean -f'                            "clean -f"
expect deny  'git clean --force -d'                    "긴 플래그"
expect allow 'git clean -n'                            "미리 보기"

echo "background (HARNESS_RUN)"
bg_json() { # bg_json <true|false>
  python3 -c "import json,sys;print(json.dumps({'tool_input':{'command':'uv run pytest','run_in_background':sys.argv[1]=='true'}}))" "$1"
}
expect_env() { # expect_env <allow|deny> <bg> <HARNESS_RUN값('' = 미설정)> <설명>
  local want="$1" bg="$2" hr="$3" label="$4" got
  if bg_json "$bg" | HARNESS_RUN="$hr" bash "$GUARD" | grep -q '"deny"'; then got=deny; else got=allow; fi
  if [ "$got" = "$want" ]; then
    PASS=$((PASS + 1)); printf '  ok    %-5s  %s\n' "$want" "$label"
  else
    FAIL=$((FAIL + 1)); printf '  FAIL  want=%s got=%s  %s\n' "$want" "$got" "$label"
  fi
}
expect_env deny  true  1  "하네스에서 백그라운드는 막는다 — 알림 받을 턴이 없다"
expect_env allow true  '' "대화형 세션의 백그라운드는 막지 않는다"
expect_env allow false 1  "하네스라도 포그라운드는 통과"
if bg_json true | HARNESS_RUN='' HARNESS_REVIEW=1 bash "$GUARD" | grep -q '"deny"'; then
  PASS=$((PASS + 1)); printf '  ok    deny   리뷰 세션(HARNESS_REVIEW)도 헤드리스다\n'
else
  FAIL=$((FAIL + 1)); printf '  FAIL  want=deny got=allow  리뷰 세션(HARNESS_REVIEW)도 헤드리스다\n'
fi

echo "헤드리스 세션의 push와 gh"
expect_cmd_env() { # expect_cmd_env <allow|deny> <command> <환경 "K=V"> <설명>
  local want="$1" cmd="$2" envs="$3" label="$4" got
  if printf '%s' "$cmd" \
    | python3 -c 'import json,sys; print(json.dumps({"tool_input":{"command":sys.stdin.read()}}))' \
    | env $envs bash "$GUARD" | grep -q '"deny"'; then
    got=deny
  else
    got=allow
  fi
  if [ "$got" = "$want" ]; then
    PASS=$((PASS + 1)); printf '  ok    %-5s  %s\n' "$want" "$label"
  else
    FAIL=$((FAIL + 1)); printf '  FAIL  want=%s got=%s  %s\n' "$want" "$got" "$label"
  fi
}
expect_cmd_env deny  'git push -u origin feat-x'      HARNESS_RUN=1    "무인 step 세션은 push하지 않는다"
expect_cmd_env deny  'git push'                       HARNESS_REVIEW=1 "리뷰 세션도"
expect_cmd_env deny  'gh pr create --fill'            HARNESS_RUN=1    "PR 생성"
expect_cmd_env deny  'gh pr merge 3 --merge'          HARNESS_RUN=1    "PR 머지"
expect_cmd_env deny  'gh issue create -t x'           HARNESS_RUN=1    "이슈 생성"
expect_cmd_env allow 'gh pr view 3'                   HARNESS_RUN=1    "읽기는 통과"
expect_cmd_env allow 'gh issue view 1'                HARNESS_RUN=1    "이슈 읽기"
expect_cmd_env allow 'git commit -m "push 로직 추가"' HARNESS_RUN=1    "커밋 메시지의 push는 git push가 아니다"
expect_cmd_env allow 'git push -u origin feat-x'      HARNESS_RUN=     "대화형 세션의 push는 통과"
expect_cmd_env allow 'gh pr create --fill'            HARNESS_RUN=     "대화형 세션의 PR 생성은 통과"

echo "jq가 없을 때"
NOJQ=$(mktemp -d)
for tool in bash cat grep python3 printf; do
  src="$(command -v "$tool")" && ln -s "$src" "$NOJQ/$tool" 2>/dev/null
done
if printf '{"tool_input":{"command":"rm -rf /tmp/x"}}' | PATH="$NOJQ" bash "$GUARD" | grep -q '"deny"'; then
  PASS=$((PASS + 1)); printf '  ok    deny   python3로 파싱해도 막는다\n'
else
  FAIL=$((FAIL + 1)); printf '  FAIL  want=deny got=allow  python3로 파싱해도 막는다\n'
fi
if printf '{"tool_input":{"command":"uv run pytest","run_in_background":true}}' | PATH="$NOJQ" HARNESS_RUN=1 bash "$GUARD" | grep -q '"deny"'; then
  PASS=$((PASS + 1)); printf '  ok    deny   python3로 파싱해도 백그라운드를 막는다\n'
else
  FAIL=$((FAIL + 1)); printf '  FAIL  want=deny got=allow  python3로 파싱해도 백그라운드를 막는다\n'
fi
rm -rf "$NOJQ"

echo "입력"
if echo '{}' | bash "$GUARD" | grep -q '"deny"'; then
  FAIL=$((FAIL + 1)); printf '  FAIL  want=allow got=deny  command 없는 입력\n'
else
  PASS=$((PASS + 1)); printf '  ok    allow  command 없는 입력\n'
fi
if printf '' | bash "$GUARD" | grep -q '"deny"'; then
  FAIL=$((FAIL + 1)); printf '  FAIL  want=allow got=deny  빈 입력\n'
else
  PASS=$((PASS + 1)); printf '  ok    allow  빈 입력\n'
fi

printf '\n통과 %d · 실패 %d\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
