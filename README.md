# Diegesis BE

Diegesis는 소설의 분위기에 맞는 음악을 재생해 주는 전자책 플랫폼이며, 이 레포는 그 백엔드입니다. 프론트엔드와 AI 파이프라인은 각각 별도의 레포([FE](https://github.com/diegesis-labs/FE), [AI](https://github.com/diegesis-labs/AI))에 있습니다.

## 현재 상태

지금은 1차 마일스톤(MVP)을 위한 설계 문서, 개발 도구와 작업 절차, 그리고 서버의 뼈대가 준비되어 있습니다. 서버와 데이터베이스를 로컬에서 띄울 수 있지만, 서버는 헬스체크에만 응답합니다. 로그인, 책, 선곡 같은 기능은 아직 구현하지 않았습니다.

## 개발 환경

먼저 [Docker Desktop](https://www.docker.com/products/docker-desktop/)을 설치하고 켜 둡니다. 검사 명령의 통합 테스트가 Docker로 데이터베이스를 띄우기 때문입니다. 그다음 아래 명령을 실행합니다.

```bash
uv sync             # Python과 개발 도구를 설치합니다.
scripts/check.sh    # 린트, 서식, 타입, 테스트를 검사합니다.
```

코드를 쓸 때 지키는 규칙은 [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)에, 에이전트에게 구현을 맡기는 절차는 [docs/HARNESS.md](docs/HARNESS.md)에 있습니다.

## 로컬에서 서버 띄우기

docker compose로 데이터베이스, 마이그레이션, 서버를 함께 띄웁니다. 아래 명령은 레포의 최상위 폴더에서 실행하며, 포트를 바꾸는 명령을 빼면 macOS의 터미널과 Windows의 PowerShell에서 똑같이 쓸 수 있습니다.

```bash
docker compose up --build -d --wait   # 이미지를 빌드하고 데이터베이스, 마이그레이션, 서버를 띄운 뒤 서버가 응답할 때까지 기다립니다.
```

처음 띄울 때, 그리고 코드를 바꾼 뒤에 이 명령을 씁니다. `--build`가 지금 레포에 있는 코드로 이미지를 다시 빌드하므로, 코드를 바꾼 뒤에 이 옵션을 빼면 바꾸기 전의 코드로 서버가 뜹니다. 처음 띄울 때에는 베이스 이미지를 받고 의존성을 설치하느라 몇 분이 걸립니다.

명령이 끝나면 브라우저에서 아래 주소를 열어 서버가 떠 있는지 확인합니다.

| 주소 | 보이는 것 |
| --- | --- |
| http://localhost:8080/api/health | 헬스체크의 응답입니다. `{"status":"ok"}`가 보이면 서버가 떠 있는 것입니다. |
| http://localhost:8080/api/docs | API 문서 화면입니다. 지금 있는 엔드포인트를 보고 직접 요청을 보내 볼 수 있습니다. |

그 밖에 자주 쓰는 명령은 다음과 같습니다.

```bash
docker compose ps -a                # 서비스마다 상태를 봅니다.
docker compose logs --tail 50 api   # 서버의 로그 가운데 마지막 50줄을 봅니다.
docker compose logs migrate         # 마이그레이션의 로그를 봅니다. 서버가 뜨지 않을 때 먼저 확인합니다.
docker compose down                 # 서버와 데이터베이스를 내립니다. 데이터베이스의 데이터는 남습니다.
```

서버의 로그에는 compose가 서버의 상태를 확인하려고 몇 초마다 보내는 헬스체크 요청이 함께 찍힙니다. 그래서 로그가 금방 길어지므로 `--tail`로 마지막 몇 줄만 보는 것이 편합니다.

`docker compose ps -a`를 실행하면 `migrate` 서비스가 `Exited (0)`, 곧 종료된 상태로 보이며, 이것이 정상입니다. `migrate`는 서버와 같은 이미지로 마이그레이션을 한 번 실행하고 끝나는 서비스이고, 서버는 이 서비스가 성공한 뒤에야 뜹니다([docs/ADR.md](docs/ADR.md#adr-015-로컬-실행-구성과-헬스체크)의 ADR-015). 종료 코드가 0이 아니라면 마이그레이션이 실패한 것이므로 `docker compose logs migrate`로 원인을 봅니다.

### 데이터베이스의 데이터

데이터베이스의 데이터는 Docker 볼륨에 저장되므로, `docker compose down`으로 내렸다가 다시 띄워도 그대로 남아 있습니다. 데이터까지 모두 지우고 빈 데이터베이스에서 다시 시작하려면 아래 명령을 씁니다. 지운 데이터는 되돌릴 수 없습니다.

```bash
docker compose down -v        # 서버와 데이터베이스를 내리고, 데이터베이스의 데이터까지 지웁니다.
```

### 포트가 이미 쓰이고 있을 때

서버는 8080 포트로, 데이터베이스는 5432 포트로 띄웁니다. 로컬에 설치한 PostgreSQL처럼 다른 프로그램이 그 포트를 쓰고 있어서 띄우지 못하면, `API_PORT`와 `DB_PORT`로 포트를 바꿉니다. 환경변수를 넘기는 문법은 셸마다 다르므로, 쓰는 셸에 맞는 명령을 고릅니다.

```bash
# macOS의 터미널(zsh, bash)
API_PORT=8081 DB_PORT=5433 docker compose up --build -d --wait   # 서버를 8081 포트로, 데이터베이스를 5433 포트로 띄웁니다.
```

```powershell
# Windows의 PowerShell
$env:API_PORT="8081"; $env:DB_PORT="5433"; docker compose up --build -d --wait   # 서버를 8081 포트로, 데이터베이스를 5433 포트로 띄웁니다.
```

포트를 바꿨다면 위에서 확인한 주소의 `8080`도 바꾼 값으로 고쳐서 엽니다. 컨테이너끼리는 Docker 안의 주소로 닿으므로, 포트를 바꾸더라도 서버의 설정은 고치지 않아도 됩니다. 그리고 macOS의 터미널에서는 이렇게 넘긴 값이 그 명령 한 번에만 적용되므로 다시 띄울 때에도 같이 적어야 하며, PowerShell에서는 그 창을 닫을 때까지 값이 유지됩니다.

### 알아 둘 것

- **`.env` 파일이 필요 없습니다.** 서버가 데이터베이스에 접속하는 주소는 `compose.yaml`이 컨테이너에 직접 넘기며, `.env`가 있더라도 그 안의 설정값은 컨테이너에 들어가지 않습니다. `.env`는 서버를 compose 밖에서 직접 실행할 때 쓰며, 설정값의 목록과 뜻은 [docs/CONFIGURATION.md](docs/CONFIGURATION.md#2-처음-시작할-때)에 있습니다.
- **이미지는 compose로만 빌드합니다.** `docker build`를 직접 쓰지 않습니다. `docker build`로 만든 이미지가 로컬 이미지 저장소에 실리는지는 각자의 Docker builder 설정에 따라 다르지만, compose는 그 설정과 관계없이 이미지를 싣기 때문입니다([docs/ADR.md](docs/ADR.md#adr-015-로컬-실행-구성과-헬스체크)의 ADR-015). 자세한 규칙은 [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md#1-개발-환경-준비) 1절에 있습니다.
- **CPU 아키텍처에 맞춰 따로 설정할 것은 없습니다.** compose는 각자의 컴퓨터에서 그 컴퓨터의 CPU 아키텍처로 이미지를 빌드하므로, Apple Silicon Mac과 Windows에서 같은 명령을 그대로 쓰면 됩니다. Docker Hub에는 CI가 `linux/amd64` 이미지만 올리지만, 그 이미지는 배포 환경에서 받는 것이므로 로컬 개발에는 받지 않습니다([docs/ADR.md](docs/ADR.md#adr-014-ci-검사와-컨테이너-이미지)의 ADR-014).

## 허용 목록에 사람 넣고 빼기

서비스는 허용 목록에 이메일이 있는 사람만 쓸 수 있습니다. 허용 목록은 데이터베이스의 `allowed_emails` 테이블이며, 관리 API가 없으므로 아래 SQL로 직접 넣고 뺍니다([docs/ADR.md](docs/ADR.md#adr-024-허용-목록의-관리와-확인)의 ADR-024). 바꾼 내용은 서버를 다시 띄우지 않아도 다음 요청부터 적용됩니다. 이 테이블은 로그인 기능(Epic 1)과 함께 만들어지므로, 그 전에는 아래 SQL이 동작하지 않습니다.

로컬에서는 compose로 띄운 데이터베이스에 아래 명령으로 접속합니다. 접속한 뒤 SQL을 입력하고, `\q`로 빠져나옵니다.

```bash
docker compose exec db psql -U diegesis -d diegesis
```

SQL 한 줄만 실행할 때에는 `-c`를 씁니다. 예를 들어 자기 자신을 관리자로 넣으려면 다음과 같이 실행합니다. 이 명령은 macOS의 터미널과 Windows의 PowerShell에서 똑같이 쓸 수 있습니다.

```bash
docker compose exec db psql -U diegesis -d diegesis -c "INSERT INTO allowed_emails (email, role) VALUES (lower('me@example.com'), 'admin') ON CONFLICT (email) DO UPDATE SET role = EXCLUDED.role;"
```

자주 쓰는 SQL은 다음과 같습니다. 이메일은 소문자로만 저장되므로 언제나 `lower()`로 감쌉니다. 역할은 `user`와 `admin` 가운데 하나입니다.

```sql
-- 한 사람을 넣습니다. 이미 있으면 역할만 바꿉니다.
INSERT INTO allowed_emails (email, role)
VALUES (lower('reader@example.com'), 'user')
ON CONFLICT (email) DO UPDATE SET role = EXCLUDED.role;

-- 여러 사람을 한 번에 넣습니다. 이미 있는 사람은 건너뜁니다.
INSERT INTO allowed_emails (email, role)
VALUES (lower('tester1@example.com'), 'user'),
       (lower('tester2@example.com'), 'user')
ON CONFLICT (email) DO NOTHING;

-- 역할을 바꿉니다.
UPDATE allowed_emails SET role = 'admin' WHERE email = lower('reader@example.com');

-- 한 사람을 뺍니다. 그 사람의 로그인 상태도 같은 트랜잭션에서 함께 지웁니다.
-- 그 사람은 다음 요청부터 막히고, 다시 로그인하려 하면 허용 목록 밖이라는 안내를 받습니다.
BEGIN;
DELETE FROM login_sessions
WHERE user_id IN (SELECT id FROM users WHERE email = lower('reader@example.com'));
DELETE FROM allowed_emails WHERE email = lower('reader@example.com');
COMMIT;

-- 허용 목록을 봅니다.
SELECT email, role, created_at FROM allowed_emails ORDER BY created_at;
```

허용 목록에서 뺐다가 다시 넣은 사람은 다시 로그인해야 합니다. 백엔드는 그 사람이 허용 목록에 들어간 시각보다 먼저 만든 로그인 상태를 받아들이지 않기 때문입니다([docs/ADR.md](docs/ADR.md#adr-027-로그인-흐름과-로그인-상태의-보안-보강)의 ADR-027). 역할만 바꾸는 SQL은 로그인 상태에 영향을 주지 않습니다.

운영 환경의 데이터베이스에도 같은 SQL을 씁니다. 운영 환경의 데이터베이스에 접속하는 방법은 PostgreSQL을 둘 곳과 함께 정합니다([docs/INFRA.md](docs/INFRA.md#32-postgresql을-어디에-둘-것인가) 3.2절).

## 백엔드가 하는 일

- 허용된 사용자가 Google 계정으로 로그인하면 책의 본문을 제공합니다.
- 독자가 페이지를 넘길 때마다 지금 보이는 장면에 어울리는 곡을 골라 줍니다.
- 어떤 장면에 어떤 곡이 나갔고 독자가 어떻게 반응했는지를 기록해서, 평가에 쓸 수 있게 합니다.
- AI 레포가 분석한 결과물을 받아서 검증하고 저장합니다.

## 기술스택

Python, FastAPI, PostgreSQL(pgvector), Docker를 씁니다. 각 기술을 고른 이유는 [docs/ADR.md](docs/ADR.md)에 있습니다.

## 문서

| 문서 | 내용 |
| --- | --- |
| [docs/PRD.md](docs/PRD.md) | 왜 만드는지, 무엇을 만드는지 |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 전체 구성, 동작 흐름, 데이터 모델, 코드 구조 |
| [docs/ADR.md](docs/ADR.md) | 기술적 결정과 그 이유 |
| [docs/API.md](docs/API.md) | 프론트엔드와 주고받는 요청과 응답의 형식 |
| [docs/AI_CONTRACT.md](docs/AI_CONTRACT.md) | AI 레포가 넘겨주는 결과물의 파일 규격 |
| [docs/CONFIGURATION.md](docs/CONFIGURATION.md) | 설정값의 목록과 바꾸는 방법 |
| [docs/INFRA.md](docs/INFRA.md) | 배포 환경에 관해 정해진 것과 정해야 할 것 |
| [docs/DECISIONS.md](docs/DECISIONS.md) | 제품의 범위와 운영에 관한 결정 |
| [docs/GLOSSARY.md](docs/GLOSSARY.md) | 문서에 나오는 용어의 뜻 |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | 개발 환경, 검사 명령, 테스트와 커밋의 규칙 |
| [docs/HARNESS.md](docs/HARNESS.md) | 에이전트에게 구현을 맡기는 절차 |
| [docs/backlog/README.md](docs/backlog/README.md) | 구현할 일의 목록 |

## 폴더 구조

```
app/            # 서버 코드. 기능별로 폴더를 나눈다.
migrations/     # 데이터베이스 구조 변경 이력
tests/          # 테스트
scripts/        # 검사 스크립트와 harness
docs/           # 문서
phases/         # harness가 실행한 작업의 기록
.claude/        # Claude Code의 설정, 명령, 스킬
compose.yaml    # 로컬에서 데이터베이스, 마이그레이션, 서버를 함께 띄우는 설정
Dockerfile      # 서버의 컨테이너 이미지를 만드는 방법
.dockerignore   # 이미지를 빌드할 때 넘기지 않을 파일. .env 같은 비밀값을 여기서 뺀다.
alembic.ini     # 마이그레이션 도구(Alembic)의 설정
```

각 폴더의 역할은 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#8-코드-구조)에 자세히 적혀 있습니다.
