"""认证模块注册（见 app.core.registry）。"""

from app.core.registry import Module, register

register(
    Module(
        name="platform.auth",
        routers=(
            "app.platform.auth.router:router",
            "app.platform.auth.router_utils:router",
        ),
    )
)
