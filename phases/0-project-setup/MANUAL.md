# Epic 0 — 사람이 확인하는 점검표

> **에이전트에게 시키지 마라.** 여기 있는 것은 사람이 직접 보고 체크한다.
> 근거는 `docs/backlog/epic-0/testcase.md`의 `manual` 항목(TC-0.7.6)이다.
> 전부 체크되기 전까지 `execute.py`는 종료 코드 5로 끝난다 — 정상이다.
>
> 이 점검표는 phase가 끝나기 전에 할 수 있는 것만 담는다. 첫 PR의 CI, ruleset, `main`의 이미지 push는 PR과 병합 뒤에 확인하며, `docs/backlog/epic-0/E0-project-setup.md`의 "끝나는 조건"에 있다.

## Docker Hub와 GitHub의 등록

GitHub의 secrets와 variable을 등록하려면 BE 레포의 Admin 권한이 필요하다(`docs/DECISIONS.md`의 D-38). 권한이 없으면 팀장에게 Admin을 받거나, 팀장이 아래 `gh` 명령을 대신 실행한다.

- [x] Docker Hub에 **공개** 저장소 `diegesis-be`를 만들고, Read & Write 권한의 액세스 토큰을 발급했다. 그리고 BE 레포에 아래 셋을 등록했다. `gh secret list`에 `DOCKERHUB_USERNAME`과 `DOCKERHUB_TOKEN`이, `gh variable list`에 `DOCKERHUB_IMAGE`가 보이면 통과다.
  - 테스트로 덮을 수 없는 이유: Docker Hub 계정과 레포의 Admin 권한은 에이전트가 닿을 수 없고, 토큰은 사람만 다뤄야 하는 비밀값이다.
  - 등록 명령(토큰은 명령줄에 쓰지 않고 입력 창에 붙여 넣는다):
    - `gh secret set DOCKERHUB_USERNAME --repo diegesis-labs/BE`
    - `gh secret set DOCKERHUB_TOKEN --repo diegesis-labs/BE`
    - `gh variable set DOCKERHUB_IMAGE --repo diegesis-labs/BE --body "<Docker Hub 사용자 이름>/diegesis-be"`
  - 관찰한 값(2026-11-23):
    - `gh secret list --repo diegesis-labs/BE`에 `DOCKERHUB_USERNAME`(02:14:06Z)과 `DOCKERHUB_TOKEN`(02:14:34Z)이 보인다.
    - `gh variable list --repo diegesis-labs/BE`에 `DOCKERHUB_IMAGE`(02:15:53Z)가 보이고, 그 값은 `<사용자 이름>/diegesis-be` 꼴이다. 값 자체는 D-37에 따라 적지 않는다.
    - 저장소를 공개로 만들고 토큰을 Read & Write로 발급한 것은 체크한 사람이 Docker Hub에서 확인했다.