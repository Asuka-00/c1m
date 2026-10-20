"""请求体校验错误（FastAPI / Pydantic）：每项附加错误码与参数，前端按 ``error.code_<错误码>`` 翻译。"""

from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core import error_codes as ec


def error_code(error_type: str) -> int:
    """Pydantic 错误类型 -> 错误码（未列入 :data:`ec.PYDANTIC_CODES` 的类型为 ``PYD_INVALID``）。"""
    return ec.PYDANTIC_CODES.get(error_type, ec.PYD_INVALID)


def _plain(v: Any) -> Any:
    if isinstance(v, str | int | float | bool) or v is None:
        return v
    if isinstance(v, list | tuple):
        return ", ".join(str(x) for x in v)
    return str(v)


async def validation_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    """422：每项带 ``code`` / ``params``，保留英文 ``msg``；不回显 ``input``（可能含密码）。"""
    assert isinstance(exc, RequestValidationError)
    items = [
        {
            "type": x["type"],
            "loc": list(x["loc"]),
            "msg": x["msg"],
            "code": error_code(x["type"]),
            "params": {k: _plain(v) for k, v in (x.get("ctx") or {}).items()},
        }
        for x in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": items})
