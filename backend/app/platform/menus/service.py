"""默认菜单注册表（init_db 幂等同步）与菜单树构建。"""

from sqlmodel import Session, col, select

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
from app.platform.menus.schemas import MenuNode, MenuTab, PermNode
from app.platform.rbac.models import Permission

# 系统页面：key -> (路径, 图标, 组件, 权限)
SYSTEM_ITEMS: dict[str, tuple[str, str | None, str, str | None]] = {
    "dashboard": ("/", "LayoutDashboard", "dashboard", None),
    "members": ("/members", "Users", "members", "members:read"),
    "tenant-roles": ("/tenant-roles", "ShieldCheck", "tenant-roles", "members:read"),
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


# 平台页面 -> 访问权限编码（与平台接口授权 auth.deps.platform_permission 对应）
PLATFORM_MENU_PERMS: dict[str, str] = {
    "p-tenants": "tenants:read",
    "p-users": "users:read",
    "p-roles": "roles:read",
    "p-permissions": "roles:read",
    "p-config": "platform.config:read",
    "p-channels": "platform.notify:read",
    "p-audit": "platform.audit:read",
    "p-login-log": "platform.audit:read",
    "p-ops-log": "platform.audit:read",
}


def platform_menus() -> list[MenuTuple]:
    """平台管理控制台菜单 ``(key, parent, title, path, icon, component, order, permission)``。

    平台菜单的访问权限见 ``PLATFORM_MENU_PERMS``（超级用户可见全部）。
    """
    out: list[MenuTuple] = [
        (g, None, lbl.split("|")[0], None, icon, None, order, None)
        for g, lbl, icon, order in PLATFORM_GROUPS
    ]
    for i, (key, (g, lbl, path, icon, comp)) in enumerate(PLATFORM_ITEMS.items()):
        p = PLATFORM_MENU_PERMS.get(key)
        out.append((key, g, lbl.split("|")[0], path, icon, comp, i * 10, p))
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
    session.flush()
    link_permissions(session)
    session.commit()


# 菜单未直接引用的资源，按资源挂到对应页面（tenant:manage 挂到租户设置）
PLATFORM_RESOURCE_MENUS = {
    "users": "p-users",
    "roles": "p-roles",
    "tenants": "p-tenants",
    "platform.config": "p-config",
    "platform.notify": "p-channels",
    "platform.audit": "p-audit",
    "tenant": "config",
}


def _resource(code: str) -> str:
    """权限编码的资源部分（``mes.lot:write`` -> ``mes.lot``）。"""
    return code.rsplit(":", 1)[0]


def link_permissions(session: Session) -> None:
    """把尚未挂接菜单的权限按资源前缀挂到菜单下（迁移已有数据，幂等）。

    菜单的权限编码（逗号分隔）中出现的权限为 MENU 类型（页面访问），同资源的其余权限为
    BUTTON 类型（页面内操作）；找不到菜单的保持未挂接（权限树中归入"其他权限"）。
    已手动挂接（menu_id 非空）的权限不改动。
    """
    menus = sorted(
        session.exec(select(Menu)).all(), key=lambda m: (m.space, m.sort_order)
    )
    by_key = {m.key: m for m in menus}
    gate: dict[str, Menu] = {}  # 访问权限编码 -> 菜单
    res: dict[str, Menu] = {}  # 资源 -> 菜单
    for m in menus:
        if not m.path or not m.permission:
            continue
        for code in m.permission.split(","):
            gate.setdefault(code, m)
            res.setdefault(_resource(code), m)
    for r, key in PLATFORM_RESOURCE_MENUS.items():
        if key in by_key:
            res.setdefault(r, by_key[key])
    for p in session.exec(select(Permission).where(col(Permission.menu_id).is_(None))):
        target = gate.get(p.code) or res.get(_resource(p.code))
        if target is None:
            continue
        p.menu_id = target.id
        p.type = "MENU" if p.code in (target.permission or "").split(",") else "BUTTON"
        session.add(p)


def permission_tree(
    session: Session, spaces: list[str], scope: str | None = None
) -> list[PermNode]:
    """统一权限树：菜单（MENU 节点，含分组与页面）-> 挂接的权限（MENU / BUTTON）。

    Args:
        session: 数据库会话。
        spaces: 包含的菜单空间（workspace / platform），多个时各作为一个根节点。
        scope: 仅包含该作用域的权限（租户角色用 ``tenant``），并剪掉没有权限的菜单。

    Returns:
        树节点列表；未挂接菜单的权限归入根节点"其他权限"。
    """
    menus = list(session.exec(select(Menu).where(col(Menu.space).in_(spaces))).all())
    perms = list(session.exec(select(Permission)).all())
    if scope:
        perms = [p for p in perms if p.scope == scope]
    menu_ids = {m.id for m in menus}
    by_menu: dict[object, list[Permission]] = {}
    for p in perms:
        by_menu.setdefault(p.menu_id if p.menu_id in menu_ids else None, []).append(p)
    kids: dict[object, list[Menu]] = {}
    for m in menus:
        kids.setdefault(m.parent_id, []).append(m)

    def perm_node(p: Permission) -> PermNode:
        return PermNode(
            id=str(p.id),
            kind="perm",
            type=p.type,
            name=p.name or p.description or p.code,
            code=p.code,
            sort_order=p.sort_order,
            status=p.status,
            scope=p.scope,
            description=p.description,
            menu_id=str(p.menu_id) if p.menu_id else None,
        )

    def build(parent: object) -> list[PermNode]:
        out = []
        for m in sorted(kids.get(parent, []), key=lambda x: (x.sort_order, x.title)):
            children = build(m.id) + [
                perm_node(p)
                for p in sorted(
                    by_menu.get(m.id, []), key=lambda p: (p.sort_order, p.code)
                )
            ]
            if scope and not children:
                continue
            out.append(
                PermNode(
                    id=str(m.id),
                    kind="menu",
                    type="MENU",
                    key=m.key,
                    name=m.title,
                    code=m.permission or "",
                    path=m.path,
                    icon=m.icon,
                    component=m.component,
                    sort_order=m.sort_order,
                    visible=not m.hidden,
                    status=m.status,
                    space=m.space,
                    menu_id=str(m.parent_id) if m.parent_id else None,
                    children=children,
                )
            )
        return out

    roots = build(None)
    other = by_menu.get(None, [])
    if other:
        roots.append(
            PermNode(
                id="other",
                kind="group",
                type="GROUP",
                key="other",
                name="Other permissions",
                sort_order=9999,
                children=[perm_node(p) for p in sorted(other, key=lambda p: p.code)],
            )
        )
    return roots


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
        return (
            not m.hidden
            and m.status != "disabled"
            and allowed_perm(m.permission, allowed, superuser)
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
