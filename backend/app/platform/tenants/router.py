"""租户、成员与租户角色接口。"""

import uuid
from datetime import timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import col, func, or_, select

from app.core import security
from app.core.config import settings
from app.core.deps import SessionDep
from app.core.models import Message
from app.core.pagination import ListParamsDep, paginate
from app.core.tenant import set_tenant
from app.platform.auth.deps import (
    CurrentUser,
    platform_api_router,
    require_tenant_permissions,
    resolve_tenant,
)
from app.platform.auth.schemas import Token
from app.platform.console.service import record_platform_audit
from app.platform.menus.schemas import PermNode
from app.platform.menus.service import permission_tree
from app.platform.rbac.models import MemberRole, Permission, Role
from app.platform.rbac.schemas import (
    PermissionCodes,
    RoleCreate,
    RolePublic,
    RolesPublic,
    RoleUpdate,
)
from app.platform.rbac.service import has_permissions, role_filters, touch
from app.platform.tenants.models import Tenant, TenantMember
from app.platform.tenants.schemas import (
    MemberAdd,
    MemberCreate,
    MemberPublic,
    MemberRolesUpdate,
    MembersPublic,
    MemberUserUpdate,
    MyTenantPublic,
    MyTenantsPublic,
    OwnerAssign,
    TenantPublic,
    TenantUpdate,
    UserTenantRoles,
    UserTenantsUpdate,
)
from app.platform.tenants.service import (
    TenantContext,
    add_member,
    get_membership,
    member_permission_codes,
    owner_count,
    set_member_roles,
)
from app.platform.users import service as crud
from app.platform.users.models import User
from app.platform.users.schemas import UserCreate, UserUpdate

router = APIRouter(prefix="/tenants", tags=["tenants"])


def _ctx(*codes: str) -> Any:
    return Depends(require_tenant_permissions(*codes, from_path=True))


TenantMember_ = Annotated[TenantContext, _ctx()]
TenantManager = Annotated[TenantContext, _ctx("tenant:manage")]
MembersReader = Annotated[TenantContext, _ctx("members:read")]
MembersWriter = Annotated[TenantContext, _ctx("members:write")]


def _member_public(m: TenantMember, sole: bool | None = None) -> MemberPublic:
    return MemberPublic(
        user_id=m.user_id,
        email=m.user.email,
        full_name=m.user.full_name,
        username=m.user.username,
        is_active=m.user.is_active,
        roles=sorted(r.name for r in m.roles),
        sole_tenant=bool(sole),
    )


def _sole_tenant_ids(session: SessionDep, user_ids: list[uuid.UUID]) -> set[uuid.UUID]:
    """只属于一个租户且非超级用户的用户 id（租户管理员可管理其账号）。"""
    if not user_ids:
        return set()
    rows = session.exec(
        select(TenantMember.user_id, func.count())
        .where(col(TenantMember.user_id).in_(user_ids))
        .group_by(col(TenantMember.user_id))
    ).all()
    supers = set(
        session.exec(
            select(User.id).where(col(User.id).in_(user_ids), col(User.is_superuser))
        ).all()
    )
    return {uid for uid, n in rows if n == 1 and uid not in supers}


def _is_sole(session: SessionDep, user_id: uuid.UUID) -> bool:
    """单个成员的 sole_tenant（按实际成员关系计算，D3）。"""
    return user_id in _sole_tenant_ids(session, [user_id])


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
    session: SessionDep,
    ctx: MembersReader,
    params: ListParamsDep,
    code: str | None = None,
    title: str | None = None,
    status: Literal["active", "disabled"] | None = None,
) -> Any:
    """Paginated; sort_by: name, title, status, updated_at; q: code/name/description;
    filters: code, title (contains), status."""
    roles, count = paginate(
        session,
        role_filters(select(Role).where(Role.tenant_id == ctx.id), code, title, status),
        params,
        {
            "name": Role.name,
            "title": Role.title,
            "status": Role.status,
            "description": Role.description,
            "updated_at": Role.updated_at,
        },
        ("name", "asc"),
        Role.id,
        search=[Role.name, Role.title, Role.description],
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
    username: str | None = None,
    full_name: str | None = None,
    is_active: bool | None = None,
) -> Any:
    """分页；sort_by: username, email, full_name, joined_at；q: 用户名/邮箱/显示名；
    筛选：role_id（租户角色）、username（用户名或邮箱包含）、full_name（包含）、is_active。"""
    stmt = (
        select(TenantMember)
        .join(User, col(User.id) == col(TenantMember.user_id))
        .where(TenantMember.tenant_id == ctx.id)
    )
    if username:
        like = f"%{username}%"
        stmt = stmt.where(
            or_(col(User.username).ilike(like), col(User.email).ilike(like))
        )
    if full_name:
        stmt = stmt.where(col(User.full_name).ilike(f"%{full_name}%"))
    if is_active is not None:
        stmt = stmt.where(col(User.is_active) == is_active)
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
            "username": User.username,
            "email": User.email,
            "full_name": User.full_name,
            "joined_at": TenantMember.created_at,
        },
        ("username", "asc"),
        TenantMember.id,
        search=[User.username, User.email, User.full_name],
    )
    sole = _sole_tenant_ids(session, [m.user_id for m in members])
    return MembersPublic(
        data=[_member_public(m, m.user_id in sole) for m in members], count=count
    )


@router.post("/{tenant_id}/members", response_model=MemberPublic)
def add_tenant_member(
    session: SessionDep, ctx: MembersWriter, member_in: MemberAdd
) -> Any:
    """按用户名（或邮箱）添加已有用户为成员；只有 owner 能授予 owner 角色。"""
    user = crud.get_user_by_username(session=session, username=member_in.username)
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
    return _member_public(member, _is_sole(session, member.user_id))


@router.post("/{tenant_id}/members/new", response_model=MemberPublic)
def create_tenant_user(
    session: SessionDep, ctx: MembersWriter, body: MemberCreate
) -> Any:
    """租户管理员在本租户内直接创建新用户并加入（不能创建超级用户、不创建个人工作区）。"""
    if "owner" in body.roles and not ctx.can("tenant:manage"):
        raise HTTPException(
            status_code=403, detail="Only owners can grant the owner role"
        )
    if detail := crud.identity_conflict(session, body.username, body.email):
        raise HTTPException(status_code=409, detail=detail)
    user = crud.create_user(
        session=session,
        user_create=UserCreate(
            username=body.username,
            email=body.email,
            full_name=body.full_name,
            password=body.password,
            is_active=body.is_active,
            is_superuser=False,
        ),
    )
    set_tenant(session, ctx.id)
    try:
        member = add_member(session, ctx.tenant, user, body.roles)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    session.commit()
    session.refresh(member)
    return _member_public(member, True)


@router.patch("/{tenant_id}/members/{user_id}/user", response_model=MemberPublic)
def update_tenant_user(
    session: SessionDep, ctx: MembersWriter, user_id: uuid.UUID, body: MemberUserUpdate
) -> Any:
    """修改成员账号（显示名 / 邮箱 / 状态 / 重置密码）。

    仅当该用户只属于本租户且不是超级用户时允许；修改 owner 需 tenant:manage。
    """
    m = _target(session, ctx, user_id)
    if user_id not in _sole_tenant_ids(session, [user_id]):
        raise HTTPException(
            status_code=403,
            detail="User belongs to other tenants; ask a platform admin",
        )
    if any(r.name == "owner" for r in m.roles) and not ctx.can("tenant:manage"):
        raise HTTPException(status_code=403, detail="Only owners can manage owners")
    if detail := crud.identity_conflict(session, None, body.email, user_id):
        raise HTTPException(status_code=409, detail=detail)
    data = body.model_dump(exclude_unset=True)
    if data.get("is_active") is None:
        data.pop("is_active", None)
    crud.update_user(session=session, db_user=m.user, user_in=UserUpdate(**data))
    session.refresh(m)
    return _member_public(m, True)


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
    return _member_public(m, _is_sole(session, m.user_id))


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


@router.get("/{tenant_id}/permission-tree", response_model=list[PermNode])
def tenant_permission_tree(session: SessionDep, _ctx: MembersReader) -> Any:
    """Workspace permission tree limited to tenant-scope permissions (role dialog)."""
    return permission_tree(session, ["workspace"], "tenant")


@router.post("/{tenant_id}/roles", response_model=RolePublic)
def create_tenant_role(
    session: SessionDep, ctx: TenantManager, role_in: RoleCreate
) -> Any:
    if session.exec(
        select(Role).where(Role.tenant_id == ctx.id, Role.name == role_in.name)
    ).first():
        raise HTTPException(status_code=409, detail="Role already exists")
    role = Role(
        name=role_in.name,
        title=role_in.title,
        description=role_in.description,
        status=role_in.status,
        tenant_id=ctx.id,
    )
    role.permissions = _tenant_perms(session, role_in.permission_codes)
    touch(role, ctx.user)
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
    if role.name == "owner" and role_in.status == "disabled":
        raise HTTPException(status_code=400, detail="The owner role cannot be disabled")
    role.sqlmodel_update(role_in.model_dump(exclude_unset=True))
    touch(role, ctx.user)
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
    touch(role, ctx.user)
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


# ---------------- platform space (superuser only) ----------------
# 平台管理控制台维护任意租户的成员与 owner：超级用户显式进入租户上下文（RLS），
# 复用上面的成员接口实现，并把每次写操作记入平台操作日志。
platform_router = platform_api_router()


def _platform_ctx(
    session: SessionDep, user: CurrentUser, tenant_id: uuid.UUID
) -> TenantContext:
    if not session.get(Tenant, tenant_id):
        raise HTTPException(status_code=404, detail="Tenant not found")
    # 平台接口已按平台权限授权；非成员的平台管理员同样获得该租户的全部权限
    return resolve_tenant(session, user, tenant_id, impersonating=True)


@platform_router.get("/tenants/{tenant_id}/members", response_model=MembersPublic)
def platform_list_members(
    session: SessionDep,
    user: CurrentUser,
    tenant_id: uuid.UUID,
    params: ListParamsDep,
    role_id: uuid.UUID | None = None,
) -> Any:
    """Members of any tenant. Paginated; same filters as the tenant endpoint."""
    return list_members(
        session, _platform_ctx(session, user, tenant_id), params, role_id
    )


@platform_router.get("/tenants/{tenant_id}/roles", response_model=RolesPublic)
def platform_list_tenant_roles(
    session: SessionDep, user: CurrentUser, tenant_id: uuid.UUID, params: ListParamsDep
) -> Any:
    """Tenant roles of any tenant (owner/admin/member templates + custom)."""
    return list_tenant_roles(session, _platform_ctx(session, user, tenant_id), params)


@platform_router.post("/tenants/{tenant_id}/members", response_model=MemberPublic)
def platform_add_member(
    session: SessionDep, user: CurrentUser, tenant_id: uuid.UUID, body: MemberAdd
) -> Any:
    ctx = _platform_ctx(session, user, tenant_id)
    record_platform_audit(
        session,
        user,
        "member.add",
        "user",
        body.username,
        tenant_id,
        {"roles": body.roles},
    )
    return add_tenant_member(session, ctx, body)


@platform_router.put(
    "/tenants/{tenant_id}/members/{user_id}/roles", response_model=MemberPublic
)
def platform_set_member_roles(
    session: SessionDep,
    user: CurrentUser,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    body: MemberRolesUpdate,
) -> Any:
    ctx = _platform_ctx(session, user, tenant_id)
    record_platform_audit(
        session, user, "member.roles", "user", user_id, tenant_id, {"roles": body.roles}
    )
    return change_member_roles(session, ctx, user_id, body)


@platform_router.delete(
    "/tenants/{tenant_id}/members/{user_id}", response_model=Message
)
def platform_remove_member(
    session: SessionDep, user: CurrentUser, tenant_id: uuid.UUID, user_id: uuid.UUID
) -> Any:
    ctx = _platform_ctx(session, user, tenant_id)
    record_platform_audit(session, user, "member.remove", "user", user_id, tenant_id)
    return remove_member(session, ctx, user_id)


@platform_router.put("/tenants/{tenant_id}/owner", response_model=MemberPublic)
def platform_assign_owner(
    session: SessionDep, user: CurrentUser, tenant_id: uuid.UUID, body: OwnerAssign
) -> Any:
    """Make an existing user an owner (adds the membership when missing)."""
    ctx = _platform_ctx(session, user, tenant_id)
    target = crud.get_user_by_username(session=session, username=body.username)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    m = get_membership(session, tenant_id, target.id)
    if m is None:
        m = add_member(session, ctx.tenant, target, ["owner"])
    else:
        set_member_roles(session, m, sorted({r.name for r in m.roles} | {"owner"}))
    record_platform_audit(session, user, "tenant.owner", "user", target.id, tenant_id)
    session.commit()
    session.refresh(m)
    return _member_public(m, _is_sole(session, m.user_id))


@platform_router.get("/users/{user_id}/tenants", response_model=list[UserTenantRoles])
def platform_user_tenants(session: SessionDep, user_id: uuid.UUID) -> Any:
    """用户所属的租户及其租户角色（平台用户编辑对话框）。"""
    if not session.get(User, user_id):
        raise HTTPException(status_code=404, detail="User not found")
    ms = session.exec(select(TenantMember).where(TenantMember.user_id == user_id)).all()
    return [
        UserTenantRoles(
            tenant_id=m.tenant_id,
            tenant_name=m.tenant.name if m.tenant else None,
            roles=sorted(r.name for r in m.roles),
        )
        for m in ms
    ]


@platform_router.put("/users/{user_id}/tenants", response_model=list[UserTenantRoles])
def platform_set_user_tenants(
    session: SessionDep, user: CurrentUser, user_id: uuid.UUID, body: UserTenantsUpdate
) -> Any:
    """整体设置用户的租户成员身份与租户角色（新增 / 修改 / 移除），逐项记入平台操作日志。"""
    target = session.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    want = {i.tenant_id: i.roles for i in body.items}
    have = {
        m.tenant_id: m
        for m in session.exec(
            select(TenantMember).where(TenantMember.user_id == user_id)
        ).all()
    }
    for tid in set(have) - set(want):
        m = have[tid]
        if any(r.name == "owner" for r in m.roles) and owner_count(session, tid) <= 1:
            raise HTTPException(
                status_code=400, detail="A tenant must keep at least one owner"
            )
        record_platform_audit(
            session, user, "member.remove", "user", target.username, tid
        )
        session.delete(m)
    for tid, roles in want.items():
        ctx = _platform_ctx(session, user, tid)
        try:
            if tid in have:
                m = have[tid]
                if (
                    any(r.name == "owner" for r in m.roles)
                    and "owner" not in roles
                    and owner_count(session, tid) <= 1
                ):
                    raise HTTPException(
                        status_code=400, detail="A tenant must keep at least one owner"
                    )
                set_member_roles(session, m, roles)
                record_platform_audit(
                    session,
                    user,
                    "member.roles",
                    "user",
                    target.username,
                    tid,
                    {"roles": roles},
                )
            else:
                add_member(session, ctx.tenant, target, roles)
                record_platform_audit(
                    session,
                    user,
                    "member.add",
                    "user",
                    target.username,
                    tid,
                    {"roles": roles},
                )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    session.commit()
    return platform_user_tenants(session, user_id)
