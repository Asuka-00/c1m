"""Default menu registry (seeded idempotently by init_db) and tree building."""

from sqlmodel import Session, select

from app.menu_layout import GROUPS, ITEMS, OBSOLETE_KEYS, OBSOLETE_PREFIXES
from app.models import Menu, MenuNode

# system pages: key -> (path, icon, component, permission)
SYSTEM_ITEMS: dict[str, tuple[str, str | None, str, str | None]] = {
    "dashboard": ("/", "LayoutDashboard", "dashboard", None),
    "users": ("/users", "UserCog", "users", "users:read"),
    "roles": ("/roles", "Shield", "roles", "roles:read"),
    "permissions": ("/permissions", "KeyRound", "permissions", "roles:read"),
    "tenants": ("/tenants", "Building2", "tenants", "tenants:read"),
    "members": ("/members", "Users", "members", "members:read"),
    "tenant-roles": ("/tenant-roles", "ShieldCheck", "tenant-roles", "members:read"),
    "menus": ("/menus", "Menu", "menus", "roles:write"),
    "config": ("/config", "SlidersHorizontal", "config", "config:read"),
    "settings": ("/settings", "Settings", "settings", None),
}

MenuTuple = tuple[
    str, str | None, str, str | None, str | None, str | None, int, str | None
]


def registry_menus() -> list[MenuTuple]:
    """(key, parent, title, path, icon, component, order, permission), groups first."""
    from app.mes.menus import mes_items

    defs = {**SYSTEM_ITEMS, **mes_items()}
    out: list[MenuTuple] = [
        (g, None, lbl.split("|")[0], None, icon, None, order, None)
        for g, lbl, icon, order in GROUPS
    ]
    for g, items in ITEMS.items():
        for i, (key, lbl) in enumerate(items):
            path, icon, comp, p = defs[key]
            out.append((key, g, lbl.split("|")[0], path, icon, comp, i * 10, p))
    return out


def seed_menus(session: Session) -> None:
    """Create / re-sync every registry menu (keeps `hidden` and custom menus);
    retired system groups are removed (their custom children move to top level)."""
    existing = {m.key: m for m in session.exec(select(Menu)).all()}
    for key, parent, title, path, icon, comp, order, p in registry_menus():
        m = existing.get(key)
        if m is None:
            m = Menu(key=key, title=title)
            existing[key] = m
        m.title, m.path, m.icon, m.component = title, path, icon, comp
        m.sort_order, m.permission = order, p
        m.parent_id = existing[parent].id if parent else None
        session.add(m)
        session.flush()
    stale = [
        m
        for k, m in existing.items()
        if k in OBSOLETE_KEYS or k.startswith(OBSOLETE_PREFIXES)
    ]
    for m in stale:
        for child in session.exec(select(Menu).where(Menu.parent_id == m.id)).all():
            child.parent_id = None
            session.add(child)
        session.flush()
        session.delete(m)
    session.commit()


def build_tree(menus: list[Menu], allowed: set[str], superuser: bool) -> list[MenuNode]:
    def visible(m: Menu) -> bool:
        return not m.hidden and (
            superuser or m.permission is None or m.permission in allowed
        )

    by_parent: dict[object, list[Menu]] = {}
    for m in menus:
        by_parent.setdefault(m.parent_id, []).append(m)

    def build(parent: object) -> list[MenuNode]:
        out = []
        for m in sorted(
            by_parent.get(parent, []), key=lambda x: (x.sort_order, x.title)
        ):
            if not visible(m):
                continue
            children = build(m.id)
            if m.path is None and not children:  # empty group
                continue
            out.append(
                MenuNode(
                    key=m.key,
                    title=m.title,
                    path=m.path,
                    icon=m.icon,
                    component=m.component,
                    permission=m.permission,
                    children=children,
                )
            )
        return out

    return build(None)


def forbidden_paths(menus: list[Menu], tree: list[MenuNode]) -> list[str]:
    allowed: set[str] = set()

    def walk(nodes: list[MenuNode]) -> None:
        for n in nodes:
            if n.path:
                allowed.add(n.path)
            walk(n.children)

    walk(tree)
    return sorted({m.path for m in menus if m.path and m.path not in allowed})
