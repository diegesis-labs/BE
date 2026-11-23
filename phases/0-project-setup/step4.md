# Step 4: container

## 읽어야 할 파일

먼저 아래 파일들을 읽고 이 step의 근거와 설계 의도를 파악하라:

- `docs/backlog/epic-0/E0-project-setup.md` — "못 박을 것 (Epic 전역)", S0.5
- `docs/backlog/epic-0/testcase.md` — TC-0.5.1 ~ TC-0.5.5
- `docs/DECISIONS.md` — D-37, D-39, D-40, D-41
- `docs/INFRA.md` 1절
- `compose.yaml`, `alembic.ini`, `migrations/`, `tests/support/postgres.py` (step 1)
- `app/__main__.py`, `app/core/config.py`, `app/main.py`, `app/health/router.py` (step 0, 3)
- `pyproject.toml`, `uv.lock`, `.python-version`, `.gitignore`

이전 step에서 만들어진 코드를 꼼꼼히 읽고, 설계 의도를 이해한 뒤 작업하라.

## 작업

### 0. Docker 확인

`docker info`가 실패하면 고치려 하지 말고 `index.json`의 이 step을 `"status": "blocked"`, `"blocked_reason": "Docker에 닿을 수 없다 — Docker Desktop을 켜야 한다"`로 적고 즉시 중단하라.

### 1. `Dockerfile`

- 멀티 스테이지로 만든다. 빌드 단계에서는 uv로 `uv.lock`대로 운영 의존성만 설치하고(`--locked`, dev 제외), 실행 단계에는 가상환경과 실행에 필요한 것(`app/`, `migrations/`, `alembic.ini`)만 복사한다.
- Python 베이스 이미지는 `python:<주>.<부>-slim` 계열이며, 주 버전과 부 버전은 `.python-version`과 같아야 한다.
- uv는 `ghcr.io/astral-sh/uv:<정확한 버전>` 이미지에서 복사한다. 버전은 로컬의 `uv --version`과 같거나 그 뒤의 안정 버전이며, `docker manifest inspect`로 태그가 있는지 확인하라. `latest`나 주 버전만 있는 태그를 쓰지 마라.
- 실행 단계는 root가 아닌 사용자로 돈다. `EXPOSE 8080`이고 시작 명령은 `python -m app`이다.
- 셸 스크립트를 진입점으로 두지 마라. 이유: Windows의 git이 CRLF로 받은 셸 스크립트는 리눅스 컨테이너 안에서 깨진다.

### 2. `.dockerignore`

`.env`, `.env.*`, `.venv`, `.git`, `phases/`, `docs/`, `tests/`, `var/`, 캐시 폴더 등을 뺀다. 이유: `.env`가 빌드 맥락에 들어가면 공개 저장소의 이미지로 나갈 수 있다(D-37).

### 3. `compose.yaml`에 서비스 두 개를 더한다

step 1의 `db` 서비스는 그대로 두고 아래 둘을 더한다.

- `migrate` — 서버와 같은 이미지로, 명령은 `alembic upgrade head`다. `db`가 healthy가 된 뒤에 시작하고, 끝나면 멈춘다(D-40).
- `api` — 서버 이미지. `migrate`가 성공적으로 끝난 뒤에 시작한다. 포트는 `${API_PORT:-8080}:8080`이다. 컨테이너 안에서 `/api/health`를 부르는 healthcheck를 둔다(이미지에 curl이 없으면 python으로 부른다). 그래야 `docker compose up --wait`가 서버가 응답할 때까지 기다린다.
- 두 서비스의 `DATABASE_URL`은 `environment`에 직접 적는다. 값은 `postgresql+asyncpg://diegesis:diegesis@db:5432/diegesis`이고, 호스트는 `db`다.
- 이미지는 레지스트리에서 받지 않고 레포에서 빌드한다. 처음 받은 레포에서 `docker compose up --build` 하나로 동작해야 한다.
- `env_file`과 `platform`을 적지 마라. 이유: CI에는 `.env`가 없고, 개발자의 `.env`에 든 `localhost` 주소가 덮어쓰면 컨테이너 안에서 데이터베이스에 닿지 못한다. 그리고 각 컴퓨터는 자기 CPU 아키텍처로 빌드해야 한다(D-37).

### 4. `scripts/compose-smoke.sh`

compose로 전부 띄워서 확인한 뒤 내린다. 확인이 하나라도 어긋나면 0이 아닌 코드로 끝난다.

- 프로젝트 이름은 스크립트 안의 상수 `diegesis-smoke`로 고정한다. 환경변수나 인자로 바꿀 수 없게 하라. 이유: 정리할 때 볼륨까지 지우는데, 다른 이름으로 돌면 개발용 데이터베이스의 볼륨이 지워진다.
- 개발용으로 띄워 둔 compose와 포트가 부딪히지 않게 한다. 예를 들어 비어 있는 포트를 골라 `API_PORT`와 `DB_PORT`로 넘긴다.
- **이미지는 compose로만 빌드한다**(`docker compose ... build` 또는 `up --build`). `docker build`와 `docker buildx build`를 직접 부르지 마라. 이유: `docker build`의 결과가 로컬 이미지 저장소에 실리는지는 Docker builder의 설정에 따라 다르다. compose는 설정과 관계없이 싣는다(D-41).
- 확인할 것은 TC-0.5.1의 다섯 가지다.
  1. `migrate`가 종료 코드 0으로 끝났다.
  2. 데이터베이스에 `vector` 확장이 있다(`docker compose exec -T db psql ...`로 질의한다).
  3. 호스트에서 요청한 `/api/health`가 정확히 `{"status":"ok"}`이다.
  4. api 컨테이너의 프로세스 uid가 0이 아니다.
  5. api 이미지 안의 작업 폴더에 `.env` 파일이 없다.
- 성공하든 실패하든 마지막에 `diegesis-smoke` 프로젝트를 볼륨까지 내린다(`trap`).
- 실패하면 무엇이 어긋났는지와 `docker compose logs`의 끝부분을 출력한다.
- bash로 쓰고 `set -euo pipefail`을 건다. macOS(BSD 도구)와 Linux(GNU 도구)에서 모두 돌아야 한다. CI는 ubuntu에서 돈다. `sed -i`, `date`, `mktemp`, `stat`처럼 둘의 동작이 다른 명령에 주의하라.
- 실행 권한을 준다(`chmod +x`).

### 5. `.gitattributes`

`*.sh text eol=lf`를 둔다. 이유: Windows의 git이 셸 스크립트를 CRLF로 받으면 `bash\r` 오류로 깨진다.

### 6. 테스트 (unit, `tests/infra/`)

DEVELOPMENT.md 4.2절대로 실행 환경의 파일은 `tests/infra/`에서 테스트한다.

- `tests/infra/test_dockerignore.py` — TC-0.5.2
- `tests/infra/test_dockerfile.py` — TC-0.5.3. `Dockerfile`과 `.python-version`을 둘 다 읽어서 비교한다. 버전 문자열을 테스트에 적지 마라.
- `tests/infra/test_compose.py` — TC-0.5.4. PyYAML로 `compose.yaml`을 읽는다.
- `tests/infra/test_compose_smoke.py` — TC-0.5.5. 스크립트의 내용을 읽어서 확인한다. 주석 줄은 빼고 본다.

## Acceptance Criteria

```bash
uv run pytest tests/infra -v
scripts/compose-smoke.sh                    # TC-0.5.1
scripts/check.sh
```

**반증 조건** — 아래의 틀린 구현으로도 초록이면 그 테스트가 틀린 것이다.

- `.dockerignore`에서 `.env`를 지워도 초록이면 TC-0.5.2가 틀렸다.
- `.python-version`만 다른 값으로 바꾸고 `Dockerfile`을 그대로 두어도 초록이면 TC-0.5.3이 틀렸다.
- `migrate`나 `api`의 `DATABASE_URL`의 호스트가 `localhost`여도 초록이면 TC-0.5.4가 틀렸다.
- 스크립트가 프로젝트 이름을 환경변수로 받거나 `docker build`를 직접 불러도 초록이면 TC-0.5.5가 틀렸다.
- 스모크가 `/api/health`만 보고 `vector` 확장을 확인하지 않으면, 서버와 데이터베이스의 연결을 확인하지 못한 것이다(D-39).

## 검증 절차

1. 위 AC 커맨드를 실행한다. `scripts/compose-smoke.sh`는 실제로 돌려서 통과를 확인하라. 실패하면 출력된 로그를 읽고 고친다.
2. 스모크가 정말로 실패를 잡는지 한 번 확인한다. 예를 들어 `compose.yaml`의 `api`의 `DATABASE_URL` 호스트를 잠시 잘못된 값으로 바꾸고 스모크가 0이 아닌 코드로 끝나는지 본 뒤, 원래대로 되돌린다.
3. 아키텍처 체크리스트를 확인한다:
   - `docs/ARCHITECTURE.md` 8절의 코드 구조와 의존 방향을 따르는가?
   - `docs/ADR.md`의 기술 스택을 벗어나지 않았는가?
   - `docs/DEVELOPMENT.md`의 "반드시 지킬 규칙"을 위반하지 않았는가?
4. 결과에 따라 `phases/0-project-setup/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"`
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 (API 키, 외부 인증, 수동 설정 등) → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- `docker push`, `docker login`을 하지 마라. 이유: 이미지는 `main`에 합쳐진 코드만 CI가 올린다(D-36). 명령 가드가 막는다.
- `diegesis-smoke`가 아닌 프로젝트의 볼륨을 지우지 마라. 직접 실행하는 `docker compose down -v`는 명령 가드가 막는다. 이유: 개발용 데이터가 사라진다.
- `docker build`나 `docker buildx build`를 직접 쓰지 마라. 이유: D-41.
- `Dockerfile`이나 compose 파일에 비밀값을 적거나 `.env`를 복사하지 마라. 이유: Docker Hub 저장소가 공개다(D-37).
- 데이터베이스 이미지를 `compose.yaml`의 `db` 서비스 밖에 다시 적지 마라. 이유: 통합 테스트가 그 값을 읽는다(DEVELOPMENT.md 1절).
- `README.md`를 고치지 마라. 이유: step 5의 일이다.
- CI workflow를 만들지 마라. 이유: step 6의 일이다.
- 기존 테스트를 깨뜨리지 마라
- `MANUAL.md`의 항목을 체크하지 마라. 이유: 그 항목은 사람이 직접 본 것만 체크한다.
