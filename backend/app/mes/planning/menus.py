"""计划模块页面菜单（非实体 CRUD 页面）。"""

from app.core.registry import MenuItem

MENUS: dict[str, MenuItem] = {
    "mes-lot-start": (
        "/mes/lot-start",
        "PlayCircle",
        "mes-page:lot-start",
        "mes.lot:start",
    ),
}
