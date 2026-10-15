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
DEFAULT_PERMISSIONS = {**PLATFORM_PERMISSIONS, **TENANT_PERMISSIONS}

DEFAULT_ROLES: dict[str, tuple[str, list[str]]] = {
    "admin": ("Platform administrator with all permissions", list(DEFAULT_PERMISSIONS)),
    "user": ("Regular platform user (tenant access comes from memberships)", []),
}
TENANT_ROLES: dict[str, tuple[str, list[str]]] = {
    "owner": ("Tenant owner", list(TENANT_PERMISSIONS)),
    "admin": (
        "Tenant administrator",
        [
            "members:read",
            "members:write",
            "config:read",
            "config:write",
            *MES_PERMISSIONS,
        ],
    ),
    "member": (
        "Tenant member",
        ["members:read", *(p for p in MES_PERMISSIONS if p.endswith(":read"))],
    ),
}
ADMIN_ROLE = "admin"
DEFAULT_USER_ROLE = "user"
