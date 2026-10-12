"""Module registration (see app.core.registry)."""

from app.core.registry import Module, register

register(
    Module(
        name="platform.menus",
        routers=("app.platform.menus.router:router",),
        router_priority=300,
    )
)
