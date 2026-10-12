from app.core.registry import Module, register

register(Module(name="platform.files", routers=("app.platform.files.router:router",)))
