from fastapi import APIRouter

from app.api.routes import (
    config,
    files,
    login,
    menus,
    private,
    rbac,
    tenants,
    users,
    utils,
)
from app.core.config import settings

api_router = APIRouter()
api_router.include_router(login.router)
api_router.include_router(rbac.user_roles_router)
api_router.include_router(users.router)
api_router.include_router(rbac.roles_router)
api_router.include_router(rbac.permissions_router)
api_router.include_router(utils.router)
# config before tenants: /tenants/current/config must win over /tenants/{tenant_id}/...
api_router.include_router(config.router)
api_router.include_router(files.router)
api_router.include_router(tenants.router)
api_router.include_router(menus.router)


if settings.FASTAPI_ENV == "development":
    api_router.include_router(private.router)
