"""租户、成员与租户角色接口。"""

import uuid
from datetime import timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import col, select

from app.core import security
from app.core.config import settings
from app.core.deps import SessionDep
from app.core.models import Message
from app.core.pagination import ListParamsDep, paginate
from app.platform.auth.deps import CurrentUser, require_tenant_permissions
from app.platform.auth.schemas import Token
from app.platform.rbac.models import MemberRole, Permission, Role
from app.platform.rbac.schemas import (
    PermissionCodes,
    RoleCreate,
    RolePublic,
    RolesPublic,
    RoleUpdate,
)
from app.platform.rbac.service import has_permissions
from app.platform.tenants.models import Tenant, TenantMember
from app.platform.tenants.schemas import (
    MemberAdd,
    MemberPublic,
    MemberRolesUpdate,
    MembersPublic,
    MyTenantPublic,
    MyTenantsPublic,
    TenantCreate,
    TenantPublic,
    TenantsPublic,
    TenantUpdate,
)
from app.platform.tenants.service import (
    TenantContext,
    add_member,
    create_tenant,
    get_membership,
    member_permission_codes,
    owner_count,
    set_member_roles,
)
from app.platform.users import service as crud
from app.platform.users.models import User

router = APIRouter(prefix="/tenants", tags=["tenants"])


def _ctx(*codes: str) -> Any:
    return Depends(require_tenant_permissions(*codes, from_path=True))


TenantMember_ = Annotated[TenantContext, _ctx()]
TenantManager = Annotated[TenantContext, _ctx("tenant:manage")]
MembersReader = Annotated[TenantContext, _ctx("members:read")]
MembersWriter = Annotated[TenantContext, _ctx("members:write")]


def _member_public(m: TenantMember) -> MemberPublic:
    return MemberPublic(
        user_id=m.user_id,
        email=m.user.email,
        full_name=m.user.full_name,
        roles=sorted(r.name for r in m.roles),
    )


@router.get("/", response_model=TenantsPublic)
def list_tenants(
    session: SessionDep,
    current_user: CurrentUser,
    params: ListParamsDep,
    status: Literal["active", "suspended"] | None = None,
) -> Any:
    """All tenants (platform tenants:read) or only the caller's tenants.
    Paginated; sort_by: name, slug, status, created_at; q: name/slug; optional status."""
    stmt = select(Tenant)
    if status:
        stmt = stmt.where(Tenant.status == status)
    if not has_permissions(current_user, "tenants:read"):
        sub = select(TenantMember.tenant_id).where(
            TenantMember.user_id == current_user.id
        )
        stmt = stmt.where(col(Tenant.id).in_(sub))
    data, count = paginate(
        session,
        stmt,
        params,
        {
            "name": Tenant.name,
            "slug": Tenant.slug,
            "status": Tenant.status,
            "created_at": Tenant.created_at,
        },
        ("slug", "asc"),
        Tenant.id,
        search=[Tenant.name, Tenant.slug],
    )
    return TenantsPublic(data=data, count=count)


@router.get("/me", response_model=MyTenantsPublic)
def my_tenants(session: SessionDep, current_user: CurrentUser) -> Any:
    """Tenants the caller belongs to, with roles and effective tenant permissions."""
    members = session.exec(
        select(TenantMember).where(TenantMember.user_id == current_user.id)
    ).all()
    data = [
        MyTenantPublic(
            tenant=TenantPublic.model_validate(m.tenant),
            roles=sorted(r.name for r in m.roles),
            permissions=sorted(member_permission_codes(m)),
        )
        for m in sorted(members, key=lambda m: m.tenant.slug)
    ]
    return MyTenantsPublic(data=data, count=len(data))


@router.post("/", response_model=TenantPublic)
def create_new_tenant(
    session: SessionDep, current_user: CurrentUser, tenant_in: TenantCreate
) -> Any:
    """Create a tenant; the caller becomes its owner."""
    if session.exec(select(Tenant).where(Tenant.slug == tenant_in.slug)).first():
        raise HTTPException(status_code=409, detail="Tenant slug already exists")
    return create_tenant(session, tenant_in.name, tenant_in.slug, owner=current_user)


@router.get("/{tenant_id}", response_model=TenantPublic)
def read_tenant(ctx: TenantMember_) -> Any:
    return ctx.tenant


@router.patch("/{tenant_id}", response_model=TenantPublic)
def update_tenant(
    session: SessionDep, ctx: TenantManager, tenant_in: TenantUpdate
) -> Any:
    data = tenant_in.model_dump(exclude_unset=True)
    if "status" in data and not has_permissions(ctx.user, "tenants:write"):
        raise HTTPException(
            status_code=403, detail="Only platform admins can change tenant status"
        )
    tenant = ctx.tenant
    tenant.sqlmodel_update(data)
    session.add(tenant)
    session.commit()
    session.refresh(tenant)
    return tenant


@router.delete("/{tenant_id}", response_model=Message)
def delete_tenant(session: SessionDep, ctx: TenantManager) -> Any:
    """Delete the tenant with all its members, roles and tenant-scoped rows (FK cascade)."""
    session.delete(ctx.tenant)
    session.commit()
    return Message(message="Tenant deleted successfully")


@router.post("/{tenant_id}/switch", response_model=Token)
def switch_tenant(ctx: TenantMember_) -> Any:
    """Issue an access token carrying a `tid` claim, so X-Tenant-ID can be omitted."""
    return Token(
        access_token=security.create_access_token(
            ctx.user.id,
            expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
            tenant_id=ctx.id,
        )
    )


@router.get("/{tenant_id}/roles", response_model=RolesPublic)
def list_tenant_roles(
    session: SessionDep, ctx: MembersReader, params: ListParamsDep
) -> Any:
    """Paginated; sort_by: name, description."""
    roles, count = paginate(
        session,
        select(Role).where(Role.tenant_id == ctx.id),
        params,
        {"name": Role.name, "description": Role.description},
        ("name", "asc"),
        Role.id,
        search=[Role.name, Role.description],
    )
    return RolesPublic(
        data=[
            RolePublic.model_validate(r, update={"permissions": r.permissions})
            for r in roles
        ],
        count=count,
    )


@router.get("/{tenant_id}/members", response_model=MembersPublic)
def list_members(
    session: SessionDep,
    ctx: MembersReader,
    params: ListParamsDep,
    role_id: uuid.UUID | None = None,
) -> Any:
    """Paginated; sort_by: email, full_name, joined_at; q: email/full_name; filter: role_id (tenant role)."""
    stmt = (
        select(TenantMember)
        .join(User, col(User.id) == col(TenantMember.user_id))
        .where(TenantMember.tenant_id == ctx.id)
    )
    if role_id is not None:
        stmt = stmt.where(
            col(TenantMember.id).in_(
                select(MemberRole.member_id).where(MemberRole.role_id == role_id)
            )
        )
    members, count = paginate(
        session,
        stmt,
        params,
        {
            "email": User.email,
            "full_name": User.full_name,
            "joined_at": TenantMember.created_at,
        },
        ("email", "asc"),
        TenantMember.id,
        search=[User.email, User.full_name],
    )
    return MembersPublic(data=[_member_public(m) for m in members], count=count)


@router.post("/{tenant_id}/members", response_model=MemberPublic)
def add_tenant_member(
    session: SessionDep, ctx: MembersWriter, member_in: MemberAdd
) -> Any:
    """Add an existing user (by email) to the tenant. Only owners may grant 'owner'."""
    user = crud.get_user_by_email(session=session, email=member_in.email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if get_membership(session, ctx.id, user.id):
        raise HTTPException(status_code=409, detail="User is already a member")
    if "owner" in member_in.roles and not ctx.can("tenant:manage"):
        raise HTTPException(
            status_code=403, detail="Only owners can grant the owner role"
        )
    try:
        member = add_member(session, ctx.tenant, user, member_in.roles)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    session.commit()
    session.refresh(member)
    return _member_public(member)


def _target(
    session: SessionDep, ctx: TenantContext, user_id: uuid.UUID
) -> TenantMember:
    m = get_membership(session, ctx.id, user_id)
    if not m:
        raise HTTPException(status_code=404, detail="Member not found")
    return m


@router.put("/{tenant_id}/members/{user_id}/roles", response_model=MemberPublic)
def change_member_roles(
    session: SessionDep, ctx: MembersWriter, user_id: uuid.UUID, body: MemberRolesUpdate
) -> Any:
    m = _target(session, ctx, user_id)
    was_owner = any(r.name == "owner" for r in m.roles)
    if ("owner" in body.roles or was_owner) and not ctx.can("tenant:manage"):
        raise HTTPException(
            status_code=403, detail="Only owners can change owner roles"
        )
    if was_owner and "owner" not in body.roles and owner_count(session, ctx.id) <= 1:
        raise HTTPException(
            status_code=400, detail="A tenant must keep at least one owner"
        )
    try:
        set_member_roles(session, m, body.roles)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    session.commit()
    session.refresh(m)
    return _member_public(m)


@router.delete("/{tenant_id}/members/{user_id}", response_model=Message)
def remove_member(session: SessionDep, ctx: TenantMember_, user_id: uuid.UUID) -> Any:
    """Remove a member (members:write), or leave the tenant yourself."""
    m = _target(session, ctx, user_id)
    if user_id != ctx.user.id and not ctx.can("members:write"):
        raise HTTPException(
            status_code=403, detail="The user doesn't have enough privileges"
        )
    is_owner = any(r.name == "owner" for r in m.roles)
    if is_owner and user_id != ctx.user.id and not ctx.can("tenant:manage"):
        raise HTTPException(status_code=403, detail="Only owners can remove owners")
    if is_owner and owner_count(session, ctx.id) <= 1:
        raise HTTPException(
            status_code=400, detail="A tenant must keep at least one owner"
        )
    session.delete(m)
    session.commit()
    return Message(message="Member removed successfully")


def _tenant_role(session: SessionDep, ctx: TenantContext, role_id: uuid.UUID) -> Role:
    role = session.get(Role, role_id)
    if not role or role.tenant_id != ctx.id:
        raise HTTPException(status_code=404, detail="Role not found")
    return role


def _tenant_perms(session: SessionDep, codes: list[str]) -> list[Permission]:
    perms = session.exec(
        select(Permission).where(col(Permission.code).in_(codes))
    ).all()
    bad = set(codes) - {p.code for p in perms if p.scope == "tenant"}
    if bad:
        raise HTTPException(
            status_code=400, detail=f"Not tenant-scope permissions: {sorted(bad)}"
        )
    return list(perms)


def _rp(role: Role) -> RolePublic:
    return RolePublic.model_validate(role, update={"permissions": role.permissions})


@router.post("/{tenant_id}/roles", response_model=RolePublic)
def create_tenant_role(
    session: SessionDep, ctx: TenantManager, role_in: RoleCreate
) -> Any:
    if session.exec(
        select(Role).where(Role.tenant_id == ctx.id, Role.name == role_in.name)
    ).first():
        raise HTTPException(status_code=409, detail="Role already exists")
    role = Role(name=role_in.name, description=role_in.description, tenant_id=ctx.id)
    role.permissions = _tenant_perms(session, role_in.permission_codes)
    session.add(role)
    session.commit()
    session.refresh(role)
    return _rp(role)


@router.patch("/{tenant_id}/roles/{role_id}", response_model=RolePublic)
def update_tenant_role(
    session: SessionDep, ctx: TenantManager, role_id: uuid.UUID, role_in: RoleUpdate
) -> Any:
    role = _tenant_role(session, ctx, role_id)
    if role.name == "owner" and role_in.name not in (None, "owner"):
        raise HTTPException(status_code=400, detail="The owner role cannot be renamed")
    role.sqlmodel_update(role_in.model_dump(exclude_unset=True))
    session.add(role)
    session.commit()
    session.refresh(role)
    return _rp(role)


@router.put("/{tenant_id}/roles/{role_id}/permissions", response_model=RolePublic)
def set_tenant_role_permissions(
    session: SessionDep, ctx: TenantManager, role_id: uuid.UUID, body: PermissionCodes
) -> Any:
    role = _tenant_role(session, ctx, role_id)
    if role.name == "owner":
        raise HTTPException(
            status_code=400, detail="The owner role permissions are fixed"
        )
    role.permissions = _tenant_perms(session, body.codes)
    session.add(role)
    session.commit()
    session.refresh(role)
    return _rp(role)


@router.delete("/{tenant_id}/roles/{role_id}", response_model=Message)
def delete_tenant_role(
    session: SessionDep, ctx: TenantManager, role_id: uuid.UUID
) -> Any:
    role = _tenant_role(session, ctx, role_id)
    if role.name == "owner":
        raise HTTPException(status_code=400, detail="The owner role cannot be deleted")
    session.delete(role)
    session.commit()
    return Message(message="Role deleted successfully")
