---
title: Epic 1 테스트 케이스
description: Epic 1의 Story가 지켜야 하는 것을 확인하는 테스트 케이스의 목록이다.
---

# Epic 1 테스트 케이스

상태를 바꾸는 요청(`POST`, `PUT`, `PATCH`, `DELETE`)을 보내는 테스트는 `Origin: {FRONTEND_URL}` 헤더를 붙입니다. 출처 확인을 시험하는 케이스(TC-1.4.7, TC-1.4.8, TC-1.5.4)만 이 헤더를 바꾸거나 뺍니다. 테스트 클라이언트의 기본 헤더로 두면 됩니다([API.md 2.4절](../../API.md#24-상태를-바꾸는-요청의-출처-확인)).

ID 토큰을 다루는 케이스에서 "정상 ID 토큰"은 다음 클레임을 가진 토큰입니다. `iss`는 `https://accounts.google.com`, `aud`와 `azp`는 테스트의 `GOOGLE_CLIENT_ID`, `exp`는 지금부터 1시간 뒤, `nonce`는 어댑터에 기대하는 값으로 넘긴 것, `sub`는 `"1234567890"`, `email`은 `reader@example.com`, `email_verified`는 `true`, `name`은 `"독자"`입니다. 각 케이스는 적힌 클레임만 바꾸고 나머지는 정상 ID 토큰과 같게 둡니다.

## S1.1 사용자, 로그인 상태, 허용 목록의 저장

| TC | Story | 방식 | 케이스 | 합격 기준 | 대응 |
| --- | --- | --- | --- | --- | --- |
| TC-1.1.1 | S1.1 | integration | 마이그레이션한 데이터베이스의 `allowed_emails`와 `users`에 각각 대문자가 섞인 이메일(`Reader@Example.com`)을 넣습니다. | 두 테이블 모두 제약 위반으로 거부합니다. **소문자 제약을 빼고 구현하면 실패해야 합니다.** | ARCHITECTURE.md 6절, ADR-024 |
| TC-1.1.2 | S1.1 | integration | `allowed_emails`의 `role`에 `owner`를 넣습니다. | 제약 위반으로 거부합니다. `user`와 `admin`은 들어갑니다. **역할의 제약을 빼고 구현하면 실패해야 합니다.** | ARCHITECTURE.md 6절 |
| TC-1.1.3 | S1.1 | integration | `users`에 같은 이메일을 두 번 넣습니다. 그리고 다른 이메일 두 개에 같은 `google_sub`를 넣고, `google_sub` 없이도 넣어 봅니다. | 같은 이메일과 같은 `google_sub`는 고유 제약 위반으로, `google_sub`가 없는 행은 `NOT NULL` 위반으로 거부합니다. **`google_sub`에 고유 제약이나 `NOT NULL`을 빼고 구현하면 실패해야 합니다.** | ARCHITECTURE.md 6절, ADR-027 |
| TC-1.1.4 | S1.1 | integration | 로그인 상태가 두 개 있는 사용자의 `users` 행을 지웁니다. | 그 사용자의 `login_sessions` 행도 모두 지워집니다. **`ON DELETE CASCADE`를 빼고 구현하면 실패해야 합니다.** | ARCHITECTURE.md 6절 |
| TC-1.1.5 | S1.1 | integration | 이 Epic의 마이그레이션을 한 단계 되돌린 뒤 다시 올립니다. | 되돌리면 세 테이블이 없고 `vector` 확장은 남아 있으며, 다시 올리면 세 테이블이 있습니다. | ADR-009 |
| TC-1.1.6 | S1.1 | integration | repository로 만료 시각이 지난 로그인 상태와 지나지 않은 로그인 상태를 각각 조회합니다. | 지난 것은 없다고 나오고, 지나지 않은 것은 나옵니다. **만료 시각을 거르지 않고 구현하면 실패해야 합니다.** | ARCHITECTURE.md 6절 |

## S1.2 Google 로그인 어댑터

| TC | Story | 방식 | 케이스 | 합격 기준 | 대응 |
| --- | --- | --- | --- | --- | --- |
| TC-1.2.1 | S1.2 | unit | `FRONTEND_URL`이 `http://localhost:5173`인 상태에서, Host 헤더가 `localhost:8080`인 요청으로 정해진 `state`, `nonce`, `code_verifier`를 넘겨 인가 주소를 만듭니다. | 인가 주소의 `redirect_uri`가 `http://localhost:5173/api/auth/google/callback`이고, `scope`가 정확히 `openid email profile`이며, `response_type=code`가 들어 있습니다. `state`와 `nonce`는 넘긴 값이고, `code_challenge`는 `code_verifier`의 SHA-256을 패딩 없는 base64url로 바꾼 값이며, `code_challenge_method`는 `S256`입니다. 주소에 `code_verifier`는 없습니다. **요청의 Host로 돌아올 주소를 만들거나, 범위를 더 요청하거나, PKCE나 `nonce`를 빼거나, `plain`을 쓰면 실패해야 합니다.** | ADR-025, ADR-027, INFRA.md 3.5절 |
| TC-1.2.2 | S1.2 | unit | 가짜 HTTP 전송으로, Google 어댑터가 토큰을 교환할 때 오류 응답과 형식이 틀린 응답을 각각 받게 합니다. | 두 경우 모두 로그인 실패를 뜻하는 예외 하나가 나옵니다. **통신 라이브러리의 예외가 그대로 나가면 실패해야 합니다.** | ADR-025 |
| TC-1.2.3 | S1.2 | unit | 가짜 HTTP 전송으로, 토큰 교환이 정상 ID 토큰을 돌려주게 합니다. 그리고 `iss`만 `accounts.google.com`으로 바꾼 토큰도 받게 합니다. | 두 경우 모두 어댑터가 신원을 돌려주며, 그 `sub`, 이메일, 이메일 확인 여부, 이름이 토큰의 값과 같습니다. | ADR-027 |
| TC-1.2.4 | S1.2 | unit | 가짜 HTTP 전송으로 다음 토큰을 각각 받게 합니다. `aud`가 다른 클라이언트 ID인 토큰, `aud`가 우리의 클라이언트 ID와 다른 ID를 함께 담은 목록인 토큰, `azp`가 다른 클라이언트 ID인 토큰입니다. | 세 경우 모두 로그인 실패를 뜻하는 예외가 나옵니다. **`aud`나 `azp`를 확인하지 않고 구현하면 실패해야 합니다.** | ADR-027 |
| TC-1.2.5 | S1.2 | unit | 가짜 HTTP 전송으로 `iss`가 `https://evil.example`인 토큰을 받게 합니다. | 로그인 실패를 뜻하는 예외가 나옵니다. **`iss`를 확인하지 않고 구현하면 실패해야 합니다.** | ADR-027 |
| TC-1.2.6 | S1.2 | unit | 가짜 HTTP 전송으로 `exp`가 1분 전인 토큰을 받게 합니다. | 로그인 실패를 뜻하는 예외가 나옵니다. **`exp`를 확인하지 않고 구현하면 실패해야 합니다.** | ADR-027 |
| TC-1.2.7 | S1.2 | unit | 가짜 HTTP 전송으로 다음 토큰을 각각 받게 합니다. `nonce`가 기대한 값과 다른 토큰, `nonce`가 없는 토큰, `sub`가 없는 토큰, `email`이 없는 토큰입니다. | 네 경우 모두 로그인 실패를 뜻하는 예외가 나옵니다. **`nonce`를 확인하지 않거나 `sub`가 없는 신원을 돌려주면 실패해야 합니다.** | ADR-027 |
| TC-1.2.8 | S1.2 | unit | 가짜 HTTP 전송으로 어댑터가 보내는 토큰 교환 요청을 가로챕니다. 어댑터에는 정해진 `code`와 `code_verifier`를 넘깁니다. | 요청은 `https://oauth2.googleapis.com/token`으로 가며, 본문에 `grant_type=authorization_code`, 넘긴 `code`와 `code_verifier`, TC-1.2.1과 같은 `redirect_uri`, 클라이언트 ID와 비밀값이 들어 있습니다. **`code_verifier`를 보내지 않으면 실패해야 합니다.** | ADR-027 |
| TC-1.2.9 | S1.2 | unit | `FRONTEND_URL`을 바꿔 가며 설정 클래스를 만듭니다. 받아들일 값은 `http://localhost:5173`, `http://127.0.0.1:5173`, `https://diegesis.example`이고, 거부할 값은 `http://diegesis.example`, `https://diegesis.example/`, `https://diegesis.example/app`, `ftp://diegesis.example`입니다. | 받아들일 값으로는 설정이 만들어지고, 거부할 값으로는 설정을 만들 때 검증 오류가 납니다. **localhost가 아닌 `http` 주소를 받아들이면 실패해야 합니다.** | CONFIGURATION.md 3.1절, ADR-027 |

## S1.3 로그인 service

이 절의 케이스는 가짜 `IdentityProvider`를 끼워서 로그인 경로를 호출합니다.

| TC | Story | 방식 | 케이스 | 합격 기준 | 대응 |
| --- | --- | --- | --- | --- | --- |
| TC-1.3.1 | S1.3 | integration | 허용 목록에 있는 이메일을 돌려주는 가짜 신원으로 로그인 결과 처리 경로를 호출합니다. | `302`이며 `Location`이 `FRONTEND_URL`의 `/`입니다. `diegesis_session` 쿠키에 `HttpOnly`, `SameSite=Lax`, `Path=/`, `Max-Age`(`LOGIN_SESSION_TTL_HOURS`×3600)가 붙습니다. `users`에 행이 하나 생기고 그 `google_sub`는 가짜 신원의 `sub`입니다. 쿠키 값은 43자의 base64url 문자열이며, `login_sessions`의 `token_hash`는 쿠키 값과 다르고 쿠키 값의 SHA-256과 같습니다. `expires_at`은 지금에 `LOGIN_SESSION_TTL_HOURS`를 더한 시각과 1분 안에서 같습니다. **쿠키 값을 그대로 저장하면 실패해야 합니다.** | API.md 4.2절, ARCHITECTURE.md 6절 |
| TC-1.3.2 | S1.3 | integration | 허용 목록에 없는 이메일을 돌려주는 가짜 신원으로 로그인 결과 처리 경로를 호출합니다. | `302`이며 `Location`이 `/login?error=NOT_ALLOWED`입니다. `diegesis_session` 쿠키를 심지 않고, `users`와 `login_sessions`에 행이 생기지 않습니다. **허용 목록을 확인하기 전에 `users`에 등록하면 실패해야 합니다.** | API.md 4.2절, ARCHITECTURE.md 6절 |
| TC-1.3.3 | S1.3 | unit | 다음 네 경우에 각각 로그인 결과 처리 경로를 호출합니다. `state` 쿠키가 없을 때, 쿠키의 `state`와 쿼리의 `state`가 다를 때, 쿠키의 `state` 부분과 쿼리의 `state`가 모두 빈 문자열일 때(쿠키는 `.{nonce}.{code_verifier}`), 쿠키가 `.`으로 나눈 세 부분이 아닐 때(쿠키에 `state`만 있음)입니다. | 네 경우 모두 `Location`이 `/login?error=LOGIN_FAILED`이고, 가짜 신원의 `code` 교환이 한 번도 불리지 않습니다. **`state`를 확인하지 않거나, 빈 `state`끼리 같다고 판정하면 실패해야 합니다.** | ADR-025, ADR-027 |
| TC-1.3.4 | S1.3 | unit | `error=access_denied` 쿼리로 로그인 결과 처리 경로를 호출합니다. | `Location`이 `/login?error=LOGIN_FAILED`이고, `code` 교환이 불리지 않습니다. | API.md 4.2절 |
| TC-1.3.5 | S1.3 | unit | 가짜 신원이 `email_verified`가 false인 신원을 돌려줍니다. 이메일은 허용 목록에 있습니다. | `Location`이 `/login?error=LOGIN_FAILED`이고 `diegesis_session` 쿠키를 심지 않습니다. **이메일 확인 여부를 보지 않고 구현하면 실패해야 합니다.** | ADR-025 |
| TC-1.3.6 | S1.3 | unit | 가짜 신원이 `code` 교환에서 로그인 실패 예외를 냅니다. | `500`이 아니라 `302`이며 `Location`이 `/login?error=LOGIN_FAILED`입니다. | ADR-025 |
| TC-1.3.7 | S1.3 | integration | 허용 목록에는 `reader@example.com`이 있고, 가짜 신원은 `Reader@Example.com`을 돌려줍니다. | 로그인에 성공하고 `users.email`은 `reader@example.com`입니다. **이메일을 소문자로 바꾸지 않고 비교하면 실패해야 합니다.** | ADR-024 |
| TC-1.3.8 | S1.3 | unit | 성공, 허용 목록 밖, 실패의 세 경우에 로그인 결과 처리 경로의 응답 헤더를 봅니다. | 세 경우 모두 `diegesis_oauth_state`를 지우는 `Set-Cookie`(`Max-Age=0`)가 있습니다. | API.md 4.2절 |
| TC-1.3.9 | S1.3 | unit | `FRONTEND_URL`을 `https://diegesis.example`과 `http://localhost:5173`으로 바꿔 가며 로그인 시작과 로그인 성공의 응답 헤더를 봅니다. | `https`일 때에는 `diegesis_oauth_state`와 `diegesis_session` 쿠키에 모두 `Secure`가 붙고, `http`일 때에는 붙지 않습니다. **`Secure`를 언제나 붙이거나 언제나 빼면 실패해야 합니다.** | ADR-027 |
| TC-1.3.10 | S1.3 | integration | 같은 사람이 이름을 바꾼 뒤, 옛 `diegesis_session` 쿠키 없이(다른 기기에서) 다시 로그인합니다. | `users` 행은 하나이고 `display_name`이 새 이름이며, `login_sessions` 행은 두 개입니다. | API.md 4.3절 |
| TC-1.3.11 | S1.3 | integration | 두 로그인 상태 가운데 하나의 쿠키로 로그아웃한 뒤, 그 쿠키와 다른 쿠키로 각각 `GET /api/me`를 호출합니다. | 로그아웃은 `204`이고 쿠키를 지우는 `Set-Cookie`가 있습니다. 로그아웃한 쿠키는 `401`을, 다른 쿠키는 `200`을 받습니다. | API.md 4.2절 |
| TC-1.3.12 | S1.3 | unit | 쿠키 없이, 그리고 백엔드가 모르는 쿠키 값으로 각각 로그아웃을 호출합니다. | 두 경우 모두 `204`입니다. **로그아웃에 관문을 걸면 실패해야 합니다.** | API.md 4.2절, ADR-025 |
| TC-1.3.13 | S1.3 | unit | 로그인 성공과 실패를 거치는 동안의 로그를 모읍니다. | 로그에 쿠키 값, Google의 `code`, 토큰, `GOOGLE_CLIENT_SECRET`의 값, `state`, `nonce`, `code_verifier`가 없습니다. 실패한 경우에는 실패의 원인이 로그에 있습니다. | E1 못 박을 것, ADR-025, ADR-027 |
| TC-1.3.14 | S1.3 | integration | `users`에 (`reader@example.com`, `sub-A`)인 행이 있고, `reader@example.com`과 `other@example.com`이 허용 목록에 있습니다. 가짜 신원이 (`reader@example.com`, `sub-B`)를 돌려줄 때와 (`other@example.com`, `sub-A`)를 돌려줄 때 각각 로그인 결과 처리 경로를 호출합니다. | 두 경우 모두 `500`이 아니라 `302`이며 `Location`이 `/login?error=LOGIN_FAILED`이고, `diegesis_session` 쿠키를 심지 않습니다. `users`에는 처음의 행 하나만 있고 그 행의 값은 바뀌지 않으며, `login_sessions`에 행이 생기지 않습니다. 로그에 거부한 이유가 있습니다. **사용자를 이메일만으로 찾거나, `google_sub`의 고유 제약 위반이 `500`으로 끝나면 실패해야 합니다.** | ARCHITECTURE.md 6절, ADR-027 |
| TC-1.3.15 | S1.3 | integration | 한 사람이 쿠키 X로 로그인해 있고, 다른 기기의 로그인 상태 Z도 있습니다. 쿠키 X를 붙인 채 다시 로그인에 성공합니다. 그다음 X와 새 쿠키 Y와 Z로 각각 `GET /api/me`를 호출합니다. | X의 행은 지워지고 Y와 Z의 행이 있습니다. X는 `401`을, Y와 Z는 `200`을 받습니다. **다시 로그인할 때 옛 쿠키의 행을 지우지 않거나, 다른 기기의 행까지 지우면 실패해야 합니다.** | ARCHITECTURE.md 6절, ADR-027 |
| TC-1.3.16 | S1.3 | integration | 사람 P에게 만료된 로그인 상태 두 개와 만료되지 않은 로그인 상태 하나가 있고, 사람 Q에게 만료된 로그인 상태 하나가 있습니다. P가 옛 쿠키 없이 로그인에 성공합니다. | P의 만료된 행 두 개는 지워지고, P의 만료되지 않은 행과 새 행이 남습니다. Q의 만료된 행은 그대로입니다. **만료된 행을 지우지 않거나, 다른 사람의 행이나 만료되지 않은 행까지 지우면 실패해야 합니다.** | ARCHITECTURE.md 6절, ADR-027 |
| TC-1.3.17 | S1.3 | unit | 임의의 값을 만드는 함수를 1000번 부르고, `secrets.token_urlsafe`를 기록하는 가짜로 바꾼 뒤 한 번 더 부릅니다. 그다음 이 함수를 정해진 값을 차례로 내는 가짜로 바꾸고, 로그인 시작과 로그인 성공의 응답을 봅니다. | 1000개의 값은 모두 `^[A-Za-z0-9_-]{43}$`에 맞고 서로 다릅니다. 함수는 `secrets.token_urlsafe`를 `32`로 부릅니다. 가짜로 바꾼 뒤에는 `diegesis_oauth_state`의 세 값과 `diegesis_session`의 값이 모두 가짜가 낸 값입니다. **임의의 값을 만드는 곳이 둘 이상이거나, `secrets`가 아닌 것으로 만들면 실패해야 합니다.** | ADR-027 |
| TC-1.3.18 | S1.3 | unit | `diegesis_oauth_state` 쿠키를 `{s}.{n}.{v}`로, 쿼리의 `state`를 `{s}`로 붙여 로그인 결과 처리 경로를 호출합니다. 가짜 `IdentityProvider`는 받은 값을 기록합니다. | 가짜 신원의 `code` 교환이 쿼리의 `code`, `code_verifier` `{v}`, 기대하는 `nonce` `{n}`을 받습니다. **쿠키의 `code_verifier`나 `nonce`를 넘기지 않으면 실패해야 합니다.** | ADR-027 |

## S1.4 관문

| TC | Story | 방식 | 케이스 | 합격 기준 | 대응 |
| --- | --- | --- | --- | --- | --- |
| TC-1.4.1 | S1.4 | unit | 쿠키 없이, 그리고 백엔드가 모르는 쿠키 값으로 각각 `GET /api/me`를 호출합니다. | 두 경우 모두 `401`이고 본문이 `code`가 `NOT_AUTHENTICATED`인 2.3절의 형식입니다. | API.md 2.2절, 2.3절 |
| TC-1.4.2 | S1.4 | integration | 만료 시각이 지난 로그인 상태의 쿠키로 `GET /api/me`를 호출합니다. | `401 NOT_AUTHENTICATED`입니다. | API.md 2.2절 |
| TC-1.4.3 | S1.4 | integration | 로그인한 뒤, 앱을 다시 만들지 않은 채 SQL로 그 사람의 `allowed_emails` 행만 지우고(로그인 상태는 남김) `GET /api/me`를 호출합니다. 그다음 SQL로 다시 넣고 같은 쿠키로 한 번 더 호출합니다. 마지막으로 다시 로그인한 새 쿠키로 호출합니다. | 지운 뒤에는 `403 NOT_ALLOWED`이고, 다시 넣은 뒤의 옛 쿠키는 `401 NOT_AUTHENTICATED`이며, 새 쿠키는 `200`입니다. **허용 목록을 로그인할 때만 확인하거나 메모리에 담아 두면, 또는 다시 넣은 뒤에 옛 로그인 상태가 통과하면 실패해야 합니다.** | API.md 2.2절, ARCHITECTURE.md 6절, ADR-024, ADR-027 |
| TC-1.4.4 | S1.4 | integration | 역할이 `user`인 사람이 관리자 관문을 건 테스트 전용 경로를 호출합니다. 그다음 앱을 다시 만들지 않은 채 SQL로 역할을 `admin`으로 바꾸고 같은 쿠키로 다시 호출합니다. | 처음에는 `403 ADMIN_ONLY`이고, 바꾼 뒤에는 `200`입니다. **역할을 로그인 상태에 복사해 두면 실패해야 합니다.** | API.md 2.2절, ADR-024 |
| TC-1.4.5 | S1.4 | integration | 로그인한 뒤 허용 목록에서 빠진 사람이 관리자 관문을 건 테스트 전용 경로를 호출합니다. | `403 NOT_ALLOWED`입니다. `ADMIN_ONLY`가 아닙니다. **관리자 관문이 역할부터 보면 실패해야 합니다.** | API.md 2.2절 |
| TC-1.4.6 | S1.4 | integration | 허용 목록에 `admin`으로 있는 사람이 `GET /api/me`를 호출합니다. | `200`이며 본문이 `id`, `email`, `display_name`, `role`이고, `role`이 `admin`입니다. | API.md 4.3절 |
| TC-1.4.7 | S1.4 | unit | 관문을 걸지 않은 테스트 전용 경로 하나를 `GET`, `POST`, `PUT`, `PATCH`, `DELETE`로 등록하고, 아래 "출처 확인의 경우"의 표대로 호출합니다. | 표의 기대와 같습니다. 거절한 응답은 `403`이며 본문은 `code`가 `ORIGIN_MISMATCH`인 2.3절의 형식이고, 테스트 전용 경로의 처리는 불리지 않습니다. **출처를 문자열의 앞부분만 비교하거나, `Origin`과 `Referer`가 없을 때 통과시키거나, `GET`까지 막으면 실패해야 합니다.** | API.md 2.4절, ADR-027 |
| TC-1.4.8 | S1.4 | integration | 로그인한 사람의 쿠키를 붙여 `POST /api/auth/logout`을 `Origin: https://evil.example`로 호출합니다. 그다음 `Origin: {FRONTEND_URL}`로 다시 호출합니다. | 처음에는 `403 ORIGIN_MISMATCH`이고 `login_sessions`의 행이 그대로 있습니다. 다음에는 `204`이고 행이 지워집니다. **공개 경로를 출처 확인에서 빼면 실패해야 합니다.** | API.md 2.4절, 4.2절, ADR-027 |
| TC-1.4.9 | S1.4 | integration | 로그인한 뒤 `GET /api/me`를 세 번 호출하고, 그 전후의 `login_sessions` 행을 비교합니다. | 행의 모든 값이 그대로입니다. **관문이 만료 시각을 늘리거나 행을 고치면 실패해야 합니다.** | ARCHITECTURE.md 6절, ADR-027 |

### 출처 확인의 경우

TC-1.4.7의 합격 기준입니다. `FRONTEND_URL`은 `http://localhost:5173`입니다. "통과"는 테스트 전용 경로가 불려 그 응답이 나온다는 뜻이고, "거절"은 `403 ORIGIN_MISMATCH`입니다.

| 메서드 | `Origin` | `Referer` | 기대 |
| --- | --- | --- | --- |
| `POST` | `http://localhost:5173` | 없음 | 통과 |
| `POST` | `http://localhost:5173` | `https://evil.example/` | 통과. `Origin`이 있으면 `Origin`만 봅니다. |
| `POST` | `https://evil.example` | 없음 | 거절 |
| `POST` | `http://localhost:5173.evil.example` | 없음 | 거절 |
| `POST` | `http://localhost:8080` | 없음 | 거절. 백엔드 자신의 주소도 프론트엔드가 아닙니다. |
| `POST` | `https://localhost:5173` | 없음 | 거절. 스킴이 다릅니다. |
| `POST` | `null` | 없음 | 거절 |
| `POST` | 없음 | `http://localhost:5173/books/1` | 통과 |
| `POST` | 없음 | `https://evil.example/page` | 거절 |
| `POST` | 없음 | 없음 | 거절 |
| `PUT`, `PATCH`, `DELETE` | `https://evil.example` | 없음 | 거절 |
| `GET` | `https://evil.example` | 없음 | 통과. `GET`은 확인하지 않습니다. |

## S1.5 로그인 경로와 내 정보

| TC | Story | 방식 | 케이스 | 합격 기준 | 대응 |
| --- | --- | --- | --- | --- | --- |
| TC-1.5.1 | S1.5 | unit | 실제 Google 어댑터를 끼운 채 `GET /api/auth/google/login`을 호출합니다. 어댑터는 네트워크를 쓰지 않습니다. | `302`이며 `Location`은 Google의 인가 주소입니다. `diegesis_oauth_state` 쿠키에 `HttpOnly`, `SameSite=Lax`, `Path=/api/auth/google`, `Max-Age=600`이 붙습니다. 쿠키의 값을 `.`으로 나누면 세 부분이며, 셋 모두 43자의 base64url 문자열이고 서로 다릅니다. 첫째는 인가 주소의 `state`와, 둘째는 `nonce`와 같고, 셋째의 SHA-256을 패딩 없는 base64url로 바꾼 값은 `code_challenge`와 같습니다. **쿠키와 인가 주소의 값이 서로 맞지 않으면 실패해야 합니다.** | API.md 4.2절, ADR-027 |
| TC-1.5.2 | S1.5 | unit | 앱에 등록된 모든 경로 가운데 공개 경로(헬스체크, 로그인 시작, 로그인 결과 처리, 로그아웃, `/api/openapi.json`, `/api/docs`)를 뺀 나머지를 쿠키 없이 호출합니다. | 모두 `401 NOT_AUTHENTICATED`입니다. 공개 경로의 목록은 테스트 안의 한곳에만 있습니다. **관문을 걸지 않은 경로를 하나 더 등록하면 실패해야 합니다.** | API.md 2.2절, 3절, ARCHITECTURE.md 1절 |
| TC-1.5.3 | S1.5 | unit | `/api/openapi.json`을 받습니다. | 이 Epic의 네 경로가 있고, `/api/admin/allowed-emails`로 시작하는 경로는 없습니다. | API.md 3절, ADR-024 |
| TC-1.5.4 | S1.5 | unit | 앱에 등록된 모든 경로 가운데 `POST`, `PUT`, `PATCH`, `DELETE`를 받는 경로를, 쿠키 없이 `Origin: https://evil.example`로 그 메서드마다 호출합니다. | 모두 `403 ORIGIN_MISMATCH`입니다. `401`이나 `2xx`가 하나도 없습니다. **출처 확인을 거치지 않는 경로를 하나 더 등록하면 실패해야 합니다.** | API.md 2.4절, ADR-027 |

## S1.6 허용 목록 SQL

| TC | Story | 방식 | 케이스 | 합격 기준 | 대응 |
| --- | --- | --- | --- | --- | --- |
| TC-1.6.1 | S1.6 | integration | 마이그레이션한 데이터베이스에 `reader@example.com`과 `other@example.com`의 `users` 행을 넣고, 두 사람에게 로그인 상태를 하나씩 만듭니다. 그다음 README의 "허용 목록에 사람 넣고 빼기" 절에 있는 `sql` 블록을 읽어서, 트랜잭션 구문을 포함해 적힌 그대로 순서대로 실행합니다. | 오류 없이 끝납니다. 끝난 뒤의 `allowed_emails`에는 `tester1@example.com`과 `tester2@example.com`이 `user`로 있고 `reader@example.com`은 없습니다. `reader@example.com`의 로그인 상태는 지워지고 `users` 행은 남으며, `other@example.com`의 로그인 상태는 그대로입니다. **테이블이나 컬럼의 이름을 바꾸고 README를 고치지 않거나, 사람을 뺄 때 로그인 상태를 지우지 않으면 실패해야 합니다.** | README, ADR-024, ADR-027 |

## S1.7 로컬 로그인 점검

| TC | Story | 방식 | 케이스 | 합격 기준 | 대응 |
| --- | --- | --- | --- | --- | --- |
| TC-1.7.1 | S1.7 | unit | 받은 헤더를 기록하는 가짜 백엔드를 띄웁니다. 가짜 백엔드는 `302`, `Location`, `Set-Cookie` 두 개를 돌려줍니다. 그다음 대역 서버로 `Cookie`를 붙여 `/api/auth/google/callback`을 요청하고, `Origin`과 `Referer`를 붙여 `POST /api/auth/logout`을 요청합니다. | 가짜 백엔드가 받은 Host가 백엔드의 주소이고, `Origin`, `Referer`, `Cookie`는 대역 서버가 받은 값 그대로입니다. 대역 서버의 응답은 `302`이고, 같은 `Location`과 두 `Set-Cookie`를 그대로 담습니다. **리디렉션을 따라가거나, `Set-Cookie`를 하나로 합치거나 빠뜨리거나, Host를 바꾸지 않고 넘기거나, `Origin`을 바꾸거나 빼면 실패해야 합니다.** | ADR-025, ADR-026, ADR-027 |
| TC-1.7.2 | S1.7 | integration | 마이그레이션한 데이터베이스에서 점검 스크립트의 점검 전 상태 확인을 부릅니다. 허용할 계정이 허용 목록에 없을 때, 그 계정의 `users` 행이 있을 때, 허용하지 않을 계정이 허용 목록에 있을 때, 세 조건이 모두 맞을 때를 각각 봅니다. | 앞의 세 경우에는 맞지 않는 조건과 그것을 맞추는 SQL을 돌려주고, 마지막 경우에는 아무것도 돌려주지 않습니다. 확인하는 동안 테이블의 내용은 바뀌지 않습니다. **점검 전 상태를 확인하지 않거나, 확인하면서 테이블을 고치면 실패해야 합니다.** | ADR-026 |
| TC-1.7.3 | S1.7 | manual | 점검 스크립트로, 허용 목록에 `user`로 넣은 실제 Google 계정 A의 로그인과 로그아웃을 점검합니다. 사람은 새 게스트 창에서 대역 서버의 화면을 열고, 스크립트의 안내대로 버튼을 누르고, Google 화면에서 A를 고릅니다. | 스크립트가 출력한 네 시점(로그인 전, 로그인 후, 로그아웃 전, 로그아웃 후)의 테이블과 브라우저의 상태가 아래 "점검 1"의 표와 같습니다. | API.md 4.2절과 4.3절, ARCHITECTURE.md 6절, ADR-026, ADR-031 |
| TC-1.7.4 | S1.7 | manual | 점검 스크립트로, 허용 목록에 없는 실제 Google 계정 B의 로그인을 점검합니다. 사람은 새 게스트 창에서 대역 서버의 화면을 열고, 스크립트의 안내대로 버튼을 누르고, Google 화면에서 B를 고릅니다. | 스크립트가 출력한 두 시점(로그인 전, 로그인 시도 후)의 테이블과 브라우저의 상태가 아래 "점검 2"의 표와 같습니다. | API.md 4.2절, ARCHITECTURE.md 6절, ADR-026, ADR-031, D-55 |
| TC-1.7.5 | S1.7 | unit | 대역 서버로 요청을 보내 대역 서버가 남긴 기록을 봅니다. 그리고 기록된 `Set-Cookie`와 `Cookie`로 점검 1의 흐름을 따라갑니다. 지우는 `Set-Cookie`의 경로가 심은 경로와 다를 때, 브라우저가 받은 쿠키를 다음 요청에 붙이지 않았을 때, 이번 점검에서 심지 않은 쿠키를 붙였을 때를 각각 봅니다. | 기록에는 요청과 응답이 순서대로 남고, 쿠키의 값과 로그인 결과 처리의 `code`와 `state`는 남지 않습니다. 표대로 움직인 흐름에서는 어긋난 것이 없고, 나머지 세 경우에는 그 쿠키의 어긋남이 하나씩 보고됩니다. **쿠키를 이름만 보고 지우거나, 요청에 붙은 `Cookie`를 그 응답을 반영한 뒤의 셈과 견주거나, 결과 처리의 쿼리를 기록하면 실패해야 합니다.** | ADR-031 |

### 로컬 로그인 점검의 테이블 상태

TC-1.7.3과 TC-1.7.4의 합격 기준입니다. phase의 MANUAL 점검표에는 아래 두 표를 그대로 옮깁니다(E1 문서의 S1.7).

- 계정 A는 허용 목록에 `user`로 넣은 Google 계정이고, 계정 B는 허용 목록에 없는 Google 계정입니다.
- 표의 행은 두 계정의 이메일에 관한 것만 봅니다. 다만 점검 2의 `login_sessions`는 전체 행의 수도 봅니다.
- "그대로"는 바로 앞 시점과 같다는 뜻입니다.
- 스크립트는 로그인 후의 상태를 출력한 다음 [내 정보 확인]을 안내해 `GET /api/me`가 한 번 지나가게 하고, 로그아웃 전의 상태를 출력한 다음 로그아웃을 안내합니다. 그래서 두 시점 사이에는 `GET /api/me`를 한 번 부른 것만 있으며, 두 시점의 테이블은 같아야 합니다.
- 브라우저의 상태는 대역 서버를 지난 요청과 응답으로 봅니다(ADR-031). 쿠키와 그 속성은 백엔드가 보낸 `Set-Cookie`로 세고, 브라우저가 다음 요청에 붙인 `Cookie`가 그 셈과 다르면 표와 다른 것으로 봅니다.
- 로그인 전의 상태가 표와 다르면, 스크립트는 점검을 시작하지 않고 상태를 맞추는 SQL을 보여 준 뒤 끝납니다(TC-1.7.2).

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

## 이 Epic에서 판정하지 않는 것

- 로그인 화면, 허용 목록 밖 안내 화면, 401과 403을 받았을 때의 화면 이동은 프론트엔드의 일입니다.
- 운영 주소에서의 Google 로그인과 `Secure` 쿠키가 실제로 동작하는지는 배포를 연결하는 Epic(E2)에서 판정합니다.
- Google 동의 화면의 모양과 문구는 Google이 정합니다.
- 허용 목록을 조회하거나 바꾸는 API가 없는 것은 결함이 아닙니다(ADR-024).
- 관리자 권한이 필요한 실제 경로(묶음 적재, 평가 자료 내보내기)의 동작은 E3과 E9에서 판정합니다.
- 점검 스크립트가 출력하는 형식(표의 모양, 문구)은 판정하지 않습니다. 판정하는 것은 출력된 상태가 위의 표와 같은지입니다.
- 점검 스크립트를 운영 주소에서 돌리는 것은 이 Epic의 일이 아닙니다. 운영 주소의 로그인은 E2에서 판정합니다.
- 운영 환경의 호스팅이 `/api` 요청을 넘길 때 `Origin`을 그대로 두는지는 E2에서 판정합니다.
- ID 토큰의 서명을 확인하지 않는 것, 쿠키 이름에 `__Host-` 접두사가 없는 것, 로그인 상태에 유휴 만료가 없는 것은 결함이 아닙니다(ADR-027).
