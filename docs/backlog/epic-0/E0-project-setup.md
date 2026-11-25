---
title: 개발 환경 세팅
description: 비즈니스 로직 없이 백엔드의 개발 환경을 세팅하고, harness 워크플로우가 처음부터 끝까지 동작하는지 확인하는 Epic의 정의다.
---

# Epic 0: 개발 환경 세팅

| 항목 | 값 |
| --- | --- |
| GitHub 이슈 | #4 |
| 마일스톤 | 2주차 |
| phase | `phases/0-project-setup/` |

## 목표

비즈니스 로직과 기능 테이블 없이 백엔드의 개발 환경을 세팅합니다. 이 Epic이 끝나면 서버가 헬스체크에 응답하고, PostgreSQL과 pgvector에 연결되며, docker compose로 서버와 데이터베이스를 함께 띄울 수 있습니다. 그리고 PR에서 검사가 돌고, `main`에 합쳐진 코드는 컨테이너 이미지가 되어 Docker Hub에 올라갑니다.

이 Epic의 또 다른 목표는 harness 워크플로우를 처음부터 끝까지 한 번 거쳐 보는 것입니다. 탐색, 논의, 설계, worktree 생성에서 시작해서 step 실행, 리뷰, MANUAL 점검, PR, `main` 병합, CI, 이미지 push까지가 실제로 동작하는지 확인합니다.

## 입력

- harness와 검사 도구(uv, ruff, pyright, pytest)의 설정이 레포에 있습니다([DECISIONS.md](../../DECISIONS.md)의 D-31).
- harness를 실행하는 컴퓨터에서 Docker Desktop이 켜져 있습니다. step 1부터는 `scripts/check.sh`의 통합 테스트가 Docker를 씁니다.
- MANUAL 점검과 병합 직전의 ruleset 설정에는 BE 레포의 Admin 권한이 필요할 수 있습니다. 지금은 Maintain 권한이므로 팀장에게 요청합니다(D-38).

## 끝나는 조건

harness phase 안에서 확인하는 것은 다음과 같습니다.

- `phases/0-project-setup/`의 모든 step이 완료되고, 리뷰와 처분이 닫히고, MANUAL 점검표가 모두 체크됩니다.
- [testcase.md](testcase.md)의 `unit`과 `integration` 케이스가 `scripts/check.sh`와 `scripts/compose-smoke.sh`에서 모두 통과합니다.

PR을 연 뒤와 `main`에 합친 뒤에 확인하는 것은 다음과 같습니다. 이 항목들은 phase가 완료된 뒤에야 일어나므로 MANUAL 점검표에 넣지 않습니다.

1. 첫 PR에서 CI의 `check`, `compose-smoke`, `image`(빌드만 함) job이 모두 통과합니다.
2. `main`에 ruleset을 겁니다. PR을 거쳐야만 합칠 수 있고, CI의 검사가 통과해야 하며, 강제 push를 막습니다(D-38).
3. PR을 `main`에 합친 뒤 `main`의 CI가 통과하고, Docker Hub에 `latest`와 `sha-<커밋>` 태그의 이미지가 올라갑니다.
4. 이슈 #4가 닫힙니다.

## 범위 밖

| 하지 않는 것 | 맡는 곳 |
| --- | --- |
| 사용자, 책, 곡, 기록 같은 기능 테이블과 그 마이그레이션 | 각 기능의 Epic |
| Google 로그인, 허용 목록, CORS(`FRONTEND_URL`) | 로그인 Epic |
| 설정값 가운데 이번 Epic의 코드가 읽지 않는 값(`FRONTEND_URL`, `GOOGLE_*` 등) | 그 값을 쓰는 Epic([CONFIGURATION.md](../../CONFIGURATION.md) 1절) |
| 배포 환경에 새 이미지를 반영하는 일, 배포 환경에서 마이그레이션을 실행하는 시점 | 인프라가 정해진 뒤([INFRA.md](../../INFRA.md) 3.7절) |
| 데이터베이스까지 확인하는 준비 상태 확인 엔드포인트 | 배포 환경이 요구할 때(D-39) |
| `linux/arm64` 이미지의 push | 배포 환경이 요구할 때(D-37) |

## 닫은 결정

| 날짜 | 결정 | 기록된 곳 |
| --- | --- | --- |
| 2026-11-23 | 통합 테스트용 데이터베이스는 testcontainers로 띄웁니다. | ADR-011 |
| 2026-11-23 | 검사와 compose 스모크는 PR과 `main` push에서 돌리고, 이미지 push는 `main` push에서 둘 다 통과한 뒤에만 합니다. | D-36 |
| 2026-11-23 | Docker Hub 저장소는 공개로 두고 `linux/amd64` 이미지만 올립니다. 팀원은 레포에서 compose로 빌드합니다. | D-37 |
| 2026-11-23 | `main`에 ruleset을 겁니다. | D-38 |
| 2026-11-23 | `GET /api/health`는 서버 상태만 확인하고, 서버와 데이터베이스의 연결은 compose 스모크가 확인합니다. | D-39 |
| 2026-11-23 | 로컬 compose에서는 마이그레이션을 일회성 서비스로 실행합니다. | D-40 |
| 2026-11-23 | 로컬과 스모크에서 이미지는 compose로 빌드합니다. | D-41 |

## 못 박을 것 (Epic 전역)

- 기능 테이블을 만들지 않습니다. 이유는 이 Epic의 목표가 개발 환경이며, 테이블은 그 기능의 Epic에서 요구사항과 함께 설계해야 하기 때문입니다.
- `GET /api/health`가 데이터베이스에 질의하지 않게 합니다. 이유는 데이터베이스에 장애가 났을 때 서버까지 죽은 것으로 판정되면 안 되기 때문입니다(D-39).
- 테스트가 개발자의 `.env`나 개발용 데이터베이스에 접속하지 않게 합니다. 이유는 마이그레이션을 되돌리는 테스트가 개발용 데이터를 지울 수 있기 때문입니다([DEVELOPMENT.md](../../DEVELOPMENT.md) 4.3절).
- 이미지에 `.env`나 비밀값을 넣지 않습니다. 이유는 Docker Hub 저장소가 공개이기 때문입니다(D-37).
- Docker Hub의 계정, 저장소 이름, 토큰을 코드에 적지 않습니다. 이유는 이 값들을 GitHub의 secrets와 variables에서만 관리하기 때문입니다(D-37).
- 무인 에이전트 세션은 `docker push`나 `docker login`을 하지 않습니다. 이유는 이미지를 올리는 것은 `main`에 합쳐진 코드를 CI가 하는 일이기 때문입니다(D-36). 명령 가드가 이것을 막습니다.
- 로컬에서 이미지는 compose로 빌드하고 `docker build`를 직접 쓰지 않습니다. 이유는 `docker build`의 결과가 로컬 이미지 저장소에 실리는지가 Docker builder의 설정에 따라 다르기 때문입니다(D-41).
- compose 파일에 `platform:`과 `env_file`을 적지 않습니다. 이유는 Apple Silicon의 Mac과 Windows가 각자의 CPU 아키텍처로 빌드해야 하고, 개발자의 `.env`에 든 주소가 컨테이너 안의 주소를 덮어쓰면 안 되기 때문입니다.
- 버전을 문서에 적지 않습니다. 이유는 버전이 [DEVELOPMENT.md](../../DEVELOPMENT.md) 1절이 정한 파일에만 있어야 하기 때문입니다.

## Story

### S0.1 설정과 앱의 골격

| Task | 내용 | 산출물 |
| --- | --- | --- |
| T0.1.1 | 서버 의존성을 추가하고, 설정 클래스를 만듭니다. | `pyproject.toml`, `uv.lock`, `app/core/config.py` |
| T0.1.2 | 앱을 조립하는 함수와 서버의 진입점을 만들고, OpenAPI 문서를 `/api/openapi.json`에 둡니다. | `app/main.py`, `app/__main__.py` |

**대응**: CONFIGURATION.md 1절과 3.1절, API.md 1절

**못 박을 것**: 설정 클래스에는 이번 Epic의 코드가 읽는 값(`PORT`, `LOG_LEVEL`, `DATABASE_URL`)만 둡니다. `.env`에 클래스에 없는 값이 있어도 설정을 읽을 수 있어야 합니다.

### S0.2 데이터베이스 연결과 마이그레이션

| Task | 내용 | 산출물 |
| --- | --- | --- |
| T0.2.1 | 데이터베이스 의존성을 추가하고, compose 파일에 데이터베이스 서비스를 둡니다. | `compose.yaml` |
| T0.2.2 | 데이터베이스 연결을 조립하고, Alembic과 pgvector 확장을 켜는 첫 마이그레이션을 만듭니다. | `app/core/database.py`, `alembic.ini`, `migrations/` |
| T0.2.3 | 통합 테스트가 testcontainers로 데이터베이스를 띄우게 합니다. | `tests/conftest.py`, `tests/support/` |

**대응**: ADR-002, ADR-009, ADR-011, ARCHITECTURE.md 4절, DEVELOPMENT.md 4.3절

**못 박을 것**: 통합 테스트의 데이터베이스 이미지는 `compose.yaml`에서 읽습니다. 이미지의 이름과 버전을 두 곳에 적지 않습니다.

### S0.3 공통 에러 형식

| Task | 내용 | 산출물 |
| --- | --- | --- |
| T0.3.1 | 모든 에러 응답을 `{code, message, detail}` 형식으로 바꾸는 처리기를 만들어 앱에 등록합니다. | `app/core/errors.py` |

**대응**: API.md 2.3절

**못 박을 것**: 500 응답에는 예외의 내용을 담지 않습니다.

### S0.4 헬스체크

| Task | 내용 | 산출물 |
| --- | --- | --- |
| T0.4.1 | `GET /api/health`를 만듭니다. | `app/health/router.py`, `app/health/schemas.py` |

**대응**: API.md 4.1절, D-39

### S0.5 컨테이너와 로컬 실행

| Task | 내용 | 산출물 |
| --- | --- | --- |
| T0.5.1 | 서버의 컨테이너 이미지를 정의합니다. | `Dockerfile`, `.dockerignore` |
| T0.5.2 | compose에 마이그레이션 서비스와 서버 서비스를 추가합니다. | `compose.yaml` |
| T0.5.3 | compose로 전체를 띄워서 확인하는 스모크 스크립트를 만듭니다. | `scripts/compose-smoke.sh`, `.gitattributes` |

**대응**: ADR-010, INFRA.md 1절, D-37, D-39, D-40, D-41

### S0.6 실행 안내

| Task | 내용 | 산출물 |
| --- | --- | --- |
| T0.6.1 | README에 docker compose로 서버와 데이터베이스를 함께 띄우는 방법을 적습니다. | `README.md` |

**대응**: D-37, D-41, DEVELOPMENT.md 1절

### S0.7 CI와 이미지 배포

| Task | 내용 | 산출물 |
| --- | --- | --- |
| T0.7.1 | PR과 `main` push에서 검사와 스모크를 돌리고, `main` push에서만 이미지를 올리는 workflow를 만듭니다. | `.github/workflows/ci.yml` |

**대응**: INFRA.md 3.7절, D-36, D-37
