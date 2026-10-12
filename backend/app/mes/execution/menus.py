"""Execution pages (not entity CRUD pages)."""

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
}
