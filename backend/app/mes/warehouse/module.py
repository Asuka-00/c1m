"""仓储模块注册（见 app.core.registry）。"""

from app.core.registry import Module, register
from app.mes.warehouse.permissions import PERM_MODULES, PERMISSIONS

register(
    Module(
        name="mes.warehouse",
        perm_modules=PERM_MODULES,
        permissions=PERMISSIONS,
        specs=("app.mes.warehouse.specs", "app.mes.warehouse.service"),
        routers=("app.mes.warehouse.router:router",),
    )
)
