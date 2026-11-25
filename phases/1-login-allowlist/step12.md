# Step 12: readme

## 읽어야 할 파일

먼저 아래 파일들을 읽고 이 step의 근거와 설계 의도를 파악하라:

- `docs/backlog/epic-1/E1-login-allowlist.md` — S1.6(T1.6.1과 "못 박을 것"), S1.7의 T1.7.3과 "MANUAL 점검표"
- `docs/backlog/epic-1/testcase.md` — TC-1.6.1, 그리고 "로컬 로그인 점검의 테이블 상태"(README가 점검의 결과를 어떻게 읽는지 안내할 때 가리킨다)
- `docs/ADR.md` — ADR-024, ADR-026, ADR-027의 "로그인 상태의 수명"
- `docs/INFRA.md` 3.5절 — Google 콘솔에 등록하는 돌아올 주소
- `README.md` 전체 — 특히 "현재 상태", "로컬에서 서버 띄우기"의 "알아 둘 것", "허용 목록에 사람 넣고 빼기"
- `compose.yaml` (step 0) — 서버가 `.env`에서 받는 세 값
- `scripts/login_check.py`의 독스트링과 `--help` (step 10, 11)
- `app/auth/models.py`와 마이그레이션 (step 1), `tests/conftest.py`의 `clean_db`
- `phases/1-login-allowlist/MANUAL.md` — 사람이 할 점검의 준비 순서(README와 어긋나지 않아야 한다)

`docs/CONFIGURATION.md`(2절 "처음 시작할 때" 포함)는 프롬프트에 이미 들어 있다.

이전 step에서 만들어진 코드를 꼼꼼히 읽고, 설계 의도를 이해한 뒤 작업하라.

## 작업

README와 CONFIGURATION.md를 이 Epic의 결과에 맞추고, README의 허용 목록 SQL이 실제 스키마에서 도는지 확인하는 테스트를 만든다.

### 1. README의 허용 목록 SQL 테스트 — `tests/infra/test_readme_allowlist.py`

TC-1.6.1. `integration`이며 `clean_db`를 쓴다.

- README에서 "허용 목록에 사람 넣고 빼기" 절을 **제목으로 찾아**, 그 절 안의 ` ```sql ` 블록을 읽는다. 줄 번호로 찾지 마라. 이유: README의 다른 절이 바뀌면 줄 번호가 밀린다.
- **SQL을 테스트 코드에 옮겨 적지 마라.** README에서 읽은 그대로, `BEGIN`과 `COMMIT`을 포함해 적힌 순서대로 실행한다(여러 문장을 한 번에 실행할 수 있는 연결로). 이유: 옮겨 적으면 README가 스키마와 어긋나도 테스트가 통과한다(E1 S1.6 "못 박을 것").
- 실행하기 전에 `reader@example.com`과 `other@example.com`의 `users` 행을 넣고, 두 사람에게 로그인 상태를 하나씩 만든다.
- 단언(testcase.md TC-1.6.1): 오류 없이 끝난다. `allowed_emails`에 `tester1@example.com`과 `tester2@example.com`이 `user`로 있고 `reader@example.com`은 없다. `reader@example.com`의 로그인 상태는 지워졌고 `users` 행은 남았다. `other@example.com`의 로그인 상태는 그대로다.
- 그 절에 ` ```sql ` 블록이 하나도 없으면 실패한다(절의 제목이 바뀌거나 블록이 사라졌을 때 아무것도 실행하지 않고 통과하면 안 된다).

### 2. README — `README.md`

- **"현재 상태"**: 이제 Google 로그인, 허용 목록, 로그아웃, 내 정보(`GET /api/me`)가 있고, 책과 선곡 같은 기능은 아직 없다는 것으로 고친다.
- **"허용 목록에 사람 넣고 빼기"**: "이 테이블은 로그인 기능(Epic 1)과 함께 만들어지므로, 그 전에는 아래 SQL이 동작하지 않습니다."라는 문장을 지운다. SQL 블록은 1번의 테스트가 통과하는 한 고치지 않는다.
- **새 절 "로컬에서 Google 로그인 점검하기"**: 백엔드 담당자가 프론트엔드 레포 없이 실제 Google 계정으로 로그인과 로그아웃을 확인하는 방법이다(ADR-026). 다음을 순서대로 적는다.
  1. 준비할 것: 로컬의 돌아올 주소 `http://localhost:5173/api/auth/google/callback`을 등록한 Google OAuth 클라이언트(INFRA.md 3.5절), 실제 Google 계정 두 개(하나는 허용 목록에 넣고 하나는 넣지 않는다), 켜 둔 Docker Desktop.
  2. `.env`를 만들어 `GOOGLE_CLIENT_ID`와 `GOOGLE_CLIENT_SECRET`을 채운다(`cp .env.example .env`). `FRONTEND_URL`은 `http://localhost:5173` 그대로 둔다.
  3. compose로 서버를 띄운다(`.env`를 바꾼 뒤에는 다시 띄워야 서버가 새 값을 받는다).
  4. 계정 A를 허용 목록에 `user`로 넣는다(아래 절의 SQL).
  5. Playwright의 브라우저를 처음 한 번 설치한다(`uv run playwright install chromium`).
  6. 점검 스크립트를 실행한다(`uv run python scripts/login_check.py --allowed-email ... --denied-email ...`). 사람은 브라우저의 Google 화면에서 안내받은 계정을 고르기만 한다.
  7. 결과를 읽는 법: 시점마다 세 테이블과 브라우저의 상태가 출력되고, 표와 다르면 0이 아닌 코드로 끝난다. 기대하는 상태는 `docs/backlog/epic-1/testcase.md`의 "로컬 로그인 점검의 테이블 상태"에 있다. 점검 전 상태가 맞지 않으면 브라우저를 열지 않고 맞추는 SQL을 보여 준다. 프론트엔드의 개발 서버가 5173을 쓰고 있으면 끄고 실행한다.
  - 각 명령은 실제 스크립트의 인자와 같아야 한다(`--help`로 확인). 명령마다 무엇을 하는지 한 줄씩 적는다.
- **"알아 둘 것"의 `.env` 항목**: "`.env` 파일이 필요 없습니다"는 더 이상 맞지 않는다. compose는 `.env`에서 `FRONTEND_URL`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` 세 값만 서버에 넘기고, `DATABASE_URL` 같은 나머지 값은 넘기지 않는다. `.env`가 없어도 서버는 뜨지만 Google 로그인은 되지 않는다. README에는 이 요지를 한두 문장으로 적고, 자세한 것은 CONFIGURATION.md 2절로 링크한다(한 정보는 한 문서에만, D-16~D-20).

### 3. CONFIGURATION.md 2절 — `docs/CONFIGURATION.md`

"docker compose로 서버와 데이터베이스를 함께 띄울 때에는 `.env`가 필요하지 않습니다"를 위 2번의 사실에 맞게 고친다. compose가 `.env`에서 어떤 값을 서버에 넘기고 어떤 값은 넘기지 않는지, 그 이유(개발자의 `.env`에 든 `localhost` 주소가 컨테이너 안의 주소를 덮어쓰면 안 된다)를 적는다. 이 문서는 최신 결정만 담는다. "처음에는 ~였다" 같은 변경 경위를 적지 마라(CLAUDE.md의 결정을 기록하는 규칙).

### 4. 확인

README에 적은 명령 가운데 이 환경에서 돌릴 수 있는 것은 실제로 돌려 본다.

- `uv run python scripts/login_check.py --help`가 README의 인자와 같은지.
- compose로 서버를 띄운 뒤(`.env` 없이) `docker compose exec db psql ...`로 README의 허용 목록 SQL 한 줄(자기 자신을 넣는 예)이 도는지, 그리고 마지막에 `docker compose down`으로 내린다. 8080이나 5432가 이미 쓰이고 있으면 README의 "포트가 이미 쓰이고 있을 때"대로 `API_PORT`와 `DB_PORT`를 바꿔서 띄운다. 볼륨을 지우는 `down -v`는 쓰지 마라(명령 가드가 막는다).
- 실제 Google 계정이 필요한 점검(6번)은 돌리지 않는다. summary에 "실행하지 못했음, 사람이 MANUAL 점검에서 실행"이라고 적는다.

## Acceptance Criteria

```bash
uv run pytest tests/infra/test_readme_allowlist.py -v
scripts/check.sh
```

**반증 조건** — 아래의 틀린 경우에도 초록이면 그 테스트가 틀린 것이다.

- README의 SQL에서 테이블이나 컬럼의 이름을 바꿔도(예: `allowed_emails`를 `allowlist`로) 초록이면 TC-1.6.1이 틀렸다.
- README의 "한 사람을 뺍니다" SQL에서 `DELETE FROM login_sessions ...` 문장을 지워도 초록이면 TC-1.6.1이 틀렸다(`reader@example.com`의 로그인 상태가 남는다).
- 그 절의 제목을 바꾸거나 `sql` 블록을 지워도 초록이면 TC-1.6.1이 틀렸다.
- 테스트가 SQL을 자기 안에 옮겨 적어 실행하면 E1 S1.6 "못 박을 것"을 어긴 것이다.

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - `docs/ARCHITECTURE.md` 8절의 코드 구조와 의존 방향을 따르는가?
   - `docs/ADR.md`의 기술 스택을 벗어나지 않았는가?
   - `docs/DEVELOPMENT.md`의 "반드시 지킬 규칙"을 위반하지 않았는가?
3. 결과에 따라 `phases/1-login-allowlist/index.json`의 해당 step을 업데이트한다:
   - 성공 → `"status": "completed"`, `"summary": "산출물 한 줄 요약"`
   - 수정 3회 시도 후에도 실패 → `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 (API 키, 외부 인증, 수동 설정 등) → `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- README의 허용 목록 SQL을 테스트가 통과하도록 바꾸지 마라. 테스트가 실패하면 스키마와 SQL 가운데 어느 쪽이 ARCHITECTURE.md 6절과 다른지 보고, 스키마가 맞으면 SQL을 고치되 그 이유를 summary에 적어라. 이유: 이 SQL은 운영 환경에서 사람이 그대로 실행한다.
- README에 Google 클라이언트의 ID나 비밀값, 실제 계정의 이메일을 적지 마라. 이유: 레포는 공개될 수 있다. 예시는 `you@example.com` 같은 값을 쓴다.
- `docs/ADR.md`, `docs/DECISIONS.md`, `docs/API.md`를 고치지 마라. 이유: 이 step이 바꾸는 결정은 없다. 고칠 곳을 찾으면 summary에 적어라.
- `.env` 파일을 만들거나 커밋하지 마라. 이유: 비밀값이 들어가는 파일이다.
- `docker compose down -v`, `playwright install`, 실제 Google 로그인을 실행하지 마라. 이유: 위 4번.
- 기존 테스트를 깨뜨리지 마라
- `MANUAL.md`의 항목을 체크하지 마라. 이유: 그 항목은 사람이 직접 본 것만 체크한다.
