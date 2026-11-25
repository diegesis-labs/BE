---
title: CONFIGURATION(설정값 안내서)
description: 백엔드의 동작을 바꾸는 모든 설정값의 이름, 뜻, 기본값, 예시를 정리하는 문서다. 설정값을 추가하거나 바꿀 때 이 문서를 함께 고친다.
---

# 설정값 안내서

이 문서는 코드를 고치지 않고 바꿀 수 있는 설정값을 모두 모아 둔 문서입니다. 설정값에 관한 설명은 이 문서에만 적으며, 다른 문서는 이 문서를 참조합니다. 낯선 용어의 뜻은 [GLOSSARY.md](GLOSSARY.md)에 있습니다.

아래 목록은 구현 전에 작성한 초안입니다. 구현하면서 설정값이 추가되거나 이름이 바뀌면 이 문서와 `.env.example`을 함께 고쳐 주세요.

## 1. 설정값을 다루는 방식

설정값은 환경변수로 전달합니다. 환경변수는 프로그램을 실행할 때 운영체제가 프로그램에 넘겨주는 이름과 값의 쌍입니다. 그리고 로컬에서 개발할 때에는 프로젝트 최상위 폴더의 `.env` 파일에 적어 두면 서버가 시작할 때 읽어 들입니다.

```mermaid
flowchart LR
  E[".env 파일<br/>(로컬 개발)"] --> S["설정 클래스<br/>app/core"]
  V["환경변수<br/>(배포 환경)"] --> S
  S --> C["나머지 코드"]
```

구현할 때에는 다음 규칙을 지킵니다.

- 모든 설정값은 `app/core`에 있는 설정 클래스 하나에 모읍니다. 이 클래스는 pydantic-settings로 만들며, 값의 타입과 기본값을 함께 선언합니다.
- 나머지 코드는 환경변수를 직접 읽지 않고, 반드시 이 설정 클래스를 통해서만 값을 가져옵니다. 이렇게 하면 어떤 설정값이 있는지를 한곳에서 볼 수 있고, 값이 잘못됐을 때 서버가 시작하는 순간에 바로 알 수 있습니다.
- 환경변수와 `.env` 파일에 같은 이름이 있으면 환경변수의 값이 우선합니다.
- 비밀값이 들어 있는 `.env` 파일은 코드 저장소에 올리지 않습니다. 그 대신 값이 비어 있는 견본인 `.env.example`을 올립니다.
- 설정 클래스에는 코드가 실제로 읽는 값만 선언합니다. 3절의 목록 가운데 아직 읽는 코드가 없는 값은 그 값을 쓰는 기능을 만들 때 클래스에 추가합니다.
- `.env.example`에는 3절의 값이 모두 들어 있습니다. 따라서 `.env`에 설정 클래스에 없는 값이 있더라도 오류로 다루지 않고 무시합니다.

이 문서는 서버가 읽는 설정값만 다룹니다. `API_PORT`와 `DB_PORT`처럼 `compose.yaml`만 읽는 변수는 서버의 설정값이 아니므로 여기에 적지 않으며, 그 쓰임은 [README](../README.md)의 "로컬에서 서버 띄우기"에 있습니다.

## 2. 처음 시작할 때

견본 파일을 복사한 다음, 비어 있는 값을 채웁니다.

```bash
cp .env.example .env
```

다만 docker compose로 서버와 데이터베이스를 함께 띄울 때에는 `.env`가 필요하지 않습니다. compose 파일이 필요한 값을 컨테이너에 직접 넣어 주기 때문입니다. `.env`는 서버를 compose 밖에서 직접 실행할 때 씁니다.

## 3. 설정값 목록

"필수"라고 적힌 값은 기본값이 없어서, 채우지 않으면 서버가 시작되지 않습니다.

### 3.1 서버

| 이름 | 뜻 | 기본값 | 예시 |
| --- | --- | --- | --- |
| `PORT` | 서버가 요청을 받는 포트입니다. 프론트엔드의 개발 서버가 `8080`으로 요청을 넘기도록 설정되어 있습니다. | `8080` | `8080` |
| `FRONTEND_URL` | 프론트엔드의 주소입니다. 로그인을 마친 사용자를 이 주소로 돌려보냅니다. 그리고 이 값 뒤에 `/api/auth/google/callback`을 붙여 Google이 로그인 결과를 돌려보낼 주소를 만듭니다. 그래서 Google 콘솔에 등록하는 돌아올 주소도 이 값을 따릅니다([INFRA.md 3.5절](INFRA.md#35-google-로그인-설정)). 이 값은 쿠키와 요청의 확인에도 쓰입니다. 이 값이 `https`로 시작하면 쿠키에 `Secure`를 붙이고, 상태를 바꾸는 요청은 `Origin`이 이 값과 같아야 받아들입니다([API.md 2.4절](API.md#24-상태를-바꾸는-요청의-출처-확인)). 스킴, 호스트, 포트만 적고 끝에 `/`를 붙이지 않으며, `http`는 호스트가 `localhost`나 `127.0.0.1`일 때만 쓸 수 있습니다. 출처 확인이 브라우저가 보낸 `Origin`과 이 값을 글자 그대로 비교하므로, 브라우저가 `Origin`을 적는 모양대로 스킴과 호스트를 소문자로 적고 기본 포트(`http`의 80, `https`의 443)는 적지 않습니다. 이 조건에 맞지 않으면 서버가 시작되지 않습니다([ADR-027](ADR.md#adr-027-로그인-흐름과-로그인-상태의-보안-보강)). 프론트엔드와 백엔드가 같은 주소를 쓰므로 CORS는 설정하지 않습니다. | 필수 | `http://localhost:5173` |
| `LOG_LEVEL` | 로그를 얼마나 자세히 남길지 정합니다. `DEBUG`, `INFO`, `WARNING`, `ERROR` 가운데 하나입니다. | `INFO` | `DEBUG` |

### 3.2 데이터베이스

| 이름 | 뜻 | 기본값 | 예시 |
| --- | --- | --- | --- |
| `DATABASE_URL` | PostgreSQL에 접속하는 주소입니다. 사용자 이름, 비밀번호, 주소, 데이터베이스 이름이 들어갑니다. | 필수 | `postgresql+asyncpg://diegesis:diegesis@localhost:5432/diegesis` |

### 3.3 로그인

| 이름 | 뜻 | 기본값 | 예시 |
| --- | --- | --- | --- |
| `GOOGLE_CLIENT_ID` | Google 로그인을 위해 Google Cloud 콘솔에서 발급받은 클라이언트 ID입니다. | 필수 | `1234567890-abc.apps.googleusercontent.com` |
| `GOOGLE_CLIENT_SECRET` | 위 클라이언트 ID와 짝을 이루는 비밀값입니다. | 필수 | (비밀값이므로 예시를 적지 않습니다) |
| `LOGIN_SESSION_TTL_HOURS` | 로그인 상태가 유지되는 시간입니다. 로그인한 때부터 세며, 로그인 상태를 쓰는 동안에도 늘어나지 않습니다. 이 시간이 지나면 다시 로그인해야 합니다. | `336` (14일) | `720` |
| `LOGIN_COOKIE_NAME` | 로그인 상태를 식별하는 쿠키의 이름입니다. | `diegesis_session` | `diegesis_session` |

허용 목록과 관리자는 설정값이 아니라 데이터베이스의 `allowed_emails` 테이블에 있습니다. 그래서 첫 관리자도 [README](../README.md#허용-목록에-사람-넣고-빼기)의 SQL로 넣습니다([ADR-024](ADR.md#adr-024-허용-목록의-관리와-확인)).

### 3.4 선곡

| 이름 | 뜻 | 기본값 | 예시 |
| --- | --- | --- | --- |
| `RECOMMENDATION_TOP_K` | 위치 알림 응답에 담는 후보 구간의 최대 수입니다. 지정 곡의 후보도 이 수 안에 셉니다. 한 곡에서 나온 여러 구간이 후보에 함께 들어갈 수 있습니다. 값이 클수록 다양한 곡이 나오지만 장면과 덜 어울리는 곡이 재생될 가능성도 커지고, 사용자가 이 수만큼 싫어요를 눌러야 그 페이지의 음악이 멈춥니다. | `10` | `5` |
| `DEFAULT_EMBEDDING_MODEL` | 사용자가 설정을 바꾸기 전에 적용되는 임베딩 모델의 이름입니다. 백엔드에 등록된 모델이어야 합니다. | `muq-mulan` | `laion-clap-music` |

### 3.5 음원 저장소

| 이름 | 뜻 | 기본값 | 예시 |
| --- | --- | --- | --- |
| `STORAGE_BACKEND` | 음원 파일을 어디에서 가져올지 정합니다. 로컬 개발에서는 `local`을 씁니다. 배포 환경의 저장소는 Cloudflare R2이며([ADR-023](ADR.md#adr-023-배포-인프라)), 그 값과 접속 정보는 음악 묶음을 적재하는 Epic(E5)에서 추가합니다. | `local` | `local` |
| `STORAGE_LOCAL_DIR` | `STORAGE_BACKEND`가 `local`일 때 음원 파일이 들어 있는 폴더입니다. | `./var/audio` | `./var/audio` |
| `STORAGE_LOCAL_BASE_URL` | `STORAGE_BACKEND`가 `local`일 때 브라우저가 음원을 받을 주소의 앞부분입니다. 이 값 뒤에 음원 파일의 이름, 만료 시각, 서명이 붙습니다. | `http://localhost:8080/api/dev/audio` | `http://localhost:8080/api/dev/audio` |
| `STORAGE_LOCAL_SIGNING_KEY` | `STORAGE_BACKEND`가 `local`일 때 서명된 주소를 만드는 데 쓰는 비밀값입니다. 로컬 개발에서만 쓰이므로 기본값이 있습니다. | `local-dev-only` | `local-dev-only` |
| `AUDIO_URL_TTL_SECONDS` | 서명된 음원 주소가 유효한 시간입니다. 초 단위입니다. 곡 한 곡을 끝까지 듣는 동안 주소가 만료되지 않도록 가장 긴 곡보다 넉넉하게 잡습니다. | `3600` (1시간) | `1800` |

음원 파일은 어느 환경에서나 서명된 주소로만 받을 수 있습니다([ARCHITECTURE.md](ARCHITECTURE.md#2-전체-구성)). 그래서 로컬 개발에서도 백엔드가 같은 방식으로 만료 시각과 서명이 붙은 주소를 만들어 주며, 서명이 맞지 않거나 시간이 지난 요청은 거부합니다. 이렇게 하면 프론트엔드가 로컬에서도 배포 환경과 같은 동작을 확인할 수 있습니다.

### 3.6 묶음 적재

| 이름 | 뜻 | 기본값 | 예시 |
| --- | --- | --- | --- |
| `BUNDLE_MAX_SIZE_MB` | 관리자 API로 올릴 수 있는 산출물 묶음의 최대 크기입니다. MB 단위입니다. | `200` | `500` |

## 4. `.env` 파일의 예시

아래는 로컬에서 개발할 때 쓰는 `.env` 파일의 예시입니다.

```dotenv
# 서버
PORT=8080
FRONTEND_URL=http://localhost:5173
LOG_LEVEL=DEBUG

# 데이터베이스
DATABASE_URL=postgresql+asyncpg://diegesis:diegesis@localhost:5432/diegesis

# 로그인
GOOGLE_CLIENT_ID=1234567890-abc.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=여기에_비밀값을_넣습니다
LOGIN_SESSION_TTL_HOURS=336

# 선곡
RECOMMENDATION_TOP_K=10
DEFAULT_EMBEDDING_MODEL=muq-mulan

# 음원 저장소
STORAGE_BACKEND=local
STORAGE_LOCAL_DIR=./var/audio
AUDIO_URL_TTL_SECONDS=3600
```

## 5. 설정값을 새로 추가할 때

1. `app/core`의 설정 클래스에 이름, 타입, 기본값을 추가합니다.
2. 이 문서의 3절에 이름, 뜻, 기본값, 예시를 추가합니다.
3. `.env.example`에 이름과 견본 값을 추가합니다.
