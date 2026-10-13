"""RBAC 服务：默认权限/角色同步、角色分配与权限判断。"""

from typing import TYPE_CHECKING, Any

from sqlmodel import Session, col, select

from app.core.models import actor_name, get_datetime_utc
from app.platform.rbac.labels import (
    ROLE_DESCRIPTIONS,
    ROLE_LABELS,
    permission_description,
    permission_label,
    role_description_key,
)
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
            perms[code] = Permission(code=code, scope=scope)
            session.add(perms[code])
            fill_names(perms[code])
            perms[code].description = perms[code].description or desc
    for name, (desc, codes) in DEFAULT_ROLES.items():
        role = get_role(session, name)
        if not role:
            role = Role(name=name)
            session.add(role)
            fill_names(role)
            role.description = role.description or desc
        have = {p.code for p in role.permissions}
        for c in codes:
            if c not in have:
                role.permissions.append(perms[c])
    session.commit()


def fill_names(obj: Permission | Role) -> None:
    """为内置权限 / 角色补齐英文显示名称与说明（仅在为空时填充；前端按 i18n 翻译内置值）。"""
    if isinstance(obj, Permission):
        if not obj.name and (lbl := permission_label(obj.code)):
            obj.name = lbl.split("|")[0]
        if desc := permission_description(obj.code):
            obj.description = obj.description or desc.split("|")[0]
        return
    if not obj.title and obj.name in ROLE_LABELS:
        obj.title = ROLE_LABELS[obj.name].split("|")[0]
    key = role_description_key(obj.name, obj.tenant_id is None)
    if not obj.description and key in ROLE_DESCRIPTIONS:
        obj.description = ROLE_DESCRIPTIONS[key].split("|")[0]


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
    """用户的平台级权限编码（忽略停用的角色与权限）。"""
    return active_codes(user.roles)


def active_codes(roles: list[Role]) -> set[str]:
    """角色集合授予的有效权限编码：跳过停用的角色与停用的权限。"""
    return {
        p.code
        for r in roles
        if r.status != "disabled"
        for p in r.permissions
        if p.status != "disabled"
    }


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


def role_filters(
    stmt: Any, code: str | None, title: str | None, status: str | None
) -> Any:
    """角色列表的筛选：编码 / 名称包含（不区分大小写）与状态。"""
    if code:
        stmt = stmt.where(col(Role.name).ilike(f"%{code}%"))
    if title:
        stmt = stmt.where(col(Role.title).ilike(f"%{title}%"))
    if status:
        stmt = stmt.where(Role.status == status)
    return stmt


def touch(role: Role, user: User) -> None:
    """记录角色的更新时间与更新人。"""
    role.updated_at = get_datetime_utc()
    role.updated_by = actor_name(user)
