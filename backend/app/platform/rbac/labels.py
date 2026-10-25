"""内置权限与角色的英文显示名称，用于种子数据（各语言显示文案在前端 ``permName`` / ``roleName``）。"""

from app.core.spec.engine import MODULES

# 非 MES 权限的显示名称
FIXED: dict[str, str] = {
    "users:read": "View platform users",
    "users:write": "Edit platform users",
    "users:delete": "Delete platform users",
    "roles:read": "View roles & permissions",
    "roles:write": "Manage roles & permissions",
    "tenants:read": "View tenants",
    "tenants:write": "Manage tenants",
    "platform.config:read": "View platform defaults",
    "platform.config:write": "Edit platform defaults",
    "platform.notify:read": "View notification channels",
    "platform.notify:write": "Configure notification channels",
    "platform.audit:read": "View audit & logs",
    "tenant:manage": "Manage system settings & admins",
    "members:read": "View users",
    "members:write": "Manage users",
    "config:read": "View configuration",
    "config:write": "Edit configuration",
    "notify:config": "Configure subscriptions",
}
# MES 操作名称（模块名 + 操作）
ACTIONS: dict[str, str] = {
    "read": "View",
    "write": "Edit",
    "e10": "Change E10 state",
    "pm": "Record PM",
    "override": "Override checks",
    "hold": "Hold / release",
    "split": "Split lots",
    "merge": "Merge lots",
    "jump": "Jump step",
    "adjust": "Scrap / bonus",
    "release": "Release / close",
    "start": "Start lots",
    "confirm": "Confirm receipts",
    "bank": "Bank in / issue",
    "approve": "Approve dispositions",
}
# 内置角色（平台 + 租户默认角色）的显示名称；工作区不出现“租户”字样，owner 显示为系统管理员
ROLE_LABELS: dict[str, str] = {
    "admin": "Administrator",
    "user": "User",
    "owner": "System admin",
    "member": "Standard user",
}


# 内置角色说明：平台角色键为 ``platform.<code>``，工作区默认角色键为 ``<code>``
ROLE_DESCRIPTIONS: dict[str, str] = {
    "platform.admin": "Platform administrator with all permissions",
    "platform.user": "Regular user without platform permissions",
    "owner": "System administrator with all permissions",
    "admin": "Manages users, settings and all business data",
    "member": "Read-only access to business data",
}
# 内置权限说明的模板（{label} 为权限名称）
PERM_DESC_TEMPLATE = "Allows: {label}"


def role_description_key(name: str, platform: bool) -> str:
    """内置角色说明的键（不存在时调用方应保留数据库中的说明）。"""
    return f"platform.{name}" if platform else name


def permission_description(code: str) -> str | None:
    """内置权限的说明（由权限名称生成）；未知编码返回 None。"""
    lbl = permission_label(code)
    return PERM_DESC_TEMPLATE.format(label=lbl) if lbl else None


def permission_label(code: str) -> str | None:
    """内置权限的名称；未知编码返回 None。"""
    if code in FIXED:
        return FIXED[code]
    res, _, act = code.rpartition(":")
    if res.startswith("mes.") and res[4:] in MODULES and act in ACTIONS:
        return f"{MODULES[res[4:]][0]}·{ACTIONS[act]}"
    return None
