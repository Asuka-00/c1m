"""坐标图模块页面菜单（非实体 CRUD 页面）。"""

from app.core.registry import MenuItem

MENUS: dict[str, MenuItem] = {
    # 坐标图 / bin 定义集导入页：只有 mes.map:import 可见
    "mes-map-import": (
        "/mes/map-import",
        "FileUp",
        "mes-page:map-import",
        "mes.map:import",
    ),
}
