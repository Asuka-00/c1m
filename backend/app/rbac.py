"""RBAC defaults and helpers (two tiers: platform roles + tenant roles)."""

from sqlmodel import Session, col, select

from app.models import Permission, Role, User

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
DEFAULT_PERMISSIONS = {**PLATFORM_PERMISSIONS, **TENANT_PERMISSIONS}

DEFAULT_ROLES: dict[str, tuple[str, list[str]]] = {
    "admin": ("Platform administrator with all permissions", list(DEFAULT_PERMISSIONS)),
    "user": ("Regular platform user (tenant access comes from memberships)", []),
}
TENANT_ROLES: dict[str, tuple[str, list[str]]] = {
    "owner": ("Tenant owner", list(TENANT_PERMISSIONS)),
    "admin": (
        "Tenant administrator",
        ["members:read", "members:write", "config:read", "config:write"],
    ),
    "member": ("Tenant member", ["members:read"]),
}
ADMIN_ROLE = "admin"
DEFAULT_USER_ROLE = "user"


def seed_rbac(session: Session) -> None:
    """Idempotently create default permissions and platform roles."""
    perms = {p.code: p for p in session.exec(select(Permission)).all()}
    for code, desc in DEFAULT_PERMISSIONS.items():
        scope = "tenant" if code in TENANT_PERMISSIONS else "platform"
        if code not in perms:
            perms[code] = Permission(code=code, description=desc, scope=scope)
            session.add(perms[code])
    for name, (desc, codes) in DEFAULT_ROLES.items():
        role = get_role(session, name)
        if not role:
            role = Role(name=name, description=desc)
            session.add(role)
        have = {p.code for p in role.permissions}
        for c in codes:
            if c not in have:
                role.permissions.append(perms[c])
    session.commit()


def get_role(session: Session, name: str) -> Role | None:
    """Platform role by name."""
    return session.exec(
        select(Role).where(Role.name == name, col(Role.tenant_id).is_(None))
    ).first()


def assign_role(session: Session, user: User, name: str) -> None:
    role = get_role(session, name)
    if role and role not in user.roles:
        user.roles.append(role)
        session.add(user)
        session.commit()
        session.refresh(user)


def user_permission_codes(user: User) -> set[str]:
    """Platform-level permissions of a user."""
    return {p.code for r in user.roles for p in r.permissions}


def has_permissions(user: User, *codes: str, extra: set[str] | None = None) -> bool:
    if user.is_superuser:
        return True
    return set(codes) <= (user_permission_codes(user) | (extra or set()))
