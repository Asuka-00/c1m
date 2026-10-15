"""打标模块注册（P3-B1，见 app.core.registry）。"""

from app.core.registry import Module, register
from app.mes.marking.permissions import PERM_MODULES, PERMISSIONS

register(
    Module(
        name="mes.marking",
        perm_modules=PERM_MODULES,
        permissions=PERMISSIONS,
        specs=("app.mes.marking.specs", "app.mes.marking.events"),
        routers=("app.mes.marking.router:router",),
    )
)
