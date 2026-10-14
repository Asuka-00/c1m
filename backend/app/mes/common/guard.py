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


async def raw_json(request: Request) -> Any:
    """读取原始请求体；空请求体返回 None，非法 JSON 抛 422。"""
    b = await request.body()
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


def validate[M: BaseModel](model: type[M], data: Any) -> M:
    """按模型校验数据，错误转换为 FastAPI 的 422（loc 前缀 body）。"""
    try:
        return model.model_validate(data)
    except ValidationError as e:
        raise RequestValidationError(
            [{**x, "loc": ("body", *x["loc"])} for x in e.errors()]
        ) from None


def perm_body[M: BaseModel](
    p: str, model: type[M], *, optional: bool = False
) -> Callable[..., Awaitable[M | None]]:
    """依赖工厂：先查权限 ``p``，再解析并校验请求体为 ``model``。

    ``optional`` 为真时允许不带请求体（返回 None）。
    """

    async def dep(ctx: CurrentTenant, request: Request) -> M | None:
        need(ctx, p)
        data = await raw_json(request)
        if data is None and optional:
            return None
        return validate(model, data)

    return dep


def perm_only(p: str) -> Callable[..., None]:
    """依赖工厂：仅查权限（用于路由级 ``dependencies``）。"""

    def dep(ctx: CurrentTenant) -> None:
        need(ctx, p)

    return dep
