"""RBAC 模块注册（见 app.core.registry）。"""

from app.core.registry import Module, register

register(
    Module(
        name="platform.rbac",
        # 角色 / 权限 / 用户角色管理只在平台空间 /platform/... 下挂载
        routers=("app.platform.rbac.router:platform_router",),
    )
)
