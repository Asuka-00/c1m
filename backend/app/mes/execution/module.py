"""执行模块注册（见 app.core.registry）。"""

from app.core.registry import Module, register
from app.mes.execution.menus import MENUS
from app.mes.execution.permissions import PERM_MODULES, PERMISSIONS

register(
    Module(
        name="mes.execution",
        perm_modules=PERM_MODULES,
        permissions=PERMISSIONS,
        specs=(
            "app.mes.execution.specs",
            "app.mes.execution.validators",
            "app.mes.execution.checks.types",
            "app.mes.execution.events",
        ),
        routers=("app.mes.execution.router:router",),
        menus=MENUS,
        tenant_seed="app.mes.execution.seed:seed_system_reasons",
    )
)
