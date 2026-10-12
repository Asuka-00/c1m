"""工厂模块注册（见 app.core.registry）。"""

from app.core.registry import Module, register
from app.mes.factory.permissions import PERM_MODULES, PERMISSIONS

register(
    Module(
        name="mes.factory",
        perm_modules=PERM_MODULES,
        permissions=PERMISSIONS,
        specs=("app.mes.factory.specs", "app.mes.factory.validators"),
    )
)
