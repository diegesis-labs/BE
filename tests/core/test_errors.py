"""공통 에러 형식의 테스트 (TC-0.3.1 ~ TC-0.3.5).

모든 테스트는 `create_app()`으로 만든 앱을 쓴다. 처리기를 따로 만든 앱에만 등록해서 확인하면,
`create_app()`이 처리기를 등록하지 않아도 초록이 되기 때문이다.
검증 실패, 처리되지 않은 예외, AppError를 일으킬 경로는 이 파일 안에서만 그 앱에 붙인다.
테스트용 경로가 `app/` 아래에 있으면 실제 서버에도 열린다.
"""

import logging
import re
from collections.abc import Iterator

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import AppError
from app.main import create_app

# 처리되지 않은 예외의 메시지에 넣는 비밀값. 응답 어디에도 나오면 안 된다.
SECRET_DSN = "postgresql://user:secret-pw@db/x"
SECRET_FRAGMENT = "secret-pw"
UNHANDLED_MESSAGE = f"데이터베이스에 연결하지 못했습니다: {SECRET_DSN}"

# HTTP 예외에 넣는 원문. 응답의 message는 이 원문이 아니라 처리기가 정한 한국어 문장이어야 한다.
RAW_HTTP_DETAIL = "raw detail from the raising code"

HANGUL = re.compile(r"[가-힣]")


class Item(BaseModel):
    price: int


class Order(BaseModel):
    item: Item
    extras: list[Item] = []


def build_app() -> FastAPI:
    """create_app()으로 만든 앱에 테스트용 경로를 붙인다."""
    app = create_app()

    @app.get("/test/items")
    def list_items(limit: int) -> dict[str, int]:
        return {"limit": limit}

    @app.post("/test/orders")
    def create_order(order: Order) -> dict[str, int]:
        return {"price": order.item.price}

    @app.get("/test/unhandled")
    def raise_unhandled() -> dict[str, str]:
        raise RuntimeError(UNHANDLED_MESSAGE)

    @app.get("/test/app-error/with-detail")
    def raise_app_error_with_detail() -> dict[str, str]:
        raise AppError(
            409,
            "BOOK_VERSION_CONFLICT",
            "이미 같은 버전의 책이 있습니다.",
            detail={"book_id": "book-1", "versions": [1, 2]},
        )

    @app.get("/test/app-error/without-detail")
    def raise_app_error_without_detail() -> dict[str, str]:
        raise AppError(409, "BOOK_VERSION_CONFLICT", "이미 같은 버전의 책이 있습니다.")

    @app.get("/test/fastapi-http/{status_code}")
    def raise_fastapi_http(status_code: int) -> dict[str, str]:
        raise HTTPException(status_code=status_code, detail=RAW_HTTP_DETAIL)

    @app.get("/test/starlette-http/{status_code}")
    def raise_starlette_http(status_code: int) -> dict[str, str]:
        raise StarletteHTTPException(status_code=status_code, detail=RAW_HTTP_DETAIL)

    return app


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(build_app()) as test_client:
        yield test_client


@pytest.fixture
def server_error_client() -> Iterator[TestClient]:
    """처리되지 않은 예외를 테스트로 다시 던지지 않고, 서버가 보낸 응답을 그대로 돌려준다."""
    with TestClient(build_app(), raise_server_exceptions=False) as test_client:
        yield test_client


def assert_korean_sentence(message: object) -> None:
    assert isinstance(message, str)
    assert HANGUL.search(message), f"message가 한국어 문장이 아니다: {message!r}"


# --- TC-0.3.1 ---------------------------------------------------------------


def test_unknown_path_returns_not_found_with_code_and_message_only(client: TestClient) -> None:
    response = client.get("/api/this-path-does-not-exist")

    assert response.status_code == 404
    body = response.json()
    assert set(body) == {"code", "message"}
    assert body["code"] == "NOT_FOUND"
    assert_korean_sentence(body["message"])


# --- TC-0.3.2 ---------------------------------------------------------------


def test_invalid_query_value_returns_validation_error(client: TestClient) -> None:
    response = client.get("/test/items", params={"limit": "not-a-number"})

    assert response.status_code == 400
    body = response.json()
    assert set(body) == {"code", "message", "detail"}
    assert body["code"] == "VALIDATION_ERROR"
    assert body["message"] == "요청 형식이 올바르지 않습니다."
    assert [item["field"] for item in body["detail"]] == ["limit"]
    for item in body["detail"]:
        assert set(item) == {"field", "reason"}
        assert isinstance(item["reason"], str) and item["reason"]


def test_invalid_nested_body_field_is_named_by_dotted_path_without_location(
    client: TestClient,
) -> None:
    response = client.post(
        "/test/orders",
        json={"item": {"price": "not-a-number"}, "extras": [{"price": "also-not-a-number"}]},
    )

    assert response.status_code == 400
    body = response.json()
    assert set(body) == {"code", "message", "detail"}
    assert body["code"] == "VALIDATION_ERROR"
    assert body["message"] == "요청 형식이 올바르지 않습니다."
    # body나 query 같은 위치는 이름에 넣지 않는다. 목록의 순번도 경로의 한 마디로 잇는다.
    assert sorted(item["field"] for item in body["detail"]) == ["extras.0.price", "item.price"]
    for item in body["detail"]:
        assert set(item) == {"field", "reason"}
        assert isinstance(item["reason"], str) and item["reason"]


# --- TC-0.3.3 ---------------------------------------------------------------


def test_unhandled_exception_returns_internal_error_without_leaking(
    server_error_client: TestClient,
) -> None:
    response = server_error_client.get("/test/unhandled")

    assert response.status_code == 500
    body = response.json()
    assert set(body) == {"code", "message"}
    assert body["code"] == "INTERNAL_ERROR"
    assert_korean_sentence(body["message"])
    # 응답의 어디에도 예외의 메시지, 타입, 스택이 없어야 한다.
    assert SECRET_FRAGMENT not in response.text
    assert "데이터베이스에 연결하지 못했습니다" not in response.text
    assert "RuntimeError" not in response.text
    assert "Traceback" not in response.text


def test_unhandled_exception_is_logged_with_its_stack(
    server_error_client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR):
        server_error_client.get("/test/unhandled")

    logged = [
        record
        for record in caplog.records
        if record.levelno >= logging.ERROR
        and record.exc_info is not None
        and isinstance(record.exc_info[1], RuntimeError)
        and str(record.exc_info[1]) == UNHANDLED_MESSAGE
    ]
    assert logged, "처리되지 않은 예외가 스택과 함께 서버 로그에 남지 않았다"
    assert logged[0].exc_info is not None
    assert logged[0].exc_info[2] is not None


# --- TC-0.3.4 ---------------------------------------------------------------


def test_wrong_method_returns_method_not_allowed(client: TestClient) -> None:
    response = client.post("/test/items")

    assert response.status_code == 405
    body = response.json()
    assert set(body) == {"code", "message"}
    assert body["code"] == "METHOD_NOT_ALLOWED"
    assert_korean_sentence(body["message"])
    # 응답 형식을 바꾸더라도 어떤 메서드를 쓸 수 있는지 알리는 헤더는 그대로 둔다.
    assert response.headers["allow"] == "GET"


# --- TC-0.3.5 ---------------------------------------------------------------


def test_app_error_is_returned_as_given(client: TestClient) -> None:
    response = client.get("/test/app-error/with-detail")

    assert response.status_code == 409
    assert response.json() == {
        "code": "BOOK_VERSION_CONFLICT",
        "message": "이미 같은 버전의 책이 있습니다.",
        "detail": {"book_id": "book-1", "versions": [1, 2]},
    }


def test_app_error_without_detail_omits_the_detail_key(client: TestClient) -> None:
    response = client.get("/test/app-error/without-detail")

    assert response.status_code == 409
    body = response.json()
    assert "detail" not in body
    assert body == {"code": "BOOK_VERSION_CONFLICT", "message": "이미 같은 버전의 책이 있습니다."}


# --- 그 밖의 HTTP 예외 (docs/API.md 2.3절의 표와, 표에 없는 상태의 code) ---------


@pytest.mark.parametrize("source", ["fastapi-http", "starlette-http"])
@pytest.mark.parametrize(
    ("status_code", "code"),
    [
        (401, "NOT_AUTHENTICATED"),
        (404, "NOT_FOUND"),
        (405, "METHOD_NOT_ALLOWED"),
        (409, "CONFLICT"),
        (429, "TOO_MANY_REQUESTS"),
    ],
)
def test_http_exception_is_converted_to_error_format(
    client: TestClient, source: str, status_code: int, code: str
) -> None:
    response = client.get(f"/test/{source}/{status_code}")

    assert response.status_code == status_code
    body = response.json()
    assert set(body) == {"code", "message"}
    assert body["code"] == code
    assert_korean_sentence(body["message"])
    assert RAW_HTTP_DETAIL not in response.text
