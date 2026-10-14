"""光罩模块页面菜单（P3-F3 光罩工作台，非实体 CRUD 页面）。"""

from app.core.registry import MenuItem

MENUS: dict[str, MenuItem] = {
    "mes-reticle-console": (
        "/mes/reticle-console",
        "Aperture",
        "mes-page:reticle",
        "mes.reticle:read",
    ),
}
