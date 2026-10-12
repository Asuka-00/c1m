from app.core.registry import Module, register
from app.mes.quality.permissions import PERM_MODULES, PERMISSIONS

register(
    Module(
        name="mes.quality",
        perm_modules=PERM_MODULES,
        permissions=PERMISSIONS,
        specs=("app.mes.quality.specs", "app.mes.quality.validators"),
    )
)
