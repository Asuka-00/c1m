"""FastAPI 应用入口：CORS、Sentry、按模块注册表挂载全部 API 路由并托管前端静态文件。"""

from pathlib import Path

import sentry_sdk
from fastapi import APIRouter, FastAPI
from fastapi.routing import APIRoute
from starlette.middleware.cors import CORSMiddleware

from app import models as _models  # noqa: F401  (registers tables + MES specs first)
from app.core import registry
from app.core.config import settings

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

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    generate_unique_id_function=custom_generate_unique_id,
)

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
app.frontend("/", directory=FRONTEND_DIR)
