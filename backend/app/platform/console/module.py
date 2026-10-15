"""平台控制台模块注册（见 app.core.registry）。"""

from app.core.registry import Module, register

register(
    Module(
        name="platform.console",
        routers=("app.platform.console.router:router",),
        router_priority=310,
    )
)
