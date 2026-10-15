"""租户模块注册（见 app.core.registry）。"""

from app.core.registry import Module, register

register(
    Module(
        name="platform.tenants",
        routers=(
            "app.platform.tenants.router:router",
            "app.platform.tenants.router:platform_router",
        ),
    )
)
