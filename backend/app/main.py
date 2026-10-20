"""FastAPI 应用入口：CORS、Sentry、按模块注册表挂载全部 API 路由并托管前端静态文件。"""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from pathlib import Path

import sentry_sdk
from fastapi import APIRouter, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from starlette.middleware.cors import CORSMiddleware

from app import models as _models  # noqa: F401  (registers tables + MES specs first)
from app.core import registry
from app.core.config import settings
from app.core.validation import validation_error_handler

FRONTEND_DIR = Path(__file__).parent / "frontend"


def custom_generate_unique_id(route: APIRoute) -> str:
    """生成 OpenAPI operationId：``<首个 tag>-<路由函数名>``（前端客户端生成依赖此格式）。

    Args:
        route: FastAPI 路由。

    Returns:
        唯一的 operationId 字符串。
    """
    return f"{route.tags[0]}-{route.name}"


if settings.SENTRY_DSN and settings.FASTAPI_ENV != "development":
    sentry_sdk.init(dsn=str(settings.SENTRY_DSN), enable_tracing=True)


async def _qtime_loop(every: int) -> None:
    """后台定时执行 Q-Time 超时扫描（QTIME_SWEEP_SECONDS > 0 时启用）。"""
    from app.mes.execution.service import sweep_all_tenants

    while True:
        await asyncio.sleep(every)
        try:
            await asyncio.to_thread(sweep_all_tenants)
        except Exception:  # noqa: BLE001 - 扫描失败不终止循环
            logging.getLogger(__name__).exception("qtime sweep loop error")


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """应用生命周期：按配置启动 / 停止后台任务。"""
    task = (
        asyncio.create_task(_qtime_loop(settings.QTIME_SWEEP_SECONDS))
        if settings.QTIME_SWEEP_SECONDS > 0
        else None
    )
    yield
    if task:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(
    title=settings.PROJECT_NAME,
    lifespan=lifespan,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    generate_unique_id_function=custom_generate_unique_id,
)

app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_HOST],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_router = APIRouter()
for _r in registry.routers(dev=settings.FASTAPI_ENV == "development"):
    api_router.include_router(_r)
app.include_router(api_router, prefix=settings.API_V1_STR)
# 单进程部署时由后端托管前端构建产物；生产 compose 由 nginx 托管，此目录不存在
if FRONTEND_DIR.is_dir():
    app.frontend("/", directory=FRONTEND_DIR)
