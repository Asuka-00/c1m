from app.core.registry import Module, register
from app.mes.equipment.permissions import PERM_MODULES, PERMISSIONS

register(
    Module(
        name="mes.equipment",
        perm_modules=PERM_MODULES,
        permissions=PERMISSIONS,
        specs=("app.mes.equipment.specs", "app.mes.equipment.validators"),
    )
)
