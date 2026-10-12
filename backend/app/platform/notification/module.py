"""站内通知模块注册（见 app.core.registry）。"""

from app.core.registry import Module, register

register(
    Module(
        name="platform.notification",
        permissions={"notify:config": "Configure notification subscriptions"},
        routers=("app.platform.notification.router:router",),
    )
)
