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
| `APP_ENV` | 실행 환경의 이름입니다. `local`, `production` 가운데 하나입니다. `production`에서는 쿠키를 HTTPS로만 보냅니다. | `local` | `production` |
| `PORT` | 서버가 요청을 받는 포트입니다. 프론트엔드의 개발 서버가 `8080`으로 요청을 넘기도록 설정되어 있습니다. | `8080` | `8080` |
| `FRONTEND_URL` | 프론트엔드의 주소입니다. 로그인을 마친 사용자를 이 주소로 돌려보내고, 이 주소에서 온 요청만 허용합니다. | 필수 | `http://localhost:5173` |
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
| `BOOTSTRAP_ADMIN_EMAILS` | 서버가 시작할 때 허용 목록에 관리자로 넣어 둘 이메일입니다. 허용 목록이 비어 있으면 아무도 들어올 수 없으므로, 첫 관리자를 이 값으로 지정합니다. 여러 명이면 쉼표로 구분합니다. | 필수 | `admin@example.com,lead@example.com` |
| `LOGIN_SESSION_TTL_HOURS` | 로그인 상태가 유지되는 시간입니다. 이 시간이 지나면 다시 로그인해야 합니다. | `336` (14일) | `720` |
| `LOGIN_COOKIE_NAME` | 로그인 상태를 식별하는 쿠키의 이름입니다. | `diegesis_session` | `diegesis_session` |

### 3.4 선곡

| 이름 | 뜻 | 기본값 | 예시 |
| --- | --- | --- | --- |
| `RECOMMENDATION_TOP_K` | 벡터 검색으로 가져올 후보 구간의 수입니다. 한 곡에서 나온 여러 구간이 후보에 함께 들어갈 수 있습니다. 값이 클수록 다양한 곡이 나오지만 장면과 덜 어울리는 곡이 뽑힐 가능성도 커집니다. | `10` | `5` |
| `RECOMMENDATION_SAMPLING` | 후보 가운데 한 구간을 뽑는 방법입니다. `uniform`은 모든 후보를 같은 확률로 뽑고, `weighted`는 장면과 더 가까운 구간을 더 높은 확률로 뽑습니다. | `uniform` | `weighted` |
| `RECOMMENDATION_SAMPLING_TEMPERATURE` | `weighted`일 때 확률의 쏠림 정도를 정합니다. 값이 작을수록 가장 가까운 곡이 뽑힐 확률이 높아집니다. `uniform`일 때에는 쓰이지 않습니다. | `1.0` | `0.5` |
| `AUTOPLAY_COOLDOWN_SECONDS` | 사용자가 곡을 중단한 뒤 새 곡을 자동으로 틀지 않는 시간(자동 재생 쉬는 시간)입니다. 초 단위입니다. | `300` (5분) | `600` |
| `DEFAULT_STRATEGY` | 사용자가 설정을 바꾸기 전에 적용되는 선곡 방식입니다. `embedding`, `random`, `silent` 가운데 하나입니다. | `embedding` | `random` |
| `DEFAULT_EMBEDDING_MODEL` | 사용자가 설정을 바꾸기 전에 적용되는 임베딩 모델의 이름입니다. 백엔드에 등록된 모델이어야 합니다. | `muq-mulan` | `laion-clap-music` |

자동 재생 쉬는 시간의 길이는 PRD에서 아직 정해지지 않은 값입니다. 기본값인 5분은 임시로 넣은 값이므로, 팀에서 정한 뒤에 바꿔 주세요.

### 3.5 음원 저장소

| 이름 | 뜻 | 기본값 | 예시 |
| --- | --- | --- | --- |
| `STORAGE_BACKEND` | 음원 파일을 어디에서 가져올지 정합니다. 로컬 개발에서는 `local`을 씁니다. 클라우드 저장소의 값은 인프라가 정해진 뒤에 추가합니다. | `local` | `local` |
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
APP_ENV=local
PORT=8080
FRONTEND_URL=http://localhost:5173
LOG_LEVEL=DEBUG

# 데이터베이스
DATABASE_URL=postgresql+asyncpg://diegesis:diegesis@localhost:5432/diegesis

# 로그인
GOOGLE_CLIENT_ID=1234567890-abc.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=여기에_비밀값을_넣습니다
BOOTSTRAP_ADMIN_EMAILS=admin@example.com
LOGIN_SESSION_TTL_HOURS=336

# 선곡
RECOMMENDATION_TOP_K=10
RECOMMENDATION_SAMPLING=uniform
AUTOPLAY_COOLDOWN_SECONDS=300
DEFAULT_STRATEGY=embedding
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
