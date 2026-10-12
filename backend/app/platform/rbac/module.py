from app.core.registry import Module, register

register(
    Module(
        name="platform.rbac",
        routers=(
            "app.platform.rbac.router:user_roles_router",
            "app.platform.rbac.router:roles_router",
            "app.platform.rbac.router:permissions_router",
        ),
    )
)
