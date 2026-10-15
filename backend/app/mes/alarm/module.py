"""报警模块注册（P2-B9；接口与联动在 execution，因为要调用 Hold）。"""

from app.core.registry import Module, register
from app.mes.alarm.permissions import PERM_MODULES, PERMISSIONS

register(
    Module(
        name="mes.alarm",
        perm_modules=PERM_MODULES,
        permissions=PERMISSIONS,
        specs=("app.mes.alarm.specs", "app.mes.alarm.validators"),
    )
)
