"""仓储模块注册（见 app.core.registry）。"""

from app.core.registry import Module, register
from app.mes.warehouse.permissions import PERM_MODULES, PERMISSIONS

register(
    Module(
        name="mes.warehouse",
        perm_modules=PERM_MODULES,
        permissions=PERMISSIONS,
        specs=(
            "app.mes.warehouse.specs",
            "app.mes.warehouse.service",
            "app.mes.warehouse.issue",
            "app.mes.warehouse.shipment",
            "app.mes.warehouse.inbound",
        ),
        routers=(
            "app.mes.warehouse.router:router",
            "app.mes.warehouse.router:issue_router",
            "app.mes.warehouse.router:shipment_router",
            "app.mes.warehouse.router:inbound_router",
        ),
    )
)
