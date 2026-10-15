"""配置模块注册（见 app.core.registry）。"""

from app.core.registry import Module, register

# config 须在 tenants 之前挂载：/tenants/current/config 要优先于 /tenants/{tenant_id}/...
register(Module(name="platform.config", routers=("app.platform.config.router:router",)))
