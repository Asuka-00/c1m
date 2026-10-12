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
    "mes-hold-release": (
        "/mes/hold-release",
        "ListChecks",
        "mes-page:hold-release",
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
