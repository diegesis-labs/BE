"""`scripts/login_check.py`의 점검 전 상태 확인의 테스트 (TC-1.7.2).

마이그레이션한 데이터베이스에서 `precheck`를 부른다. 맞지 않는 조건이 있으면 그 조건과 맞추는 SQL이
나오고, 모두 맞으면 빈 목록이다. 그리고 다음을 함께 확인한다.

- 확인하는 동안 세 테이블의 내용이 바뀌지 않는다. 스크립트는 개발자의 데이터를 읽기만 한다
  (E1 S1.7 "못 박을 것").
- `precheck`가 쓰는 연결은 읽기 전용이라서, 그 연결로는 `INSERT`가 실패한다.
- 나온 SQL을 (읽기 전용이 아닌 연결로) 실행하면 그 조건이 맞춰진다. 보여 준 SQL이 틀리면 사람이
  따라 해도 점검을 시작할 수 없기 때문이다.

설정과 확인은 asyncpg로 직접 한다. 맞추는 SQL에는 `BEGIN`과 `COMMIT`이 든 여러 문장이 있으므로,
여러 문장을 한 번에 실행할 수 있는 연결이 필요하다.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

import asyncpg
import pytest

from scripts import login_check
from scripts.login_check import (
    AllowedRow,
    PrecheckProblem,
    SessionRow,
    connect_read_only,
    precheck,
    read_state,
)

pytestmark = pytest.mark.integration

A = "reader-a@example.com"
B = "outsider-b@example.com"
OTHER = "someone-else@example.com"

Statement = tuple[str, tuple[object, ...]]


def plain_dsn(url: str) -> str:
    """asyncpg가 받는 주소. 테스트의 주소는 SQLAlchemy 형식(postgresql+asyncpg://)이다."""
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def execute(url: str, statements: Sequence[Statement]) -> None:
    conn = await asyncpg.connect(plain_dsn(url))
    try:
        for sql, args in statements:
            await conn.execute(sql, *args)
    finally:
        await conn.close()


async def dump_tables(url: str) -> dict[str, list[tuple[object, ...]]]:
    """세 테이블의 모든 행과 모든 컬럼."""
    conn = await asyncpg.connect(plain_dsn(url))
    try:
        return {
            table: [tuple(row) for row in await conn.fetch(f"SELECT * FROM {table} ORDER BY 1")]
            for table in ("allowed_emails", "users", "login_sessions")
        }
    finally:
        await conn.close()


def allow(email: str, role: str = "user") -> Statement:
    return ("INSERT INTO allowed_emails (email, role) VALUES ($1, $2)", (email, role))


def user(email: str, sub: str) -> Statement:
    return (
        "INSERT INTO users (email, google_sub, display_name) VALUES ($1, $2, '이름')",
        (email, sub),
    )


def session(email: str, token_hash: str) -> Statement:
    return (
        "INSERT INTO login_sessions (token_hash, user_id, expires_at) "
        "SELECT $2, id, now() + interval '1 day' FROM users WHERE email = $1",
        (email, token_hash),
    )


# 점검과 상관없는 다른 사람. 어느 경우에나 있으며, 맞지 않는 조건으로 보고되지 않아야 한다.
UNRELATED = (allow(OTHER), user(OTHER, "sub-other"), session(OTHER, "hash-other"))


@dataclass(frozen=True)
class Case:
    setup: tuple[Statement, ...]
    email: str  # 맞지 않는 조건이 가리키는 계정
    words: tuple[str, ...]  # 그 조건의 문장에 들어 있어야 하는 말


CASES = {
    "a_not_allowed": Case(setup=(), email=A, words=("허용 목록",)),
    "a_is_admin": Case(setup=(allow(A, "admin"),), email=A, words=("admin",)),
    "a_has_user_row": Case(
        setup=(allow(A), user(A, "sub-a"), session(A, "hash-a")), email=A, words=("users",)
    ),
    "b_allowed": Case(setup=(allow(A), allow(B)), email=B, words=("허용 목록",)),
    "b_has_user_row": Case(
        setup=(allow(A), user(B, "sub-b"), session(B, "hash-b")), email=B, words=("users",)
    ),
}


@pytest.mark.parametrize("name", list(CASES))
async def test_reports_one_condition_and_its_sql_fixes_it(clean_db: str, name: str) -> None:
    case = CASES[name]
    await execute(clean_db, [*UNRELATED, *case.setup])
    before = await dump_tables(clean_db)

    problems = await precheck(clean_db, allowed_email=A, denied_email=B)

    assert await dump_tables(clean_db) == before
    assert len(problems) == 1, problems
    problem = problems[0]
    assert isinstance(problem, PrecheckProblem)
    assert case.email in problem.problem
    for word in case.words:
        assert word in problem.problem
    # README의 SQL과 같은 꼴이다. 이메일은 lower()로 감싼다.
    assert f"lower('{case.email}')" in problem.fix_sql

    await execute(clean_db, [(problem.fix_sql, ())])
    assert await precheck(clean_db, allowed_email=A, denied_email=B) == []
    # 다른 사람의 행은 맞추는 SQL이 건드리지 않는다.
    after_fix = await dump_tables(clean_db)
    for table, rows in before.items():
        others = [row for row in rows if OTHER in row or "hash-other" in row]
        assert all(row in after_fix[table] for row in others), table


async def test_all_conditions_hold(clean_db: str) -> None:
    await execute(clean_db, [*UNRELATED, allow(A)])
    before = await dump_tables(clean_db)

    assert await precheck(clean_db, allowed_email=A, denied_email=B) == []
    assert await dump_tables(clean_db) == before


async def test_reports_every_condition_and_their_sql_fix_all(clean_db: str) -> None:
    setup = [allow(A, "admin"), user(A, "sub-a"), allow(B), user(B, "sub-b"), session(B, "hash-b")]
    await execute(clean_db, setup)
    before = await dump_tables(clean_db)

    problems = await precheck(clean_db, allowed_email=A, denied_email=B)

    assert await dump_tables(clean_db) == before
    assert len(problems) == 4, problems
    await execute(clean_db, [(problem.fix_sql, ()) for problem in problems])
    assert await precheck(clean_db, allowed_email=A, denied_email=B) == []


async def test_emails_are_compared_in_lowercase(clean_db: str) -> None:
    await execute(clean_db, [allow(A)])

    assert await precheck(clean_db, allowed_email=A.upper(), denied_email=B.upper()) == []


async def test_connection_is_read_only(clean_db: str) -> None:
    conn = await connect_read_only(clean_db)
    try:
        with pytest.raises(asyncpg.exceptions.ReadOnlySQLTransactionError):
            await conn.execute("INSERT INTO allowed_emails (email, role) VALUES ($1, 'user')", A)
    finally:
        await conn.close()

    assert (await dump_tables(clean_db))["allowed_emails"] == []


async def test_precheck_reads_through_read_only_connection(
    clean_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened: list[str] = []
    original = login_check.connect_read_only

    async def spy(database_url: str) -> asyncpg.Connection:
        conn = await original(database_url)
        opened.append(str(await conn.fetchval("SHOW default_transaction_read_only")))
        return conn

    monkeypatch.setattr(login_check, "connect_read_only", spy)

    await precheck(clean_db, allowed_email=A, denied_email=B)

    assert opened == ["on"]


# 점검이 시점마다 읽는 상태(read_state)의 값. 점검 1의 login_sessions 칸(token_hash, expires_at)과
# 점검 2의 전체 행 수는 이 값으로 판정한다(3차 리뷰 TST-4).
ALLOWED_AT = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
A_SESSION_CREATED = datetime(2026, 1, 5, 9, 30, tzinfo=UTC)
A_SESSION_EXPIRES = datetime(2026, 1, 19, 9, 30, tzinfo=UTC)
A_TOKEN_HASH = "a" * 64


async def test_read_state_reads_sessions_of_the_two_accounts_and_counts_all(clean_db: str) -> None:
    await execute(
        clean_db,
        [
            (
                "INSERT INTO allowed_emails (email, role, created_at) VALUES ($1, 'user', $2)",
                (A, ALLOWED_AT),
            ),
            allow(OTHER),
            user(A, "sub-a"),
            user(OTHER, "sub-other"),
            (
                "INSERT INTO login_sessions (token_hash, user_id, expires_at, created_at) "
                "SELECT $2, id, $3, $4 FROM users WHERE email = $1",
                (A, A_TOKEN_HASH, A_SESSION_EXPIRES, A_SESSION_CREATED),
            ),
            # 다른 사람의 로그인 상태 둘. 두 계정의 행에는 나오지 않고, 전체 행 수에만 든다.
            session(OTHER, "hash-other-1"),
            session(OTHER, "hash-other-2"),
        ],
    )
    conn = await asyncpg.connect(plain_dsn(clean_db))
    try:
        a_id = await conn.fetchval("SELECT id FROM users WHERE email = $1", A)
    finally:
        await conn.close()

    state = await read_state(clean_db, emails=(A, B))

    assert state.allowed == (AllowedRow(A, "user", ALLOWED_AT),)
    assert [(row.email, row.google_sub) for row in state.users] == [(A, "sub-a")]
    assert state.sessions_for(A) == (
        SessionRow(A_TOKEN_HASH, a_id, A, A_SESSION_EXPIRES, A_SESSION_CREATED),
    )
    # 두 계정의 행은 A의 것 하나뿐이다. 다른 사람의 행은 담지 않는다.
    assert state.sessions == state.sessions_for(A)
    assert state.sessions_for(B) == ()
    # login_sessions의 전체 행 수는 두 계정과 상관없이 센다(점검 2의 칸).
    assert state.session_total == 3
