---
title: API(프론트엔드 연동 규약)
description: 프론트엔드가 백엔드를 호출할 때 지켜야 하는 공통 규칙과 엔드포인트별 요청·응답 형식을 예시와 함께 정의하는 문서다.
---

# API

이 문서는 프론트엔드와 백엔드가 주고받는 요청과 응답의 약속을 정의합니다. 왜 이런 방식을 골랐는지는 [ADR-005](ADR.md#adr-005-프론트엔드와의-api-연동-방식)와 [ADR-006](ADR.md#adr-006-로그인과-접근-제한)에, 요청들이 어떤 순서로 오가는지는 [ARCHITECTURE.md](ARCHITECTURE.md#3-책을-읽는-동안의-흐름)에, 낯선 용어의 뜻은 [GLOSSARY.md](GLOSSARY.md)에 있습니다.

이 문서의 엔드포인트는 구현 전에 작성한 초안입니다. 서버가 구현된 뒤에는 서버가 자동으로 만들어 내는 OpenAPI 문서(`/api/openapi.json`)가 세부 형식의 기준이 되며, 이 문서는 전체 흐름과 규칙을 설명하는 역할을 맡습니다.

## 1. 프론트엔드가 남겨 둔 합의 항목에 대한 답

프론트엔드 레포의 `docs/architecture.md`에는 백엔드와 합의해야 할 항목 다섯 가지가 남아 있습니다. 각 항목에 대한 백엔드의 답은 다음과 같습니다.

| 프론트엔드의 질문 | 백엔드의 답 |
| --- | --- |
| API 기본 경로와 로컬 포트 | 모든 경로에 `/api` 접두사를 붙이고, 로컬 개발 서버는 `8080` 포트를 씁니다. 프론트엔드의 현재 설정과 같으므로 고칠 것이 없습니다. |
| 인증 방식 | 쿠키 방식을 씁니다. 백엔드가 Google 로그인을 처리한 다음, 스크립트가 읽을 수 없는 쿠키를 브라우저에 심습니다. 프론트엔드는 지금처럼 `credentials: 'include'`로 요청하면 됩니다. |
| 에러 응답 형식 | `{ "code", "message", "detail" }` 형식을 씁니다. 자세한 내용은 아래 2.3절에 있습니다. |
| API 스펙 공유 방식 | 서버가 `/api/openapi.json`으로 OpenAPI 문서를 제공합니다. 프론트엔드는 이 문서에서 TypeScript 타입을 자동으로 생성할 수 있으며, 같은 내용을 브라우저에서 `/api/docs`로 볼 수 있습니다. |
| 헬스체크 엔드포인트 | `GET /api/health`이며, `{ "status": "ok" }`를 응답합니다. |

## 2. 공통 규칙

### 2.1 요청과 응답의 형식

- 요청과 응답의 본문은 JSON이며, 필드 이름은 `snake_case`로 씁니다.
- 시각은 UTC 기준의 ISO 8601 문자열로 표현합니다. 예를 들면 `"2026-12-01T12:05:00Z"`와 같습니다.
- 길이와 위치는 밀리초 단위의 정수로 표현하며, 필드 이름 끝에 `_ms`를 붙입니다.
- 번호에는 필드 이름 끝에 `_no`를, 인덱스에는 `_idx`를 붙입니다. 예를 들어 `chapter_no`는 1부터 세고, `first_sentence_idx`는 0부터 셉니다. 다만 목록의 항목이 자기 자신의 인덱스를 담을 때에는 `idx`라고만 씁니다. 번호와 인덱스의 뜻은 [GLOSSARY.md](GLOSSARY.md#표기와-관련된-용어)에, 이렇게 정한 이유는 [ADR-017](ADR.md#adr-017-번호와-인덱스의-구분)에 있습니다.

### 2.2 로그인 상태

로그인에 성공하면 백엔드가 쿠키를 심고, 그 뒤의 모든 요청은 쿠키로 사용자를 식별합니다. 그래서 프론트엔드는 토큰을 저장하거나 요청 헤더에 붙일 필요가 없습니다. 다만 로그인하지 않은 상태로 보호된 경로를 호출하면 `401` 응답을 받으므로, 프론트엔드는 이 응답을 받았을 때 로그인 화면으로 보내면 됩니다.

쿠키 방식이 안정적으로 동작하려면 배포 환경에서 프론트엔드와 백엔드가 같은 도메인 아래에 있어야 합니다. 이 조건에 대한 설명은 [INFRA.md](INFRA.md)에 있습니다.

### 2.3 에러 응답

요청이 실패하면 백엔드는 알맞은 HTTP 상태 코드와 함께 아래 형식의 본문을 응답합니다.

| 필드 | 설명 |
| --- | --- |
| `code` | 프로그램이 분기하는 데 쓰는 식별자입니다. 대문자와 밑줄로 씁니다. |
| `message` | 사람이 읽을 수 있는 설명입니다. 화면에 그대로 보여 주어도 됩니다. |
| `detail` | 추가 정보가 있을 때에만 들어갑니다. 예를 들어 어느 필드가 잘못됐는지를 담습니다. |

```json
{
  "code": "VALIDATION_ERROR",
  "message": "요청 형식이 올바르지 않습니다.",
  "detail": [{ "field": "first_sentence_idx", "reason": "0 이상의 정수여야 합니다." }]
}
```

검증 오류(`VALIDATION_ERROR`)의 `detail`은 `{ "field", "reason" }`의 목록이며, 두 값은 언제나 문자열입니다. `field`는 잘못된 필드의 이름이고, 안쪽의 필드는 점으로 잇습니다. 예를 들어 `item.price`와 같으며, 목록 안의 항목은 `extras.0.price`처럼 그 항목의 인덱스를 넣습니다. 본문이 JSON으로 읽히지 않거나 본문 전체의 모양이 틀려서 특정 필드를 가리킬 수 없으면 `field`는 빈 문자열 `""`입니다.

```json
{
  "code": "VALIDATION_ERROR",
  "message": "요청 형식이 올바르지 않습니다.",
  "detail": [{ "field": "", "reason": "JSON decode error" }]
}
```

자주 쓰이는 에러 코드는 다음과 같습니다.

| HTTP 상태 | `code` | 언제 발생하는가 |
| --- | --- | --- |
| 400 | `VALIDATION_ERROR` | 요청의 형식이나 값이 잘못됐을 때 |
| 401 | `NOT_AUTHENTICATED` | 로그인하지 않았거나 로그인 상태가 만료됐을 때 |
| 403 | `NOT_ALLOWED` | 허용 목록에 없는 계정일 때 |
| 403 | `ADMIN_ONLY` | 관리자만 쓸 수 있는 경로를 일반 사용자가 호출했을 때 |
| 404 | `NOT_FOUND` | 요청한 책, 챕터, 선곡 기록 등이 없을 때 |
| 405 | `METHOD_NOT_ALLOWED` | 경로는 있지만 그 메서드로는 호출할 수 없을 때 |
| 422 | `BUNDLE_INVALID` | 올린 산출물 묶음이 규격에 어긋날 때 (4.9절) |
| 500 | `INTERNAL_ERROR` | 서버 내부에서 예상하지 못한 문제가 생겼을 때 |

위 표에 없는 상태 코드로 응답할 때에는 그 HTTP 상태의 영문 이름을 대문자와 밑줄로 쓴 값을 `code`로 씁니다. 예를 들어 409이면 `CONFLICT`입니다.

## 3. 엔드포인트 목록

| 메서드와 경로 | 용도 | 권한 |
| --- | --- | --- |
| [`GET /api/health`](#41-헬스체크) | 서버가 살아 있는지 확인합니다. | 누구나 |
| [`GET /api/auth/google/login`](#42-로그인과-로그아웃) | Google 로그인 화면으로 이동시킵니다. | 누구나 |
| [`GET /api/auth/google/callback`](#42-로그인과-로그아웃) | Google이 로그인 결과를 돌려주는 주소입니다. | Google만 호출 |
| [`POST /api/auth/logout`](#42-로그인과-로그아웃) | 로그아웃합니다. | 로그인한 사용자 |
| [`GET /api/me`](#43-내-정보) | 내 정보를 조회합니다. | 로그인한 사용자 |
| [`GET /api/me/settings`](#44-선곡-설정) | 내 선곡 설정을 조회합니다. | 로그인한 사용자 |
| [`PUT /api/me/settings`](#44-선곡-설정) | 내 선곡 설정을 바꿉니다. | 로그인한 사용자 |
| [`GET /api/books`](#45-책-목록과-책-정보) | 책 목록을 조회합니다. | 로그인한 사용자 |
| [`GET /api/books/{book_id}`](#45-책-목록과-책-정보) | 책 한 권의 정보와 챕터 목록을 조회합니다. | 로그인한 사용자 |
| [`GET /api/books/{book_id}/chapters/{chapter_no}`](#46-챕터-본문) | 챕터의 본문을 조회합니다. | 로그인한 사용자 |
| [`POST /api/books/{book_id}/position`](#47-위치-알림) | 화면에 보이는 문장의 범위를 알리고, 곡을 어떻게 할지 응답받습니다. | 로그인한 사용자 |
| [`POST /api/recommendations/{id}/events`](#48-반응-기록) | 재생, 중단, 좋아요 같은 반응을 기록합니다. | 로그인한 사용자 |
| [`POST /api/admin/bundles`](#49-관리자-산출물-묶음-적재) | 산출물 묶음을 올립니다. | 관리자 |
| [`GET /api/admin/allowed-emails`](#410-관리자-허용-목록) | 허용 목록을 조회합니다. | 관리자 |
| [`POST /api/admin/allowed-emails`](#410-관리자-허용-목록) | 허용 목록에 한 사람을 추가합니다. | 관리자 |
| [`DELETE /api/admin/allowed-emails/{email}`](#410-관리자-허용-목록) | 허용 목록에서 한 사람을 뺍니다. | 관리자 |
| [`GET /api/admin/exports/recommendations`](#411-관리자-평가-자료-내보내기) | 선곡 기록을 CSV로 내려받습니다. | 관리자 |
| [`GET /api/admin/exports/playback-events`](#411-관리자-평가-자료-내보내기) | 반응 기록을 CSV로 내려받습니다. | 관리자 |

## 4. 엔드포인트별 형식과 예시

이 절은 모든 엔드포인트를 같은 틀로 적습니다. 엔드포인트 하나가 가장 바깥의 항목이고, 그 아래에 **Request Header**, **Request Body**, **Response Body**를 들여 써서 차례로 적습니다. 응답에 눈여겨볼 헤더가 있는 엔드포인트에는 **Response Header**를, 덧붙일 설명이 있는 엔드포인트에는 **설명**을 추가로 적습니다.

예시를 읽을 때에는 다음 세 가지를 알아 두면 됩니다.

- `Cookie` 헤더의 `diegesis_session`은 로그인 상태를 담은 쿠키이며, 예시에 적힌 값은 형태를 보여 주기 위한 것입니다. 이 헤더는 프론트엔드가 `credentials: 'include'`로 요청하면 브라우저가 자동으로 붙이므로, 프론트엔드 코드가 직접 다루지 않습니다.
- `Content-Type: application/json` 헤더는 요청에 JSON 본문이 있을 때에만 붙입니다.
- 요청이 실패했을 때의 응답은 모든 엔드포인트가 2.3절의 형식을 따르므로, 이 절에서는 성공했을 때의 응답만 적습니다.

### 4.1 헬스체크

- **`GET /api/health`**: 서버가 살아 있는지 확인합니다.
  - **Request Header**: 필요한 헤더가 없습니다. 로그인하지 않아도 호출할 수 있습니다.
  - **Request Body**: 없습니다.
  - **Response Body** (`200 OK`)

    ```json
    { "status": "ok" }
    ```

### 4.2 로그인과 로그아웃

로그인은 화면 이동으로 이루어지며, 프론트엔드가 JSON을 주고받지 않습니다. 순서는 다음과 같습니다.

1. 프론트엔드가 브라우저를 `GET /api/auth/google/login`으로 이동시킵니다.
2. 백엔드가 브라우저를 Google 로그인 화면으로 보냅니다.
3. 사용자가 로그인하면 Google이 브라우저를 `GET /api/auth/google/callback`으로 돌려보냅니다.
4. 백엔드는 그 계정의 이메일이 허용 목록에 있는지 확인합니다.
   - 목록에 있다면 로그인 상태를 만들고 쿠키를 심은 다음, 브라우저를 프론트엔드의 첫 화면으로 보냅니다.
   - 목록에 없다면 쿠키를 심지 않고, 브라우저를 프론트엔드의 `/login?error=NOT_ALLOWED`로 보냅니다.

각 엔드포인트의 형식은 다음과 같습니다.

- **`GET /api/auth/google/login`**: 브라우저를 Google 로그인 화면으로 이동시킵니다.
  - **Request Header**: 필요한 헤더가 없습니다. 프론트엔드는 이 주소를 `fetch`로 호출하지 않고, 브라우저의 주소를 이 주소로 바꿉니다.
  - **Request Body**: 없습니다.
  - **Response Header** (`302 Found`)

    ```http
    Location: https://accounts.google.com/o/oauth2/v2/auth?client_id=...&redirect_uri=...&state=...
    ```

  - **Response Body**: 없습니다.

- **`GET /api/auth/google/callback`**: Google이 로그인 결과를 돌려주는 주소입니다. 프론트엔드가 직접 호출하지 않습니다.
  - **Request Header**: 필요한 헤더가 없습니다. 로그인 결과는 Google이 주소 뒤에 붙여 주는 `code`와 `state` 쿼리로 전달됩니다.

    ```http
    GET /api/auth/google/callback?code=4/0AeaYSH...&state=Zx81kQ...
    ```

  - **Request Body**: 없습니다.
  - **Response Header** (`302 Found`): 허용 목록에 있는 계정이라면 쿠키를 심고 프론트엔드의 첫 화면으로 보냅니다.

    ```http
    Location: http://localhost:5173/
    Set-Cookie: diegesis_session=4mXq8ZpT1vK0; HttpOnly; Secure; SameSite=Lax; Path=/
    ```

    허용 목록에 없는 계정이라면 쿠키를 심지 않고 아래 주소로 보냅니다.

    ```http
    Location: http://localhost:5173/login?error=NOT_ALLOWED
    ```

  - **Response Body**: 없습니다.

- **`POST /api/auth/logout`**: 로그아웃합니다.
  - **Request Header**

    ```http
    Cookie: diegesis_session=4mXq8ZpT1vK0
    ```

  - **Request Body**: 없습니다.
  - **Response Header** (`204 No Content`): 브라우저에 남아 있는 쿠키를 지웁니다.

    ```http
    Set-Cookie: diegesis_session=; Max-Age=0; Path=/
    ```

  - **Response Body**: 없습니다.

### 4.3 내 정보

- **`GET /api/me`**: 로그인한 사용자 자신의 정보를 조회합니다.
  - **Request Header**

    ```http
    Cookie: diegesis_session=4mXq8ZpT1vK0
    ```

  - **Request Body**: 없습니다.
  - **Response Body** (`200 OK`)

    ```json
    {
      "id": "0b9f6c1e-2c8a-4f5e-9a51-3d0c7b1e2f44",
      "email": "reader@example.com",
      "display_name": "독자",
      "role": "user"
    }
    ```

  - **설명**: `role`은 `user` 또는 `admin`입니다.

### 4.4 선곡 설정

- **`GET /api/me/settings`**: 내 선곡 설정을 조회합니다.
  - **Request Header**

    ```http
    Cookie: diegesis_session=4mXq8ZpT1vK0
    ```

  - **Request Body**: 없습니다.
  - **Response Body** (`200 OK`)

    ```json
    { "strategy": "embedding", "embedding_model": "muq-mulan" }
    ```

  - **설명**
    - `strategy`는 선곡 방식이며 `embedding`(장면에 맞춘 선곡), `random`(무작위 선곡), `silent`(음악 없음) 가운데 하나입니다.
    - `embedding_model`은 임베딩 모델의 이름이며, 현재는 `muq-mulan`과 `laion-clap-music` 가운데 하나입니다. 이 값은 선곡 방식이 `embedding`일 때에만 의미가 있습니다.

- **`PUT /api/me/settings`**: 내 선곡 설정을 바꿉니다.
  - **Request Header**

    ```http
    Cookie: diegesis_session=4mXq8ZpT1vK0
    Content-Type: application/json
    ```

  - **Request Body**

    ```json
    { "strategy": "random", "embedding_model": "muq-mulan" }
    ```

  - **Response Body** (`200 OK`): 바뀐 뒤의 설정을 조회할 때와 같은 형식으로 응답합니다.

    ```json
    { "strategy": "random", "embedding_model": "muq-mulan" }
    ```

### 4.5 책 목록과 책 정보

- **`GET /api/books`**: 책 목록을 조회합니다.
  - **Request Header**

    ```http
    Cookie: diegesis_session=4mXq8ZpT1vK0
    ```

  - **Request Body**: 없습니다.
  - **Response Body** (`200 OK`)

    ```json
    {
      "books": [
        {
          "id": "sample-novel",
          "title": "견본 소설",
          "author": "견본 작가",
          "language": "ko",
          "chapter_count": 3
        }
      ]
    }
    ```

- **`GET /api/books/{book_id}`**: 책 한 권의 정보와 챕터 목록을 조회합니다.
  - **Request Header**

    ```http
    Cookie: diegesis_session=4mXq8ZpT1vK0
    ```

  - **Request Body**: 없습니다.
  - **Response Body** (`200 OK`)

    ```json
    {
      "id": "sample-novel",
      "title": "견본 소설",
      "author": "견본 작가",
      "language": "ko",
      "chapters": [
        { "chapter_no": 1, "title": "제1장", "first_sentence_idx": 0, "last_sentence_idx": 511 },
        { "chapter_no": 2, "title": "제2장", "first_sentence_idx": 512, "last_sentence_idx": 1040 }
      ],
      "last_position": { "chapter_no": 1, "first_sentence_idx": 412 }
    }
    ```

  - **설명**: `last_position`은 사용자가 이 책을 마지막으로 읽은 위치입니다. 처음 읽는 책이라면 `null`입니다.

### 4.6 챕터 본문

- **`GET /api/books/{book_id}/chapters/{chapter_no}`**: 챕터의 본문을 조회합니다.
  - **Request Header**

    ```http
    Cookie: diegesis_session=4mXq8ZpT1vK0
    ```

  - **Request Body**: 없습니다.
  - **Response Body** (`200 OK`)

    ```json
    {
      "book_id": "sample-novel",
      "chapter_no": 1,
      "title": "제1장",
      "paragraphs": [
        {
          "paragraph_idx": 0,
          "sentences": [
            { "idx": 0, "text": "기차가 역을 빠져나가자 창밖으로 낮은 지붕들이 천천히 흘러갔다." },
            { "idx": 1, "text": "나는 이마를 유리창에 기댄 채 한동안 아무 생각도 하지 않았다." }
          ]
        },
        {
          "paragraph_idx": 1,
          "sentences": [
            { "idx": 2, "text": "옆자리의 라디오에서 오래된 노래가 작게 흘러나오기 시작했다." }
          ]
        }
      ]
    }
    ```

  - **설명**
    - 본문은 문단의 목록이고, 각 문단은 문장의 목록입니다. 문단의 `paragraph_idx`는 챕터 안에서 0부터 세고, 문장마다 붙은 `idx`는 문장 인덱스입니다.
    - 프론트엔드는 이 구조를 바탕으로 직접 페이지를 나누며, 한 페이지에 보이는 첫 문장과 마지막 문장의 `idx`를 기억해 두었다가 4.7절의 위치 알림 요청에 씁니다.
    - 장면의 경계는 이 응답에 들어 있지 않습니다. 어느 장면의 곡을 틀지는 백엔드가 판단하기 때문입니다.

### 4.7 위치 알림

- **`POST /api/books/{book_id}/position`**: 화면에 보이는 문장의 범위를 알리고, 곡을 어떻게 할지 응답받습니다. 책을 처음 열었을 때와 화면에 보이는 범위가 바뀔 때마다 호출합니다.
  - **Request Header**

    ```http
    Cookie: diegesis_session=4mXq8ZpT1vK0
    Content-Type: application/json
    ```

  - **Request Body**

    ```json
    {
      "chapter_no": 1,
      "first_sentence_idx": 412,
      "last_sentence_idx": 431,
      "trigger": "page_turn",
      "current_recommendation_id": "8a2f4b1c-3d5e-4f6a-9b7c-0d1e2f3a4b5c"
    }
    ```

    | 요청 필드 | 설명 |
    | --- | --- |
    | `chapter_no` | 지금 보고 있는 챕터의 번호입니다. |
    | `first_sentence_idx` | 화면에 보이는 첫 문장의 문장 인덱스입니다. |
    | `last_sentence_idx` | 화면에 보이는 마지막 문장의 문장 인덱스입니다. |
    | `trigger` | 이 요청을 보내게 된 계기입니다. 페이지를 넘겼다면 `page_turn`, 재생 중이던 곡이 끝났다면 `track_ended`를 보냅니다. |
    | `current_recommendation_id` | 지금 재생 중인 곡을 받을 때 함께 받았던 `recommendation_id`입니다. 재생 중인 곡이 없다면 `null`을 보냅니다. |

  - **Response Body** (`200 OK`): 응답의 `action`은 아래 세 가지 가운데 하나이며, 프론트엔드는 이 값에 따라 동작합니다.

    | `action` | 뜻 | 프론트엔드가 할 일 |
    | --- | --- | --- |
    | `play` | 새 곡을 틀어야 합니다. | 응답에 담긴 곡으로 바꿔서 재생합니다. |
    | `keep` | 지금 재생 중인 곡이 이 장면의 곡입니다. | 지금 재생 중인 곡을 그대로 둡니다. |
    | `silence` | 지금은 곡을 틀지 않습니다. | 재생 중인 곡이 있다면 멈춥니다. |

    새 곡을 틀어야 할 때(`play`)의 응답은 다음과 같습니다.

    ```json
    {
      "action": "play",
      "recommendation_id": "c41e7a90-6b2d-4f0a-b1c3-9e8d7f6a5b40",
      "track": {
        "id": "trk_0042",
        "title": "Quiet Streets",
        "artist": "Example Artist",
        "audio_url": "https://storage.example.com/audio/trk_0042.mp3?expires=1796126700&signature=3f9a1c",
        "audio_url_expires_at": "2026-12-01T13:00:00Z",
        "duration_ms": 184000,
        "segment": { "start_ms": 30000, "end_ms": 60000 },
        "license": "CC0 1.0",
        "attribution": null,
        "liked": false
      }
    }
    ```

    장면이 그대로일 때(`keep`)의 응답은 다음과 같습니다.

    ```json
    { "action": "keep" }
    ```

    곡을 틀지 않을 때(`silence`)의 응답은 다음과 같습니다.

    ```json
    { "action": "silence", "cooldown_until": "2026-12-01T12:05:00Z" }
    ```

  - **설명**
    - 요청의 `first_sentence_idx`와 `last_sentence_idx`는 `chapter_no` 챕터의 범위, 곧 4.5절 응답에 있는 그 챕터의 `first_sentence_idx`부터 `last_sentence_idx`까지의 안에 있어야 합니다. 그리고 요청의 `first_sentence_idx`는 `last_sentence_idx`보다 클 수 없습니다. 이를 어기면 `400 VALIDATION_ERROR`를 응답합니다.
    - `segment`는 장면과 가장 잘 맞아떨어진 구간의 위치이며, 프론트엔드는 곡의 맨 앞이 아니라 이 구간이 시작하는 위치(`start_ms`)부터 재생합니다.
    - 백엔드는 `current_recommendation_id`로 지금 재생 중인 곡이 어느 장면의 곡인지를 찾습니다. 그 장면이 이번에 보이는 범위에서 고른 장면과 같고 `trigger`가 `page_turn`이라면 `keep`을 응답합니다. 반면에 `trigger`가 `track_ended`라면 장면이 같더라도 새 곡을 골라서 `play`를 응답합니다.
    - 응답의 `recommendation_id`는 다음 위치 알림의 `current_recommendation_id`와 4.8절의 반응 기록에 씁니다.
    - `silence` 응답의 `cooldown_until`은 자동 재생 쉬는 시간이 끝나는 시각입니다. 곡을 틀지 않는 이유가 쉬는 시간이 아니라 사용자의 선곡 방식이 무음이기 때문이라면 `cooldown_until`은 `null`입니다.
    - `audio_url`은 서명된 주소입니다. 서명된 주소는 정해진 시간 동안만 유효한 임시 주소이며, 음원 파일은 이 주소로만 받을 수 있습니다. 그러므로 프론트엔드는 다음 세 가지를 지켜야 합니다.
      - `audio_url`을 저장해 두었다가 나중에 다시 쓰지 않습니다. 이 주소는 `audio_url_expires_at`에 적힌 시각이 지나면 쓸 수 없게 됩니다.
      - 주소를 고치거나 조립하지 않고 받은 그대로 씁니다. 주소의 일부를 바꾸면 서명이 맞지 않아서 요청이 거부됩니다. 위 예시의 `expires`와 `signature`는 형태를 보여 주기 위한 것이며, 실제 모양은 저장소 서비스에 따라 다릅니다.
      - 사용자가 곡을 오래 멈춰 두었다가 다시 재생하는 경우처럼 주소가 만료된 뒤에 음원을 다시 받아야 한다면, `current_recommendation_id`를 `null`로 두고 위치 알림을 다시 보내서 새 곡을 받습니다.

### 4.8 반응 기록

- **`POST /api/recommendations/{id}/events`**: 재생, 중단, 좋아요 같은 반응을 기록합니다.
  - **Request Header**

    ```http
    Cookie: diegesis_session=4mXq8ZpT1vK0
    Content-Type: application/json
    ```

  - **Request Body**

    ```json
    { "type": "stopped", "position_ms": 42000 }
    ```

    | 요청 필드 | 설명 |
    | --- | --- |
    | `type` | 반응의 종류입니다. 아래 표의 다섯 가지 가운데 하나를 보냅니다. |
    | `position_ms` | 그 순간 곡의 재생 위치입니다. |

    | `type` | 언제 보내는가 |
    | --- | --- |
    | `started` | 곡이 실제로 재생되기 시작했을 때 보냅니다. |
    | `stopped` | 사용자가 중단 버튼을 눌렀을 때 보냅니다. 이 곡은 그 사용자에게 다시 나오지 않으며, 그 책에서 자동 재생 쉬는 시간이 시작됩니다. |
    | `completed` | 곡이 끝까지 재생됐을 때 보냅니다. |
    | `liked` | 사용자가 좋아요를 눌렀을 때 보냅니다. |
    | `unliked` | 사용자가 좋아요를 취소했을 때 보냅니다. |

  - **Response Body**: `type`이 `stopped`일 때에는 `200 OK`와 함께 자동 재생 쉬는 시간이 끝나는 시각을 응답합니다.

    ```json
    { "cooldown_until": "2026-12-01T12:05:00Z" }
    ```

    그 밖의 `type`일 때에는 `204 No Content`이며 본문이 없습니다.

### 4.9 관리자: 산출물 묶음 적재

- **`POST /api/admin/bundles`**: 산출물 묶음을 올립니다.
  - **Request Header**

    ```http
    Cookie: diegesis_session=4mXq8ZpT1vK0
    Content-Type: multipart/form-data; boundary=----bundle-boundary
    ```

  - **Request Body**: zip 파일 하나를 `file` 필드에 담습니다.

    ```http
    ------bundle-boundary
    Content-Disposition: form-data; name="file"; filename="sample-novel.zip"
    Content-Type: application/zip

    (zip 파일의 내용)
    ------bundle-boundary--
    ```

  - **Response Body** (`200 OK`): 적재가 끝난 뒤에 응답합니다.

    ```json
    { "bundle_type": "book" }
    ```

  - **Response Body** (`422 Unprocessable Entity`): 묶음이 규격에 어긋나면 아무것도 적재하지 않고 오류 목록을 응답합니다.

    ```json
    {
      "code": "BUNDLE_INVALID",
      "message": "묶음이 규격에 맞지 않습니다.",
      "detail": [
        { "file": "scenes.jsonl", "line_no": 7, "reason": "end_sentence_idx(455)가 마지막 문장 인덱스(440)보다 큽니다." },
        { "file": "scenes.jsonl", "line_no": 9, "reason": "gems에 쓸 수 없는 값(fear)이 있습니다." },
        { "file": "scene_embeddings.muq-mulan.parquet", "reason": "벡터의 차원이 512가 아닙니다." }
      ]
    }
    ```

  - **설명**: 에러의 형식은 2.3절과 같고, `detail`이 `{ "file", "line_no", "reason" }`의 목록입니다. 묶음의 규격과 검증 항목은 [AI_CONTRACT.md](AI_CONTRACT.md)에 정의되어 있습니다. 백엔드는 검증과 적재를 모두 마친 뒤에 응답하므로, 적재의 결과를 따로 조회하는 엔드포인트는 없습니다([ADR-019](ADR.md#adr-019-정확-검색과-동기-적재)). 오류의 `line_no`는 그 파일에서 문제가 있는 줄의 번호이며 1부터 셉니다. Parquet 파일처럼 줄을 가리킬 수 없는 파일의 오류에는 `line_no`가 없습니다.

### 4.10 관리자: 허용 목록

- **`GET /api/admin/allowed-emails`**: 허용 목록을 조회합니다.
  - **Request Header**

    ```http
    Cookie: diegesis_session=4mXq8ZpT1vK0
    ```

  - **Request Body**: 없습니다.
  - **Response Body** (`200 OK`)

    ```json
    {
      "allowed_emails": [
        { "email": "admin@example.com", "role": "admin" },
        { "email": "reader@example.com", "role": "user" }
      ]
    }
    ```

- **`POST /api/admin/allowed-emails`**: 허용 목록에 한 사람을 추가합니다.
  - **Request Header**

    ```http
    Cookie: diegesis_session=4mXq8ZpT1vK0
    Content-Type: application/json
    ```

  - **Request Body**

    ```json
    { "email": "new-reader@example.com", "role": "user" }
    ```

  - **Response Body** (`201 Created`)

    ```json
    { "email": "new-reader@example.com", "role": "user" }
    ```

- **`DELETE /api/admin/allowed-emails/{email}`**: 허용 목록에서 한 사람을 뺍니다.
  - **Request Header**: 이메일의 `@`는 주소에 넣을 때 `%40`으로 바꿔서 적습니다.

    ```http
    DELETE /api/admin/allowed-emails/new-reader%40example.com
    Cookie: diegesis_session=4mXq8ZpT1vK0
    ```

  - **Request Body**: 없습니다.
  - **Response Body**: `204 No Content`이며 본문이 없습니다.
  - **설명**: 목록에서 뺀 사람의 로그인 상태도 함께 끊습니다.

### 4.11 관리자: 평가 자료 내보내기

두 엔드포인트는 모두 CSV 파일을 응답하며, `from`과 `to` 쿼리로 기간을 지정할 수 있습니다. 앱 밖에서 받는 설문과는 사용자의 이메일로 연결하므로, 설문에서도 같은 Google 이메일을 받아야 합니다.

- **`GET /api/admin/exports/recommendations`**: 선곡 기록을 CSV로 내려받습니다.
  - **Request Header**

    ```http
    GET /api/admin/exports/recommendations?from=2026-12-01&to=2026-12-08
    Cookie: diegesis_session=4mXq8ZpT1vK0
    ```

  - **Request Body**: 없습니다.
  - **Response Header** (`200 OK`)

    ```http
    Content-Type: text/csv; charset=utf-8
    Content-Disposition: attachment; filename="recommendations.csv"
    ```

  - **Response Body**

    ```csv
    recommendation_id,created_at,user_email,book_id,book_version,scene_id,strategy,selection_reason,embedding_model,track_id,segment_id,segment_start_ms,similarity,scene_valence,scene_arousal,scene_tags,scene_gems,segment_valence,segment_arousal,segment_tags,segment_gems
    c41e7a90-...,2026-12-01T12:01:10Z,reader@example.com,sample-novel,1,scene_0007,embedding,embedding,muq-mulan,trk_0042,trk_0042_s00,0,0.412,-0.6,-0.35,sad|melancholic,sadness,-0.55,-0.4,sad|melancholic,sadness|nostalgia
    ```

  - **설명**: 뒤의 여덟 열은 그 장면과 뽑힌 구간의 평가 라벨입니다([AI_CONTRACT.md 2절](AI_CONTRACT.md#라벨에-대한-규칙)). `tags`와 `gems`처럼 값이 여러 개인 열은 한 칸 안에서 `|`로 잇습니다. 이 열들로 장면과 구간의 V-A 거리, 태그와 GEMS 차원의 일치 여부를 계산할 수 있습니다.

- **`GET /api/admin/exports/playback-events`**: 반응 기록을 CSV로 내려받습니다.
  - **Request Header**

    ```http
    GET /api/admin/exports/playback-events?from=2026-12-01&to=2026-12-08
    Cookie: diegesis_session=4mXq8ZpT1vK0
    ```

  - **Request Body**: 없습니다.
  - **Response Header** (`200 OK`)

    ```http
    Content-Type: text/csv; charset=utf-8
    Content-Disposition: attachment; filename="playback-events.csv"
    ```

  - **Response Body**

    ```csv
    event_id,created_at,recommendation_id,user_email,type,position_ms
    9a8b7c6d-...,2026-12-01T12:01:52Z,c41e7a90-...,reader@example.com,stopped,42000
    ```

## 5. 프론트엔드와 더 합의할 것

- 구간이 끝나는 위치(`end_ms`)에 이르렀을 때 곡을 이어서 틀지, 거기서 멈추고 다음 곡을 요청할지를 정해야 합니다. 재생을 구간의 시작 위치에서 시작한다는 것까지만 정해져 있습니다.
- 곡이 바뀔 때 앞 곡을 서서히 줄이고 다음 곡을 서서히 키우는 처리(크로스페이드)를 할지 정해야 합니다.
- 독자가 페이지를 빠르게 연달아 넘길 때 위치 알림 요청을 얼마나 묶어서 보낼지 정해야 합니다.
- 선곡 방식과 임베딩 모델을 바꾸는 설정 화면을 어디에 둘지 정해야 합니다.
- 허용 목록에 없는 계정으로 로그인했을 때 보여 줄 화면의 경로를 확정해야 합니다. 이 문서에서는 `/login?error=NOT_ALLOWED`로 가정했습니다.
