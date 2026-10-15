"""模块注册表。

每个功能模块（``app/platform/<x>``、``app/mes/<x>``）提供 ``module.py``，以纯元数据调用
:func:`register`。路由、规格模块、菜单提供函数等代码引用均为点分字符串，注册时不导入实现；
由组合根 ``app.modules`` 决定顺序，:func:`load` / :func:`routers` 在需要时才延迟导入。
"""

import importlib
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

from app.core.spec.engine import ENTITIES, ENUMS, EXTRA_PERMISSIONS, MODULES, build_all

# key -> (路径, 图标, 组件, 权限)
MenuItem = tuple[str, str | None, str, str | None]


@dataclass(frozen=True)
class Module:
    """模块元数据。

    Attributes:
        name: 模块名，如 ``mes.lot``。
        perm_modules: 规格权限模块 ``{编码: ("en|zh|ja" 标签, 排序)}``，各生成 ``mes.<编码>:read/write``。
        permissions: 额外的租户权限 ``{编码: 描述}``。
        specs: 为副作用导入的模块（实体规格、CRUD 校验器）。
        routers: ``"pkg.mod:attr"`` 形式的路由引用，按此顺序挂载。
        dev_routers: 仅开发环境挂载的路由。
        router_priority: 路由挂载优先级（升序，稳定）；通配路由需排在具体路由之后。
        menus: 静态菜单项 ``{key: (path, icon, component, permission)}``。
        menu_provider: 返回更多菜单项的函数引用 ``"pkg.mod:fn"``。
        tenant_seed: 租户初始化时调用的幂等函数引用 ``"pkg.mod:fn(session, tenant_id)"``。
    """

    name: str
    #: spec permission modules: code -> ("en|zh|ja" label, sort order); each
    #: yields ``mes.<code>:read`` / ``mes.<code>:write``
    perm_modules: dict[str, tuple[str, int]] = field(default_factory=dict)
    #: extra tenant permission codes -> description
    permissions: dict[str, str] = field(default_factory=dict)
    #: modules imported for side effects (entity specs, CRUD validators)
    specs: tuple[str, ...] = ()
    #: "pkg.mod:attr" APIRouter references, included in this order
    routers: tuple[str, ...] = ()
    #: routers only mounted in development
    dev_routers: tuple[str, ...] = ()
    #: routers are mounted by ascending priority (stable): catch-all routes
    #: (e.g. /mes/{entity}) must come after specific ones
    router_priority: int = 100
    #: static menu items (key -> item) and/or "pkg.mod:fn" returning more
    menus: dict[str, MenuItem] = field(default_factory=dict)
    menu_provider: str | None = None
    #: "pkg.mod:fn" called as fn(session, tenant_id) when a tenant is created /
    #: synced; must be idempotent
    tenant_seed: str | None = None


REGISTRY: dict[str, Module] = {}
_loaded = False


def register(m: Module) -> Module:
    """注册模块，并把其权限模块 / 额外权限合并到规格引擎。

    Args:
        m: 模块元数据。

    Returns:
        原样返回 ``m``。
    """
    REGISTRY[m.name] = m
    MODULES.update(m.perm_modules)
    EXTRA_PERMISSIONS.update(m.permissions)
    return m


def modules() -> Iterator[Module]:
    """按注册顺序遍历全部模块（必要时先加载组合根）。"""
    load_metadata()
    yield from REGISTRY.values()


def load_metadata() -> None:
    """导入组合根 ``app.modules``，确保所有 module.py 均已注册。"""
    importlib.import_module("app.modules")


def _ref(ref: str) -> Any:
    mod, _, attr = ref.partition(":")
    return getattr(importlib.import_module(mod), attr)


def load() -> None:
    """按模块顺序导入全部规格 / 校验器模块，填充实体类型枚举并构建规格表（只执行一次）。"""
    global _loaded
    if _loaded:
        return
    for m in modules():
        for s in m.specs:
            importlib.import_module(s)
    ENUMS["entity_type"][:] = [
        (e.code, e.label) for e in ENTITIES.values() if not e.internal
    ]
    build_all()
    _loaded = True


def routers(dev: bool = False) -> list[Any]:
    """按 ``router_priority`` 排序返回全部 APIRouter。

    Args:
        dev: 是否包含仅开发环境的路由。

    Returns:
        路由对象列表。
    """
    out = []
    for m in sorted(modules(), key=lambda x: x.router_priority):
        out += [_ref(r) for r in m.routers]
        if dev:
            out += [_ref(r) for r in m.dev_routers]
    return out


def menu_items() -> dict[str, MenuItem]:
    """汇总所有模块的菜单项（静态项 + 提供函数生成的项，如按规格生成的实体菜单）。"""
    load()  # 实体菜单依赖已加载的规格
    out: dict[str, MenuItem] = {}
    for m in modules():
        out.update(m.menus)
        if m.menu_provider:
            fn: Callable[[], dict[str, MenuItem]] = _ref(m.menu_provider)
            out.update(fn())
    return out


def seed_tenant(session: Any, tenant_id: Any) -> None:
    """依次调用各模块的 ``tenant_seed``（幂等），为租户补齐系统数据（如系统原因码）。"""
    load()  # 种子函数依赖规格表
    for m in modules():
        if m.tenant_seed:
            fn: Callable[[Any, Any], None] = _ref(m.tenant_seed)
            fn(session, tenant_id)
