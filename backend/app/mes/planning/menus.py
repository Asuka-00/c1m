"""Planning pages (not entity CRUD pages)."""

from app.core.registry import MenuItem

MENUS: dict[str, MenuItem] = {
    "mes-lot-start": (
        "/mes/lot-start",
        "PlayCircle",
        "mes-page:lot-start",
        "mes.lot:start",
    ),
}
