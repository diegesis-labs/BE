"""로컬 로그인 점검 스크립트.

백엔드 담당자가 프론트엔드 레포 없이, 로컬에서 실제 Google 계정으로 로그인과 로그아웃을 끝까지
확인하는 도구다(docs/ADR.md의 ADR-026, docs/backlog/epic-1/E1-login-allowlist.md의 S1.7).
"""


class FrontendStandIn:
    def __init__(self, *, listen_host: str, listen_port: int, backend_url: str) -> None:
        raise NotImplementedError

    def start(self) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError

    @property
    def port(self) -> int:
        raise NotImplementedError
