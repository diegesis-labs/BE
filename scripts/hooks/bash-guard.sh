#!/usr/bin/env bash
# Bash Guard — PreToolUse[Bash]
# OnlineFourCut의 scripts/hooks/bash-guard.sh를 옮긴 것이다. 주석의 Epic 번호는 원본 프로젝트의 사례다.
# 이 레포에서 더한 것은 5번 이후의 규칙(Docker, Alembic, PostgreSQL, git clean)과
# 헤드리스 세션의 push·PR·이미지 push 금지다.
# 되돌릴 수 없는 명령을 막는다. 하네스가 --dangerously-skip-permissions로 돌기 때문에
# 사람이 확인할 기회가 없고, 이 훅이 유일한 방어선이다.
#
# 이전 버전(.claude/settings.json 인라인)이 아무것도 막지 못한 이유 둘.
#   1. $CLAUDE_TOOL_INPUT을 읽었다. 훅은 stdin으로 JSON을 받으므로 늘 빈 문자열이었고
#      빈 문자열을 grep해서 항상 통과했다.
#   2. exit 1로 끝냈다. PreToolUse에서 1은 차단이 아니라 '비차단 오류'다.
#      차단은 permissionDecision: "deny"를 JSON으로 돌려주는 것이다 (tdd-guard.sh와 같다).

INPUT=$(cat)

# --- 입력 파싱. jq → python3 순으로 쓰고, 둘 다 없으면 막지 않는다(fail-open) ---
if command -v jq >/dev/null 2>&1; then
  CMD=$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty')
  BG=$(printf '%s' "$INPUT" | jq -r '.tool_input.run_in_background // false')
elif command -v python3 >/dev/null 2>&1; then
  CMD=$(printf '%s' "$INPUT" | python3 -c '
import json, sys
try:
    sys.stdout.write((json.load(sys.stdin).get("tool_input") or {}).get("command") or "")
except Exception:
    pass
')
  BG=$(printf '%s' "$INPUT" | python3 -c '
import json, sys
try:
    bg = (json.load(sys.stdin).get("tool_input") or {}).get("run_in_background") is True
except Exception:
    bg = False
sys.stdout.write("true" if bg else "false")
')
else
  exit 0
fi

# --- 0. 하네스 세션의 백그라운드 실행 ---
# 헤드리스(claude -p)에선 턴이 끝나면 세션도 끝난다. 백그라운드로 띄우고 완료 알림을
# 기다리는 마무리는 그 알림을 받을 주체가 없다 — Epic 5 step 17이 정확히 이걸로 3회를
# 태웠고(e2e를 백그라운드로 걸고 "알림 오면 갱신하겠다"며 종료), 리뷰 세션도 같은 병으로
# 죽었다(HARNESS_REVIEW — "실측이 끝날 때까지 대기"). 대화형 세션은 막지 않는다.
if { [ "${HARNESS_RUN:-}" = "1" ] || [ "${HARNESS_REVIEW:-}" = "1" ]; } && [ "$BG" = "true" ]; then
  cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "HARNESS GUARD: 헤드리스 세션에서 백그라운드 실행은 금지다. 턴을 끝내는 순간 세션이 종료되어 완료 알림을 받을 주체가 없다. 같은 명령을 run_in_background 없이 포그라운드로(timeout을 넉넉히 잡고) 완주하고, 같은 턴 안에서 AC 검증과 index.json status 갱신까지 끝내라."
  }
}
EOF
  exit 0
fi

[ -n "$CMD" ] || exit 0

deny() {
  cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "BASH GUARD: $1 이 명령은 되돌릴 수 없다. 실행하지 말고 무엇을 하려 했는지 사람에게 알려라. 정말 필요하면 사람이 직접 실행한다."
  }
}
EOF
  exit 0
}

has() { printf '%s' "$CMD" | grep -qE "$1"; }

HEADLESS=""
if [ "${HARNESS_RUN:-}" = "1" ] || [ "${HARNESS_REVIEW:-}" = "1" ]; then
  HEADLESS=1
fi

# --- 0-1. 헤드리스 세션이 레포 밖에 보이는 행동을 하는 것 ---
# push는 execute.py가(--push), PR은 사람이 부르는 harness-pr.sh가 한다. 무인 세션이
# 스스로 올리거나 PR·이슈를 열 이유가 없고, 한번 나간 것은 되돌려도 흔적이 남는다.
# 대화형 세션은 막지 않는다.
if [ -n "$HEADLESS" ]; then
  if has '(^|[^[:alnum:]_])git[[:space:]]+push([[:space:]]|$)'; then
    deny "헤드리스 세션은 push하지 않는다(git push). 커밋까지만 해라."
  fi
  if has '(^|[^[:alnum:]_])gh[[:space:]]+(pr[[:space:]]+(create|edit|merge|close)|issue[[:space:]]+(create|close)|release[[:space:]]+create)([[:space:]]|$)'; then
    deny "헤드리스 세션은 PR·이슈·릴리스를 만들거나 고치거나 닫지 않는다(gh)."
  fi
  # 컨테이너 이미지는 main에 합쳐진 코드만 CI가 올린다(docs/DECISIONS.md D-36). Docker Hub
  # 저장소가 공개라서 한번 올라간 이미지는 누구나 받아 간다(D-37). 로그인도 막는다 — 무인
  # 세션에 레지스트리 자격 증명이 남을 이유가 없다.
  #
  # 이 규칙은 에이전트의 실수를 막는 장치이며, 일부러 피해 가는 명령까지 막지는 않는다. 알고 둔 한계 둘.
  #   - 놓치는 것: 절대 경로(/usr/local/bin/docker push), docker 뒤의 전역 옵션(--context, -H,
  #     --config), compose build --push, buildx bake --push, manifest push, imagetools create.
  #     이것들까지 막으려고 경계를 넓히면 아래의 오탐이 함께 늘어난다.
  #   - 오탐: 명령 문자열 전체를 보므로 커밋 메시지나 echo 안의 'docker push' 낱말에도 막힌다.
  #     4번의 DROP과 같은 이유로 받아들인다. 따옴표 안팎을 가르려면 셸을 파싱해야 하고, 그 틈으로
  #     'bash -c "docker push …"' 같은 진짜 명령이 샌다. 막히면 그 낱말을 쓰지 않고 다시 적는다.
  # (0-project-setup 1차 리뷰 COR-10 · SEC-1, 사람이 기록만 하기로 정했다)
  if has '(^|[^[:alnum:]_./-])docker[[:space:]]+(image[[:space:]]+)?push([[:space:]]|$)' \
    || has '(^|[^[:alnum:]_./-])docker[[:space:]]+login([[:space:]]|$)' \
    || has '(^|[^[:alnum:]_./-])docker([[:space:]]+|-)compose[[:space:]]+([^;&|]*[[:space:]])?push([[:space:]]|$)' \
    || { has '(^|[^[:alnum:]_./-])docker[[:space:]]+(buildx[[:space:]]+)?build([[:space:]]|$)' \
      && has '(^|[[:space:]])--push([[:space:]=]|$)'; }; then
    deny "헤드리스 세션은 컨테이너 이미지를 레지스트리에 올리거나 로그인하지 않는다(docker push, docker login, --push). 이미지는 main에 합쳐진 코드만 CI가 올린다."
  fi
fi

# --- 1. rm — 재귀와 강제가 함께 걸린 것만 ---
# 'rm -f file' 하나나 'rm -r dir' 하나는 막지 않는다. 둘이 겹칠 때가 사고다.
# 'uv run format ...' 같은 낱말 속의 rm은 단어 경계로 걸러진다.
if has '(^|[^[:alnum:]_./-])rm([^[:alnum:]_]|$)' \
  && has '(^|[[:space:]])(-[[:alnum:]]*[rR]|--recursive)' \
  && has '(^|[[:space:]])(-[[:alnum:]]*f|--force)'; then
  deny "재귀 강제 삭제(rm -rf)다."
fi

# --- 2. git push --force / -f ---
# --force-with-lease도 함께 막는다. 더 안전한 쪽이지만 원격 이력을 바꾸는 것은 같다.
if has '(^|[^[:alnum:]_])git[[:space:]]+push([[:space:]]|$)' \
  && has '(^|[[:space:]])(--force|-[[:alnum:]]*f)'; then
  deny "원격 이력을 덮어쓴다(git push --force)."
fi

# --- 3. git reset --hard ---
if has '(^|[^[:alnum:]_])git[[:space:]]+reset([[:space:]]|$)' \
  && has '(^|[[:space:]])--hard'; then
  deny "작업 내용이 사라진다(git reset --hard)."
fi

# --- 4. DROP TABLE / DATABASE / SCHEMA, dropdb ---
# 명령 문자열 전체를 보므로 이 문구가 든 grep이나 커밋 메시지도 막힌다. 알고 둔 한계다 —
# 따옴표 안팎을 가르려면 셸을 파싱해야 하고, 그 틈으로 진짜 명령이 샌다.
if has '[Dd][Rr][Oo][Pp][[:space:]]+([Tt][Aa][Bb][Ll][Ee]|[Dd][Aa][Tt][Aa][Bb][Aa][Ss][Ee]|[Ss][Cc][Hh][Ee][Mm][Aa])'; then
  deny "테이블·데이터베이스·스키마를 지운다(DROP)."
fi
if has '(^|[^[:alnum:]_./-])dropdb([[:space:]]|$)'; then
  deny "데이터베이스를 지운다(dropdb)."
fi

# --- 5. TRUNCATE — psql과 함께 쓰일 때만 ---
# coreutils의 `truncate -s 0 file`과 일반 문장을 막지 않으려고 psql을 조건에 넣는다.
# 평가 기록이 사라지는 것은 이 제품의 실패 조건이다(docs/ARCHITECTURE.md 1절).
if has '(^|[^[:alnum:]_./-])psql([[:space:]]|$)' && has '[Tt][Rr][Uu][Nn][Cc][Aa][Tt][Ee][[:space:]]'; then
  deny "테이블의 행을 모두 지운다(TRUNCATE)."
fi

# --- 6. Docker 볼륨 ---
# `docker compose down`만으로는 볼륨이 남는다. -v가 붙을 때 로컬 DB가 통째로 사라진다.
if has '(^|[^[:alnum:]_./-])docker([[:space:]]+|-)compose[[:space:]]+([^;&|]*[[:space:]])?down([[:space:]]|$)' \
  && has '(^|[[:space:]])(-[[:alnum:]]*v[[:alnum:]]*|--volumes)([[:space:]]|$)'; then
  deny "컨테이너와 함께 볼륨을 지운다(docker compose down -v)."
fi
if has '(^|[^[:alnum:]_./-])docker[[:space:]]+volume[[:space:]]+(rm|prune)([[:space:]]|$)'; then
  deny "Docker 볼륨을 지운다(docker volume rm/prune)."
fi
if has '(^|[^[:alnum:]_./-])docker[[:space:]]+system[[:space:]]+prune([[:space:]]|$)'; then
  deny "쓰지 않는 Docker 자원을 모두 지운다(docker system prune)."
fi

# --- 7. alembic downgrade base ---
# 한 단계 되돌리기(-1)는 마이그레이션을 다듬을 때 늘 쓰므로 막지 않는다. base는 스키마 전체를 지운다.
if has '(^|[^[:alnum:]_./-])alembic[[:space:]]+([^;&|]*[[:space:]])?downgrade[[:space:]]+([^;&|]*[[:space:]])?base([[:space:]]|$)'; then
  deny "스키마 전체를 되돌린다(alembic downgrade base)."
fi

# --- 8. git clean -f ---
# 추적하지 않는 파일을 지운다. -x가 붙으면 .env와 var/(음원, 묶음)까지 사라진다.
if has '(^|[^[:alnum:]_])git[[:space:]]+clean([[:space:]]|$)' \
  && has '(^|[[:space:]])(-[[:alnum:]]*f[[:alnum:]]*|--force)([[:space:]]|$)'; then
  deny "추적하지 않는 파일을 지운다(git clean -f)."
fi

exit 0
