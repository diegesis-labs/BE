#!/usr/bin/env bash
# harness-pr.sh 검증. 통과/실패 수를 찍고 하나라도 실패하면 1로 끝난다.
#   실행: bash scripts/harness-pr.test.sh
#
# 이 스크립트가 틀리면 두 가지로 샌다. 관문이 느슨하면 리뷰가 닫히지 않은 코드가 PR로 나가고,
# 드라이런이 새면 사람이 승인하기 전에 push와 PR이 나간다. 둘 다 되돌려도 흔적이 남는다.
set -u

# 이 테스트가 무인 세션 안에서 돌면 그 세션의 HARNESS_* 변수를 물려받는다. 그러면 가드가
# "헤드리스다"로 판정해 테스트의 기대와 어긋난다. 필요한 변수는 경우마다 직접 넣는다.
unset HARNESS_RUN HARNESS_REVIEW HARNESS_FIX HARNESS_MODEL HARNESS_MAX_REVIEW_ROUNDS HARNESS_CHECK_CMD

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

lacks() { # lacks <설명> <없어야 할 문구> <본문>
  case "$3" in
    *"$2"*) FAIL=$((FAIL + 1)); printf '  FAIL  %s — [%s]가 있다\n' "$1" "$2" ;;
    *) PASS=$((PASS + 1)); printf '  ok    %s\n' "$1" ;;
  esac
}

# 가짜 gh. 받은 인자와 본문 파일의 내용을 기록한다.
STUB_BIN="$TMP/bin"
mkdir -p "$STUB_BIN"
cat >"$STUB_BIN/gh" <<'STUB'
#!/usr/bin/env bash
echo "gh $*" >>"$GH_LOG"
prev=""
for a in "$@"; do
  [ "$prev" = "--body-file" ] && cat "$a" >"$GH_LOG.body"
  prev="$a"
done
echo "https://example.invalid/pull/1"
STUB
chmod +x "$STUB_BIN/gh"

G() { git -c user.name=t -c user.email=t@t "$@"; }

# 관문을 모두 통과하는 phase를 가진 레포를 만든다. 원격은 옆에 둔 빈 저장소다.
# 각 테스트는 여기서 하나만 어긋나게 만든 뒤 돌린다.
make_repo() { # make_repo <이름> → 레포 경로를 찍는다
  local repo="$TMP/$1" remote="$TMP/$1-remote.git"
  mkdir -p "$repo/scripts" "$repo/phases/3-books/review" "$repo/docs/backlog/epic-3"
  cp "$SCRIPT_DIR/harness-pr.sh" "$repo/scripts/"
  cat >"$repo/phases/3-books/index.json" <<'JSON'
{
  "project": "Diegesis BE",
  "phase": "3-books",
  "completed_at": "2026-12-01T10:00:00+0900",
  "steps": [
    {"step": 0, "name": "books-repository", "status": "completed", "summary": "책과 챕터를 읽는 repository"},
    {"step": 1, "name": "books-router", "status": "completed", "summary": "책 목록과 본문 경로"}
  ]
}
JSON
  cat >"$repo/phases/3-books/MANUAL.md" <<'MD'
# Epic 3 — 사람이 확인하는 점검표

> 안내 문장은 체크 항목이 아니다.

- [x] 본문이 읽기 편한 단위로 끊겨 보인다
  - 테스트로 덮을 수 없는 이유: 읽기 편한지는 사람이 판단한다
  - 관찰한 값: 문단마다 끊긴다
MD
  cat >"$repo/phases/3-books/review/review-1.md" <<'MD'
# Epic 3 코드 리뷰 — 1차

## 종합 판정

| 차원 | critical | major | minor | 판정 |
|---|---|---|---|---|
| **합계** | **0** | **1** | **2** | |

## 실측

여기는 본문에 실리지 않는다.

<!-- verdict: critical=0 major=1 minor=2 -->
MD
  cat >"$repo/phases/3-books/review/fix-1.md" <<'MD'
# 3-books 리뷰 처분 — 1차

> `review-1.md`의 결함 3건에 대한 처분. 2026-12-01.
> 고친 것 3건, 기각 0건, 사람 판단 필요 0건.

<!-- disposition: fixed=3 rejected=0 needs-human=0 -->
MD
  cat >"$repo/phases/3-books/review/review-2.md" <<'MD'
# Epic 3 코드 리뷰 — 2차

## 종합 판정

| 차원 | critical | major | minor | 판정 |
|---|---|---|---|---|
| **합계** | **0** | **0** | **0** | 2차-합계-줄 |

**phase를 닫아도 되는가**: 가능

## 실측

<!-- verdict: critical=0 major=0 minor=0 -->
MD
  cat >"$repo/docs/backlog/epic-3/E3-books.md" <<'MD'
---
title: 책 목록과 챕터 본문
description: 테스트용
---

| 항목 | 값 |
| --- | --- |
| GitHub 이슈 | #12 |
| 마일스톤 | 3주차 |
MD
  : >"$repo/docs/backlog/epic-3/testcase.md"
  (
    cd "$repo" && git init --quiet -b main && G add -A && G commit --quiet -m init &&
      printf -- '- step 0 `books-repository`: 최종-요약-첫-줄\n  - 처분 뒤의 모습\n- step 1 `books-router`: 최종-요약-둘째-줄\n\n<!-- summary-of: %s -->\n' \
        "$(git rev-parse HEAD)" >phases/3-books/summary.md &&
      G add -A && G commit --quiet -m "docs(3-books): 최종 요약" &&
      git init --quiet --bare "$remote" && git remote add origin "$remote" &&
      git checkout --quiet -b feat-3-books
  ) >/dev/null 2>&1
  echo "$repo"
}

commit_all() { (cd "$1" && G add -A && G commit --quiet -m "fixture") >/dev/null 2>&1; }

# 요약의 판독용 줄을 지금의 코드로 고쳐 커밋한다. 픽스처의 phases/ 밖을 고친 경우에 쓴다.
refresh_summary() { # refresh_summary <레포>
  local f="$1/phases/3-books/summary.md" of
  of="$(git -C "$1" log -1 --format=%H -- . ':(exclude)phases')"
  sed -i.bak "s/^<!-- summary-of: .* -->$/<!-- summary-of: $of -->/" "$f" && rm "$f.bak"
  commit_all "$1"
}

# run <레포> <인자...> — 종료 코드를 RC에, 표준 출력을 OUT에, 표준 오류를 ERR에 둔다.
run() {
  local repo="$1"
  shift
  GH_LOG="$TMP/gh.log"
  rm -f "$GH_LOG" "$GH_LOG.body"
  OUT=$(cd "$repo" && PATH="$STUB_BIN:$PATH" GH_LOG="$GH_LOG" \
    HARNESS_CHECK_CMD="${CHECK_CMD:-printf '=== 요약\nruff check: exit 0\npytest: exit 0\n'}" \
    bash scripts/harness-pr.sh "$@" 2>"$TMP/err")
  RC=$?
  ERR=$(cat "$TMP/err")
}

gh_calls() { cat "$TMP/gh.log" 2>/dev/null; }
remote_branches() { git -C "$1-remote.git" branch --format='%(refname:short)' | tr '\n' ' '; }

echo "드라이런"
R="$(make_repo dry)"
run "$R" 3-books
check "관문을 통과하면 0" 0 "$RC"
check "gh를 부르지 않는다" "" "$(gh_calls)"
check "push하지 않는다" "" "$(remote_branches "$R")"
contains "제목은 Epic 문서의 title에서 온다" "제목: feat(3-books): 책 목록과 챕터 본문" "$OUT"
contains "대상 브랜치를 알린다" "feat-3-books → main" "$OUT"
contains "이슈를 닫는 줄이 있다" "Closes #12" "$OUT"
contains "만든 것은 최종 요약을 싣는다" "- step 1 \`books-router\`: 최종-요약-둘째-줄" "$OUT"
contains "최종 요약의 하위 항목도 싣는다" "  - 처분 뒤의 모습" "$OUT"
lacks "처분 전에 쓴 step의 summary는 싣지 않는다" "책 목록과 본문 경로" "$OUT"
lacks "요약의 판독용 줄은 싣지 않는다" "<!-- summary-of" "$OUT"
contains "라운드 수를 싣는다" "2라운드" "$OUT"
contains "마지막 리뷰의 종합 판정을 싣는다" "2차-합계-줄" "$OUT"
lacks "앞 라운드의 판정은 싣지 않는다" "**1** | **2**" "$OUT"
lacks "종합 판정 다음 절은 싣지 않는다" "## 실측" "$OUT"
lacks "기계 판독용 줄은 싣지 않는다" "<!-- verdict" "$OUT"
contains "처분의 머리 요약을 싣는다" "고친 것 3건, 기각 0건, 사람 판단 필요 0건." "$OUT"
contains "사람이 체크한 항목을 싣는다" "- [x] 본문이 읽기 편한 단위로 끊겨 보인다" "$OUT"
lacks "체크 항목이 아닌 안내는 싣지 않는다" "안내 문장은" "$OUT"
contains "검사 결과를 싣는다" "pytest: exit 0" "$OUT"
contains "승인 뒤에 --create를 붙이라고 알린다" "사람의 승인" "$ERR"

echo "생성"
R="$(make_repo create)"
run "$R" 3-books --create
check "0으로 끝난다" 0 "$RC"
check "브랜치를 push한다" "feat-3-books " "$(remote_branches "$R")"
contains "gh pr create를 부른다" "gh pr create --base main --head feat-3-books --title feat(3-books): 책 목록과 챕터 본문 --body-file" "$(gh_calls)"
contains "본문 파일에 이슈를 닫는 줄이 있다" "Closes #12" "$(cat "$TMP/gh.log.body")"
run "$R" 3-books --create --base develop
contains "--base로 대상 브랜치를 바꾼다" "--base develop" "$(gh_calls)"

echo "관문 — 걸리면 push도 PR도 없다"
blocked() { # blocked <설명> <문구> — 직전에 어긋나게 만든 레포 $R을 --create로 돌린다
  run "$R" 3-books --create
  check "$1: 종료 코드 1" 1 "$RC"
  contains "$1: 이유를 알린다" "$2" "$ERR"
  check "$1: gh를 부르지 않는다" "" "$(gh_calls)"
  check "$1: push하지 않는다" "" "$(remote_branches "$R")"
}

R="$(make_repo g-step)"
sed -i.bak 's/"name": "books-router", "status": "completed"/"name": "books-router", "status": "error"/' "$R/phases/3-books/index.json" && rm "$R/phases/3-books/index.json.bak"
commit_all "$R"
blocked "completed가 아닌 step" "books-router"

R="$(make_repo g-manual)"
printf -- '- [ ] 아직 안 본 것\n' >>"$R/phases/3-books/MANUAL.md"
commit_all "$R"
blocked "MANUAL 미확인" "MANUAL.md에 확인 안 된 항목이 1개"

R="$(make_repo g-completed)"
sed -i.bak '/"completed_at"/d' "$R/phases/3-books/index.json" && rm "$R/phases/3-books/index.json.bak"
commit_all "$R"
blocked "완료로 찍히지 않은 phase" "완료로 찍히지 않았다"

R="$(make_repo g-dirty)"
echo "남은 변경" >"$R/untracked.txt"
blocked "커밋되지 않은 변경" "커밋되지 않은 변경"

R="$(make_repo g-branch)"
(cd "$R" && git checkout --quiet -b other) >/dev/null 2>&1
blocked "다른 브랜치" "feat-3-books가 아니다"

R="$(make_repo g-noreview)"
rm "$R/phases/3-books/review/"*.md
commit_all "$R"
blocked "리뷰 리포트 없음" "리뷰 리포트가 없다"

R="$(make_repo g-major)"
rm "$R/phases/3-books/review/review-2.md"
commit_all "$R"
blocked "마지막 리뷰에 major가 남았다" "major 1"

R="$(make_repo g-critical)"
printf '# 3차\n<!-- verdict: critical=1 major=0 minor=0 -->\n' >"$R/phases/3-books/review/review-3.md"
commit_all "$R"
blocked "마지막 리뷰에 critical이 있다" "critical 1"

R="$(make_repo g-noverdict)"
printf '# 3차\n결함 없음\n' >"$R/phases/3-books/review/review-3.md"
commit_all "$R"
blocked "verdict 줄이 없는 리포트" "review-3.md 끝에 verdict 줄이 없다"

R="$(make_repo g-minor)"
printf '# 3차\n<!-- verdict: critical=0 major=0 minor=2 -->\n' >"$R/phases/3-books/review/review-3.md"
commit_all "$R"
blocked "minor를 처분하지 않았다" "fix-3.md"

R="$(make_repo g-human)"
sed -i.bak 's/needs-human=0/needs-human=2/' "$R/phases/3-books/review/fix-1.md" && rm "$R/phases/3-books/review/fix-1.md.bak"
commit_all "$R"
blocked "사람 판단 필요가 남았다" "사람 판단 필요가 2건"

R="$(make_repo g-nodisp)"
sed -i.bak '/disposition/d' "$R/phases/3-books/review/fix-1.md" && rm "$R/phases/3-books/review/fix-1.md.bak"
commit_all "$R"
blocked "disposition 줄이 없는 처분 기록" "fix-1.md 끝에 disposition 줄이 없다"

R="$(make_repo g-nosummary)"
rm "$R/phases/3-books/summary.md"
commit_all "$R"
blocked "최종 요약 없음" "최종 요약(phases/3-books/summary.md)이 없다"

R="$(make_repo g-stale)"
echo "요약 뒤의 코드" >"$R/code.txt"
commit_all "$R"
blocked "요약 뒤에 코드가 바뀌었다" "최종 요약을 쓴 뒤로 코드가 바뀌었다"

R="$(make_repo g-nomark)"
sed -i.bak '/summary-of/d' "$R/phases/3-books/summary.md" && rm "$R/phases/3-books/summary.md.bak"
commit_all "$R"
blocked "판독용 줄이 없는 요약" "다룬 커밋을 읽을 수 없다"

R="$(make_repo g-check)"
CHECK_CMD="printf '=== 요약\npytest: exit 1\n'; exit 1" blocked "검사 실패" "검사가 실패했다"

echo "관문 — 통과하는 모양"
R="$(make_repo ok-lastsection)"
printf '# 3차\n\n## 종합 판정\n\n| 마지막-절 |\n\n<!-- verdict: critical=0 major=0 minor=0 -->\n' >"$R/phases/3-books/review/review-3.md"
commit_all "$R"
run "$R" 3-books
contains "종합 판정이 마지막 절이어도 싣는다" "마지막-절" "$OUT"
lacks "그때도 기계 판독용 줄은 싣지 않는다" "<!-- verdict" "$OUT"

R="$(make_repo ok-minor)"
printf '# 3차\n<!-- verdict: critical=0 major=0 minor=2 -->\n' >"$R/phases/3-books/review/review-3.md"
printf '# 처분\n> 고친 것 2건.\n<!-- disposition: fixed=2 rejected=0 needs-human=0 -->\n' >"$R/phases/3-books/review/fix-3.md"
commit_all "$R"
run "$R" 3-books
check "minor를 처분했으면 다시 리뷰하지 않아도 통과" 0 "$RC"

R="$(make_repo ok-nomanual)"
rm "$R/phases/3-books/MANUAL.md"
commit_all "$R"
run "$R" 3-books
check "MANUAL.md가 없어도 통과" 0 "$RC"
contains "사람이 볼 항목이 없다고 적는다" "사람이 따로 확인할 항목이 없습니다" "$OUT"

R="$(make_repo ok-phases)"
echo "- 처분 기록을 고쳤다" >>"$R/phases/3-books/review/fix-1.md"
commit_all "$R"
run "$R" 3-books
check "요약 뒤에 phases/ 아래만 바뀌었으면 통과" 0 "$RC"

R="$(make_repo ok-noissue)"
sed -i.bak '/GitHub 이슈/d' "$R/docs/backlog/epic-3/E3-books.md" && rm "$R/docs/backlog/epic-3/E3-books.md.bak"
commit_all "$R"
refresh_summary "$R"
run "$R" 3-books
check "이슈 번호가 없어도 통과" 0 "$RC"
lacks "없는 이슈를 닫는다고 적지 않는다" "Closes #" "$OUT"

echo "입력"
R="$(make_repo input)"
run "$R"
check "task가 없으면 64" 64 "$RC"
run "$R" nope
check "없는 phase면 64" 64 "$RC"
run "$R" 3-books --bogus
check "모르는 인자면 64" 64 "$RC"
check "어느 경우에도 gh를 부르지 않는다" "" "$(gh_calls)"

printf '\n통과 %d · 실패 %d\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
