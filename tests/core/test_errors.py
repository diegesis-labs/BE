"""공통 에러 형식의 테스트 (TC-0.3.1 ~ TC-0.3.5).

모든 테스트는 `create_app()`으로 만든 앱을 쓴다. 처리기를 따로 만든 앱에만 등록해서 확인하면,
`create_app()`이 처리기를 등록하지 않아도 초록이 되기 때문이다.
검증 실패, 처리되지 않은 예외, AppError를 일으킬 경로는 이 파일 안에서만 그 앱에 붙인다.
테스트용 경로가 `app/` 아래에 있으면 실제 서버에도 열린다.
"""

import logging
import re
from collections.abc import Iterator
from typing import Any

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
    def raise_fastapi_http(status_code: int, etag: str | None = None) -> dict[str, str]:
        headers = {"ETag": etag} if etag else None
        raise HTTPException(status_code=status_code, detail=RAW_HTTP_DETAIL, headers=headers)

    @app.get("/test/starlette-http/{status_code}")
    def raise_starlette_http(status_code: int, etag: str | None = None) -> dict[str, str]:
        headers = {"ETag": etag} if etag else None
        raise StarletteHTTPException(
            status_code=status_code, detail=RAW_HTTP_DETAIL, headers=headers
        )

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


@pytest.mark.parametrize(
    "content",
    [
        pytest.param(b'{"item": {"price": 1},', id="unparsable-json"),
        pytest.param(b"[1, 2]", id="body-is-not-an-object"),
    ],
)
def test_body_error_without_a_field_has_empty_field(client: TestClient, content: bytes) -> None:
    # 특정 필드를 가리킬 수 없는 오류의 field는 빈 문자열이다(API.md 2.3절). 깨진 JSON의 오류
    # 위치에는 글자 번호가 들어 있어서, 그것을 이름으로 이으면 "12" 같은 없는 필드가 나간다.
    response = client.post(
        "/test/orders", content=content, headers={"content-type": "application/json"}
    )

    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert [item["field"] for item in body["detail"]] == [""]
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
        # 표에 있는 상태는 표의 code를 쓴다. FastAPI는 본문을 해석하지 못하면 스스로 400을 던진다.
        (400, "VALIDATION_ERROR"),
        (401, "NOT_AUTHENTICATED"),
        (404, "NOT_FOUND"),
        (405, "METHOD_NOT_ALLOWED"),
        (500, "INTERNAL_ERROR"),
        # 표에 없는 상태는 HTTP 상태의 영문 이름을 쓴다.
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


def error_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    """에러 처리기의 로거가 남긴 ERROR 이상의 기록."""
    return [
        record
        for record in caplog.records
        if record.name == "app.core.errors" and record.levelno >= logging.ERROR
    ]


@pytest.mark.parametrize("source", ["fastapi-http", "starlette-http"])
def test_http_exception_with_unnamed_status_is_an_internal_error(
    client: TestClient, caplog: pytest.LogCaptureFixture, source: str
) -> None:
    # 499처럼 HTTP 표준에 이름이 없는 상태는 처리기가 code를 정할 수 없다. 던진 코드의 잘못이므로
    # 예상하지 못한 문제(500, INTERNAL_ERROR)로 응답한다. 처리기 자신이 예외를 내면 안 된다.
    # client는 서버의 예외를 테스트로 다시 던지므로, 처리기가 터지면 여기서 실패한다.
    with caplog.at_level(logging.ERROR, logger="app.core.errors"):
        response = client.get(f"/test/{source}/499")

    assert response.status_code == 500
    assert response.json() == {
        "code": "INTERNAL_ERROR",
        "message": "서버에서 예상하지 못한 문제가 생겼습니다.",
    }
    # 응답은 500이지만 던진 상태는 499다. 무엇을 던졌는지는 서버 로그에만 남는다.
    records = error_records(caplog)
    assert len(records) == 1, records
    assert "499" in records[0].getMessage()
    assert f"/test/{source}/499" in records[0].getMessage()


@pytest.mark.parametrize("source", ["fastapi-http", "starlette-http"])
@pytest.mark.parametrize("status_code", [500, 503, 499])
def test_http_exception_answered_as_server_error_is_logged_with_its_stack(
    client: TestClient, caplog: pytest.LogCaptureFixture, source: str, status_code: int
) -> None:
    # 코드가 직접 던진 5xx와 이름 없는 상태(499 → 500)는 응답만으로는 처리되지 않은 예외와 구별되지
    # 않는다. 원인을 찾을 수 있게 무엇을 어디서 던졌는지를 서버 로그에 스택과 함께 남긴다.
    with caplog.at_level(logging.ERROR, logger="app.core.errors"):
        response = client.get(f"/test/{source}/{status_code}")

    assert response.status_code >= 500
    records = error_records(caplog)
    assert len(records) == 1, records
    message = records[0].getMessage()
    assert "GET" in message and f"/test/{source}/{status_code}" in message, message
    assert str(status_code) in message, message
    assert RAW_HTTP_DETAIL in message, message
    exc_info = records[0].exc_info
    assert exc_info is not None, "스택이 남지 않았다"
    assert isinstance(exc_info[1], StarletteHTTPException)
    assert exc_info[1].status_code == status_code
    assert exc_info[2] is not None


@pytest.mark.parametrize("source", ["fastapi-http", "starlette-http"])
@pytest.mark.parametrize("status_code", [400, 404, 409])
def test_http_exception_answered_as_client_error_is_not_logged_as_error(
    client: TestClient, caplog: pytest.LogCaptureFixture, source: str, status_code: int
) -> None:
    # 4xx는 요청한 쪽의 문제다. 서버 오류 로그에 섞이면 원인을 찾아야 할 기록이 묻힌다.
    with caplog.at_level(logging.ERROR, logger="app.core.errors"):
        response = client.get(f"/test/{source}/{status_code}")

    assert response.status_code == status_code
    assert error_records(caplog) == []


@pytest.mark.parametrize("source", ["fastapi-http", "starlette-http"])
@pytest.mark.parametrize("status_code", [204, 205, 304])
def test_http_exception_without_body_status_has_no_body(
    client: TestClient, source: str, status_code: int
) -> None:
    # 이 상태들의 응답에는 본문이 있으면 안 된다(RFC 9110). 본문을 붙이면 서버가 응답을 끊는다.
    response = client.get(f"/test/{source}/{status_code}")

    assert response.status_code == status_code
    assert response.content == b""


@pytest.mark.parametrize("source", ["fastapi-http", "starlette-http"])
def test_http_exception_without_body_keeps_its_headers(client: TestClient, source: str) -> None:
    # 본문을 빼더라도 예외가 함께 실은 헤더(304의 ETag 등)는 그대로 보낸다.
    response = client.get(f"/test/{source}/304", params={"etag": '"v1"'})

    assert response.status_code == 304
    assert response.content == b""
    assert response.headers["etag"] == '"v1"'


# --- OpenAPI 문서의 검증 실패 응답 (docs/API.md 1절, 2.3절) -------------------------


def schema_of(document: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
    ref = response["content"]["application/json"]["schema"]["$ref"]
    assert ref.startswith("#/components/schemas/"), ref
    return document["components"]["schemas"][ref.removeprefix("#/components/schemas/")]


def test_openapi_documents_validation_failure_as_400_in_error_format(client: TestClient) -> None:
    # 프론트엔드는 이 문서에서 타입을 만든다. 실제 응답(400, {code, message, detail})과 같아야 한다.
    document = client.get("/api/openapi.json").json()

    for path, operations in document["paths"].items():
        for method, operation in operations.items():
            assert "422" not in operation["responses"], f"{method.upper()} {path}에 422가 있다"
    schemas = document["components"]["schemas"]
    assert "HTTPValidationError" not in schemas
    assert "ValidationError" not in schemas

    actual = client.get("/test/items", params={"limit": "not-a-number"}).json()
    for path, method in (("/test/items", "get"), ("/test/orders", "post")):
        error = schema_of(document, document["paths"][path][method]["responses"]["400"])
        assert set(error["properties"]) == set(actual) == {"code", "message", "detail"}
        # detail은 추가 정보가 있을 때에만 들어간다(docs/API.md 2.3절). 같은 400이라도
        # 본문을 해석하지 못한 HTTP 예외에는 detail이 없다
        # (test_body_parse_failure_matches_documented_400).
        assert set(error["required"]) == {"code", "message"}
        assert error["properties"]["code"]["type"] == "string"
        assert error["properties"]["code"]["const"] == actual["code"] == "VALIDATION_ERROR"
        assert error["properties"]["message"]["type"] == "string"
        items = error["properties"]["detail"]
        assert items["type"] == "array"
        item_ref = items["items"]["$ref"].removeprefix("#/components/schemas/")
        item = schemas[item_ref]
        assert set(item["properties"]) == set(actual["detail"][0]) == {"field", "reason"}
        assert set(item["required"]) == {"field", "reason"}
        assert item["properties"]["field"]["type"] == "string"
        assert item["properties"]["reason"]["type"] == "string"
        assert all(isinstance(actual["detail"][0][key], str) for key in ("field", "reason"))


def test_body_parse_failure_matches_documented_400(client: TestClient) -> None:
    # UTF-8이 아닌 본문은 FastAPI가 해석하지 못해 스스로 HTTP 예외 400을 던진다. 그 응답도
    # 같은 operation의 문서가 적은 400 스키마에 맞아야 한다. 프론트엔드는 그 문서에서 만든
    # 타입으로 응답을 읽는다.
    document = client.get("/api/openapi.json").json()
    response = client.post(
        "/test/orders",
        content=b'{"item": {"price": "\xff"}}',
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 400
    body = response.json()
    error = schema_of(document, document["paths"]["/test/orders"]["post"]["responses"]["400"])
    missing = set(error["required"]) - set(body)
    assert not missing, f"문서가 필수로 적은 키가 응답에 없다: {missing} (응답: {body})"
    assert set(body) <= set(error["properties"]), body
    assert body["code"] == error["properties"]["code"]["const"]
    assert isinstance(body["message"], str)


def test_openapi_does_not_add_400_to_operations_without_input(client: TestClient) -> None:
    document = client.get("/api/openapi.json").json()

    assert set(document["paths"]["/api/health"]["get"]["responses"]) == {"200"}
