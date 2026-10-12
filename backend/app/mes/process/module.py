from app.core.registry import Module, register
from app.mes.process.permissions import PERM_MODULES, PERMISSIONS

register(
    Module(
        name="mes.process",
        perm_modules=PERM_MODULES,
        permissions=PERMISSIONS,
        specs=("app.mes.process.specs", "app.mes.process.validators"),
    )
)
