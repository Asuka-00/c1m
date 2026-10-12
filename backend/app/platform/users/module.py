"""用户模块注册（见 app.core.registry）。"""

from app.core.registry import Module, register

register(
    Module(
        name="platform.users",
        routers=("app.platform.users.router:router",),
        dev_routers=("app.platform.users.router_private:router",),
    )
)
