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
    TENANT_ROLES,
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
        fill_names(perms[code])
    for name, (desc, codes) in DEFAULT_ROLES.items():
        role = get_role(session, name)
        if not role:
            role = Role(name=name, description=desc)
            session.add(role)
        fill_names(role)
        have = {p.code for p in role.permissions}
        for c in codes:
            if c not in have:
                role.permissions.append(perms[c])
    session.commit()


#: 历次改名前的内置英文名称：数据库中仍是这些旧默认值时视为未自定义，同步为新名称
LEGACY_NAMES = {
    "Owner",
    "Member",
    "View members",
    "Manage members",
    "Manage tenant",
    "View users",
    "Edit users",
    "Delete users",
}


def _builtin(current: str | None, new: str) -> str:
    """未设置或仍为旧内置默认值时返回新名称，否则保留自定义名称。"""
    return (
        new if not current or (current in LEGACY_NAMES and current != new) else current
    )


#: 历次种子数据中的内置英文说明：仍为这些值时视为未自定义，同步为新的内置说明
LEGACY_DESCRIPTIONS = {
    *DEFAULT_PERMISSIONS.values(),
    *(d for d, _ in DEFAULT_ROLES.values()),
    *(d for d, _ in TENANT_ROLES.values()),
    "Administrator with all permissions",
    "Regular user",
    "Tenant owner",
    "Tenant administrator",
    "Tenant member",
}


def _builtin_desc(current: str | None, new: str) -> str:
    """说明为空或仍为旧内置说明（含自动生成的 ``MES …``）时返回新说明。"""
    legacy = not current or current in LEGACY_DESCRIPTIONS or current.startswith("MES ")
    return new if legacy else current  # type: ignore[return-value]


def fill_names(obj: Permission | Role) -> None:
    """为内置权限 / 角色同步英文显示名称与说明（自定义内容不覆盖；前端按 i18n 翻译内置值）。"""
    if isinstance(obj, Permission):
        if lbl := permission_label(obj.code):
            obj.name = _builtin(obj.name, lbl.split("|")[0])
        if desc := permission_description(obj.code):
            obj.description = _builtin_desc(obj.description, desc.split("|")[0])
        return
    if obj.name in ROLE_LABELS:
        obj.title = _builtin(obj.title, ROLE_LABELS[obj.name].split("|")[0])
    key = role_description_key(obj.name, obj.tenant_id is None)
    if key in ROLE_DESCRIPTIONS:
        obj.description = _builtin_desc(
            obj.description, ROLE_DESCRIPTIONS[key].split("|")[0]
        )


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
