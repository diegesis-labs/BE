"""로그인 테스트의 가짜(tests/support/auth_fakes.py)가 지키는 약속의 테스트 (1차 리뷰 ARC-5).

service, 관문, 라우터의 단위 테스트는 이 가짜를 믿고 "저장소에 쓰지 않았다", "조회하지 않았다",
"제약을 어기면 실패한다"를 판정한다. 가짜가 그 약속을 어기면 그 테스트들이 틀린 구현을 통과시킨다.
FakeAuthStore의 약속은 AuthRepository(app/auth/repository.py)와 데이터베이스의 제약
(docs/ARCHITECTURE.md 6절)을 흉내 내는 것이다. 실제 repository의 동작은
tests/auth/test_repository.py가 같은 경우들로 본다.
"""

from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest

from app.auth.repository import ActiveLogin, AllowedEmail
from app.core.ports import Identity, LoginFailedError
from tests.support.auth_fakes import (
    FAKE_AUTHORIZATION_ENDPOINT,
    READER_IDENTITY,
    AuthorizationUrlCall,
    ExchangeCodeCall,
    FakeAuthStore,
    FakeConstraintError,
    FakeIdentityProvider,
    StoreWrite,
)

HOUR = timedelta(hours=1)

# --- FakeIdentityProvider ------------------------------------------------------


def test_authorization_url_records_call_and_carries_state_and_nonce_only() -> None:
    provider = FakeIdentityProvider()

    url = provider.authorization_url(state="s-1", nonce="n-1", code_verifier="v-1")

    assert provider.authorization_url_calls == [
        AuthorizationUrlCall(state="s-1", nonce="n-1", code_verifier="v-1")
    ]
    parts = urlsplit(url)
    assert f"{parts.scheme}://{parts.netloc}{parts.path}" == FAKE_AUTHORIZATION_ENDPOINT
    # 실제 인가 주소처럼 code_verifier는 담지 않는다.
    assert parse_qs(parts.query) == {"state": ["s-1"], "nonce": ["n-1"]}


async def test_exchange_code_records_arguments_and_returns_current_identity() -> None:
    provider = FakeIdentityProvider()

    first = await provider.exchange_code(code="c-1", code_verifier="v-1", expected_nonce="n-1")
    renamed = Identity(sub="sub-2", email="other@example.com", email_verified=False, name=None)
    provider.identity = renamed
    second = await provider.exchange_code(code="c-2", code_verifier="v-2", expected_nonce="n-2")

    assert (first, second) == (READER_IDENTITY, renamed)
    assert provider.exchange_code_calls == [
        ExchangeCodeCall(code="c-1", code_verifier="v-1", expected_nonce="n-1"),
        ExchangeCodeCall(code="c-2", code_verifier="v-2", expected_nonce="n-2"),
    ]


async def test_exchange_code_raises_given_error_after_recording_the_call() -> None:
    error = LoginFailedError("가짜 실패")
    provider = FakeIdentityProvider(error=error)

    with pytest.raises(LoginFailedError) as caught:
        await provider.exchange_code(code="c", code_verifier="v", expected_nonce="n")

    assert caught.value is error
    assert provider.exchange_code_calls == [
        ExchangeCodeCall(code="c", code_verifier="v", expected_nonce="n")
    ]


# --- FakeAuthStore: 데이터베이스의 제약 ---------------------------------------


@pytest.mark.parametrize("email", ["Reader@example.com", "READER@EXAMPLE.COM"])
async def test_emails_must_be_lowercase(email: str) -> None:
    store = FakeAuthStore()

    with pytest.raises(FakeConstraintError, match="ck_email_lowercase"):
        store.allow(email)
    with pytest.raises(FakeConstraintError, match="ck_email_lowercase"):
        store.put_user(email, "sub-1")
    with pytest.raises(FakeConstraintError, match="ck_email_lowercase"):
        await store.create_user(email=email, google_sub="sub-1", display_name=None)
    assert store.allowed_emails == {}
    assert store.users == {}


@pytest.mark.parametrize(
    ("email", "google_sub", "constraint"),
    [
        pytest.param("reader@example.com", "sub-other", "uq_users_email", id="same-email"),
        pytest.param("other@example.com", "sub-reader", "uq_users_google_sub", id="same-sub"),
    ],
)
def test_put_user_rejects_duplicate_email_or_sub(
    email: str, google_sub: str, constraint: str
) -> None:
    store = FakeAuthStore()
    existing = store.put_user("reader@example.com", "sub-reader")

    with pytest.raises(FakeConstraintError, match=constraint):
        store.put_user(email, google_sub)
    assert store.users == {existing.id: existing}


@pytest.mark.parametrize(
    ("email", "google_sub"),
    [
        pytest.param("reader@example.com", "sub-reader", id="same-pair"),
        pytest.param("reader@example.com", "sub-other", id="same-email"),
        pytest.param("other@example.com", "sub-reader", id="same-sub"),
    ],
)
async def test_create_user_returns_none_on_conflict_like_on_conflict_do_nothing(
    email: str, google_sub: str
) -> None:
    store = FakeAuthStore()
    existing = store.put_user("reader@example.com", "sub-reader")

    created = await store.create_user(email=email, google_sub=google_sub, display_name="새 이름")

    assert created is None
    assert store.users == {existing.id: existing}
    # 아무것도 만들지 않았어도 쓰기 메서드를 부른 것은 남는다.
    assert store.writes == [
        StoreWrite(
            "create_user", {"email": email, "google_sub": google_sub, "display_name": "새 이름"}
        )
    ]


async def test_create_user_runs_before_create_user_hook_before_checking_conflicts() -> None:
    store = FakeAuthStore()
    store.before_create_user = lambda: store.put_user("reader@example.com", "sub-reader")

    created = await store.create_user(
        email="reader@example.com", google_sub="sub-reader", display_name=None
    )

    # 훅이 만든 행과 부딪히므로 만들지 않는다. 겹친 다른 요청이 먼저 만든 경우를 흉내 낸다.
    assert created is None
    assert len(store.users) == 1


async def test_create_user_without_conflict_stores_and_returns_the_user() -> None:
    store = FakeAuthStore()

    created = await store.create_user(
        email="reader@example.com", google_sub="sub-reader", display_name="독자"
    )

    assert created is not None
    assert (created.email, created.google_sub, created.display_name) == (
        "reader@example.com",
        "sub-reader",
        "독자",
    )
    assert store.users == {created.id: created}


def test_login_session_needs_unique_hash_and_existing_user() -> None:
    store = FakeAuthStore()
    user = store.put_user("reader@example.com", "sub-reader")
    store.put_login_session("hash-1", user.id, datetime.now(UTC) + HOUR)

    with pytest.raises(FakeConstraintError, match="pk_login_sessions"):
        store.put_login_session("hash-1", user.id, datetime.now(UTC) + HOUR)
    other = store.put_user("other@example.com", "sub-other")
    del store.users[other.id]
    with pytest.raises(FakeConstraintError, match="fk_login_sessions_user_id_users"):
        store.put_login_session("hash-2", other.id, datetime.now(UTC) + HOUR)
    assert set(store.login_sessions) == {"hash-1"}


# --- FakeAuthStore: 읽기 ------------------------------------------------------


async def test_get_allowed_email_compares_exactly_as_given() -> None:
    store = FakeAuthStore()
    allowed = store.allow("reader@example.com", "admin")

    assert await store.get_allowed_email("reader@example.com") == allowed
    # 소문자로 바꾸는 것은 service의 일이다(AuthRepository와 같다).
    assert await store.get_allowed_email("Reader@example.com") is None
    assert await store.get_allowed_email("other@example.com") is None


async def test_find_users_by_email_or_sub_returns_rows_matching_either() -> None:
    store = FakeAuthStore()
    by_email = store.put_user("reader@example.com", "sub-1")
    by_sub = store.put_user("other@example.com", "sub-2")
    store.put_user("third@example.com", "sub-3")

    found = await store.find_users_by_email_or_sub(email="reader@example.com", google_sub="sub-2")

    assert sorted(found, key=lambda user: user.email) == [by_sub, by_email]


async def test_find_active_login_skips_unknown_and_expired_and_records_lookups() -> None:
    store = FakeAuthStore()
    user = store.put_user("reader@example.com", "sub-reader")
    store.put_login_session("expired", user.id, datetime.now(UTC) - HOUR)

    assert await store.find_active_login("unknown") is None
    assert await store.find_active_login("expired") is None
    assert store.lookups == ["unknown", "expired"]
    # 읽기는 쓰기로 남지 않는다.
    assert store.writes == []


async def test_find_active_login_returns_user_session_time_and_allowed_row() -> None:
    store = FakeAuthStore()
    allowed_at = datetime.now(UTC) - 2 * HOUR
    created_at = datetime.now(UTC) - HOUR
    allowed = store.allow("reader@example.com", "admin", created_at=allowed_at)
    reader = store.put_user("reader@example.com", "sub-reader", "독자")
    outsider = store.put_user("outsider@example.com", "sub-outsider")
    store.put_login_session("reader", reader.id, datetime.now(UTC) + HOUR, created_at=created_at)
    store.put_login_session("outsider", outsider.id, datetime.now(UTC) + HOUR)

    assert await store.find_active_login("reader") == ActiveLogin(
        user=reader, session_created_at=created_at, allowed=allowed
    )
    outsider_login = await store.find_active_login("outsider")
    assert outsider_login is not None
    assert outsider_login.allowed is None


def test_allow_and_session_times_default_to_now() -> None:
    store = FakeAuthStore()
    before = datetime.now(UTC)
    allowed = store.allow("reader@example.com")
    user = store.put_user("reader@example.com", "sub-reader")
    store.put_login_session("hash", user.id, before + HOUR)
    after = datetime.now(UTC)

    assert allowed == AllowedEmail(
        email="reader@example.com", role="user", created_at=allowed.created_at
    )
    assert before <= allowed.created_at <= after
    assert before <= store.login_sessions["hash"].created_at <= after


# --- FakeAuthStore: 쓰기와 그 기록 ----------------------------------------------


async def test_writes_are_recorded_but_test_setup_is_not() -> None:
    store = FakeAuthStore()
    store.allow("reader@example.com")
    user = store.put_user("reader@example.com", "sub-reader", "옛 이름")
    store.put_login_session("hash", user.id, datetime.now(UTC) + HOUR)
    assert store.writes == []
    expires_at = datetime.now(UTC) + HOUR

    await store.update_display_name(user.id, "새 이름")
    await store.add_login_session(token_hash="new", user_id=user.id, expires_at=expires_at)
    await store.delete_login_session("hash")
    await store.delete_expired_login_sessions(user.id)

    assert store.writes == [
        StoreWrite("update_display_name", {"user_id": user.id, "display_name": "새 이름"}),
        StoreWrite(
            "add_login_session",
            {"token_hash": "new", "user_id": user.id, "expires_at": expires_at},
        ),
        StoreWrite("delete_login_session", {"token_hash": "hash"}),
        StoreWrite("delete_expired_login_sessions", {"user_id": user.id}),
    ]
    assert store.users[user.id].display_name == "새 이름"
    assert set(store.login_sessions) == {"new"}


async def test_delete_login_session_removes_only_that_hash_and_ignores_unknown() -> None:
    store = FakeAuthStore()
    user = store.put_user("reader@example.com", "sub-reader")
    store.put_login_session("keep", user.id, datetime.now(UTC) + HOUR)
    store.put_login_session("drop", user.id, datetime.now(UTC) + HOUR)

    await store.delete_login_session("drop")
    await store.delete_login_session("unknown")

    assert set(store.login_sessions) == {"keep"}


async def test_delete_expired_login_sessions_removes_only_that_users_expired_rows() -> None:
    store = FakeAuthStore()
    now = datetime.now(UTC)
    reader = store.put_user("reader@example.com", "sub-reader")
    other = store.put_user("other@example.com", "sub-other")
    store.put_login_session("reader-expired", reader.id, now - HOUR)
    store.put_login_session("reader-valid", reader.id, now + HOUR)
    store.put_login_session("other-expired", other.id, now - HOUR)

    await store.delete_expired_login_sessions(reader.id)

    assert set(store.login_sessions) == {"reader-valid", "other-expired"}
