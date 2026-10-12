"""Module registry.

Every feature module (``app/platform/<x>``, ``app/mes/<x>``) ships a small
``module.py`` that calls :func:`register` with plain metadata. References to
code (routers, spec modules, menu providers, demo seeders) are dotted strings,
so registering a module never imports its implementation; the composition
root (``app.modules``) decides the order and :func:`load` / :func:`routers`
import things lazily when they are needed.
"""

import importlib
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

from app.core.spec.engine import ENTITIES, ENUMS, EXTRA_PERMISSIONS, MODULES, build_all

# key -> (path, icon, component, permission)
MenuItem = tuple[str, str | None, str, str | None]


@dataclass(frozen=True)
class Module:
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


REGISTRY: dict[str, Module] = {}
_loaded = False


def register(m: Module) -> Module:
    REGISTRY[m.name] = m
    MODULES.update(m.perm_modules)
    EXTRA_PERMISSIONS.update(m.permissions)
    return m


def modules() -> Iterator[Module]:
    load_metadata()
    yield from REGISTRY.values()


def load_metadata() -> None:
    """Import the composition root so every module.py has registered."""
    importlib.import_module("app.modules")


def _ref(ref: str) -> Any:
    mod, _, attr = ref.partition(":")
    return getattr(importlib.import_module(mod), attr)


def load() -> None:
    """Import every module's specs/validators (in module order) and build tables."""
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
    out = []
    for m in sorted(modules(), key=lambda x: x.router_priority):
        out += [_ref(r) for r in m.routers]
        if dev:
            out += [_ref(r) for r in m.dev_routers]
    return out


def menu_items() -> dict[str, MenuItem]:
    load()  # entity menus need the specs
    out: dict[str, MenuItem] = {}
    for m in modules():
        out.update(m.menus)
        if m.menu_provider:
            fn: Callable[[], dict[str, MenuItem]] = _ref(m.menu_provider)
            out.update(fn())
    return out
