# Epic 1 — 사람이 확인하는 점검표

> **에이전트에게 시키지 마라.** 여기 있는 것은 사람이 직접 보고 체크한다.
> 근거는 `docs/backlog/epic-1/testcase.md`의 `manual` 항목(TC-1.7.3, TC-1.7.4)이다.
> 전부 체크되기 전까지 `execute.py`는 종료 코드 5로 끝난다 — 정상이다.
>
> 두 항목은 점검 스크립트 한 번의 실행으로 함께 확인한다. 스크립트가 점검 1(계정 A)을 끝낸 뒤 점검 2(계정 B)를 이어서 한다.

## 점검을 준비하는 순서

이 worktree의 최상위 폴더에서 아래 순서대로 한다. 계정 A는 허용 목록에 넣을 실제 Google 계정이고, 계정 B는 허용 목록에 넣지 않을 다른 실제 Google 계정이다. 명령의 `<A>`, `<B>`를 두 계정의 이메일로 바꾼다.

**1. Google OAuth 클라이언트.** 승인된 리디렉션 URI에 `http://localhost:5173/api/auth/google/callback`이 등록된 클라이언트가 있어야 한다(`docs/INFRA.md` 3.5절). 어느 계정으로 만든 클라이언트든 이 주소만 등록되어 있으면 된다.

**2. `.env`.** 견본을 복사하고 `GOOGLE_CLIENT_ID`와 `GOOGLE_CLIENT_SECRET`을 채운다. `FRONTEND_URL`은 `http://localhost:5173` 그대로 둔다. `.env`는 커밋하지 않는다.

```bash
cp .env.example .env
```

**3. 서버.** compose로 데이터베이스, 마이그레이션, 서버를 띄운다. `.env`를 고친 뒤에는 다시 띄워야 서버가 새 값을 받는다.

```bash
docker compose up --build -d --wait
```

**4. 허용 목록.** 계정 A를 `user`로 넣는다. 계정 B는 넣지 않는다.

```bash
docker compose exec db psql -U diegesis -d diegesis -c "INSERT INTO allowed_emails (email, role) VALUES (lower('<A>'), 'user') ON CONFLICT (email) DO UPDATE SET role = EXCLUDED.role;"
```

**5. Playwright의 브라우저.** 이 컴퓨터에서 처음 한 번만 설치한다.

```bash
uv sync
uv run playwright install chromium
```

**6. 점검 스크립트.** 프론트엔드의 개발 서버가 5173 포트를 쓰고 있으면 끄고 실행한다. 점검 전 상태가 아래 표의 "로그인 전"과 다르면 스크립트는 브라우저를 열지 않고 상태를 맞추는 SQL을 보여 준 뒤 끝난다. 그 SQL을 위 4번처럼 실행하고 다시 돌린다.

```bash
uv run python scripts/login_check.py --allowed-email <A> --denied-email <B>
```

브라우저가 열리고 Google 화면이 나오면, 스크립트의 안내에 따라 점검 1에서는 계정 A를, 점검 2에서는 계정 B를 골라 로그인한다. 그 밖의 입력은 스크립트가 한다. Google이 "안전하지 않은 브라우저"라며 로그인을 막으면 우회하지 말고 멈춘다. 그때의 방법은 `docs/ADR.md`의 ADR-026 재검토 조건에 따라 정한다.

점검이 끝나면 서버를 내린다. 데이터베이스의 데이터는 남는다.

```bash
docker compose down
```

## 시점마다 기대하는 상태

아래 두 표는 `docs/backlog/epic-1/testcase.md`의 "로컬 로그인 점검의 테이블 상태"를 그대로 옮긴 것이다. 스크립트가 출력한 시점마다의 실제 상태를 이 표와 칸마다 대조한다. 스크립트는 표와 다른 것이 있으면 끝에 모아 보여 주고 0이 아닌 코드로 끝나지만, 출력도 직접 읽고 대조한다.

계정 A는 허용 목록에 `user`로 넣은 Google 계정이고, 계정 B는 허용 목록에 없는 Google 계정이다. 표의 행은 두 계정의 이메일에 관한 것만 본다. 다만 점검 2의 `login_sessions`는 전체 행의 수도 본다. "그대로"는 바로 앞 시점과 같다는 뜻이다. 스크립트는 로그인 후의 상태를 출력한 다음 `GET /api/me`를 부르고, 로그아웃 전의 상태를 출력한 다음 로그아웃한다. 그래서 두 시점 사이에는 `GET /api/me`를 한 번 부른 것만 있으며, 두 시점의 테이블은 같아야 한다.

**점검 1: 허용된 계정 A의 로그인과 로그아웃 (TC-1.7.3)**

| 시점 | `allowed_emails` | `users` | `login_sessions` | 브라우저 |
| --- | --- | --- | --- | --- |
| 로그인 전 | A의 행이 하나 있고, `role`은 `user`입니다. | A의 행이 없습니다. | A의 행이 없습니다. | 쿠키가 없습니다. `GET /api/me`는 `401`입니다. |
| 로그인 후 | 그대로입니다. | A의 행이 하나 생깁니다. `email`은 소문자이고, `google_sub`는 비어 있지 않으며, `display_name`은 A의 Google 이름이고, `created_at`은 방금입니다. | A의 행이 하나 생깁니다. `token_hash`는 쿠키 값의 SHA-256과 같습니다. `expires_at`은 로그인한 시각에 `LOGIN_SESSION_TTL_HOURS`(기본 336시간)를 더한 시각과 1분 안에서 같습니다. | 주소가 `FRONTEND_URL`의 `/`입니다. `diegesis_session` 쿠키에 `HttpOnly`, `SameSite=Lax`, `Path=/`가 붙고 `Secure`는 붙지 않습니다. `diegesis_oauth_state` 쿠키는 없습니다. |
| 로그아웃 전 | 그대로입니다. | 그대로입니다. | 그대로입니다. `GET /api/me`를 불러도 행이 늘거나 바뀌지 않습니다. | `GET /api/me`가 `200`이고, 본문의 `email`은 A, `role`은 `user`, `display_name`은 A의 Google 이름입니다. |
| 로그아웃 후 | 그대로입니다. | 그대로입니다. 로그아웃은 `users` 행을 지우지 않습니다. | A의 행이 없습니다. | 로그아웃의 응답이 `204`입니다. 이것은 대역 서버를 거친 요청이 출처 확인을 통과했다는 뜻이기도 합니다. `diegesis_session` 쿠키가 없고, `GET /api/me`는 `401`입니다. |

**점검 2: 허용 목록 밖 계정 B의 로그인 시도 (TC-1.7.4)**

B에게는 로그인 상태가 생기지 않으므로 로그아웃 전후는 보지 않습니다.

| 시점 | `allowed_emails` | `users` | `login_sessions` | 브라우저 |
| --- | --- | --- | --- | --- |
| 로그인 전 | B의 행이 없습니다. | B의 행이 없습니다. | 전체 행의 수를 기록합니다. | 쿠키가 없습니다. |
| 로그인 시도 후 | 그대로입니다. B가 들어가지 않습니다. | 그대로입니다. 허용 목록에 없는 계정의 행을 만들지 않습니다. | 전체 행의 수가 로그인 전과 같습니다. | 주소가 `FRONTEND_URL`의 `/login?error=NOT_ALLOWED`입니다. `diegesis_session`과 `diegesis_oauth_state` 쿠키가 없고, `GET /api/me`는 `401`입니다. |

## 실제 Google 계정으로 하는 로그인과 로그아웃

- [ ] 점검 1(TC-1.7.3): 계정 A로 로그인하고 로그아웃했을 때, 스크립트가 출력한 네 시점(로그인 전, 로그인 후, 로그아웃 전, 로그아웃 후)의 테이블과 브라우저의 상태가 위 "점검 1"의 표와 칸마다 같다.
  - 테스트로 덮을 수 없는 이유: 실제 Google 계정과 Google 화면의 입력은 사람만 다룰 수 있고, 검사의 테스트는 실제 Google에 요청하지 않는다(ADR-026).
  - 실행 명령: `uv run python scripts/login_check.py --allowed-email <A> --denied-email <B>`
  - 관찰한 값(체크한 날짜와 함께 적는다. 이메일, 쿠키 값, `token_hash`의 값은 적지 않는다):
    - 로그인 전:
    - 로그인 후:
    - 로그아웃 전:
    - 로그아웃 후:
    - 표와 다른 점(없으면 "없음"):
- [ ] 점검 2(TC-1.7.4): 계정 B로 로그인을 시도했을 때, 스크립트가 출력한 두 시점(로그인 전, 로그인 시도 후)의 테이블과 브라우저의 상태가 위 "점검 2"의 표와 칸마다 같다.
  - 테스트로 덮을 수 없는 이유: 위와 같다. 허용 목록 밖의 실제 Google 계정이 Google 로그인을 마치고 돌아오는 경로는 실제 계정으로만 지나간다.
  - 실행 명령: 점검 1과 같은 실행에서 이어진다.
  - 관찰한 값(체크한 날짜와 함께 적는다):
    - 로그인 전(`login_sessions`의 전체 행 수 포함):
    - 로그인 시도 후:
    - 표와 다른 점(없으면 "없음"):
