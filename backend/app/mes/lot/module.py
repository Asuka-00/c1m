from app.core.registry import Module, register
from app.mes.lot.permissions import PERM_MODULES, PERMISSIONS

register(
    Module(
        name="mes.lot",
        perm_modules=PERM_MODULES,
        permissions=PERMISSIONS,
        specs=("app.mes.lot.specs", "app.mes.lot.validators"),
    )
)
