"""RBAC 服务：默认权限/角色同步、角色分配与权限判断。"""

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
    """幂等创建默认权限与平台角色，并补齐角色权限。"""
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
    """按名称获取平台角色（tenant_id 为空）。"""
    return session.exec(
        select(Role).where(Role.name == name, col(Role.tenant_id).is_(None))
    ).first()


def assign_role(session: Session, user: User, name: str) -> None:
    """为用户分配平台角色（已有则跳过）。"""
    role = get_role(session, name)
    if role and role not in user.roles:
        user.roles.append(role)
        session.add(user)
        session.commit()
        session.refresh(user)


def user_permission_codes(user: User) -> set[str]:
    """用户的平台级权限编码。"""
    return {p.code for r in user.roles for p in r.permissions}


def has_permissions(user: User, *codes: str, extra: set[str] | None = None) -> bool:
    """判断用户是否同时具备全部权限（超级用户恒为 True）。

    Args:
        user: 用户。
        *codes: 权限编码。
        extra: 额外的权限集合（如租户角色权限）。
    """
    if user.is_superuser:
        return True
    return set(codes) <= (user_permission_codes(user) | (extra or set()))
