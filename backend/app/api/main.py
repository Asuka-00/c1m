from fastapi import APIRouter

from app.api.routes import mes, mes_exec, mes_wo
from app.core.config import settings
from app.platform.auth import router as login
from app.platform.auth import router_utils as utils
from app.platform.config import router as config
from app.platform.files import router as files
from app.platform.menus import router as menus
from app.platform.rbac import router as rbac
from app.platform.tenants import router as tenants
from app.platform.users import router as users
from app.platform.users import router_private as private

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
api_router.include_router(mes_wo.router)
api_router.include_router(mes_exec.router)
api_router.include_router(mes.router)
api_router.include_router(menus.router)


if settings.FASTAPI_ENV == "development":
    api_router.include_router(private.router)
