"""통합 테스트용 데이터베이스를 띄우는 도구의 테스트 (TC-0.2.4의 일부, TC-0.2.5).

이 파일의 테스트는 Docker 없이 돈다.
"""

from pathlib import Path

import pytest
from testcontainers.core.config import testcontainers_config

from tests.support.postgres import db_image, start_database

# --- TC-0.2.4 ---------------------------------------------------------------


def test_db_image_follows_the_compose_file(tmp_path: Path) -> None:
    """db_image()는 compose 파일의 db 서비스의 이미지를 돌려준다. 파일이 바뀌면 따라 바뀐다."""
    compose_file = tmp_path / "compose.yaml"
    compose_file.write_text(
        "services:\n"
        "  api:\n"
        "    image: example/api:9.9.9\n"
        "  db:\n"
        "    image: example/pgvector:1.2.3-pg99\n",
        encoding="utf-8",
    )

    assert db_image(compose_file) == "example/pgvector:1.2.3-pg99"


# --- TC-0.2.5 ---------------------------------------------------------------


def test_start_database_without_docker_raises_instead_of_skipping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Docker에 닿을 수 없으면 건너뛰지 않고, Docker가 필요하다는 오류를 낸다."""
    # 없는 소켓을 가리키게 해서 Docker에 닿을 수 없는 상태를 만든다.
    # 경로는 짧게 둔다. 유닉스 소켓의 경로가 너무 길면 다른 종류의 오류가 난다.
    monkeypatch.setenv("DOCKER_HOST", "unix:///nonexistent-diegesis/docker.sock")
    # testcontainers는 ~/.testcontainers.properties의 tc.host를 DOCKER_HOST보다 먼저 쓴다.
    # 그 파일이 있는 컴퓨터에서도 위의 소켓을 쓰게 한다.
    monkeypatch.setattr(testcontainers_config, "tc_properties", {})

    # pytest.skip이 내는 예외는 Exception이 아니라 BaseException을 잇는다.
    # 그것까지 잡아서 아래에서 실패로 판정한다.
    # 잡지 않으면 이 테스트가 건너뛰기로 끝나 초록처럼 보인다.
    with pytest.raises(BaseException) as excinfo:
        start_database()

    error = excinfo.value
    assert not isinstance(error, pytest.skip.Exception), (
        "Docker가 없을 때 건너뛰면 통합 테스트를 돌리지 않고도 검사가 통과한다"
    )
    assert isinstance(error, Exception)
    assert "통합 테스트에는 Docker가 필요하다" in str(error)
