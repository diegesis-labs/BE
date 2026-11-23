---
title: Epic 0 테스트 케이스
description: Epic 0의 Story가 지켜야 하는 것을 확인하는 테스트 케이스의 목록이다.
---

# Epic 0 테스트 케이스

## S0.1 설정과 앱의 골격

| TC | Story | 방식 | 케이스 | 합격 기준 | 대응 |
| --- | --- | --- | --- | --- | --- |
| TC-0.1.1 | S0.1 | unit | `DATABASE_URL`이 환경변수에도 `.env`에도 없는 상태로 설정을 읽습니다. | 설정을 읽는 순간 검증 오류가 납니다. **`DATABASE_URL`에 기본값을 넣으면 실패해야 합니다.** | CONFIGURATION.md 1절, 3.2절 |
| TC-0.1.2 | S0.1 | unit | `.env`에 `DATABASE_URL`과 함께 설정 클래스에 없는 값(`GOOGLE_CLIENT_ID`, `APP_ENV` 등 `.env.example`에 있는 값)이 들어 있습니다. | 설정을 정상으로 읽습니다. **클래스에 없는 값을 거부하는 pydantic-settings의 기본 동작을 그대로 두면 실패해야 합니다.** | CONFIGURATION.md 1절 |
| TC-0.1.3 | S0.1 | unit | 같은 이름의 값이 환경변수와 `.env`에 모두 있습니다. | 환경변수의 값을 씁니다. | CONFIGURATION.md 1절 |
| TC-0.1.4 | S0.1 | unit | `PORT`와 `LOG_LEVEL`을 주지 않거나, `LOG_LEVEL`에 정해지지 않은 값을 줍니다. | 주지 않으면 `8080`과 `INFO`이고, 정해지지 않은 값을 주면 검증 오류가 납니다. | CONFIGURATION.md 3.1절 |
| TC-0.1.5 | S0.1 | unit | `DATABASE_URL`이 없는 상태로 앱을 import하고 `/api/openapi.json`, `/openapi.json`, `/api/docs`를 요청합니다. | import가 실패하지 않습니다. `/api/openapi.json`은 200과 OpenAPI 문서를, `/api/docs`는 200을, `/openapi.json`은 404를 응답합니다. **OpenAPI를 기본 경로에 그대로 두면 실패해야 합니다.** | API.md 1절 |

## S0.2 데이터베이스 연결과 마이그레이션

| TC | Story | 방식 | 케이스 | 합격 기준 | 대응 |
| --- | --- | --- | --- | --- | --- |
| TC-0.2.1 | S0.2 | integration | testcontainers로 띄운 데이터베이스에 `alembic upgrade head`를 실행합니다. | `pg_extension`에 `vector`가 있고, 그 버전이 0.8.0 이상입니다. **마이그레이션이 확장을 만들지 않거나 0.8.0 미만의 이미지를 쓰면 실패해야 합니다.** | ARCHITECTURE.md 4절 |
| TC-0.2.2 | S0.2 | integration | 임시 테이블에 2차원 벡터 두 개를 넣고, `app/core/database.py`로 만든 연결로 질의 벡터와 코사인 거리가 가장 가까운 행을 찾습니다. 픽스처는 코사인 거리로 가장 가까운 행과 유클리드 거리로 가장 가까운 행이 서로 다르게 만듭니다. | 코사인 거리로 가장 가까운 행이 돌아옵니다. **유클리드 거리(`<->`)로 검색하면 실패해야 합니다.** | ARCHITECTURE.md 4절 |
| TC-0.2.3 | S0.2 | integration | 마이그레이션을 한 단계 되돌린 뒤 다시 올립니다. | 되돌리면 `vector` 확장이 없고, 다시 올리면 있습니다. | ADR-009 |
| TC-0.2.4 | S0.2 | integration | 통합 테스트가 띄운 데이터베이스 컨테이너의 이미지를 확인합니다. | `compose.yaml`의 `db` 서비스의 이미지와 같습니다. **`compose.yaml`의 이미지를 바꿨는데 테스트의 이미지가 따라 바뀌지 않으면 실패해야 합니다.** | DEVELOPMENT.md 1절, 4.3절 |
| TC-0.2.5 | S0.2 | unit | Docker에 닿을 수 없는 상태에서 통합 테스트용 데이터베이스를 띄우는 함수를 부릅니다. | 건너뛰기(skip)가 아니라, Docker가 필요하다는 뜻의 메시지를 담은 오류가 납니다. **Docker가 없을 때 `pytest.skip`으로 넘어가면 실패해야 합니다.** | ADR-011 |

## S0.3 공통 에러 형식

| TC | Story | 방식 | 케이스 | 합격 기준 | 대응 |
| --- | --- | --- | --- | --- | --- |
| TC-0.3.1 | S0.3 | unit | `create_app()`으로 만든 앱에 없는 경로를 요청합니다. | 404이며, 본문의 키는 정확히 `code`와 `message`이고 `code`는 `NOT_FOUND`입니다. **FastAPI의 기본 형식(`{"detail": "Not Found"}`)이 그대로 나가면 실패해야 합니다.** | API.md 2.3절 |
| TC-0.3.2 | S0.3 | unit | 정수를 받는 쿼리 값에 문자열을 보내고, 요청 본문의 중첩된 필드에 잘못된 값을 보냅니다. | 400과 `VALIDATION_ERROR`이며, `detail`의 각 항목에 잘못된 필드의 이름(`field`)과 이유(`reason`)가 있습니다. 중첩된 필드의 이름은 점으로 이은 경로(예: `item.price`)이고, `body`나 `query` 같은 위치는 이름에 넣지 않습니다. **FastAPI의 기본인 422가 나가면 실패해야 합니다.** | API.md 2.3절 |
| TC-0.3.3 | S0.3 | unit | 처리되지 않은 예외를 던지는 경로를 요청합니다. 예외의 메시지에는 비밀값처럼 보이는 문자열이 들어 있습니다. | 500과 `INTERNAL_ERROR`이며, 응답 본문 어디에도 예외의 메시지와 스택이 없습니다. **예외의 메시지를 `message`나 `detail`에 담으면 실패해야 합니다.** | API.md 2.3절 |
| TC-0.3.4 | S0.3 | unit | GET만 받는 경로에 POST를 보냅니다. | 405와 `METHOD_NOT_ALLOWED`입니다. | API.md 2.3절 |
| TC-0.3.5 | S0.3 | unit | 앱의 예외(`AppError`)를 상태 409, 임의의 `code`, `message`, `detail`과 함께 던지고, `detail` 없이도 던집니다. | 그 상태, `code`, `message`, `detail`이 그대로 나갑니다. `detail`이 없으면 응답에 `detail` 키가 없습니다. | API.md 2.3절 |

## S0.4 헬스체크

| TC | Story | 방식 | 케이스 | 합격 기준 | 대응 |
| --- | --- | --- | --- | --- | --- |
| TC-0.4.1 | S0.4 | unit | `GET /api/health`를 요청합니다. | 200이며 본문이 정확히 `{"status": "ok"}`입니다. | API.md 4.1절 |
| TC-0.4.2 | S0.4 | unit | `DATABASE_URL`을 닿을 수 없는 주소(`127.0.0.1:1`)로 두고 `GET /api/health`를 요청합니다. | 200이며 본문이 정확히 `{"status": "ok"}`입니다. **데이터베이스에 질의하는 구현이면 실패해야 합니다.** | D-39 |
| TC-0.4.3 | S0.4 | unit | `/api/openapi.json`을 요청하고, `POST /api/health`를 요청합니다. | OpenAPI 문서의 `paths`에 `/api/health`의 `get`이 있습니다. POST는 405와 `METHOD_NOT_ALLOWED`입니다. | API.md 1절, 2.3절 |

## S0.5 컨테이너와 로컬 실행

| TC | Story | 방식 | 케이스 | 합격 기준 | 대응 |
| --- | --- | --- | --- | --- | --- |
| TC-0.5.1 | S0.5 | integration | `scripts/compose-smoke.sh`를 실행합니다. | 다섯 가지가 모두 확인되고 종료 코드가 0입니다. (1) `migrate` 서비스가 종료 코드 0으로 끝납니다. (2) 데이터베이스에 `vector` 확장이 있습니다. (3) 호스트에서 요청한 `/api/health`가 `{"status": "ok"}`입니다. (4) api 컨테이너의 프로세스가 root가 아닙니다. (5) api 이미지 안에 `.env` 파일이 없습니다. **하나라도 어긋나면 0이 아닌 코드로 끝나야 합니다.** | D-39, D-40 |
| TC-0.5.2 | S0.5 | unit | `.dockerignore`를 읽습니다. | `.env`와 `.env.*`를 빌드 맥락에서 뺍니다. **`.dockerignore`에서 `.env`를 지우면 실패해야 합니다.** | D-37 |
| TC-0.5.3 | S0.5 | unit | `Dockerfile`과 `.python-version`을 읽습니다. | Python 베이스 이미지의 주 버전과 부 버전이 `.python-version`과 같고, uv 이미지는 정확한 버전으로 고정되어 있고, 마지막 단계는 root가 아닌 사용자로 실행됩니다. **`.python-version`만 올리고 `Dockerfile`을 그대로 두면 실패해야 합니다.** | DEVELOPMENT.md 1절 |
| TC-0.5.4 | S0.5 | unit | `compose.yaml`을 읽습니다. | 어느 서비스에도 `platform`과 `env_file`이 없고, `migrate`와 `api`의 `DATABASE_URL`의 호스트가 `db`이며, `api`는 `migrate`가 성공한 뒤에, `migrate`는 `db`가 준비된 뒤에 시작합니다. **`DATABASE_URL`의 호스트가 `localhost`이면 실패해야 합니다.** | D-37, D-40 |
| TC-0.5.5 | S0.5 | unit | `scripts/compose-smoke.sh`와 `.gitattributes`를 읽습니다. | 스크립트는 이미지를 compose로만 빌드하며 `docker build`와 `docker buildx build`를 직접 부르지 않습니다. 그리고 프로젝트 이름은 스크립트 안에 고정된 `diegesis-smoke`이며 환경변수나 인자로 바꿀 수 없습니다. `.gitattributes`는 `*.sh`의 줄바꿈을 LF로 고정합니다. **스크립트가 프로젝트 이름을 바깥에서 받거나 `docker build`를 직접 부르면 실패해야 합니다.** | D-41 |

## S0.7 CI와 이미지 배포

| TC | Story | 방식 | 케이스 | 합격 기준 | 대응 |
| --- | --- | --- | --- | --- | --- |
| TC-0.7.1 | S0.7 | unit | workflow의 트리거를 읽습니다. | `main`을 향한 `pull_request`와 `main`의 `push`에서만 돕니다. `pull_request_target`을 쓰지 않습니다. | D-36 |
| TC-0.7.2 | S0.7 | unit | 검사 job과 스모크 job을 읽습니다. | 검사 job은 `scripts/check.sh`를 부르고, ruff, pyright, pytest를 따로 부르지 않습니다. 스모크 job은 `scripts/compose-smoke.sh`를 부릅니다. CI가 설치하는 uv의 버전은 `Dockerfile`의 uv 이미지의 버전과 같습니다. **검사 명령을 workflow에 따로 적거나, 두 uv 버전이 다르면 실패해야 합니다.** | DEVELOPMENT.md 2절 |
| TC-0.7.3 | S0.7 | unit | 이미지 job을 읽습니다. | 검사 job과 스모크 job을 `needs`로 기다립니다. Docker Hub 로그인과 push는 `main`에 push된 경우에만 합니다. 플랫폼은 `linux/amd64` 하나이고, 태그는 `latest`와 `sha-`로 시작하는 커밋 태그입니다. **`needs`가 없거나, PR에서도 push하거나, `linux/arm64`가 들어 있으면 실패해야 합니다.** | D-36, D-37 |
| TC-0.7.4 | S0.7 | unit | workflow의 자격 증명, 이미지 이름, 권한을 읽습니다. | Docker Hub의 사용자 이름과 토큰은 `secrets.DOCKERHUB_USERNAME`과 `secrets.DOCKERHUB_TOKEN`에서, 이미지 이름은 `vars.DOCKERHUB_IMAGE`에서만 읽습니다. workflow의 권한은 `contents: read`입니다. **토큰이나 이미지 이름을 문자열로 적으면 실패해야 합니다.** | D-37 |
| TC-0.7.5 | S0.7 | unit | workflow 파일에 actionlint를 실행합니다. | 종료 코드가 0입니다. actionlint가 없으면 건너뛰지 않고 실패합니다. | INFRA.md 3.7절 |
| TC-0.7.6 | S0.7 | manual | Docker Hub에 저장소와 토큰을 만들고, GitHub에 secrets와 variable을 등록합니다. | `gh secret list`에 `DOCKERHUB_USERNAME`과 `DOCKERHUB_TOKEN`이, `gh variable list`에 `DOCKERHUB_IMAGE`가 보입니다. | D-37, INFRA.md 3.7절 |

## 이 Epic에서 판정하지 않는 것

- 배포 환경에서 이미지가 실행되는지는 판정하지 않습니다. 배포할 곳이 아직 정해지지 않았습니다(INFRA.md 3.1절).
- GitHub Actions가 실제로 실행된 결과는 phase 안에서 판정하지 않습니다. phase가 끝난 뒤 PR과 병합에서 확인하며, Epic 문서의 "끝나는 조건"에 적었습니다.
- 이미지의 크기와 빌드 시간은 판정하지 않습니다.
- 기능 Epic의 설정값(`APP_ENV`, `GOOGLE_*` 등)이 설정 클래스에 없는 것은 결함이 아닙니다(CONFIGURATION.md 1절).
- `linux/arm64` 이미지가 Docker Hub에 없는 것은 결함이 아닙니다(D-37).
- S0.6(README)에는 테스트 케이스가 없습니다. 그 step은 README에 적은 명령을 적힌 그대로 실행해서 확인합니다.
