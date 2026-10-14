"""平台与租户权限编码及默认角色（MES 权限由各模块 module.py 声明后汇总）。"""

from app.core import registry
from app.core.spec.engine import EXTRA_PERMISSIONS as _MES_EXTRA
from app.core.spec.engine import MODULES as _MES_MODULES

# 模块权限由各功能模块的 module.py 声明
registry.load_metadata()

# 平台级权限（全局，经 user_role 关联到平台角色）
PLATFORM_PERMISSIONS: dict[str, str] = {
    "users:read": "Read any user",
    "users:write": "Create/update any user",
    "users:delete": "Delete any user",
    "roles:read": "Read roles and permissions",
    "roles:write": "Manage roles, permissions and assignments",
    "tenants:read": "Read any tenant (platform)",
    "tenants:write": "Manage any tenant (platform)",
    "platform.config:read": "Read platform default configuration",
    "platform.config:write": "Edit platform default configuration and tenant branding",
    "platform.notify:read": "Read notification channels",
    "platform.notify:write": "Configure notification channels",
    "platform.audit:read": "Read cross-tenant audit, login and platform operation logs",
}
# 租户级权限（经 member_role 关联到租户角色）
TENANT_PERMISSIONS: dict[str, str] = {
    "tenant:manage": "Update/delete the tenant",
    "members:read": "List tenant members",
    "members:write": "Add/remove members and change their roles",
    "config:read": "Read system configuration (tenant overrides; platform defaults with a platform role)",
    "config:write": "Edit system configuration (tenant overrides; platform defaults with a platform role)",
}
# MES 主数据：每个模块 read/write（租户作用域）

MES_PERMISSIONS: dict[str, str] = {
    f"mes.{m}:{a}": f"MES {lbl.split('|')[0]}: {a}"
    for m, (lbl, _) in _MES_MODULES.items()
    for a in ("read", "write")
}
MES_PERMISSIONS.update(_MES_EXTRA)
TENANT_PERMISSIONS.update(MES_PERMISSIONS)
# 只给服务账号的权限：不进 owner / admin 等通用角色（D54-1）
SERVICE_ONLY_PERMISSIONS = {"mes.eap:write"}
EAP_SERVICE_ROLE = "eap_service"
DEFAULT_PERMISSIONS = {**PLATFORM_PERMISSIONS, **TENANT_PERMISSIONS}

DEFAULT_ROLES: dict[str, tuple[str, list[str]]] = {
    "admin": (
        "Platform administrator with all permissions",
        [p for p in DEFAULT_PERMISSIONS if p not in SERVICE_ONLY_PERMISSIONS],
    ),
    "user": ("Regular platform user (tenant access comes from memberships)", []),
}
TENANT_ROLES: dict[str, tuple[str, list[str]]] = {
    "owner": (
        "System administrator with all permissions",
        [p for p in TENANT_PERMISSIONS if p not in SERVICE_ONLY_PERMISSIONS],
    ),
    "admin": (
        "Administrator",
        [
            "members:read",
            "members:write",
            "config:read",
            "config:write",
            *(p for p in MES_PERMISSIONS if p not in SERVICE_ONLY_PERMISSIONS),
        ],
    ),
    "member": (
        "Standard user",
        ["members:read", *(p for p in MES_PERMISSIONS if p.endswith(":read"))],
    ),
    EAP_SERVICE_ROLE: (
        "EAP / simulator service account (POST /mes/eap/events only)",
        sorted(SERVICE_ONLY_PERMISSIONS),
    ),
}
ADMIN_ROLE = "admin"
DEFAULT_USER_ROLE = "user"
