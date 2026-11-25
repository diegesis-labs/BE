---
title: Epic 1 테스트 케이스
description: Epic 1의 Story가 지켜야 하는 것을 확인하는 테스트 케이스의 목록이다.
---

# Epic 1 테스트 케이스

## S1.1 사용자, 로그인 상태, 허용 목록의 저장

| TC | Story | 방식 | 케이스 | 합격 기준 | 대응 |
| --- | --- | --- | --- | --- | --- |
| TC-1.1.1 | S1.1 | integration | 마이그레이션한 데이터베이스의 `allowed_emails`와 `users`에 각각 대문자가 섞인 이메일(`Reader@Example.com`)을 넣습니다. | 두 테이블 모두 제약 위반으로 거부합니다. **소문자 제약을 빼고 구현하면 실패해야 합니다.** | ARCHITECTURE.md 6절, ADR-024 |
| TC-1.1.2 | S1.1 | integration | `allowed_emails`의 `role`에 `owner`를 넣습니다. | 제약 위반으로 거부합니다. `user`와 `admin`은 들어갑니다. **역할의 제약을 빼고 구현하면 실패해야 합니다.** | ARCHITECTURE.md 6절 |
| TC-1.1.3 | S1.1 | integration | `users`에 같은 이메일을 두 번 넣습니다. | 두 번째는 고유 제약 위반으로 거부합니다. | ARCHITECTURE.md 6절 |
| TC-1.1.4 | S1.1 | integration | 로그인 상태가 두 개 있는 사용자의 `users` 행을 지웁니다. | 그 사용자의 `login_sessions` 행도 모두 지워집니다. **`ON DELETE CASCADE`를 빼고 구현하면 실패해야 합니다.** | ARCHITECTURE.md 6절 |
| TC-1.1.5 | S1.1 | integration | 이 Epic의 마이그레이션을 한 단계 되돌린 뒤 다시 올립니다. | 되돌리면 세 테이블이 없고 `vector` 확장은 남아 있으며, 다시 올리면 세 테이블이 있습니다. | ADR-009 |
| TC-1.1.6 | S1.1 | integration | repository로 만료 시각이 지난 로그인 상태와 지나지 않은 로그인 상태를 각각 조회합니다. | 지난 것은 없다고 나오고, 지나지 않은 것은 나옵니다. **만료 시각을 거르지 않고 구현하면 실패해야 합니다.** | ARCHITECTURE.md 6절 |

## S1.2 Google 로그인 어댑터

| TC | Story | 방식 | 케이스 | 합격 기준 | 대응 |
| --- | --- | --- | --- | --- | --- |
| TC-1.2.1 | S1.2 | unit | `FRONTEND_URL`이 `http://localhost:5173`인 상태에서, Host 헤더가 `localhost:8080`인 요청으로 인가 주소를 만듭니다. | 인가 주소의 `redirect_uri`가 `http://localhost:5173/api/auth/google/callback`이고, `scope`가 정확히 `openid email profile`이며, `response_type=code`와 `state`가 들어 있습니다. **요청의 Host로 돌아올 주소를 만들거나 범위를 더 요청하면 실패해야 합니다.** | ADR-025, INFRA.md 3.5절 |
| TC-1.2.2 | S1.2 | unit | 가짜 HTTP 전송으로, Google 어댑터가 토큰을 교환할 때 오류 응답과 형식이 틀린 응답을 각각 받게 합니다. | 두 경우 모두 로그인 실패를 뜻하는 예외 하나가 나옵니다. **통신 라이브러리의 예외가 그대로 나가면 실패해야 합니다.** | ADR-025 |
| TC-1.2.3 | S1.2 | unit | 가짜 HTTP 전송으로, ID 토큰의 대상(`aud`)이 우리의 클라이언트 ID가 아닌 응답을 받게 합니다. | 로그인 실패를 뜻하는 예외가 나옵니다. **ID 토큰의 대상을 확인하지 않고 구현하면 실패해야 합니다.** | ADR-025 |

## S1.3 로그인 service

이 절의 케이스는 가짜 `IdentityProvider`를 끼워서 로그인 경로를 호출합니다.

| TC | Story | 방식 | 케이스 | 합격 기준 | 대응 |
| --- | --- | --- | --- | --- | --- |
| TC-1.3.1 | S1.3 | integration | 허용 목록에 있는 이메일을 돌려주는 가짜 신원으로 로그인 결과 처리 경로를 호출합니다. | `302`이며 `Location`이 `FRONTEND_URL`의 `/`입니다. `diegesis_session` 쿠키에 `HttpOnly`, `SameSite=Lax`, `Path=/`, `Max-Age`(`LOGIN_SESSION_TTL_HOURS`×3600)가 붙습니다. `users`에 행이 하나 생기고, `login_sessions`의 `token_hash`는 쿠키 값과 다르며 쿠키 값의 SHA-256과 같습니다. **쿠키 값을 그대로 저장하면 실패해야 합니다.** | API.md 4.2절, ARCHITECTURE.md 6절 |
| TC-1.3.2 | S1.3 | integration | 허용 목록에 없는 이메일을 돌려주는 가짜 신원으로 로그인 결과 처리 경로를 호출합니다. | `302`이며 `Location`이 `/login?error=NOT_ALLOWED`입니다. `diegesis_session` 쿠키를 심지 않고, `users`와 `login_sessions`에 행이 생기지 않습니다. **허용 목록을 확인하기 전에 `users`에 등록하면 실패해야 합니다.** | API.md 4.2절, ARCHITECTURE.md 6절 |
| TC-1.3.3 | S1.3 | unit | `state` 쿠키 없이, 그리고 쿼리의 `state`와 다른 값의 `state` 쿠키를 붙여서 각각 로그인 결과 처리 경로를 호출합니다. | 두 경우 모두 `Location`이 `/login?error=LOGIN_FAILED`이고, 가짜 신원의 `code` 교환이 한 번도 불리지 않습니다. **`state`를 확인하지 않고 구현하면 실패해야 합니다.** | ADR-025 |
| TC-1.3.4 | S1.3 | unit | `error=access_denied` 쿼리로 로그인 결과 처리 경로를 호출합니다. | `Location`이 `/login?error=LOGIN_FAILED`이고, `code` 교환이 불리지 않습니다. | API.md 4.2절 |
| TC-1.3.5 | S1.3 | unit | 가짜 신원이 `email_verified`가 false인 신원을 돌려줍니다. 이메일은 허용 목록에 있습니다. | `Location`이 `/login?error=LOGIN_FAILED`이고 `diegesis_session` 쿠키를 심지 않습니다. **이메일 확인 여부를 보지 않고 구현하면 실패해야 합니다.** | ADR-025 |
| TC-1.3.6 | S1.3 | unit | 가짜 신원이 `code` 교환에서 로그인 실패 예외를 냅니다. | `500`이 아니라 `302`이며 `Location`이 `/login?error=LOGIN_FAILED`입니다. | ADR-025 |
| TC-1.3.7 | S1.3 | integration | 허용 목록에는 `reader@example.com`이 있고, 가짜 신원은 `Reader@Example.com`을 돌려줍니다. | 로그인에 성공하고 `users.email`은 `reader@example.com`입니다. **이메일을 소문자로 바꾸지 않고 비교하면 실패해야 합니다.** | ADR-024 |
| TC-1.3.8 | S1.3 | unit | 성공, 허용 목록 밖, 실패의 세 경우에 로그인 결과 처리 경로의 응답 헤더를 봅니다. | 세 경우 모두 `diegesis_oauth_state`를 지우는 `Set-Cookie`(`Max-Age=0`)가 있습니다. | API.md 4.2절 |
| TC-1.3.9 | S1.3 | unit | `APP_ENV`를 `production`과 `local`로 바꿔 가며 로그인 시작과 로그인 성공의 응답 헤더를 봅니다. | `production`에서는 두 쿠키에 `Secure`가 붙고, `local`에서는 붙지 않습니다. **`Secure`를 언제나 붙이거나 언제나 빼면 실패해야 합니다.** | ADR-025 |
| TC-1.3.10 | S1.3 | integration | 같은 사람이 이름을 바꾼 뒤 다시 로그인합니다. | `users` 행은 하나이고 `display_name`이 새 이름이며, `login_sessions` 행은 두 개입니다. | API.md 4.3절 |
| TC-1.3.11 | S1.3 | integration | 두 로그인 상태 가운데 하나의 쿠키로 로그아웃한 뒤, 그 쿠키와 다른 쿠키로 각각 `GET /api/me`를 호출합니다. | 로그아웃은 `204`이고 쿠키를 지우는 `Set-Cookie`가 있습니다. 로그아웃한 쿠키는 `401`을, 다른 쿠키는 `200`을 받습니다. | API.md 4.2절 |
| TC-1.3.12 | S1.3 | unit | 쿠키 없이, 그리고 백엔드가 모르는 쿠키 값으로 각각 로그아웃을 호출합니다. | 두 경우 모두 `204`입니다. **로그아웃에 관문을 걸면 실패해야 합니다.** | API.md 4.2절, ADR-025 |
| TC-1.3.13 | S1.3 | unit | 로그인 성공과 실패를 거치는 동안의 로그를 모읍니다. | 로그에 쿠키 값, Google의 `code`, 토큰, `GOOGLE_CLIENT_SECRET`의 값이 없습니다. 실패한 경우에는 실패의 원인이 로그에 있습니다. | E1 못 박을 것, ADR-025 |

## S1.4 관문

| TC | Story | 방식 | 케이스 | 합격 기준 | 대응 |
| --- | --- | --- | --- | --- | --- |
| TC-1.4.1 | S1.4 | unit | 쿠키 없이, 그리고 백엔드가 모르는 쿠키 값으로 각각 `GET /api/me`를 호출합니다. | 두 경우 모두 `401`이고 본문이 `code`가 `NOT_AUTHENTICATED`인 2.3절의 형식입니다. | API.md 2.2절, 2.3절 |
| TC-1.4.2 | S1.4 | integration | 만료 시각이 지난 로그인 상태의 쿠키로 `GET /api/me`를 호출합니다. | `401 NOT_AUTHENTICATED`입니다. | API.md 2.2절 |
| TC-1.4.3 | S1.4 | integration | 로그인한 뒤, 앱을 다시 만들지 않은 채 SQL로 그 사람의 `allowed_emails` 행을 지우고 `GET /api/me`를 호출합니다. 그다음 SQL로 다시 넣고 한 번 더 호출합니다. | 지운 뒤에는 `403 NOT_ALLOWED`이고, 다시 넣은 뒤에는 `200`입니다. **허용 목록을 로그인할 때만 확인하거나 메모리에 담아 두면 실패해야 합니다.** | API.md 2.2절, ADR-024 |
| TC-1.4.4 | S1.4 | integration | 역할이 `user`인 사람이 관리자 관문을 건 테스트 전용 경로를 호출합니다. 그다음 앱을 다시 만들지 않은 채 SQL로 역할을 `admin`으로 바꾸고 같은 쿠키로 다시 호출합니다. | 처음에는 `403 ADMIN_ONLY`이고, 바꾼 뒤에는 `200`입니다. **역할을 로그인 상태에 복사해 두면 실패해야 합니다.** | API.md 2.2절, ADR-024 |
| TC-1.4.5 | S1.4 | integration | 로그인한 뒤 허용 목록에서 빠진 사람이 관리자 관문을 건 테스트 전용 경로를 호출합니다. | `403 NOT_ALLOWED`입니다. `ADMIN_ONLY`가 아닙니다. **관리자 관문이 역할부터 보면 실패해야 합니다.** | API.md 2.2절 |
| TC-1.4.6 | S1.4 | integration | 허용 목록에 `admin`으로 있는 사람이 `GET /api/me`를 호출합니다. | `200`이며 본문이 `id`, `email`, `display_name`, `role`이고, `role`이 `admin`입니다. | API.md 4.3절 |

## S1.5 로그인 경로와 내 정보

| TC | Story | 방식 | 케이스 | 합격 기준 | 대응 |
| --- | --- | --- | --- | --- | --- |
| TC-1.5.1 | S1.5 | unit | `GET /api/auth/google/login`을 호출합니다. | `302`이며 `Location`은 `IdentityProvider`가 만든 인가 주소입니다. `diegesis_oauth_state` 쿠키에 `HttpOnly`, `SameSite=Lax`, `Path=/api/auth/google`, `Max-Age=600`이 붙고, 그 값이 인가 주소의 `state`와 같습니다. | API.md 4.2절 |
| TC-1.5.2 | S1.5 | unit | 앱에 등록된 모든 경로 가운데 공개 경로(헬스체크, 로그인 시작, 로그인 결과 처리, 로그아웃, `/api/openapi.json`, `/api/docs`)를 뺀 나머지를 쿠키 없이 호출합니다. | 모두 `401 NOT_AUTHENTICATED`입니다. 공개 경로의 목록은 테스트 안의 한곳에만 있습니다. **관문을 걸지 않은 경로를 하나 더 등록하면 실패해야 합니다.** | API.md 2.2절, 3절, ARCHITECTURE.md 1절 |
| TC-1.5.3 | S1.5 | unit | `/api/openapi.json`을 받습니다. | 이 Epic의 네 경로가 있고, `/api/admin/allowed-emails`로 시작하는 경로는 없습니다. | API.md 3절, ADR-024 |
| TC-1.5.4 | S1.5 | manual | 로컬에서 허용 목록에 있는 실제 Google 계정으로 로그인합니다. FE 개발 서버(5173)를 띄우거나, `FRONTEND_URL`을 `http://localhost:8080`으로 두고 그 돌아올 주소를 클라이언트에 등록합니다. | 브라우저가 `FRONTEND_URL`의 `/`로 돌아오고, 같은 브라우저에서 `/api/me`가 `200`입니다. 로그아웃한 뒤에는 `401`입니다. | INFRA.md 3.5절, D-53 |
| TC-1.5.5 | S1.5 | manual | 로컬에서 허용 목록에 없는 실제 Google 계정으로 로그인합니다. | 브라우저의 주소가 `/login?error=NOT_ALLOWED`로 바뀌고, 같은 브라우저에서 `/api/me`가 `401`입니다. | API.md 4.2절, D-55 |

## S1.6 허용 목록 SQL

| TC | Story | 방식 | 케이스 | 합격 기준 | 대응 |
| --- | --- | --- | --- | --- | --- |
| TC-1.6.1 | S1.6 | integration | README의 "허용 목록에 사람 넣고 빼기" 절에 있는 `sql` 블록을 읽어서, 마이그레이션한 데이터베이스에서 순서대로 실행합니다. | 오류 없이 끝나고, 끝난 뒤의 `allowed_emails`에는 `tester1@example.com`과 `tester2@example.com`이 `user`로 있고 `reader@example.com`은 없습니다. **테이블이나 컬럼의 이름을 바꾸고 README를 고치지 않으면 실패해야 합니다.** | README, ADR-024 |

## 이 Epic에서 판정하지 않는 것

- 로그인 화면, 허용 목록 밖 안내 화면, 401과 403을 받았을 때의 화면 이동은 프론트엔드의 일입니다.
- 운영 주소에서의 Google 로그인과 `Secure` 쿠키가 실제로 동작하는지는 배포를 연결하는 Epic(E2)에서 판정합니다.
- Google 동의 화면의 모양과 문구는 Google이 정합니다.
- 허용 목록을 조회하거나 바꾸는 API가 없는 것은 결함이 아닙니다(ADR-024).
- 관리자 권한이 필요한 실제 경로(묶음 적재, 평가 자료 내보내기)의 동작은 E3과 E9에서 판정합니다.
