"""D65 补充 2：所有 422 的 detail 为列表，且每一项都带 ``code``（无专用码时 code = type）。"""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

# pydantic 原生 type -> 固定码（type 保留原值）
TYPE_CODES = {"extra_forbidden": "unknown_field"}


def _code(x: dict[str, Any]) -> str:
    t = x.get("type") or "value_error"
    return x.get("code") or TYPE_CODES.get(t, t)


def with_code(items: Any) -> Any:
    """给 422 列表的每一项补上 ``code``（已有则保留；extra_forbidden → unknown_field）。"""
    if not isinstance(items, list):
        return items
    return [{**x, "code": _code(x)} if isinstance(x, dict) else x for x in items]


async def _validation(_r: Request, exc: Exception) -> Response:
    assert isinstance(exc, RequestValidationError)
    return JSONResponse(
        status_code=422,
        content={"detail": with_code(jsonable_encoder(exc.errors()))},
    )


async def _http(request: Request, exc: Exception) -> Response:
    assert isinstance(exc, StarletteHTTPException)
    if exc.status_code == 422 and isinstance(exc.detail, list):
        exc = StarletteHTTPException(422, with_code(exc.detail), exc.headers)
    return await http_exception_handler(request, exc)


def install(app: FastAPI) -> None:
    """注册全局 422 处理器。"""
    app.add_exception_handler(RequestValidationError, _validation)
    app.add_exception_handler(StarletteHTTPException, _http)
