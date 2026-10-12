"""Platform + tenant permission codes and default roles."""

from app.core.spec.engine import EXTRA_PERMISSIONS as _MES_EXTRA
from app.core.spec.engine import MODULES as _MES_MODULES

# Platform-level permissions (global, attached to platform roles via user_role)
PLATFORM_PERMISSIONS: dict[str, str] = {
    "users:read": "Read any user",
    "users:write": "Create/update any user",
    "users:delete": "Delete any user",
    "roles:read": "Read roles and permissions",
    "roles:write": "Manage roles, permissions and assignments",
    "tenants:read": "Read any tenant (platform)",
    "tenants:write": "Manage any tenant (platform)",
}
# Tenant-level permissions (attached to tenant roles via member_role)
TENANT_PERMISSIONS: dict[str, str] = {
    "tenant:manage": "Update/delete the tenant",
    "members:read": "List tenant members",
    "members:write": "Add/remove members and change their roles",
    "config:read": "Read system configuration (tenant overrides; platform defaults with a platform role)",
    "config:write": "Edit system configuration (tenant overrides; platform defaults with a platform role)",
}
# MES master data: read/write per module (tenant scope)

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
