"""D34：P1 新接口先查权限、再校验请求体。

FastAPI 默认在依赖之前解析并校验请求体，无权限的用户发错误请求体会先拿到带字段明细的
422。这里的依赖不声明 Body 参数，而是先检查权限，再读取原始请求体自己做 JSON 解析和
Pydantic 校验；校验失败抛 ``RequestValidationError``，响应格式与 FastAPI 默认一致。
"""

import json
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError

from app.platform.auth.deps import CurrentTenant
from app.platform.tenants.service import TenantContext


def need(ctx: TenantContext, p: str) -> None:
    """无权限时 403，不带任何字段明细。"""
    if not ctx.can(p):
        raise HTTPException(status_code=403, detail="Not enough permissions")


async def raw_json(request: Request, max_bytes: int | None = None) -> Any:
    """读取原始请求体；空请求体返回 None，非法 JSON 抛 422；超过 ``max_bytes`` 413。"""
    b = (
        await request.body()
        if max_bytes is None
        else await limited_body(request, max_bytes)
    )
    if not b.strip():
        return None
    try:
        return json.loads(b)
    except ValueError:
        raise RequestValidationError(
            [
                {
                    "type": "json_invalid",
                    "loc": ("body",),
                    "msg": "JSON decode error",
                    "input": {},
                }
            ]
        ) from None


MB = 1024 * 1024


async def limited_body(request: Request, max_bytes: int) -> bytes:
    """读取请求体，超过 ``max_bytes`` 时 413（先看 Content-Length，再边读边计数）。"""

    def too_large() -> HTTPException:
        return HTTPException(
            status_code=413,
            detail={
                "code": "payload_too_large",
                "message": f"request body exceeds {max_bytes} bytes",
                "max_bytes": max_bytes,
            },
        )

    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > max_bytes:
        raise too_large()
    buf = bytearray()
    async for chunk in request.stream():
        buf += chunk
        if len(buf) > max_bytes:
            raise too_large()
    return bytes(buf)


def validate[M: BaseModel](model: type[M], data: Any) -> M:
    """按模型校验数据，错误转换为 FastAPI 的 422（loc 前缀 body）。"""
    try:
        return model.model_validate(data)
    except ValidationError as e:
        raise RequestValidationError(
            [{**x, "loc": ("body", *x["loc"])} for x in e.errors()]
        ) from None


def perm_body[M: BaseModel](
    p: str, model: type[M], *, optional: bool = False, max_bytes: int | None = None
) -> Callable[..., Awaitable[M | None]]:
    """依赖工厂：先查权限，再查请求体大小（超出 413），再解析校验。

    顺序：权限 ``p`` → ``max_bytes``（可选）→ JSON 解析 → ``model`` 校验。

    ``optional`` 为真时允许不带请求体（返回 None）。
    """

    async def dep(ctx: CurrentTenant, request: Request) -> M | None:
        need(ctx, p)
        data = await raw_json(request, max_bytes)
        if data is None and optional:
            return None
        return validate(model, data)

    return dep


def perm_only(p: str) -> Callable[..., None]:
    """依赖工厂：仅查权限（用于路由级 ``dependencies``）。"""

    def dep(ctx: CurrentTenant) -> None:
        need(ctx, p)

    return dep
