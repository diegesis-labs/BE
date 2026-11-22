#!/usr/bin/env bash
# 이 레포의 검사 명령을 한 곳에 모은다. Stop 훅, step의 AC, 리뷰의 실측이 모두 이것을 부른다.
# 명령을 여러 곳에 적으면 한 곳만 바뀌어 기준이 갈라진다.
#
#   scripts/check.sh         첫 실패에서 멈춘다. 종료 코드는 실패한 명령의 것이다.
#   scripts/check.sh --all   넷을 다 돌리고 명령별 종료 코드를 한 줄씩 찍는다. 하나라도 실패하면 1.
#
# pytest가 테스트를 하나도 수집하지 못하면 종료 코드 5를 낸다. 이것을 통과로 바꾸지 않는다.
# "0개를 수집해도 초록"은 검사가 꺼진 것을 숨긴다.

set -u

cd "$(dirname "$0")/.." || exit 1

NAMES=("ruff check" "ruff format --check" "pyright" "pytest")

run_one() {
  case "$1" in
    0) uv run ruff check . ;;
    1) uv run ruff format --check . ;;
    2) uv run pyright ;;
    3) uv run pytest ;;
  esac
}

if [ "${1:-}" = "--all" ]; then
  codes=()
  for i in 0 1 2 3; do
    echo "=== ${NAMES[$i]}"
    run_one "$i"
    codes+=("$?")
  done
  echo
  echo "=== 요약"
  failed=0
  for i in 0 1 2 3; do
    echo "${NAMES[$i]}: exit ${codes[$i]}"
    [ "${codes[$i]}" = "0" ] || failed=1
  done
  exit "$failed"
fi

if [ -n "${1:-}" ]; then
  echo "사용법: scripts/check.sh [--all]" >&2
  exit 64
fi

for i in 0 1 2 3; do
  echo "=== ${NAMES[$i]}"
  run_one "$i" || exit "$?"
done
