# Step 5: readme

## 읽어야 할 파일

먼저 아래 파일들을 읽고 이 step의 근거와 설계 의도를 파악하라:

- `docs/backlog/epic-0/E0-project-setup.md` — S0.6
- `docs/backlog/epic-0/testcase.md` — "이 Epic에서 판정하지 않는 것"의 S0.6 항목
- `docs/DECISIONS.md` — D-37, D-40, D-41
- `README.md` — 지금의 내용과 문체
- `compose.yaml`, `Dockerfile`, `scripts/compose-smoke.sh`, `.env.example` (step 1, 4)
- `app/__main__.py`, `app/health/router.py` (step 0, 3)

이전 step에서 만들어진 코드를 꼼꼼히 읽고, 설계 의도를 이해한 뒤 작업하라.

## 작업

### 0. Docker 확인

`docker info`가 실패하면 고치려 하지 말고 `index.json`의 이 step을 `"status": "blocked"`, `"blocked_reason": "Docker에 닿을 수 없다 — Docker Desktop을 켜야 한다"`로 적고 즉시 중단하라.

### 1. `README.md`를 고친다

이 레포를 처음 받은 팀원이 README만 보고 서버와 데이터베이스를 띄울 수 있어야 한다. 팀원 중에는 Apple Silicon Mac을 쓰는 사람도, Windows를 쓰는 사람도 있다.

- **"현재 상태"** — 서버의 소스코드가 아직 없다는 문장을 지금 상태에 맞게 고친다. 헬스체크만 있고 기능은 아직 없다는 정도로 적는다.
- **"개발 환경"** — Docker Desktop을 설치하고 켜 두어야 한다는 것을 더한다. 검사 명령의 통합 테스트가 Docker로 데이터베이스를 띄우기 때문이다.
- **새 절 "로컬에서 서버 띄우기"** — "개발 환경" 바로 뒤에 둔다. 아래 내용을 담는다.
  - 처음 한 번, 그리고 코드를 바꾼 뒤에 쓰는 명령. 이미지를 레포에서 빌드하고 데이터베이스, 마이그레이션, 서버를 함께 띄운다(예: `docker compose up --build -d --wait`).
  - 떠 있는지 확인하는 방법. 헬스체크 주소와 API 문서 화면의 주소(`/api/docs`)를 적는다.
  - 서버의 로그를 보는 명령, 내리는 명령(`docker compose down`).
  - 데이터베이스의 데이터는 볼륨에 남아서 내렸다 다시 띄워도 유지된다는 것. 데이터까지 지우는 명령(`docker compose down -v`)은 따로 적고, 되돌릴 수 없다는 것을 함께 적는다.
  - 포트가 이미 쓰이고 있을 때 바꾸는 방법(`API_PORT`, `DB_PORT`).
  - compose로 띄울 때에는 `.env`가 필요 없다는 것. 접속 주소를 compose 파일이 넘긴다(CONFIGURATION.md 2절).
  - **이미지는 compose로만 빌드한다는 규칙과 그 이유.** `docker build`를 직접 쓰지 않는다. `docker build`의 결과가 로컬 이미지 저장소에 실리는지는 각자의 Docker builder 설정에 따라 다르기 때문이다(D-41). 자세한 규칙은 `docs/DEVELOPMENT.md` 1절로 잇는다.
  - CPU 아키텍처에 관한 안내. 각자의 컴퓨터는 자기 CPU 아키텍처로 빌드하므로 Apple Silicon Mac과 Windows에서 따로 설정할 것이 없다. Docker Hub에는 CI가 `linux/amd64` 이미지만 올리며, 그 이미지는 배포용이라 로컬 개발에는 받지 않는다(D-37).
  - 마이그레이션은 서버보다 먼저 한 번 실행되고 끝나는 서비스라는 것(D-40). `docker compose ps -a`에 그 서비스가 종료된 상태로 보이는 것이 정상이다.
- **"폴더 구조"** — `compose.yaml`, `Dockerfile`처럼 이번 Epic에서 생긴 최상위 파일 가운데 팀원이 알아야 할 것을 더한다.

### 2. 문체

- 이 레포 README의 문체를 따른다. "~합니다"로 끝나는 문장을 쓰고, 명령은 코드 블록에 넣고 같은 줄에 `# ~합니다.` 꼴의 주석을 단다. 지금 README의 "개발 환경" 절이 그 예다.
- `docs/DECISIONS.md`의 "문서 작성 규칙"을 지킨다. 특히 버전을 README에 적지 마라. 이유: 버전은 DEVELOPMENT.md 1절의 표에 적힌 파일에만 적는다.
- 한 가지 정보는 한 문서에만 적는다. 설정값의 목록은 CONFIGURATION.md에, 개발 규칙은 DEVELOPMENT.md에 있으니 README에서는 링크로 잇는다.

## Acceptance Criteria

README에 적은 명령을 **적힌 그대로** 실행해서 확인한다. 이 step에는 테스트 케이스가 없다(testcase.md).

```bash
lsof -nP -iTCP:8080 -sTCP:LISTEN; lsof -nP -iTCP:5432 -sTCP:LISTEN   # 비어 있는지 먼저 본다
# README의 "로컬에서 서버 띄우기"에 적은 명령을 순서대로 실행한다
scripts/check.sh
```

- 8080이나 5432가 이미 쓰이고 있으면, README에 적은 포트 바꾸는 방법 그대로 `API_PORT`와 `DB_PORT`를 바꿔서 실행한다. 다른 방법으로 우회하지 마라. 이유: 그 안내도 README가 맞는지 확인할 대상이다.
- 띄우는 명령, 헬스체크 확인, 로그 보기, 내리기(`docker compose down`)를 실제로 실행한다. 헬스체크의 응답이 `{"status":"ok"}`인지 본다.
- 데이터까지 지우는 명령(`docker compose down -v`)은 실행하지 마라. 명령 가드가 막는다.

**반증 조건** — 없음. 이 step은 판정하는 로직을 만들지 않는다. 그 대신 README의 명령 가운데 하나라도 적힌 그대로 실행해서 실패하면 README가 틀린 것이다.

## 검증 절차

1. 위 AC를 실행한다. 확인이 끝나면 `docker compose down`으로 내린다.
2. README를 처음 읽는 팀원의 입장에서 다시 읽는다. Windows를 쓰는 팀원이 따라 할 때 막힐 곳(경로 구분자, 셸에 따라 다른 문법, 환경변수를 넘기는 문법)이 없는지 본다. 셸마다 문법이 다른 명령은 피하거나, 두 가지를 모두 적는다.
3. 아키텍처 체크리스트를 확인한다:
   - `docs/ARCHITECTURE.md` 8절의 코드 구조와 의존 방향을 따르는가?
   - `docs/ADR.md`의 기술 스택을 벗어나지 않았는가?
   - `docs/DEVELOPMENT.md`의 "반드시 지킬 규칙"을 위반하지 않았는가?
4. 결과에 따라 `phases/0-project-setup/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"`
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 (API 키, 외부 인증, 수동 설정 등) → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- README에 버전을 적지 마라. 이유: 위 2번.
- README에 Docker Hub의 사용자 이름, 이미지의 전체 이름, 토큰을 적지 마라. 이유: 그 값은 GitHub의 secrets와 variable에만 둔다(D-37).
- 팀원에게 Docker Hub에서 이미지를 받으라고 안내하지 마라. 이유: 팀원은 레포에서 compose로 빌드한다(D-37).
- `docker build`나 `docker buildx build`를 안내하지 마라. 이유: D-41.
- README 밖의 문서(`docs/`)를 고치지 마라. 이유: 이번 Epic의 문서 개정은 이미 끝났다. 고칠 곳을 찾으면 summary에 적어라.
- 코드, `compose.yaml`, `Dockerfile`을 고치지 마라. README의 명령이 동작하지 않는 원인이 그쪽에 있으면 고치지 말고 `"status": "blocked"`로 그 원인을 적어라. 이유: 이 step은 문서만 다룬다. 컨테이너 설정은 step 4의 테스트와 스모크가 지킨다.
- 기존 테스트를 깨뜨리지 마라
- `MANUAL.md`의 항목을 체크하지 마라. 이유: 그 항목은 사람이 직접 본 것만 체크한다.
