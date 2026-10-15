"""产品模块注册（见 app.core.registry）。"""

from app.core.registry import Module, register
from app.mes.product.permissions import PERM_MODULES, PERMISSIONS

register(
    Module(
        name="mes.product",
        perm_modules=PERM_MODULES,
        permissions=PERMISSIONS,
        specs=("app.mes.product.specs", "app.mes.product.validators"),
    )
)
