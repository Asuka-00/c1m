"""Module registration (see app.core.registry)."""

from app.core.registry import Module, register

register(
    Module(name="platform.tenants", routers=("app.platform.tenants.router:router",))
)
