이 프로젝트는 Harness 프레임워크를 사용한다. 아래 워크플로우에 따라 작업을 진행하라.

이 문서는 OnlineFourCut의 `/harness`를 옮긴 것이다. 본문의 "Epic 0", "Epic 5" 같은 사례는 원본 프로젝트에서 실제로 있었던 일이며, 원칙이 왜 생겼는지를 보여 주려고 남겼다. 전체 흐름과 사람이 하는 순서는 `docs/HARNESS.md`에 있다. 이 문서는 step 설계 원칙, 파일 형식, 종료 코드를 소유한다.

---

## 워크플로우

### A. 탐색

`docs/` 하위 문서를 읽고 프로젝트의 기획·아키텍처·설계 의도를 파악한다. 어느 문서가 무엇을 맡는지는 `CLAUDE.md`의 표에 있다. 필요시 Explore 에이전트를 병렬로 사용한다.

작업 단위는 Epic이다. `docs/backlog/README.md`의 Epic 지도에서 이번에 돌릴 Epic을 찾고, 그 Epic 문서와 `testcase.md`를 읽는다. Epic 문서가 아직 없으면 `docs/backlog/README.md`의 형식대로 먼저 쓴다.

### B. 논의

구현을 위해 구체화하거나 기술적으로 결정해야 할 사항이 있으면 사용자에게 제시하고 논의한다.

### C. Step 설계

사용자가 구현 계획 작성을 지시하면 여러 step으로 나뉜 초안을 작성해 피드백을 요청한다.

설계 원칙:

1. **Scope 최소화** — 하나의 step에서 한 기능 폴더의 한 층만 다룬다(`docs/ARCHITECTURE.md` 8절). 순서는 안쪽부터다: `models`·마이그레이션·`repository` → `service`(필요한 포트 선언 포함) → `router`·`schemas`. 포트 선언(`app/core`)과 어댑터 구현(`app/adapters`)은 서로 다른 step이다. 여러 기능 폴더를 동시에 수정해야 하면 step을 쪼갠다.
2. **자기완결성** — 각 step 파일은 독립된 Claude 세션에서 실행된다. "이전 대화에서 논의한 바와 같이" 같은 외부 참조는 금지한다. 필요한 정보는 전부 파일 안에 적는다.
3. **사전 준비 강제** — 관련 문서 경로와 이전 step에서 생성/수정된 파일 경로를 명시한다. 세션이 코드를 읽고 맥락을 파악한 뒤 작업하도록 유도한다.
4. **시그니처 수준 지시** — 함수/클래스의 인터페이스만 제시하고 내부 구현은 에이전트 재량에 맡긴다. 단, 설계 의도에서 벗어나면 안 되는 핵심 규칙(멱등성, 보안, 데이터 무결성 등)은 반드시 명시한다.
5. **AC는 실행 가능한 커맨드** — "~가 동작해야 한다" 같은 추상적 서술이 아닌 `uv run pytest tests/books/test_service.py && scripts/check.sh` 같은 실제 실행 가능한 검증 커맨드를 포함한다. 마지막은 항상 `scripts/check.sh`다 — Stop 훅이 같은 것을 돌린다.
6. **주의사항은 구체적으로** — "조심해라" 대신 "X를 하지 마라. 이유: Y" 형식으로 적는다.
7. **네이밍** — step name은 kebab-case slug로, 해당 step의 핵심 모듈/작업을 한두 단어로 표현한다 (예: `settings-class`, `books-repository`, `auth-router`).
8. **AC에 반증 조건을 박아라** — step이 로직을 만들면, 테스트가 무엇을 단언해야 하는지와 **어떤 가짜 구현이 그 단언을 통과하는지**를 함께 적는다. 형식: "테스트는 X를 단언한다. Y로 구현해도 초록이면 그 테스트가 틀린 것이다."

   단언을 쓰는 자와 구현을 쓰는 자가 같고 AC는 "커맨드가 0으로 끝남"이라 **자기 채점**이다. 사람이 손대는 마지막 지점은 step 파일뿐이므로 여기서 못 박아야 한다. 원본 프로젝트의 Epic 0에서 이것이 없어 세 번 뚫렸다 — 합성 테스트가 캔버스 크기만 봐서 프레임이 서로를 덮는 것을 놓쳤고, 관통 테스트가 "컷이 떴다"만 봐서 참가자 하나가 통째로 빠지는 것을 놓쳤다.
9. **가드 예외는 사람이 미리 넣는다** — 그 step이 만들 파일 가운데 단위 테스트를 먼저 쓸 수 없는 것(외부 SDK를 부르기만 하는 얇은 래퍼, 엔진과 연결의 조립)은 step 파일에 이미 적혀 있다. `scripts/hooks/tdd-guard.sh`의 "개별 파일 예외"에 필요한 줄을 이유 주석과 함께 **step 파일과 같은 커밋에** 넣어라. 무인 실행은 가드를 고칠 수 없어(`HARNESS_RUN`) 예외가 없으면 `blocked`로 서고, 새벽에 서면 손해다. 가드가 기대하는 테스트 위치는 `docs/DEVELOPMENT.md`의 테스트 규칙에 있다.
10. **순수 로직 step은 RED를 커밋으로 남기게 지시한다** — step이 순수 로직(장면 선택, 후보 샘플링, 중단한 곡 제외, 묶음 검증 같은 것)을 만들면, 그 step 파일에 순서를 명시한다: "테스트를 먼저 쓰고 → 실패를 눈으로 확인하고 → `test(scope): RED` 로 커밋하고 → 구현해서 초록으로 만든다."

    TDD를 지시만 하면 **지켰는지를 밖에서 반증할 수 없다.** 완성된 커밋 하나에는 테스트와 구현이 함께 들어 있어서, 테스트를 나중에 구현에 맞춰 쓴 것과 구별되지 않는다 — 원본 프로젝트 Epic 5의 1차 리뷰가 정확히 그 자리에서 "판정 불가"로 남았고, 소급해서 확인할 방법도 없었다. 붉은 커밋 하나가 그 증거다.

    `execute.py`는 고치지 않아도 된다 — step 중간 커밋이 가능하고 마지막에 `git add -A`가 남은 것을 걷는다. 응답 시간처럼 계측으로 닫는 step에는 이 지시를 넣지 마라(붉힐 것이 없다).
11. **문서 개정이 먼저다** — Story가 `docs/API.md`나 `docs/AI_CONTRACT.md`의 규격을 바꿔야 하면, 문서를 고치는 step을 구현 step보다 앞에 둔다. 구현이 문서를 근거로 삼아야지 문서가 구현을 따라가면 안 된다. 모델을 바꾸는 step은 마이그레이션을 같은 step에 넣는다.
12. **사람이 볼 것은 최소로** — `MANUAL.md`에는 사람만 확인할 수 있는 것만 적는다. 단언으로 적을 수 있는 것은 전부 `testcase.md`의 테스트 케이스로 만들어 step의 AC에 넣는다. 기준은 D-4에 있다.

### D. 파일 생성

사용자가 승인하면 아래 파일들을 생성한다.

#### D-0. worktree

작업은 메인 체크아웃이 아니라 phase마다 따로 만든 worktree에서 한다. 파일을 만들기 전에 worktree부터 만든다.

```bash
scripts/harness-worktree.sh {task-name}    # 표준 출력의 마지막 줄이 worktree 경로다
```

이 스크립트는 Orca로 `feat-{task-name}` 브랜치의 worktree를 만든다. 그래야 Orca 왼쪽 사이드패널에 보인다. `git worktree add`로 직접 만들지 마라. 이유: Orca가 만들지 않은 worktree는 사이드패널에 보이지 않아, 무인 실행이 어디서 도는지 사람이 볼 수 없다.

이후의 파일(Epic 문서, `phases/` 아래 전부, 가드 예외)은 **그 worktree 안에** 쓰고 그 안에서 커밋한다. 그래야 설계와 구현이 한 PR에 담긴다. `scripts/harness-run.sh`는 메인 체크아웃에서 부르면 실행을 거부한다.

#### D-1. `phases/index.json` (전체 현황)

여러 task를 관리하는 top-level 인덱스. 이미 존재하면 `phases` 배열에 새 항목을 추가한다.

```json
{
  "phases": [
    {
      "dir": "0-project-setup",
      "status": "pending"
    }
  ]
}
```

- `dir`: task 디렉토리명. `{Epic 번호}-{slug}` 형식이다 (`docs/backlog/epic-0/` ↔ `phases/0-project-setup/`).
- `status`: `"pending"` | `"completed"` | `"error"` | `"blocked"`. execute.py가 실행 중 자동으로 업데이트한다.
- 타임스탬프(`completed_at`, `failed_at`, `blocked_at`)는 execute.py가 상태 변경 시 자동 기록한다. 생성 시 넣지 않는다.

#### D-2. `phases/{task-name}/index.json` (task 상세)

```json
{
  "project": "Diegesis BE",
  "phase": "<task-name>",
  "steps": [
    { "step": 0, "name": "dependencies", "status": "pending" },
    { "step": 1, "name": "settings-class", "status": "pending" },
    { "step": 2, "name": "error-format", "status": "pending" }
  ]
}
```

필드 규칙:

- `project`: `Diegesis BE`.
- `phase`: task 이름. 디렉토리명과 일치시킨다. 브랜치 이름(`feat-{phase}`)과 커밋의 scope가 여기서 나온다.
- `steps[].step`: 0부터 시작하는 순번.
- `steps[].name`: kebab-case slug.
- `steps[].status`: 초기값은 모두 `"pending"`.

상태 전이와 자동 기록 필드:

| 전이 | 기록되는 필드 | 기록 주체 |
|------|-------------|----------|
| → `completed` | `completed_at`, `summary` | Claude 세션 (summary), execute.py (timestamp, 검사 통과를 확인한 뒤) |
| → `error` | `failed_at`, `error_message` | Claude 세션 (message), execute.py (timestamp) |
| → `blocked` | `blocked_at`, `blocked_reason` | Claude 세션 (reason), execute.py (timestamp) |

**`completed`는 세션의 신고만으로 인정되지 않는다.** 세션이 `completed`를 적으면 execute.py가 `scripts/check.sh`를 직접 돌린다. 실패하면 step을 `pending`으로 되돌리고 검사 출력을 실어 재시도하며, 3회 뒤에도 빨가면 `error`로 끝낸다. Stop 훅은 세 번 되돌린 뒤 세션을 놓아주므로, 이 확인이 없으면 빨간 검사 위의 `completed`가 그대로 기록된다. step이 고칠 수 없는 원인으로 검사가 빨가면 세션은 `completed`가 아니라 `blocked`를 적어야 한다.

`summary`는 step 완료 시 산출물을 한 줄로 요약한 것으로, execute.py가 다음 step 프롬프트에 컨텍스트로 누적 전달한다. 따라서 다음 step에 유용한 정보(생성된 파일, 핵심 결정 등)를 담아야 한다.

`created_at`은 execute.py가 최초 실행 시 task 레벨에 한 번만 기록한다. step 레벨의 `started_at`도 execute.py가 각 step 시작 시 자동 기록한다. 생성 시 넣지 않는다.

#### D-3. `phases/{task-name}/step{N}.md` (각 step마다 1개)

매 step 프롬프트에는 `CLAUDE.md`와 `docs/DEVELOPMENT.md`, `docs/ARCHITECTURE.md`, `docs/CONFIGURATION.md`, `docs/GLOSSARY.md`가 통째로 주입된다(`scripts/execute.py`의 `GUARDRAIL_DOCS`). 이 문서들은 "읽어야 할 파일"에 다시 적지 않는다. 주입되지 않는 문서(`docs/API.md`, `docs/AI_CONTRACT.md`, `docs/ADR.md`, `docs/DECISIONS.md`, Epic 문서와 `testcase.md`)는 그 step에 필요한 것만 **절 번호까지** 적는다.

````markdown
# Step {N}: {이름}

## 읽어야 할 파일

먼저 아래 파일들을 읽고 이 step의 근거와 설계 의도를 파악하라:

- `docs/backlog/epic-{N}/E{N}-{slug}.md` — {Story 번호}
- `docs/backlog/epic-{N}/testcase.md` — {TC 번호}
- `docs/API.md` {절 번호} — {무엇을 확인할지}
- {이전 step에서 생성/수정된 파일 경로}

이전 step에서 만들어진 코드를 꼼꼼히 읽고, 설계 의도를 이해한 뒤 작업하라.

## 작업

{구체적인 구현 지시. 파일 경로, 클래스/함수 시그니처, 로직 설명을 포함.
코드 스니펫은 인터페이스/시그니처 수준만 제시하고, 구현체는 에이전트에게 맡겨라.
단, 설계 의도에서 벗어나면 안 되는 핵심 규칙은 명확히 박아넣어라.}

## Acceptance Criteria

```bash
uv run pytest tests/{기능}/test_{이름}.py   # 이 step의 테스트 케이스
scripts/check.sh                            # ruff, pyright, 전체 테스트
```

**반증 조건** — {이 테스트가 반드시 빨개져야 하는 가짜 구현. **없으면 "없음"이라고 적는다.**
예: "테스트는 중단한 곡이 후보에서 빠짐을 단언한다. 후보가 하나뿐인 픽스처라 아무 곡이나 돌려줘도 초록이면 틀렸다."}

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - `docs/ARCHITECTURE.md` 8절의 코드 구조와 의존 방향을 따르는가?
   - `docs/ADR.md`의 기술 스택을 벗어나지 않았는가?
   - `docs/DEVELOPMENT.md`의 "반드시 지킬 규칙"을 위반하지 않았는가?
3. 결과에 따라 `phases/{task-name}/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"`
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 (API 키, 외부 인증, 수동 설정 등) → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- {이 step에서 하지 말아야 할 것. "X를 하지 마라. 이유: Y" 형식}
- 기존 테스트를 깨뜨리지 마라
- `MANUAL.md`의 항목을 체크하지 마라. 이유: 그 항목은 사람이 직접 본 것만 체크한다.
````

#### D-4. `phases/{task-name}/MANUAL.md` (사람이 확인할 것이 있을 때만)

자동 AC가 전부 통과해도 요구사항이 깨져 있을 수 있다. `MANUAL.md`는 그 틈을 사람이 메우는 점검표다. 여기에 `- [ ]`가 하나라도 남아 있으면 execute.py는 phase를 완료로 찍지 않고 종료 코드 5로 끝난다.

**그래서 여기에 적는 것은 사람의 시간을 쓰는 약속이다. 꼭 사람이 봐야 하는 것만 적는다.**

MANUAL에 넣는 것은 세 종류뿐이다.

| 종류 | 예 |
|---|---|
| 사람의 감각이나 판단이 필요한 것 | 선곡된 곡이 그 장면에 어울리는가. 중단한 뒤의 쉬는 시간이 독서 중에 길게 느껴지지 않는가. |
| 에이전트가 닿을 수 없는 계정이나 콘솔이 필요한 것 | 실제 Google 계정으로 로그인이 끝까지 되는가. Google Cloud 콘솔에 리디렉션 주소를 등록했는가. |
| 실제 운영 환경에서만 볼 수 있는 것 | 배포된 주소에서 프론트엔드가 쿠키를 주고받는가. |

MANUAL에 넣지 않는 것:

- **단언으로 적을 수 있는 것.** "헬스체크가 200을 돌려준다", "허용 목록 밖의 계정이 403을 받는다", "에러 응답이 `{code, message, detail}` 형식이다", "로그에 선곡 방식이 남는다"는 전부 테스트 케이스다. `testcase.md`에 `unit`이나 `integration`으로 적고 step의 AC에 넣어라. 이유: 사람이 `curl`로 한 번 본 것은 다음 변경에서 다시 깨져도 아무도 모른다. 테스트는 매번 본다.
- **명령을 실행하고 출력을 읽기만 하면 되는 것.** 그 명령과 기대 출력을 테스트로 옮겨라.
- **"혹시 모르니" 넣는 재확인.** 테스트가 이미 보는 것을 사람이 또 보게 하지 마라.

테스트로 옮기기 어려워 보이면 먼저 방법을 찾아라. 가짜 어댑터를 끼우면 Google 없이 로그인 흐름의 분기를 볼 수 있고, 통합 테스트용 DB를 쓰면 실제 쿼리를 볼 수 있다. 그래도 안 되는 것만 MANUAL에 남긴다.

항목마다 **테스트로 덮을 수 없는 이유**를 한 줄 적는다. 이유를 적을 수 없으면 그 항목은 테스트 케이스다.

````markdown
# Epic {N} — 사람이 확인하는 점검표

> **에이전트에게 시키지 마라.** 여기 있는 것은 사람이 직접 보고 체크한다.
> 근거는 `docs/backlog/epic-{N}/testcase.md`의 `manual` 항목이다.
> 전부 체크되기 전까지 `execute.py`는 종료 코드 5로 끝난다 — 정상이다.

## {무엇을 확인하는가}

- [ ] {확인할 것. 무엇을 하고 무엇이 보이면 통과인지 구체적으로}
  - 테스트로 덮을 수 없는 이유: {한 줄}
  - {따라 할 명령이 있으면 그 이름. 예: 등록 명령}:
    - `{명령}`
  - 관찰한 값: {사람이 체크하면서 적는다. 여러 가지면 아래 단계 목록으로 나눈다}
````

형식 규칙:

- 체크 항목은 줄 맨 앞이 `- [ ]`다. execute.py가 이 접두로 미확인 항목을 센다.
- 체크 항목이 아닌 안내는 목록 기호 없이 쓰거나 인용(`>`)으로 쓴다. `- [ ]`로 쓰면 미확인으로 세어진다.
- 체크 항목에 딸린 내용은 두 칸 들여 쓴 하위 목록으로 쓰고, 하위 항목마다 `이름: 내용`의 꼴로 한 가지만 적는다. 명령이나 관찰한 값이 여럿이면 한 단계 더 들여 쓴 목록으로 나눈다. 이유: 사람이 읽으며 따라 하고 체크하는 문서다. 한 문단에 이어 쓰면 무엇을 해야 하는지와 무엇을 적어야 하는지를 찾기 어렵다.
- 하위 목록에는 체크 상자(`- [ ]`)를 쓰지 마라. 이유: execute.py와 harness-pr.sh는 들여쓰기를 지우고 세므로, 하위의 `- [ ]`도 미확인 항목이 된다.
- **항목이 하나도 없으면 `MANUAL.md`를 만들지 않는다.** 파일이 없으면 execute.py는 그대로 완료로 찍는다. 사람이 볼 것이 없는 phase가 정상이다.

### E. 실행

worktree 안에서 띄운다.

```bash
scripts/harness-run.sh {task-name}           # step 실행 → 리뷰 → 리뷰 처분
scripts/harness-run.sh {task-name} --push     # phase가 완료되면 브랜치를 push
scripts/harness-run.sh {task-name} --no-fix   # 리뷰까지만. 처분은 /review-fix 로 직접
```

수십 분이 걸리므로 **백그라운드로 띄운다.** 세션이 Bash 도구로 직접 붙들고 있으면 도구 상한에 걸린다.

실행 전 조건: 워킹트리가 깨끗해야 한다(`phases/` 아래는 예외). Epic 문서, step 파일, 가드 예외를 먼저 커밋해라.

**step 실행.** harness-run.sh가 execute.py를 감싼다. execute.py가 자동으로 처리하는 것:

- `feat-{task-name}` 브랜치 확인 — worktree가 이미 그 브랜치에 있다
- 가드레일 주입 — `CLAUDE.md`와 `GUARDRAIL_DOCS`에 적힌 문서를 매 step 프롬프트에 포함
- 컨텍스트 누적 — 완료된 step의 summary를 다음 step 프롬프트에 전달
- 자가 교정 — 실패 시 최대 3회 재시도하며, 이전 에러 메시지를 프롬프트에 피드백
- 2단계 커밋 — 코드 변경(`feat`)과 메타데이터(`chore`)를 분리 커밋
- 타임스탬프 — started_at, completed_at, failed_at, blocked_at 자동 기록

헤드리스 세션의 모델은 `claude-opus-5-5`다. 환경 변수 `HARNESS_MODEL`로 바꾼다.

**리뷰.** `phases/{task-name}/index.json`의 step이 **전원 `completed`일 때만** 리뷰 세션을 띄운다. 리뷰는 `claude -p`로 뜨는 별도 세션이라 구현 세션의 컨텍스트를 물려받지 않는다 — 그것이 리뷰를 여기에 붙이는 이유다. 산출물은 `phases/{task-name}/review/review-{N}.md`이고 harness-run.sh가 커밋한다.

상위 `phases/index.json`은 게이트가 보지 않는다. MANUAL.md에 미확인 항목이 남으면 execute.py가 종료 코드 5로 끝나며 상위 인덱스를 쓰지 않는데, 그때도 코드는 전부 커밋된 뒤라 리뷰 대상이 맞다. 종료 코드도 게이트에 넣지 않는다 — 1·2·3·4는 반드시 어떤 step을 `completed`가 아닌 상태로 남기므로 step 검사가 알아서 막는다.

**리뷰 처분.** 리포트에 결함이 있으면 또 다른 별도 세션이 `review-fix` 스킬로 처분한다. 결함마다 타당한지 대조하고, 재현 테스트를 먼저 쓴 뒤 고치고, `phases/{task-name}/review/fix-{N}.md`에 처분을 기록한다. 그 라운드에 critical이나 major가 있었으면 고친 결과를 확인하려고 다시 리뷰한다. 이 왕복은 최대 `HARNESS_MAX_REVIEW_ROUNDS`(기본 3) 라운드다. minor만 있던 라운드는 처분으로 닫고 다시 리뷰하지 않는다.

같은 명령을 다시 돌려도(예: MANUAL.md를 체크한 뒤) 마지막 리뷰가 닫혀 있고 그 뒤로 `phases/` 밖의 코드가 바뀌지 않았으면 리뷰를 다시 띄우지 않는다. 코드가 바뀌었으면 다시 리뷰한다.

리뷰와 처분의 결과는 각 파일 끝의 한 줄로 읽는다. 이 줄이 없으면 harness-run.sh는 추정하지 않고 멈춘다.

```
<!-- verdict: critical=0 major=2 minor=5 -->
<!-- disposition: fixed=6 rejected=1 needs-human=0 -->
```

**종료 코드.** 종료 코드로 무엇이 막혔는지 가른다. **3·4·5는 step을 건드리지 않는다** — 원인만 없애고 같은 명령을 다시 돌리면 이어서 간다.

| 코드 | 뜻 | 할 일 |
|---|---|---|
| 0 | step, 리뷰, 처분이 모두 닫혔고 phase가 완료됐다 | F로 간다 |
| 1 | step 실패(3회 자가 교정 후) 또는 더티 워킹트리 | 아래 참조 |
| 2 | blocked — 사람 개입이 필요하다 | 아래 참조 |
| 3 | 사용 한도(HTTP 429) | 한도가 풀릴 때까지 기다렸다 재실행 |
| 4 | 60분 상한 초과 | 무엇이 멈췄는지 보고 원인 제거 후 재실행 |
| 5 | `MANUAL.md`에 확인 안 된 항목이 남음 (리뷰와 처분은 닫혔다) | 사람이 직접 확인하고 체크한 뒤 재실행 |
| 6 | 리뷰와 처분이 닫히지 않았다 | 아래 참조 |
| 64 | 사용법 오류, 또는 메인 체크아웃에서 불렀다 | 인자를 고치거나 worktree에서 다시 부른다 |

- **error 발생 시**: `phases/{task-name}/index.json`에서 해당 step의 `status`를 `"pending"`으로 바꾸고 `error_message`를 삭제한 뒤 재실행한다.
- **blocked 발생 시**: `blocked_reason`에 적힌 사유를 해결한 뒤, `status`를 `"pending"`으로 바꾸고 `blocked_reason`을 삭제한 뒤 재실행한다.
- **더티 워킹트리로 멈춘 경우**: 하네스는 `git add -A`로 커밋하므로 남은 변경이 step 커밋에 섞인다. 커밋하거나 stash한 뒤 재실행한다(`phases/` 아래는 검사에서 뺀다).
- **6으로 끝난 경우**: 표준 오류의 마지막 두 줄이 이유를 말한다. 경우는 넷이다.
  - 최대 라운드를 돌았는데 마지막 리뷰의 critical·major를 고친 결과가 재리뷰로 확인되지 않았다 → 사람이 마지막 `review-{N}.md`와 `fix-{N}.md`를 읽고, `/review`로 한 번 더 판정하거나 직접 닫는다.
  - 처분이 "사람 판단 필요"로 넘긴 항목이 있다 → `fix-{N}.md`의 그 항목을 사람이 정한다. 정한 뒤 `/review-fix`를 대화형으로 돌리거나 직접 고친다.
  - 세션이 리포트나 처분 기록, 또는 그 끝의 판독용 줄을 남기지 않았다 → `phases/{task-name}/review/session.log`를 본다.
  - 처분 세션이 커밋하지 않은 변경을 남겼다 → `git status`로 보고 정리한다.

### F. PR

phase가 완료되면(종료 코드 0) PR을 준비한다.

```bash
scripts/harness-pr.sh {task-name}            # 관문을 검사하고 PR 제목과 본문을 출력만 한다
scripts/harness-pr.sh {task-name} --create   # 브랜치를 push하고 PR을 연다
```

`--create`는 **사람이 출력된 본문을 보고 승인한 뒤에만** 붙인다. PR은 레포 밖에 보이는 행동이고, 한번 열면 닫아도 흔적이 남는다. 헤드리스 세션은 push와 PR 생성을 할 수 없다(bash-guard가 막는다).

머지는 GitHub에서 사람이 한다. 머지 방식과 그 이유는 `docs/DEVELOPMENT.md`에 있다.

다음 phase는 앞의 PR이 머지된 main에서 시작한다. 앞의 PR이 아직 열려 있으면 `scripts/harness-worktree.sh {다음 task} --base feat-{앞 task}`로 그 위에서 시작하고, 리뷰의 범위를 `scripts/harness-run.sh {다음 task} --review-base feat-{앞 task}`로 좁힌다.
