"""文件模块注册（见 app.core.registry）。"""

from app.core.registry import Module, register

register(Module(name="platform.files", routers=("app.platform.files.router:router",)))
