import re
import secrets
import uuid
from dataclasses import dataclass, field

from sqlmodel import Session, select

from app.platform.rbac.models import Permission, Role
from app.platform.rbac.permissions import TENANT_ROLES
from app.platform.tenants.models import Tenant, TenantMember
from app.platform.users.models import User
from app.platform.users.service import USER_CREATED_HOOKS

DEFAULT_TENANT_SLUG = "default"


@dataclass
class TenantContext:
    tenant: Tenant
    user: User
    member: TenantMember | None
    permissions: set[str] = field(default_factory=set)

    @property
    def id(self) -> uuid.UUID:
        return self.tenant.id

    def can(self, *codes: str) -> bool:
        return self.user.is_superuser or set(codes) <= self.permissions


# ---------- tenants / members ----------
def member_permission_codes(member: TenantMember | None) -> set[str]:
    if not member:
        return set()
    return {p.code for r in member.roles for p in r.permissions}


def get_membership(
    session: Session, tenant_id: uuid.UUID, user_id: uuid.UUID
) -> TenantMember | None:
    return session.exec(
        select(TenantMember).where(
            TenantMember.tenant_id == tenant_id, TenantMember.user_id == user_id
        )
    ).first()


def tenant_role(session: Session, tenant_id: uuid.UUID, name: str) -> Role | None:
    return session.exec(
        select(Role).where(Role.tenant_id == tenant_id, Role.name == name)
    ).first()


def seed_tenant_roles(session: Session, tenant: Tenant) -> None:
    perms = {p.code: p for p in session.exec(select(Permission)).all()}
    for name, (desc, codes) in TENANT_ROLES.items():
        role = tenant_role(session, tenant.id, name)
        if not role:
            role = Role(name=name, description=desc, tenant_id=tenant.id)
            session.add(role)
        have = {p.code for p in role.permissions}
        for c in codes:
            if c not in have and c in perms:
                role.permissions.append(perms[c])


def add_member(
    session: Session, tenant: Tenant, user: User, roles: list[str]
) -> TenantMember:
    member = get_membership(session, tenant.id, user.id)
    if not member:
        member = TenantMember(tenant_id=tenant.id, user_id=user.id)
        session.add(member)
    set_member_roles(session, member, roles)
    return member


def set_member_roles(session: Session, member: TenantMember, roles: list[str]) -> None:
    resolved = []
    for name in roles:
        role = tenant_role(session, member.tenant_id, name)
        if not role:
            raise ValueError(f"Role '{name}' does not exist in this tenant")
        resolved.append(role)
    member.roles = resolved
    session.add(member)


def create_tenant(session: Session, name: str, slug: str, owner: User | None) -> Tenant:
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


def slugify(value: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return (s or "t")[:40]


def create_personal_tenant(session: Session, user: User) -> Tenant:
    base = slugify(user.email.split("@")[0])
    slug = f"{base}-{secrets.token_hex(3)}"
    return create_tenant(session, f"{user.email}'s workspace", slug, owner=user)


# every new user (signup or admin-created) gets a personal tenant where they
# are the owner; they can be invited to other tenants afterwards
def _on_user_created(session: Session, user: User) -> None:
    create_personal_tenant(session, user)


USER_CREATED_HOOKS.append(_on_user_created)


def ensure_default_tenant(session: Session) -> Tenant:
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
    return sum(
        1
        for m in session.exec(
            select(TenantMember).where(TenantMember.tenant_id == tenant_id)
        ).all()
        if any(r.name == "owner" for r in m.roles)
    )
