from typing import TYPE_CHECKING

from sqlmodel import Session, col, select

from app.platform.rbac.models import Permission, Role
from app.platform.rbac.permissions import (
    DEFAULT_PERMISSIONS,
    DEFAULT_ROLES,
    TENANT_PERMISSIONS,
)

if TYPE_CHECKING:
    from app.platform.users.models import User


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
