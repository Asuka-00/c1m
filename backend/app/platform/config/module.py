from app.core.registry import Module, register

# config before tenants: /tenants/current/config must win over /tenants/{tenant_id}/...
register(Module(name="platform.config", routers=("app.platform.config.router:router",)))
