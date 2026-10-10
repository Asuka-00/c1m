"""Multi-tenancy helpers: tenant creation, membership, per-transaction RLS context."""

import re
import secrets
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import event, text
from sqlmodel import Session, select
from sqlmodel.sql.expression import SelectOfScalar

from app.models import Permission, Role, Tenant, TenantMember, User
from app.rbac import TENANT_ROLES

DEFAULT_TENANT_SLUG = "default"


# ---------- Postgres RLS context ----------
# The tenant id lives in session.info; every transaction the Session begins gets
# `set_config('app.current_tenant', <id>, true)` (== SET LOCAL), so it survives commits
# within a request and never leaks to the next user of a pooled connection.
@event.listens_for(Session, "after_begin")
def _set_tenant_on_begin(session: Session, _txn: Any, connection: Any) -> None:
    tid = session.info.get("tenant_id")
    if tid is not None:
        connection.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(tid)}
        )


def set_tenant(session: Session, tenant_id: uuid.UUID | None) -> None:
    session.info["tenant_id"] = tenant_id
    if session.in_transaction():
        # raw SQL on the session's current connection (sqlmodel's exec() is for selects)
        session.connection().execute(
            text("SELECT set_config('app.current_tenant', :t, true)"),
            {"t": str(tenant_id) if tenant_id else ""},
        )


def tenant_scoped[T](
    stmt: SelectOfScalar[T], model: Any, tenant_id: uuid.UUID
) -> SelectOfScalar[T]:
    """App-layer filter: add `WHERE model.tenant_id = :tenant` (RLS is the backstop)."""
    return stmt.where(model.tenant_id == tenant_id)


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
