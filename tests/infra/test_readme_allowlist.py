"""README의 허용 목록 SQL이 마이그레이션한 스키마에서 도는지 확인하는 테스트 (TC-1.6.1).

README의 "허용 목록에 사람 넣고 빼기" 절에 있는 SQL은 운영 환경에서도 사람이 그대로 실행한다.
그래서 테스트는 그 SQL을 자기 안에 옮겨 적지 않고, README에서 읽어서 실행한다. 옮겨 적으면 README가
스키마와 어긋나도 테스트가 통과하기 때문이다(E1 S1.6 "못 박을 것").

- 절은 줄 번호가 아니라 제목으로 찾는다. README의 다른 절이 바뀌면 줄 번호가 밀리기 때문이다. 코드
  블록 안에서 `#`으로 시작하는 줄(셸의 주석)은 제목으로 보지 않는다.
- 그 절의 `sql` 블록을 `BEGIN`과 `COMMIT`을 포함해 적힌 그대로, 적힌 순서대로 실행한다. 블록
  하나를 asyncpg의 `execute`에 인자 없이 넘기면, asyncpg는 여러 문장을 한 번에 보내는 방식
  (simple query)으로 실행한다.
- 그 절에 `sql` 블록이 하나도 없으면 실패한다. 제목이 바뀌거나 블록이 사라졌을 때 아무것도 실행하지
  않고 통과하면 안 되기 때문이다.
- 실행하는 연결과 결과를 읽는 연결을 나눈다. `COMMIT`이 빠져 트랜잭션이 열린 채로 남으면, 다른
  연결에서는 바뀐 내용이 보이지 않아 실패한다.
"""

import re
from collections.abc import Sequence
from pathlib import Path

import asyncpg
import pytest

README = Path(__file__).resolve().parents[2] / "README.md"
SECTION_TITLE = "허용 목록에 사람 넣고 빼기"

FENCE = "```"
HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*$")

READER = "reader@example.com"
OTHER = "other@example.com"


# --- README에서 SQL을 읽는 부분 ---


def section_lines(markdown: str, title: str) -> list[str]:
    """제목이 `title`인 절의 줄. 제목 다음 줄부터, 수준이 같거나 높은 다음 제목의 앞까지다.

    그보다 낮은 수준의 제목(하위 절)은 절 안에 든다. 그런 제목이 없거나 둘 이상이면 ValueError다.
    """
    lines = markdown.splitlines()
    headings: list[tuple[int, int, str]] = []  # (줄의 위치, 수준, 제목)
    in_code = False
    for index, line in enumerate(lines):
        if line.strip().startswith(FENCE):
            in_code = not in_code
            continue
        if in_code:
            continue
        match = HEADING.match(line)
        if match:
            headings.append((index, len(match.group(1)), match.group(2)))

    found = [heading for heading in headings if heading[2] == title]
    if len(found) != 1:
        raise ValueError(f"제목이 {title!r}인 절이 {len(found)}개 있습니다. 하나여야 합니다.")
    start, level, _ = found[0]
    end = next(
        (index for index, other_level, _ in headings if index > start and other_level <= level),
        len(lines),
    )
    return lines[start + 1 : end]


def code_blocks(lines: Sequence[str]) -> list[tuple[str, str]]:
    """줄들 안의 코드 블록. (여는 줄의 언어 표시, 내용)을 적힌 순서대로 돌려준다."""
    blocks: list[tuple[str, str]] = []
    info: str | None = None
    body: list[str] = []
    for line in lines:
        stripped = line.strip()
        if info is None:
            if stripped.startswith(FENCE):
                info = stripped.removeprefix(FENCE).strip()
                body = []
        elif stripped == FENCE:
            blocks.append((info, "\n".join(body)))
            info = None
        else:
            body.append(line)
    if info is not None:
        raise ValueError("닫히지 않은 코드 블록이 있습니다.")
    return blocks


def allowlist_sql(markdown: str) -> list[str]:
    """README의 "허용 목록에 사람 넣고 빼기" 절에 있는 `sql` 블록들. 하나도 없으면 ValueError다."""
    blocks = [
        body for info, body in code_blocks(section_lines(markdown, SECTION_TITLE)) if info == "sql"
    ]
    if not blocks:
        raise ValueError(f"{SECTION_TITLE!r} 절에 sql 블록이 없습니다.")
    return blocks


# --- 위 함수들의 단위 테스트 ---


def test_section_is_found_by_title_and_ends_at_next_heading_of_same_level() -> None:
    markdown = "\n".join(
        [
            "# 문서",
            "## 앞 절",
            "앞",
            "## 찾는 절",
            "본문",
            "### 하위 절",
            "하위",
            "## 다음 절",
            "다음",
        ]
    )

    assert section_lines(markdown, "찾는 절") == ["본문", "### 하위 절", "하위"]


def test_hash_lines_in_code_blocks_are_not_headings() -> None:
    # README의 셸 블록에는 `# macOS의 터미널` 같은 주석이 있다. 이것을 제목으로 보면 절이 일찍
    # 끝나거나, 같은 글자의 주석을 절로 잘못 찾는다.
    markdown = "\n".join(
        [
            "## 찾는 절",
            "```bash",
            "# 셸의 주석",
            "```",
            "```sql",
            "SELECT 1;",
            "```",
            "## 다음 절",
            "```bash",
            "# 찾는 절",
            "```",
        ]
    )

    assert code_blocks(section_lines(markdown, "찾는 절")) == [
        ("bash", "# 셸의 주석"),
        ("sql", "SELECT 1;"),
    ]


@pytest.mark.parametrize("count", [0, 2])
def test_section_title_must_appear_exactly_once(count: int) -> None:
    markdown = "\n".join(["## 다른 절", "본문", *(["## 찾는 절", "본문"] * count)])

    with pytest.raises(ValueError, match="찾는 절"):
        section_lines(markdown, "찾는 절")


def test_allowlist_sql_returns_only_sql_blocks_of_the_section_in_order() -> None:
    markdown = "\n".join(
        [
            f"## {SECTION_TITLE}",
            "```bash",
            "psql",
            "```",
            "```sql",
            "SELECT 1;",
            "SELECT 2;",
            "```",
            "```sql",
            "SELECT 3;",
            "```",
            "## 다음 절",
            "```sql",
            "SELECT 4;",
            "```",
        ]
    )

    assert allowlist_sql(markdown) == ["SELECT 1;\nSELECT 2;", "SELECT 3;"]


@pytest.mark.parametrize(
    "markdown",
    [
        pytest.param(
            f"## {SECTION_TITLE}\n```bash\npsql\n```\n## 다음 절\n```sql\nSELECT 1;\n```",
            id="no-sql-block",
        ),
        pytest.param("## 허용 목록 관리\n```sql\nSELECT 1;\n```", id="renamed-title"),
    ],
)
def test_allowlist_sql_fails_when_nothing_would_run(markdown: str) -> None:
    with pytest.raises(ValueError):
        allowlist_sql(markdown)


def test_unclosed_code_block_fails() -> None:
    with pytest.raises(ValueError, match="닫히지 않은"):
        code_blocks(["```sql", "SELECT 1;"])


# --- README의 SQL을 실제 스키마에서 실행하는 테스트 ---


def plain_dsn(url: str) -> str:
    """asyncpg가 받는 주소. 테스트의 주소는 SQLAlchemy 형식(postgresql+asyncpg://)이다."""
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def fetch(url: str, sql: str) -> list[tuple[object, ...]]:
    conn = await asyncpg.connect(plain_dsn(url))
    try:
        return [tuple(row) for row in await conn.fetch(sql)]
    finally:
        await conn.close()


async def run_blocks(url: str, blocks: Sequence[str]) -> list[str]:
    """블록마다 인자 없이 `execute`로 실행하고, 그동안 서버가 보낸 경고를 돌려준다."""
    warnings: list[str] = []

    def listen(_connection: object, message: object) -> None:
        severity = getattr(message, "severity_en", None) or getattr(message, "severity", "")
        if severity == "WARNING":
            warnings.append(str(message))

    conn = await asyncpg.connect(plain_dsn(url))
    conn.add_log_listener(listen)
    try:
        for block in blocks:
            await conn.execute(block)
        # 경고는 다음 질의의 응답보다 먼저 온다. 그래서 질의를 하나 더 보내 앞의 경고를 모두 받는다.
        await conn.fetchval("SELECT 1")
    finally:
        await conn.close()
    return warnings


async def set_up_two_logged_in_users(url: str) -> None:
    conn = await asyncpg.connect(plain_dsn(url))
    try:
        for email, sub, token_hash in (
            (READER, "sub-reader", "hash-reader"),
            (OTHER, "sub-other", "hash-other"),
        ):
            await conn.execute(
                "INSERT INTO users (email, google_sub, display_name) VALUES ($1, $2, '이름')",
                email,
                sub,
            )
            await conn.execute(
                "INSERT INTO login_sessions (token_hash, user_id, expires_at) "
                "SELECT $2, id, now() + interval '1 day' FROM users WHERE email = $1",
                email,
                token_hash,
            )
    finally:
        await conn.close()


USERS = "SELECT * FROM users ORDER BY email"
SESSIONS = (
    "SELECT u.email, s.* FROM login_sessions s JOIN users u ON u.id = s.user_id ORDER BY u.email"
)


@pytest.mark.integration
async def test_readme_allowlist_sql_runs_and_removes_only_that_persons_login(clean_db: str) -> None:
    blocks = allowlist_sql(README.read_text(encoding="utf-8"))
    await set_up_two_logged_in_users(clean_db)
    users_before = await fetch(clean_db, USERS)
    sessions_before = await fetch(clean_db, SESSIONS)
    assert [row[0] for row in sessions_before] == [OTHER, READER]

    warnings = await run_blocks(clean_db, blocks)

    assert warnings == []
    assert await fetch(clean_db, "SELECT email, role FROM allowed_emails ORDER BY email") == [
        ("tester1@example.com", "user"),
        ("tester2@example.com", "user"),
    ]
    # 사람을 빼도 users 행은 남는다. 기록이 그 행을 가리키기 때문이다(ARCHITECTURE.md 6절).
    assert await fetch(clean_db, USERS) == users_before
    # 뺀 사람의 로그인 상태만 지워지고, 다른 사람의 것은 그대로다(ADR-027).
    assert await fetch(clean_db, SESSIONS) == [row for row in sessions_before if row[0] == OTHER]


@pytest.mark.integration
async def test_run_blocks_reports_server_warnings(clean_db: str) -> None:
    # 위 테스트의 `warnings == []`가 빈 검출기 때문에 통과하는 것이 아님을 확인한다.
    # 트랜잭션 밖의 COMMIT에는 PostgreSQL이 경고("there is no transaction in progress")를 보낸다.
    assert await run_blocks(clean_db, ["SELECT 1;"]) == []
    assert len(await run_blocks(clean_db, ["SELECT 1;", "COMMIT;"])) == 1
