"""光罩模块注册（P3-B4，见 app.core.registry）。"""

from app.core.registry import Module, register
from app.mes.reticle.menus import MENUS
from app.mes.reticle.permissions import PERM_MODULES, PERMISSIONS

register(
    Module(
        name="mes.reticle",
        perm_modules=PERM_MODULES,
        permissions=PERMISSIONS,
        menus=MENUS,
        specs=(
            "app.mes.reticle.specs",
            "app.mes.reticle.validators",
            "app.mes.reticle.events",
        ),
        routers=("app.mes.reticle.router:router",),
    )
)
