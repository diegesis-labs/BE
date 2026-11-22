# Diegesis BE

Diegesis는 소설의 분위기에 맞는 음악을 재생해 주는 전자책 플랫폼이며, 이 레포는 그 백엔드입니다. 프론트엔드와 AI 파이프라인은 각각 별도의 레포([FE](https://github.com/diegesis-labs/FE), [AI](https://github.com/diegesis-labs/AI))에 있습니다.

## 현재 상태

지금은 1차 마일스톤(MVP)을 위한 설계 문서, 폴더 구조, 그리고 개발 도구와 작업 절차가 준비되어 있습니다. 서버의 소스코드는 아직 작성하지 않았습니다. 따라서 서버를 실행하는 방법은 구현이 시작된 뒤에 이 문서에 추가합니다.

## 개발 환경

```bash
uv sync             # Python과 개발 도구를 설치합니다.
scripts/check.sh    # 린트, 서식, 타입, 테스트를 검사합니다.
```

코드를 쓸 때 지키는 규칙은 [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)에, 에이전트에게 구현을 맡기는 절차는 [docs/HARNESS.md](docs/HARNESS.md)에 있습니다.

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
```

각 폴더의 역할은 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#8-코드-구조)에 자세히 적혀 있습니다.
