# Diegesis BE

소설의 분위기에 맞는 음악을 재생해 주는 전자책 플랫폼 Diegesis의 백엔드 레포다. 이 파일은 내용을 직접 담지 않고, 아래 문서들을 참조하기만 한다. 한 가지 정보는 한 문서에만 적으며, 정보를 추가하거나 고칠 때에는 그 정보를 맡은 문서를 고친다.

## 문서

| 문서 | 맡은 정보 | 언제 읽는가 |
| --- | --- | --- |
| [docs/PRD.md](docs/PRD.md) | 제품의 목적, 대상 사용자, 마일스톤, 유저 스토리 | 기능의 의도나 범위를 판단해야 할 때 |
| [docs/GLOSSARY.md](docs/GLOSSARY.md) | 용어의 정의 | 낯선 용어를 만났을 때, 새 용어를 쓰려고 할 때 |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 전체 구성, 동작 흐름, 선곡 방법, 데이터 모델, 코드 구조와 포트 | 코드를 작성하거나 구조를 바꾸기 전에 |
| [docs/ADR.md](docs/ADR.md) | 기술적 결정과 그 이유, 재검토 조건 | 기술을 고르거나 바꾸려고 할 때 |
| [docs/API.md](docs/API.md) | 프론트엔드와의 공통 규칙, 엔드포인트별 요청과 응답 | 엔드포인트를 추가하거나 고칠 때 |
| [docs/AI_CONTRACT.md](docs/AI_CONTRACT.md) | AI 레포가 넘겨주는 산출물 묶음의 파일 규격과 검증 규칙 | 적재 기능을 다룰 때 |
| [docs/CONFIGURATION.md](docs/CONFIGURATION.md) | 설정값의 이름, 뜻, 기본값, 다루는 규칙 | 설정값을 추가하거나 읽는 코드를 작성할 때 |
| [docs/INFRA.md](docs/INFRA.md) | 배포 환경에 관해 정해진 것과 정해야 할 것 | 배포와 관련된 작업을 할 때 |
| [docs/DECISIONS.md](docs/DECISIONS.md) | 제품의 범위와 운영에 관한 결정, 문서 작성 규칙, 팀과 합의할 항목 | 문서를 작성할 때, 범위가 애매할 때 |

`docs/notion-exports/`는 팀 노션에서 내보낸 회의록과 리서치 원본을 모아 둔 참고 자료이며, 결정의 기준으로 쓰지 않는다. 이 폴더는 git에 올리지 않으므로 각자의 로컬에만 있다.
