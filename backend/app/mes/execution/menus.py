"""执行模块页面菜单（非实体 CRUD 页面）。"""

from app.core.registry import MenuItem

MENUS: dict[str, MenuItem] = {
    "mes-lot-console": (
        "/mes/lot-console",
        "Gauge",
        "mes-page:lot-console",
        "mes.exec:read",
    ),
    "mes-lot-trace": (
        "/mes/lot-trace",
        "History",
        "mes-page:lot-trace",
        "mes.exec:read",
    ),
    "mes-batch-ops": (
        "/mes/batch-ops",
        "Layers",
        "mes-page:batch-ops",
        "mes.exec:read",
    ),
    "mes-qtime-monitor": (
        "/mes/qtime-monitor",
        "Timer",
        "mes-page:qtime-monitor",
        "mes.exec:read",
    ),
    "mes-trace": (
        "/mes/trace",
        "Network",
        "mes-page:trace",
        "mes.exec:read",
    ),
    # Hold 管理：覆盖通用实体页（生效中 / 历史 + 单条 / 批量释放）
    "mes-lot_hold": (
        "/mes/lot-hold",
        "PauseCircle",
        "mes-page:hold",
        "mes.exec:read",
    ),
    "mes-wip-dashboard": (
        "/mes/wip-dashboard",
        "LayoutDashboard",
        "mes-page:wip-dashboard",
        "mes.exec:read",
    ),
    "mes-oee-report": (
        "/mes/oee-report",
        "Gauge",
        "mes-page:oee-report",
        "mes.exec:read",
    ),
}
