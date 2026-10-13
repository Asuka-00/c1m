"""RBAC 模块注册（见 app.core.registry）。"""

from app.core.registry import Module, register

register(
    Module(
        name="platform.rbac",
        routers=(
            "app.platform.rbac.router:user_roles_router",
            "app.platform.rbac.router:roles_router",
            "app.platform.rbac.router:permissions_router",
            "app.platform.rbac.router:platform_router",
        ),
    )
)
