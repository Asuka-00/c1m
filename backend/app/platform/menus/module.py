"""菜单模块注册（见 app.core.registry）。"""

from app.core.registry import Module, register

register(
    Module(
        name="platform.menus",
        routers=(
            "app.platform.menus.router:router",
            "app.platform.menus.router:platform_router",
        ),
        router_priority=300,
    )
)
