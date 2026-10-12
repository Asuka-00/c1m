"""MES menu items: one per (non-child) entity (pages come from each module).

Grouping/titles live in app.platform.menus.layout; this only supplies path, icon,
component key and required permission per menu key.
"""

from app.core.spec.engine import ENTITIES, perm

# key -> (path, icon, component, permission)
ItemDef = tuple[str, str | None, str, str | None]


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
    return out
