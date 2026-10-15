"""坐标图模块注册（见 app.core.registry）。"""

from app.core.registry import Module, register
from app.mes.map.menus import MENUS
from app.mes.map.permissions import PERM_MODULES, PERMISSIONS

register(
    Module(
        name="mes.map",
        perm_modules=PERM_MODULES,
        permissions=PERMISSIONS,
        specs=("app.mes.map.specs",),
        routers=("app.mes.map.router:router",),
        menus=MENUS,
    )
)
