#!/usr/bin/env bash
# docker compose로 데이터베이스, 마이그레이션, 서버를 실제로 띄워서 가장 기본적인 동작을 확인하고 내린다.
# 확인하는 것은 docs/backlog/epic-0/testcase.md의 TC-0.5.1 다섯 가지다. 하나라도 어긋나면 무엇이
# 어긋났는지와 compose 로그의 끝부분을 찍고 0이 아닌 코드로 끝난다.
#
#   scripts/compose-smoke.sh     인자를 받지 않는다.
#
# 이미지를 빌드하느라 몇 분이 걸리므로 scripts/check.sh에는 넣지 않았다. 언제 돌리는지는
# docs/DEVELOPMENT.md 2절에 있다.
#
# - 프로젝트 이름은 아래의 상수 하나로 고정하며, 환경변수나 인자로 바꿀 수 없다. 끝날 때 볼륨까지
#   지우므로, 다른 이름으로 돌면 개발용으로 띄워 둔 compose의 데이터베이스 볼륨이 지워진다.
#   compose는 -p로 넘긴 이름을 COMPOSE_PROJECT_NAME보다 먼저 쓴다.
# - 이미지는 compose로만 빌드한다(docs/DECISIONS.md의 D-41).
# - 호스트 포트는 0으로 넘겨 Docker가 비어 있는 포트를 고르게 한다. 개발용 compose와 부딪히지 않는다.
# - 개발자의 `.env`를 compose의 변수로 읽지 않는다(--env-file /dev/null). 그 안의 값이 스모크를
#   바꾸지 못하게 하기 위해서다.
# - macOS(bash 3.2, BSD 도구)와 Linux(GNU 도구)에서 모두 돈다. sed -i, date, mktemp, stat처럼
#   둘의 동작이 다른 명령을 쓰지 않는다.

set -euo pipefail

readonly PROJECT="diegesis-smoke"

if [ "$#" -ne 0 ]; then
  echo "사용법: scripts/compose-smoke.sh" >&2
  echo "인자를 받지 않는다. 프로젝트 이름은 ${PROJECT}로 고정되어 있다." >&2
  exit 64
fi

cd "$(dirname "$0")/.."

# compose.yaml의 db 서비스에 적힌 로컬 전용 계정이다.
readonly DB_USER="diegesis"
readonly DB_NAME="diegesis"
readonly VECTOR_QUERY="SELECT extversion FROM pg_extension WHERE extname = 'vector'"
readonly HEALTH_BODY='{"status":"ok"}'

export API_PORT=0
export DB_PORT=0

compose() {
  docker compose -p "$PROJECT" -f compose.yaml --env-file /dev/null "$@"
}

fail() {
  echo "스모크 실패: $1" >&2
  exit 1
}

ok() {
  echo "확인: $1"
}

cleanup() {
  local status=$?
  trap - EXIT
  if [ "$status" -ne 0 ]; then
    echo >&2
    echo "=== 컨테이너 상태" >&2
    compose ps --all >&2 || true
    echo "=== compose 로그(끝부분)" >&2
    compose logs --no-color --tail 60 >&2 || true
  fi
  echo "=== ${PROJECT} 프로젝트를 볼륨까지 내린다"
  if ! compose down --volumes --remove-orphans --rmi local >/dev/null 2>&1; then
    echo "경고: ${PROJECT}를 내리지 못했다. 'docker compose -p ${PROJECT} down --volumes'로 직접 내려라." >&2
  fi
  exit "$status"
}

command -v docker >/dev/null 2>&1 || fail "docker 명령을 찾을 수 없다"
command -v curl >/dev/null 2>&1 || fail "curl 명령을 찾을 수 없다"
docker info >/dev/null 2>&1 || fail "Docker에 닿을 수 없다. Docker Desktop을 켠 뒤 다시 실행해라"

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# 지난 실행이 중간에 끊겨 남은 컨테이너와 볼륨을 지운다. 남은 볼륨에 마이그레이션이 이미 적용되어
# 있으면, 이번 마이그레이션이 아무 일도 하지 않고 성공해서 확인이 약해진다.
compose down --volumes --remove-orphans >/dev/null 2>&1 || true

echo "=== 이미지를 빌드하고 db, migrate, api를 띄운다"
up_status=0
compose up --build --detach --wait --wait-timeout 300 || up_status=$?

# (1) migrate가 종료 코드 0으로 끝났다.
migrate_id=$(compose ps --all --quiet migrate 2>/dev/null || true)
if [ -z "$migrate_id" ]; then
  fail "(1) migrate 컨테이너가 만들어지지 않았다. compose up이 종료 코드 ${up_status}로 끝났다(이미지 빌드나 db의 준비에서 멈췄을 수 있다)"
fi
migrate_state=$(docker inspect --format '{{.State.Status}} {{.State.ExitCode}}' "$migrate_id") \
  || fail "(1) migrate 컨테이너의 상태를 읽지 못했다"
[ "$migrate_state" = "exited 0" ] \
  || fail "(1) migrate가 종료 코드 0으로 끝나지 않았다(상태와 종료 코드: ${migrate_state})"
ok "(1) migrate가 종료 코드 0으로 끝났다"

[ "$up_status" -eq 0 ] \
  || fail "compose up이 종료 코드 ${up_status}로 끝났다. api가 healthy가 되지 못했을 수 있다"

# (2) 데이터베이스에 vector 확장이 있다. 서버 이미지로 실행한 마이그레이션이 데이터베이스에 닿았다는
# 증거다. /api/health는 데이터베이스를 보지 않는다(docs/DECISIONS.md의 D-39).
vector_version=$(compose exec -T db psql -U "$DB_USER" -d "$DB_NAME" -tAc "$VECTOR_QUERY") \
  || fail "(2) db에 질의하지 못했다"
[ -n "$vector_version" ] || fail "(2) 데이터베이스에 vector 확장이 없다"
ok "(2) 데이터베이스에 vector 확장이 있다(버전 ${vector_version})"

# (3) 호스트에서 요청한 /api/health가 정확히 {"status":"ok"}이다.
api_address=$(compose port api 8080) || fail "(3) api의 호스트 포트를 알아내지 못했다"
api_address=${api_address%%$'\n'*}
api_port=${api_address##*:}
case "$api_port" in
  '' | *[!0-9]*) fail "(3) api의 호스트 포트를 알아내지 못했다(${api_address})" ;;
esac
health_body=$(curl --silent --show-error --fail --max-time 10 "http://127.0.0.1:${api_port}/api/health") \
  || fail "(3) 호스트에서 /api/health를 요청하지 못했다(포트 ${api_port})"
[ "$health_body" = "$HEALTH_BODY" ] \
  || fail "(3) /api/health의 본문이 ${HEALTH_BODY}가 아니다: ${health_body}"
ok "(3) 호스트에서 요청한 /api/health가 ${HEALTH_BODY}이다"

# (4) api 컨테이너의 프로세스가 root가 아니다. 서버 프로세스(PID 1)의 실제, 유효, 저장, 파일시스템
# uid를 모두 본다.
api_uids=$(compose exec -T api python -c 'print(*open("/proc/1/status").read().split("Uid:")[1].split()[:4])') \
  || fail "(4) api 컨테이너의 프로세스 uid를 읽지 못했다"
[ -n "$api_uids" ] || fail "(4) api 컨테이너의 프로세스 uid를 읽지 못했다"
for uid in $api_uids; do
  [ "$uid" != "0" ] || fail "(4) api 컨테이너의 프로세스가 root로 돈다(Uid: ${api_uids})"
done
ok "(4) api 컨테이너의 프로세스가 root가 아니다(Uid: ${api_uids})"

# (5) api 이미지 안의 작업 폴더에 .env 파일이 없다.
api_workdir=$(compose exec -T api pwd) || fail "(5) api 컨테이너의 작업 폴더를 읽지 못했다"
env_present=$(compose exec -T api python -c 'import os; print("yes" if os.path.lexists(".env") else "no")') \
  || fail "(5) api 컨테이너에서 .env 파일을 확인하지 못했다"
[ "$env_present" = "no" ] || fail "(5) api 이미지의 작업 폴더(${api_workdir})에 .env 파일이 있다"
ok "(5) api 이미지의 작업 폴더(${api_workdir})에 .env 파일이 없다"

echo "스모크 통과: 다섯 가지를 모두 확인했다"
