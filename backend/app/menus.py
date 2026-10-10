"""Default menu registry (seeded idempotently by init_db) and tree building."""

from sqlmodel import Session, select

from app.models import Menu, MenuNode

# key, parent key, title, path, icon, component, order, permission
DEFAULT_MENUS: list[
    tuple[str, str | None, str, str | None, str | None, str | None, int, str | None]
] = [
    ("general", None, "General", None, None, None, 0, None),
    ("dashboard", "general", "Dashboard", "/", "LayoutDashboard", "dashboard", 0, None),
    ("tenant", None, "Tenant", None, None, None, 10, None),
    ("members", "tenant", "Members", "/members", "Users", "members", 0, "members:read"),
    (
        "tenant-roles",
        "tenant",
        "Tenant roles",
        "/tenant-roles",
        "ShieldCheck",
        "tenant-roles",
        10,
        "members:read",
    ),
    ("admin", None, "Administration", None, None, None, 20, None),
    ("users", "admin", "Users", "/users", "UserCog", "users", 0, "users:read"),
    ("roles", "admin", "Roles", "/roles", "Shield", "roles", 10, "roles:read"),
    (
        "permissions",
        "admin",
        "Permissions",
        "/permissions",
        "KeyRound",
        "permissions",
        20,
        "roles:read",
    ),
    (
        "tenants",
        "admin",
        "Tenants",
        "/tenants",
        "Building2",
        "tenants",
        30,
        "tenants:read",
    ),
    ("menus", "admin", "Menus", "/menus", "Menu", "menus", 40, "roles:write"),
    (
        "config",
        "admin",
        "System configuration",
        "/config",
        "SlidersHorizontal",
        "config",
        50,
        "config:read",
    ),
    ("other", None, "Other", None, None, None, 30, None),
    ("settings", "other", "Settings", "/settings", "Settings", "settings", 0, None),
]


def seed_menus(session: Session) -> None:
    existing = {m.key: m for m in session.exec(select(Menu)).all()}
    from app.mes.menus import mes_menus

    for key, parent, title, path, icon, comp, order, perm in [
        *DEFAULT_MENUS,
        *mes_menus(),
    ]:
        if key in existing:
            continue
        m = Menu(
            key=key,
            title=title,
            path=path,
            icon=icon,
            component=comp,
            sort_order=order,
            permission=perm,
            parent_id=existing[parent].id if parent else None,
        )
        session.add(m)
        session.flush()
        existing[key] = m
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
