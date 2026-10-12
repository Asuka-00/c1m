"""审计模块注册（见 app.core.registry）。"""

from app.core.registry import Module, register

# 审计实体（每次规格写操作由 app.core.spec.audit 写入）
register(Module(name="platform.audit", specs=("app.platform.audit.specs",)))
