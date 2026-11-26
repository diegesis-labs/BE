"""tests/support/frontend_urls.py의 두 목록이 지키는 약속의 테스트.

두 목록은 판정 함수와 설정 클래스의 테스트가 함께 쓴다. 목록에서 TC-1.2.9의 값이 빠지거나 같은 값이
두 목록에 함께 들어가면, 두 테스트가 모두 초록이어도 TC-1.2.9를 확인하지 않게 된다.
"""

from tests.support.frontend_urls import ACCEPTED_FRONTEND_URLS, REJECTED_FRONTEND_URLS

# testcase.md TC-1.2.9가 이름을 들어 적은 값.
TC_1_2_9_ACCEPTED = {"http://localhost:5173", "http://127.0.0.1:5173", "https://diegesis.example"}
TC_1_2_9_REJECTED = {
    "http://diegesis.example",
    "https://diegesis.example/",
    "https://diegesis.example/app",
    "ftp://diegesis.example",
}


def test_lists_contain_values_named_by_tc_1_2_9() -> None:
    assert TC_1_2_9_ACCEPTED <= set(ACCEPTED_FRONTEND_URLS)
    assert TC_1_2_9_REJECTED <= set(REJECTED_FRONTEND_URLS)


def test_no_value_is_both_accepted_and_rejected() -> None:
    assert set(ACCEPTED_FRONTEND_URLS).isdisjoint(REJECTED_FRONTEND_URLS)


def test_each_list_has_no_duplicates() -> None:
    assert len(set(ACCEPTED_FRONTEND_URLS)) == len(ACCEPTED_FRONTEND_URLS)
    assert len(set(REJECTED_FRONTEND_URLS)) == len(REJECTED_FRONTEND_URLS)
