# Diegesis BE

Diegesis는 소설의 분위기에 맞는 음악을 재생해 주는 전자책 플랫폼이며, 이 레포는 그 백엔드입니다. 프론트엔드와 AI 파이프라인은 각각 별도의 레포([FE](https://github.com/diegesis-labs/FE), [AI](https://github.com/diegesis-labs/AI))에 있습니다.

## 현재 상태

지금은 1차 마일스톤(MVP)을 위한 설계 문서, 개발 도구와 작업 절차, 그리고 로그인까지 갖춘 서버가 준비되어 있습니다. 서버와 데이터베이스를 로컬에서 띄울 수 있고, 서버에는 헬스체크, Google 로그인, 로그아웃, 내 정보 조회(`GET /api/me`)가 있습니다. 로그인은 허용 목록에 있는 사람만 할 수 있습니다. 책, 선곡 같은 기능은 아직 구현하지 않았습니다.

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
| http://localhost:8080/api/docs | API 문서 화면입니다. 지금 있는 엔드포인트를 보고 직접 요청을 보내 볼 수 있습니다. 다만 로그아웃처럼 상태를 바꾸는 요청은 출처 확인 때문에 이 주소의 화면에서 보내면 `403 ORIGIN_MISMATCH`로 거절됩니다([API.md 2.4절](docs/API.md#24-상태를-바꾸는-요청의-출처-확인)). 그런 요청은 프론트엔드의 개발 서버가 백엔드로 넘겨 주는 주소의 화면(http://localhost:5173/api/docs)에서 보냅니다. |

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

- **compose는 `.env`에서 `FRONTEND_URL`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` 세 값만 서버에 넘깁니다.** `DATABASE_URL` 같은 나머지 값은 넘기지 않으므로, `.env`가 없어도 서버는 뜨지만 Google 로그인은 되지 않습니다. 자세한 것은 [docs/CONFIGURATION.md](docs/CONFIGURATION.md#2-처음-시작할-때) 2절에 있습니다.
- **이미지는 compose로만 빌드합니다.** `docker build`를 직접 쓰지 않습니다. `docker build`로 만든 이미지가 로컬 이미지 저장소에 실리는지는 각자의 Docker builder 설정에 따라 다르지만, compose는 그 설정과 관계없이 이미지를 싣기 때문입니다([docs/ADR.md](docs/ADR.md#adr-015-로컬-실행-구성과-헬스체크)의 ADR-015). 자세한 규칙은 [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md#1-개발-환경-준비) 1절에 있습니다.
- **CPU 아키텍처에 맞춰 따로 설정할 것은 없습니다.** compose는 각자의 컴퓨터에서 그 컴퓨터의 CPU 아키텍처로 이미지를 빌드하므로, Apple Silicon Mac과 Windows에서 같은 명령을 그대로 쓰면 됩니다. Docker Hub에는 CI가 `linux/amd64` 이미지만 올리지만, 그 이미지는 배포 환경에서 받는 것이므로 로컬 개발에는 받지 않습니다([docs/ADR.md](docs/ADR.md#adr-014-ci-검사와-컨테이너-이미지)의 ADR-014).

## 허용 목록에 사람 넣고 빼기

서비스는 허용 목록에 이메일이 있는 사람만 쓸 수 있습니다. 허용 목록은 데이터베이스의 `allowed_emails` 테이블이며, 관리 API가 없으므로 아래 SQL로 직접 넣고 뺍니다([docs/ADR.md](docs/ADR.md#adr-024-허용-목록의-관리와-확인)의 ADR-024). 바꾼 내용은 서버를 다시 띄우지 않아도 다음 요청부터 적용됩니다.

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

## 로컬에서 Google 로그인 점검하기

백엔드 담당자는 프론트엔드 레포 없이 로컬에서 실제 Google 계정으로 로그인과 로그아웃을 끝까지 확인할 수 있습니다. 점검 스크립트(`scripts/login_check.py`)는 프론트엔드의 개발 서버를 흉내 내는 대역 서버를 `FRONTEND_URL`에 띄우고, 사람이 할 일을 차례로 안내합니다. 사람은 자기 브라우저의 게스트 창에서 대역 서버의 화면을 열어 안내대로 버튼을 누르고, Google 화면에서 계정을 고릅니다. 스크립트는 브라우저를 열거나 조작하지 않고, 대역 서버를 지나가는 요청과 응답으로 브라우저의 상태를 봅니다. 이렇게 점검하는 이유는 [docs/ADR.md](docs/ADR.md#adr-026-로컬에서-실제-google-로그인을-점검하는-방법)의 ADR-026과 [ADR-031](docs/ADR.md#adr-031-로컬-로그인-점검에서-브라우저를-다루는-방법)에 있습니다.

### 준비할 것

- 로컬의 돌아올 주소 `http://localhost:5173/api/auth/google/callback`을 등록한 Google OAuth 클라이언트의 ID와 비밀값. 주소를 등록하는 곳은 [docs/INFRA.md](docs/INFRA.md#35-google-로그인-설정) 3.5절에 있습니다.
- 실제 Google 계정 두 개. 계정 A는 허용 목록에 넣고, 계정 B는 넣지 않습니다.
- 게스트 창을 열 수 있는 브라우저. Chrome에서는 오른쪽 위의 프로필 메뉴에서 '게스트'를 고르면 게스트 창이 열립니다.
- 켜 둔 Docker Desktop.
- [개발 환경](#개발-환경)의 `uv sync`를 마친 레포.

### 점검하는 순서

아래 명령은 레포의 최상위 폴더에서 실행합니다. 명령의 `a@example.com`과 `b@example.com`은 계정 A와 계정 B의 이메일로 바꿉니다.

**1. `.env`를 만듭니다.** 견본을 복사한 뒤 `GOOGLE_CLIENT_ID`와 `GOOGLE_CLIENT_SECRET`을 채웁니다. `FRONTEND_URL`은 `http://localhost:5173` 그대로 둡니다. 서버가 만드는 돌아올 주소와 대역 서버가 뜨는 주소가 모두 이 값을 따르기 때문입니다. `.env`는 커밋하지 않습니다.

```bash
cp .env.example .env   # 견본을 복사해 .env를 만듭니다.
```

**2. compose로 서버를 띄웁니다.** `.env`를 바꾼 뒤에는 이 명령으로 다시 띄워야 서버가 새 값을 받습니다. 8080이나 5432 포트를 다른 프로그램이 쓰고 있으면 [포트가 이미 쓰이고 있을 때](#포트가-이미-쓰이고-있을-때)대로 띄우고, 4번의 점검 스크립트에도 같은 `API_PORT`와 `DB_PORT`를 환경변수로 넘깁니다.

```bash
docker compose up --build -d --wait   # 데이터베이스, 마이그레이션, 서버를 띄웁니다. 서버는 .env의 세 값을 받습니다.
```

**3. 계정 A를 허용 목록에 `user`로 넣습니다.** 계정 B는 넣지 않습니다. 이 SQL의 뜻과 다른 SQL은 [허용 목록에 사람 넣고 빼기](#허용-목록에-사람-넣고-빼기)에 있습니다.

```bash
docker compose exec db psql -U diegesis -d diegesis -c "INSERT INTO allowed_emails (email, role) VALUES (lower('a@example.com'), 'user') ON CONFLICT (email) DO UPDATE SET role = EXCLUDED.role;"   # 계정 A를 user로 넣습니다.
```

**4. 점검 스크립트를 실행합니다.** 프론트엔드의 개발 서버가 5173 포트를 쓰고 있으면 끄고 실행합니다. 대역 서버가 그 포트에 떠야 하기 때문입니다.

```bash
uv run python scripts/login_check.py --allowed-email a@example.com --denied-email b@example.com   # 계정 A의 로그인과 로그아웃, 계정 B의 로그인 시도를 차례로 점검합니다.
```

**5. 스크립트의 안내대로 게스트 창에서 버튼을 누릅니다.** 스크립트는 `>>>`로 시작하는 줄로 할 일을 하나씩 알려 주고, 그 요청이 대역 서버를 지나가면 그 시점의 상태를 출력한 뒤 다음 할 일을 알려 줍니다. 대역 서버의 화면에는 [Google로 로그인], [내 정보 확인], [로그아웃]의 세 버튼이 있으며, 버튼은 프론트엔드가 보내는 것과 같은 요청을 보냅니다. 안내하는 순서는 다음과 같습니다.

| 점검 | 할 일 |
| --- | --- |
| 점검 1 (계정 A) | 새 게스트 창에서 `http://localhost:5173/`을 열고 [내 정보 확인]을 누릅니다. |
| | [Google로 로그인]을 누르고 Google 화면에서 계정 A를 고릅니다. |
| | 첫 화면으로 돌아오면 [내 정보 확인]을 누릅니다. |
| | [로그아웃]을 누릅니다. 화면이 로그아웃한 뒤 내 정보를 한 번 더 확인합니다. |
| 점검 2 (계정 B) | 열려 있는 게스트 창을 모두 닫고, 새 게스트 창에서 `http://localhost:5173/`을 열고 [내 정보 확인]을 누릅니다. |
| | [Google로 로그인]을 누르고 Google 화면에서 계정 B를 고릅니다. |
| | 허용 목록 밖 안내 주소로 돌아오면 [내 정보 확인]을 누릅니다. |

게스트 창을 쓰는 이유는 점검마다 쿠키가 없는 브라우저에서 시작해야 하고, 점검에 쓴 Google 계정의 로그인이 평소의 브라우저 프로필에 남지 않아야 하기 때문입니다. 게스트 창은 모두 닫으면 쿠키와 Google의 로그인이 지워집니다. 비밀번호를 물으면 게스트 창에서 직접 넣습니다. 스크립트는 Google 화면에 아무것도 입력하지 않고, 비밀번호를 받지도 않습니다.

스크립트는 할 일마다 그 요청이 대역 서버를 지나가기를 최대 5분 기다립니다. 5분 안에 지나가지 않으면 무엇을 기다렸는지 보여 주고 끝나므로, 처음부터 다시 돌립니다. 이때 점검 전의 테이블 상태가 바뀌어 있으면 스크립트가 상태를 맞추는 SQL을 보여 줍니다.

점검을 마치면 게스트 창을 모두 닫고, `docker compose down`으로 서버를 내립니다.

### 결과를 읽는 법

스크립트는 시점마다 `allowed_emails`, `users`, `login_sessions`의 상태와 브라우저의 상태(주소, 쿠키, 보낸 쿠키, `GET /api/me`의 응답)를 출력합니다. 시점은 계정 A의 로그인 전, 로그인 후, 로그아웃 전, 로그아웃 후와 계정 B의 로그인 전, 로그인 시도 후입니다. 시점마다 기대하는 상태는 [docs/backlog/epic-1/testcase.md](docs/backlog/epic-1/testcase.md#로컬-로그인-점검의-테이블-상태)의 "로컬 로그인 점검의 테이블 상태"에 있습니다. 스크립트도 그 표로 판정해서, 표와 다른 것이 있으면 끝에 모아 보여 주고 0이 아닌 코드로 끝납니다. 종료 코드마다의 뜻은 `uv run python scripts/login_check.py --help`로 봅니다.

브라우저의 상태는 대역 서버가 자신을 지나간 요청과 응답으로 알아낸 것입니다. 주소는 게스트 창이 마지막으로 연 대역 서버의 화면이고, 쿠키는 대역 서버가 본 `Set-Cookie`를 브라우저의 규칙대로 쌓은 것이고, 보낸 쿠키는 그 시점의 요청에 브라우저가 실제로 붙인 쿠키의 이름입니다. 브라우저가 붙인 쿠키가 쌓은 쿠키와 다르면(받은 쿠키를 붙이지 않았거나, 이번 점검에서 심지 않은 쿠키를 붙였으면) 그것도 표와 다른 것으로 보여 줍니다. 이번 점검에서 심지 않은 쿠키가 보이면 새 게스트 창에서 시작했는지 확인합니다.

쿠키의 값과 `token_hash`의 값은 출력하지 않고, `token_hash`가 쿠키 값의 SHA-256과 같은지만 출력합니다.

스크립트는 점검을 시작하기 전에 서버가 응답하는지, 서버가 Google 클라이언트 ID와 돌아올 주소를 제대로 받았는지, 점검 전의 테이블 상태가 표의 "로그인 전"과 같은지, 5173 포트가 비어 있는지를 확인합니다. 하나라도 어긋나면 점검을 시작하지 않고, 어긋난 것과 고치는 방법을 보여 준 뒤 끝납니다. 점검 전의 테이블 상태가 맞지 않을 때에는 상태를 맞추는 SQL과 데이터베이스에 접속하는 명령을 보여 줍니다. 스크립트는 개발용 데이터베이스를 읽기만 하므로 그 SQL을 직접 실행하지 않습니다. 사람이 그 SQL을 실행한 뒤 스크립트를 다시 돌립니다. 예를 들어 한 번 점검한 계정 A의 `users` 행은 로그아웃한 뒤에도 남아 있으므로, 같은 계정으로 다시 점검하면 스크립트는 그 행을 지우는 SQL을 보여 줍니다.

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
scripts/        # 검사 스크립트, harness, 로컬 로그인 점검 스크립트
docs/           # 문서
phases/         # harness가 실행한 작업의 기록
.claude/        # Claude Code의 설정, 명령, 스킬
compose.yaml    # 로컬에서 데이터베이스, 마이그레이션, 서버를 함께 띄우는 설정
Dockerfile      # 서버의 컨테이너 이미지를 만드는 방법
.dockerignore   # 이미지를 빌드할 때 넘기지 않을 파일. .env 같은 비밀값을 여기서 뺀다.
alembic.ini     # 마이그레이션 도구(Alembic)의 설정
```

각 폴더의 역할은 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#8-코드-구조)에 자세히 적혀 있습니다.
