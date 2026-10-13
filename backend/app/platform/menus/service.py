"""默认菜单注册表（init_db 幂等同步）与菜单树构建。"""

from sqlmodel import Session, select

from app.core import registry
from app.platform.menus.layout import (
    GROUPS,
    ITEMS,
    MERGED,
    OBSOLETE_KEYS,
    OBSOLETE_PREFIXES,
    PLATFORM_GROUPS,
    PLATFORM_ITEMS,
    TAB_TITLES,
    tab_keys,
)
from app.platform.menus.layout import titles as titles
from app.platform.menus.models import Menu
from app.platform.menus.schemas import MenuNode, MenuTab

# 系统页面：key -> (路径, 图标, 组件, 权限)
SYSTEM_ITEMS: dict[str, tuple[str, str | None, str, str | None]] = {
    "dashboard": ("/", "LayoutDashboard", "dashboard", None),
    "members": ("/members", "Users", "members", "members:read"),
    "tenant-roles": ("/tenant-roles", "ShieldCheck", "tenant-roles", "members:read"),
    "tenant-role-perms": (
        "/tenant-role-permissions",
        "KeyRound",
        "tenant-role-permissions",
        "members:read",
    ),
    "config": ("/config", "SlidersHorizontal", "config", "config:read"),
    "settings": ("/settings", "Settings", "settings", None),
    "notifications": ("/notifications", "Bell", "notifications", None),
    "notify-subscriptions": (
        "/notify-subscriptions",
        "BellRing",
        "notify-subscriptions",
        "notify:config",
    ),
}

MenuTuple = tuple[
    str, str | None, str, str | None, str | None, str | None, int, str | None
]


def _defs() -> dict[str, tuple[str, str | None, str, str | None]]:
    """全部页面定义 ``{key: (路径, 图标, 组件, 权限)}``（系统页面 + 模块菜单）。"""
    return {**SYSTEM_ITEMS, **registry.menu_items()}


def _merged(key: str) -> tuple[str, str | None, str, str | None]:
    """合并菜单的 ``(路径, 图标, 视图组件, 权限)``：权限为各页签权限（任一即可，逗号分隔）。"""
    path, icon, view, tabs = MERGED[key]
    defs = _defs()
    perms = [defs[t][3] for t in tabs]
    p = None if None in perms else ",".join(dict.fromkeys(x for x in perms if x))
    return path, icon, view, p


def merged_tabs(key: str) -> list[MenuTab]:
    """合并菜单的全部页签（未按权限过滤）。"""
    if key not in MERGED:
        return []
    defs = _defs()
    return [
        MenuTab(
            key=t,
            title=TAB_TITLES[t].split("|")[0],
            path=defs[t][0],
            component=defs[t][2],
            permission=defs[t][3],
        )
        for t in MERGED[key][3]
    ]


def allowed_perm(p: str | None, allowed: set[str], superuser: bool) -> bool:
    """权限判断：空表示无需权限；逗号分隔的多个编码满足任一即可。"""
    return superuser or not p or any(x in allowed for x in p.split(","))


def registry_menus() -> list[MenuTuple]:
    """注册表菜单 ``(key, parent, title, path, icon, component, order, permission)``，分组在前。"""
    defs = _defs()
    out: list[MenuTuple] = [
        (g, None, lbl.split("|")[0], None, icon, None, order, None)
        for g, lbl, icon, order in GROUPS
    ]
    for g, items in ITEMS.items():
        for i, (key, lbl) in enumerate(items):
            path, icon, comp, p = defs[key] if key not in MERGED else _merged(key)
            out.append((key, g, lbl.split("|")[0], path, icon, comp, i * 10, p))
    return out


def platform_menus() -> list[MenuTuple]:
    """平台管理控制台菜单 ``(key, parent, title, path, icon, component, order, permission)``。

    平台菜单不设权限编码：整个平台空间仅超级用户可见（由 /menus/me?space=platform 把关）。
    """
    out: list[MenuTuple] = [
        (g, None, lbl.split("|")[0], None, icon, None, order, None)
        for g, lbl, icon, order in PLATFORM_GROUPS
    ]
    for i, (key, (g, lbl, path, icon, comp)) in enumerate(PLATFORM_ITEMS.items()):
        out.append((key, g, lbl.split("|")[0], path, icon, comp, i * 10, None))
    return out


def seed_menus(session: Session) -> None:
    """创建 / 同步注册表菜单（工作区与平台两个空间分别同步）。

    保留 hidden 与自定义菜单；移除已废弃的系统分组（其自定义子项移到顶层）。
    """
    existing = {m.key: m for m in session.exec(select(Menu)).all()}
    for space, rows in (
        ("workspace", registry_menus()),
        ("platform", platform_menus()),
    ):
        for key, parent, title, path, icon, comp, order, p in rows:
            m = existing.get(key)
            if m is None:
                m = Menu(key=key, title=title)
                existing[key] = m
            m.title, m.path, m.icon, m.component = title, path, icon, comp
            m.sort_order, m.permission, m.space = order, p, space
            m.parent_id = existing[parent].id if parent else None
            session.add(m)
            session.flush()
    merged_away = tab_keys() - {k for items in ITEMS.values() for k, _ in items}
    stale = [
        m
        for k, m in existing.items()
        if k in OBSOLETE_KEYS or k in merged_away or k.startswith(OBSOLETE_PREFIXES)
    ]
    for m in stale:
        for child in session.exec(select(Menu).where(Menu.parent_id == m.id)).all():
            child.parent_id = None
            session.add(child)
        session.flush()
        session.delete(m)
    session.commit()


def build_tree(menus: list[Menu], allowed: set[str], superuser: bool) -> list[MenuNode]:
    """按权限构建菜单树。

    Args:
        menus: 全部菜单。
        allowed: 用户拥有的权限编码。
        superuser: 是否超级用户（可见全部）。

    Returns:
        可见的菜单节点树（空分组被剔除）。
    """

    def visible(m: Menu) -> bool:
        return not m.hidden and allowed_perm(m.permission, allowed, superuser)

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
            if m.path is None and not children:  # 空分组
                continue
            out.append(
                MenuNode(
                    key=m.key,
                    title=m.title,
                    path=m.path,
                    icon=m.icon,
                    component=m.component,
                    permission=m.permission,
                    tabs=[
                        tb
                        for tb in merged_tabs(m.key)
                        if allowed_perm(tb.permission, allowed, superuser)
                    ],
                    children=children,
                )
            )
        return out

    return build(None)


def forbidden_paths(menus: list[Menu], tree: list[MenuNode]) -> list[str]:
    """存在但对当前用户不可见的页面路径（含合并菜单中无权限的页签旧路径；前端据此显示 403 而非 404）。"""
    allowed: set[str] = set()

    def walk(nodes: list[MenuNode]) -> None:
        for n in nodes:
            if n.path:
                allowed.add(n.path)
            allowed.update(tb.path for tb in n.tabs if tb.path)
            walk(n.children)

    walk(tree)
    known = {m.path for m in menus if m.path}
    known |= {tb.path for m in menus for tb in merged_tabs(m.key) if tb.path}
    return sorted(known - allowed)


def redirects(tree: list[MenuNode]) -> dict[str, str]:
    """已并入合并菜单的旧路径 -> ``新路径?tab=页签``（仅当前用户可见的页签）。"""
    out: dict[str, str] = {}

    def walk(nodes: list[MenuNode]) -> None:
        for n in nodes:
            for tb in n.tabs:
                if tb.path and tb.path != n.path:
                    out[tb.path] = f"{n.path}?tab={tb.key}"
            walk(n.children)

    walk(tree)
    return out
