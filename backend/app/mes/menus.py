"""MES menu items: one per (non-child) entity + special pages.

Grouping/titles live in app.menu_layout; this only supplies path, icon,
component key and required permission per menu key.
"""

from app.mes.core import ENTITIES, perm

# key -> (path, icon, component, permission)
ItemDef = tuple[str, str | None, str, str | None]

PAGES: dict[str, ItemDef] = {
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
    "mes-lot-start": (
        "/mes/lot-start",
        "PlayCircle",
        "mes-page:lot-start",
        "mes.lot:start",
    ),
}


def mes_items() -> dict[str, ItemDef]:
    out: dict[str, ItemDef] = {
        f"mes-{e.code}": (
            f"/mes/{e.url}",
            e.icon,
            f"mes:{e.code}",
            perm(e.pmod, "read"),
        )
        for e in ENTITIES.values()
        if not e.internal and not e.parent and e.menu
    }
    out.update(PAGES)
    return out
