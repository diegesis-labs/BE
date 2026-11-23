# Step 6: ci-workflow

## 읽어야 할 파일

먼저 아래 파일들을 읽고 이 step의 근거와 설계 의도를 파악하라:

- `docs/backlog/epic-0/E0-project-setup.md` — "못 박을 것 (Epic 전역)", S0.7, "끝나는 조건"
- `docs/backlog/epic-0/testcase.md` — TC-0.7.1 ~ TC-0.7.6
- `docs/INFRA.md` 3.7절 — CI의 흐름, secrets와 variable의 이름
- `docs/DECISIONS.md` — D-36, D-37, D-38, D-41
- `scripts/check.sh`, `scripts/compose-smoke.sh`, `Dockerfile`, `compose.yaml` (step 4)
- `tests/infra/` (step 4) — 실행 환경 파일을 테스트하는 방식
- `pyproject.toml`

이전 step에서 만들어진 코드를 꼼꼼히 읽고, 설계 의도를 이해한 뒤 작업하라.

## 작업

### 1. workflow — `.github/workflows/ci.yml`

`.github/workflows/.gitkeep`은 지운다.

**트리거와 권한**

- `main`을 향한 `pull_request`와 `main`의 `push`에서만 돈다. `pull_request_target`을 쓰지 마라. 이유: 그 트리거는 PR의 코드를 secrets가 있는 맥락에서 돌린다.
- workflow 최상위의 `permissions`는 `contents: read` 하나다.
- 같은 브랜치에 새 커밋이 오면 그 브랜치의 이전 실행을 취소해도 된다(`concurrency`). 다만 `main`의 push는 취소하지 마라. 이유: 취소된 커밋의 이미지가 올라가지 않는다.

**job 세 개**

| job | 하는 일 |
| --- | --- |
| `check` | uv를 설치하고 `uv sync --locked`를 한 뒤 `scripts/check.sh`를 부른다. |
| `compose-smoke` | `scripts/compose-smoke.sh`를 부른다. |
| `image` | `check`와 `compose-smoke`를 `needs`로 기다린 뒤 `linux/amd64` 이미지를 빌드한다. `main`의 push에서만 Docker Hub에 로그인하고 올린다. |

- **`check`**: 검사 명령(ruff, pyright, pytest)을 workflow에 따로 적지 마라. 이유: 검사 명령은 `scripts/check.sh` 한 곳에만 둔다(DEVELOPMENT.md 2절). 통합 테스트도 이 job에서 돈다. GitHub의 ubuntu 실행기에는 Docker가 있어 testcontainers가 동작한다. Python은 uv가 `.python-version`을 읽어 설치하게 둔다.
- **uv의 버전**: `astral-sh/setup-uv`로 설치하고 버전을 고정한다. 그 버전은 `Dockerfile`이 복사해 오는 uv 이미지의 버전과 같아야 한다(DEVELOPMENT.md 1절).
- **`image`의 이미지 이름과 태그**: 이미지 이름은 `vars.DOCKERHUB_IMAGE`에서만 읽는다. 태그는 `latest`와 `sha-<커밋>`이다.
- **PR에서의 `image`**: 빌드만 하고 올리지 않는다. 이때 secrets와 variable에 기대지 않아야 한다. 이유: secrets와 variable을 등록하기 전(MANUAL.md)에도, secrets를 받지 못하는 PR(Dependabot 등)에서도 빌드 확인은 초록이어야 한다. variable이 비어 있으면 `:latest`처럼 이름 없는 태그가 만들어져 빌드가 실패하니, PR에서는 태그를 붙이지 않거나 고정된 로컬 이름을 쓴다.
- **`main`의 push에서의 `image`**: 로그인하기 전에 `DOCKERHUB_IMAGE`가 비어 있지 않은지 확인하고, 비어 있으면 무엇을 등록해야 하는지 출력하고 실패한다. 이유: 등록을 빠뜨린 것이 이상한 이름의 push나 알아보기 어려운 오류로 나타나면 안 된다.
- **이미지 빌드 도구**: `image` job은 Docker의 공식 action(`docker/setup-buildx-action`, `docker/login-action`, `docker/build-push-action`)으로 빌드하고 올린다. D-41의 "compose로만 빌드한다"는 로컬과 스모크의 규칙이며, 레지스트리에 올리는 이 job은 해당하지 않는다. 스모크 job은 D-41대로 compose로 빌드한다.
- **action의 버전**: 각 action은 지금의 최신 주 버전 태그(예: `@v5`)로 고정한다. 태그가 있는지 `git ls-remote --tags https://github.com/<소유자>/<action>`으로 확인하라. `@main`이나 `@master`를 쓰지 마라.
- `continue-on-error`를 쓰지 마라. 이유: 실패한 검사가 초록으로 보인다.

### 2. actionlint

`uv add --dev actionlint-py`로 actionlint를 dev 의존성에 더한다. 이유: 개발자의 컴퓨터와 CI가 같은 버전의 actionlint를 쓴다.

actionlint는 shellcheck와 pyflakes가 설치되어 있으면 그것까지 부른다. 테스트에서는 이 둘을 끄고 부른다(`-shellcheck=` `-pyflakes=`). 이유: ubuntu 실행기에는 shellcheck가 있고 개발자의 컴퓨터에는 없을 수 있어서, 켜 두면 같은 파일이 CI에서만 실패한다.

### 3. 테스트 — `tests/infra/test_workflow.py` (unit)

TC-0.7.1 ~ TC-0.7.5. PyYAML로 `.github/workflows/ci.yml`을 읽는다.

- **PyYAML의 `on` 키**: PyYAML은 YAML 1.1을 따라 `on`이라는 키를 문자열이 아니라 `True`로 읽는다. 트리거를 찾을 때 이것을 처리하라. `on` 키를 따옴표로 감싸서 피하지 마라. 이유: GitHub의 일반적인 형식에서 벗어나고, 테스트가 그 형식에만 맞게 된다.
- **TC-0.7.2**: `check` job의 `run` 가운데 `scripts/check.sh`가 있고, `ruff`, `pyright`, `pytest`를 직접 부르는 줄이 없는지 본다. uv의 버전은 `Dockerfile`과 workflow를 둘 다 읽어서 비교한다. 버전 문자열을 테스트에 적지 마라.
- **TC-0.7.3**: `image`의 `needs`에 두 job이 모두 있는지, 로그인과 push가 `main`의 push일 때로 제한되는지, `platforms`가 `linux/amd64` 하나뿐인지, 태그에 `latest`와 `sha-`가 있는지 본다.
- **TC-0.7.4**: workflow 전체의 텍스트에서 Docker Hub의 사용자 이름과 토큰이 `secrets.DOCKERHUB_USERNAME`과 `secrets.DOCKERHUB_TOKEN`으로만, 이미지 이름이 `vars.DOCKERHUB_IMAGE`로만 쓰이는지 본다. 최상위 `permissions`가 정확히 `{"contents": "read"}`인지 본다.
- **TC-0.7.5**: actionlint를 subprocess로 부른다. 실행 파일을 찾지 못하면 skip하지 말고 실패한다.

## Acceptance Criteria

```bash
uv run pytest tests/infra/test_workflow.py -v
uv run actionlint -shellcheck= -pyflakes= .github/workflows/ci.yml
scripts/check.sh
```

workflow가 GitHub에서 실제로 도는지는 이 step에서 확인할 수 없다. phase가 끝난 뒤 첫 PR에서 확인한다(Epic 문서의 "끝나는 조건").

**반증 조건** — 아래의 틀린 구현으로도 초록이면 그 테스트가 틀린 것이다.

- `check` job에 `uv run pytest`를 따로 적어도 초록이면 TC-0.7.2가 틀렸다.
- `setup-uv`의 버전과 `Dockerfile`의 uv 버전이 달라도 초록이면 TC-0.7.2가 틀렸다.
- `image` job에서 `needs`를 지우거나, PR에서도 push하거나, `platforms`에 `linux/arm64`를 더해도 초록이면 TC-0.7.3이 틀렸다.
- 이미지 이름을 `someone/diegesis-be`처럼 문자열로 적어도 초록이면 TC-0.7.4가 틀렸다.
- `pull_request_target`을 써도 초록이면 TC-0.7.1이 틀렸다.
- actionlint가 없는 환경에서 TC-0.7.5가 skip되면 틀렸다.

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 반증 조건 가운데 TC-0.7.3의 세 가지를 실제로 하나씩 만들어 보고 테스트가 빨개지는지 확인한 뒤 되돌린다.
3. `scripts/compose-smoke.sh`를 한 번 더 돌려 초록인지 확인한다. 이유: CI의 스모크 job이 부르는 것이 이 스크립트다.
4. 아키텍처 체크리스트를 확인한다:
   - `docs/ARCHITECTURE.md` 8절의 코드 구조와 의존 방향을 따르는가?
   - `docs/ADR.md`의 기술 스택을 벗어나지 않았는가?
   - `docs/DEVELOPMENT.md`의 "반드시 지킬 규칙"을 위반하지 않았는가?
5. 결과에 따라 `phases/0-project-setup/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"`
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 (API 키, 외부 인증, 수동 설정 등) → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- Docker Hub의 사용자 이름, 토큰, 이미지의 전체 이름을 어떤 파일에도 적지 마라. 이유: 저장소가 공개이고, 이 값은 GitHub의 secrets와 variable에만 둔다(D-37).
- `git push`, PR 생성, `gh secret set`, `gh variable set`, `docker login`, `docker push`를 하지 마라. 이유: 레포 밖에 보이는 행동은 사람이 한다. 이 가운데 push, PR 생성, `docker login`, `docker push`는 명령 가드가 막는다.
- `linux/arm64` 이미지를 더하지 마라. 이유: D-37.
- 배포 단계(서버에 새 이미지를 반영하는 job)를 만들지 마라. 이유: 배포할 곳이 아직 정해지지 않았다(INFRA.md 3.7절).
- `scripts/check.sh`를 CI에 맞춰 고치거나, CI에서 통합 테스트를 빼지 마라. 이유: CI와 로컬과 Stop 훅이 같은 검사를 돌려야 한다(ADR-011).
- `docs/`를 고치지 마라. 이유: 이번 Epic의 문서 개정은 이미 끝났다. 고칠 곳을 찾으면 summary에 적어라.
- 기존 테스트를 깨뜨리지 마라
- `MANUAL.md`의 항목을 체크하지 마라. 이유: 그 항목은 사람이 직접 본 것만 체크한다.
