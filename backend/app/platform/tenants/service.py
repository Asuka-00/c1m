"""租户服务：成员关系、租户角色、租户创建与默认租户。"""

import uuid
from dataclasses import dataclass, field

from sqlmodel import Session, select

from app.platform.rbac.models import Permission, Role
from app.platform.rbac.permissions import TENANT_ROLES
from app.platform.rbac.service import fill_names
from app.platform.tenants.models import Tenant, TenantMember
from app.platform.users.models import User

DEFAULT_TENANT_SLUG = "default"


@dataclass
class TenantContext:
    """一次请求的租户上下文。

    Attributes:
        tenant: 当前租户。
        user: 当前用户。
        member: 成员关系（平台管理员访问非成员租户时为 None）。
        permissions: 有效权限（平台权限 ∪ 租户角色权限）。
    """

    tenant: Tenant
    user: User
    member: TenantMember | None
    permissions: set[str] = field(default_factory=set)

    @property
    def id(self) -> uuid.UUID:
        """租户 id。"""
        return self.tenant.id

    def can(self, *codes: str) -> bool:
        """是否具备全部给定权限（超级用户恒为 True）。"""
        return self.user.is_superuser or set(codes) <= self.permissions


# ---------- tenants / members ----------
def member_permission_codes(member: TenantMember | None) -> set[str]:
    """成员在租户内的角色权限编码（忽略停用的角色与权限）。"""
    if not member:
        return set()
    from app.platform.rbac.service import active_codes

    return active_codes(member.roles)


def get_membership(
    session: Session, tenant_id: uuid.UUID, user_id: uuid.UUID
) -> TenantMember | None:
    """查询用户在租户的成员关系。"""
    return session.exec(
        select(TenantMember).where(
            TenantMember.tenant_id == tenant_id, TenantMember.user_id == user_id
        )
    ).first()


def tenant_role(session: Session, tenant_id: uuid.UUID, name: str) -> Role | None:
    """按名称获取租户角色。"""
    return session.exec(
        select(Role).where(Role.tenant_id == tenant_id, Role.name == name)
    ).first()


def seed_tenant_roles(session: Session, tenant: Tenant) -> None:
    """幂等创建 / 同步租户默认角色（owner / admin / member）及其权限。"""
    perms = {p.code: p for p in session.exec(select(Permission)).all()}
    for name, (desc, codes) in TENANT_ROLES.items():
        role = tenant_role(session, tenant.id, name)
        if not role:
            role = Role(name=name, tenant_id=tenant.id)
            session.add(role)
            fill_names(role)
            role.description = role.description or desc
        have = {p.code for p in role.permissions}
        for c in codes:
            if c not in have and c in perms:
                role.permissions.append(perms[c])


def add_member(
    session: Session, tenant: Tenant, user: User, roles: list[str]
) -> TenantMember:
    """添加成员并分配租户角色。"""
    member = get_membership(session, tenant.id, user.id)
    if not member:
        member = TenantMember(tenant_id=tenant.id, user_id=user.id)
        session.add(member)
    set_member_roles(session, member, roles)
    return member


def set_member_roles(session: Session, member: TenantMember, roles: list[str]) -> None:
    """替换成员的租户角色。"""
    resolved = []
    for name in roles:
        role = tenant_role(session, member.tenant_id, name)
        if not role:
            raise ValueError(f"Role '{name}' does not exist in this tenant")
        resolved.append(role)
    member.roles = resolved
    session.add(member)


def create_tenant(session: Session, name: str, slug: str, owner: User | None) -> Tenant:
    """创建租户及默认角色，可指定 owner。"""
    tenant = Tenant(name=name, slug=slug)
    session.add(tenant)
    session.flush()
    seed_tenant_roles(session, tenant)
    session.flush()
    if owner:
        add_member(session, tenant, owner, ["owner"])
    session.commit()
    session.refresh(tenant)
    return tenant


def ensure_default_tenant(session: Session) -> Tenant:
    """确保默认租户（slug=default）存在。"""
    tenant = session.exec(
        select(Tenant).where(Tenant.slug == DEFAULT_TENANT_SLUG)
    ).first()
    if not tenant:
        tenant = create_tenant(session, "Default", DEFAULT_TENANT_SLUG, owner=None)
    else:
        seed_tenant_roles(session, tenant)
        session.commit()
    return tenant


def owner_count(session: Session, tenant_id: uuid.UUID) -> int:
    """租户的 owner 数量（防止移除最后一个 owner）。"""
    return sum(
        1
        for m in session.exec(
            select(TenantMember).where(TenantMember.tenant_id == tenant_id)
        ).all()
        if any(r.name == "owner" for r in m.roles)
    )
