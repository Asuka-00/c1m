"""Module registration (see app.core.registry)."""

from app.core.registry import Module, register
from app.mes.planning.menus import MENUS
from app.mes.planning.permissions import PERM_MODULES, PERMISSIONS

register(
    Module(
        name="mes.planning",
        perm_modules=PERM_MODULES,
        permissions=PERMISSIONS,
        specs=("app.mes.planning.specs", "app.mes.planning.service"),
        routers=("app.mes.planning.router:router",),
        menus=MENUS,
    )
)
