"""MES 实体菜单：每个非子表实体一项（页面菜单由各模块提供）；分组与标题见 app.platform.menus.layout。"""

from app.core.spec.engine import ENTITIES, perm

# key -> (路径, 图标, 组件, 权限)
ItemDef = tuple[str, str | None, str, str | None]


def mes_items() -> dict[str, ItemDef]:
    """按规格生成实体菜单项 ``{key: (path, icon, component, permission)}``。"""
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
