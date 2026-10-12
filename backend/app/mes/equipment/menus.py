"""设备模块页面菜单（非实体 CRUD 页面）。"""

from app.core.registry import MenuItem

MENUS: dict[str, MenuItem] = {
    "mes-eqp-board": (
        "/mes/eqp-board",
        "MonitorCheck",
        "mes-page:eqp-board",
        "mes.equipment:read",
    ),
}
