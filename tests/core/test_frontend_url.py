"""FRONTEND_URL의 모양을 판정하는 함수의 테스트 (TC-1.2.9, docs/CONFIGURATION.md 3.1절, ADR-027).

설정 클래스(app/core/config.py)는 선언만 하므로 판정을 app/core/frontend_url.py에 둔다
(docs/DEVELOPMENT.md 4.2절, 1차 리뷰 ARC-3). 설정 클래스가 이 판정을 거치는지는
tests/core/test_config.py가 같은 값들(tests/support/frontend_urls.py)로 본다.
"""

import pytest

from app.core.frontend_url import check_frontend_url, uses_https
from tests.support.frontend_urls import ACCEPTED_FRONTEND_URLS, REJECTED_FRONTEND_URLS


@pytest.mark.parametrize("url", ACCEPTED_FRONTEND_URLS)
def test_accepted_frontend_url_is_returned_unchanged(url: str) -> None:
    assert check_frontend_url(url) == url


@pytest.mark.parametrize("url", REJECTED_FRONTEND_URLS)
def test_rejected_frontend_url_raises_value_error_naming_the_setting(url: str) -> None:
    # 설정 클래스의 검증은 ValueError를 검증 오류로 바꾼다. 문장에는 어느 설정값인지가 있어야 한다.
    with pytest.raises(ValueError, match="FRONTEND_URL"):
        check_frontend_url(url)


@pytest.mark.parametrize(
    ("url", "https"),
    [
        ("https://diegesis.example", True),
        ("https://localhost:5173", True),
        ("http://localhost:5173", False),
        ("http://127.0.0.1:5173", False),
    ],
)
def test_uses_https_follows_only_the_scheme(url: str, https: bool) -> None:
    """쿠키에 Secure를 붙일지는 FRONTEND_URL의 스킴 하나로만 정한다(ADR-027)."""
    assert uses_https(url) is https
