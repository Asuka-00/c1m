from app.core.registry import Module, register
from app.mes.common.permissions import PERM_MODULES, PERMISSIONS

register(
    Module(
        name="mes.common",
        perm_modules=PERM_MODULES,
        permissions=PERMISSIONS,
        specs=("app.mes.common.specs", "app.mes.common.validators"),
        routers=("app.mes.common.router:router",),
        router_priority=200,
        menu_provider="app.mes.common.menus:mes_items",
    )
)
