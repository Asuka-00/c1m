from app.core.registry import Module, register

# audit trail entity (written by app.core.spec.audit on every spec write)
register(Module(name="platform.audit", specs=("app.platform.audit.specs",)))
