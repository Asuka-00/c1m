"""权限、角色及用户角色分配接口。"""

import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import col, select

from app.core.deps import SessionDep
from app.core.models import Message
from app.core.pagination import ListParamsDep, paginate
from app.platform.auth.deps import platform_api_router, require_permissions
from app.platform.rbac.models import Permission, Role
from app.platform.rbac.schemas import (
    PermissionCodes,
    PermissionCreate,
    PermissionPublic,
    PermissionsPublic,
    PermissionUpdate,
    RoleCreate,
    RolePublic,
    RolesPublic,
    RoleUpdate,
)
from app.platform.users.models import User

read_dep = [Depends(require_permissions("roles:read"))]
write_dep = [Depends(require_permissions("roles:write"))]

permissions_router = APIRouter(prefix="/permissions", tags=["rbac"])
roles_router = APIRouter(prefix="/roles", tags=["rbac"])
user_roles_router = APIRouter(prefix="/users", tags=["rbac"])


def is_platform_code(code: str) -> bool:
    """权限编码是否属于平台空间（内置平台权限或 ``platform:`` 前缀）。"""
    from app.platform.rbac.permissions import PLATFORM_PERMISSIONS

    return code in PLATFORM_PERMISSIONS or code.startswith("platform:")


def _check_scope(code: str, scope: str) -> None:
    """平台权限不得声明为租户作用域（否则可被授予租户角色）。"""
    if scope not in ("platform", "tenant"):
        raise HTTPException(status_code=400, detail="scope must be platform or tenant")
    if scope == "tenant" and is_platform_code(code):
        raise HTTPException(
            status_code=400,
            detail=f"Platform permission {code} cannot be tenant-scoped",
        )


def _get_or_404(session: SessionDep, model: Any, id: uuid.UUID, name: str) -> Any:
    obj = session.get(model, id)
    # /roles manages platform roles only; tenant roles live under /tenants/{id}/roles
    if not obj or (model is Role and obj.tenant_id is not None):
        raise HTTPException(status_code=404, detail=f"{name} not found")
    return obj


# ---------------- permissions ----------------
@permissions_router.get("/", dependencies=read_dep, response_model=PermissionsPublic)
def list_permissions(
    session: SessionDep,
    params: ListParamsDep,
    scope: Literal["platform", "tenant"] | None = None,
) -> Any:
    """Paginated; sort_by: code, scope, description; q: code/description; filter: scope."""
    stmt = (
        select(Permission)
        if scope is None
        else select(Permission).where(Permission.scope == scope)
    )
    data, count = paginate(
        session,
        stmt,
        params,
        {
            "code": Permission.code,
            "scope": Permission.scope,
            "description": Permission.description,
        },
        ("code", "asc"),
        Permission.id,
        search=[Permission.code, Permission.description],
    )
    return PermissionsPublic(data=data, count=count)


@permissions_router.post("/", dependencies=write_dep, response_model=PermissionPublic)
def create_permission(session: SessionDep, perm_in: PermissionCreate) -> Any:
    if session.exec(select(Permission).where(Permission.code == perm_in.code)).first():
        raise HTTPException(status_code=409, detail="Permission already exists")
    _check_scope(perm_in.code, perm_in.scope)
    perm = Permission.model_validate(perm_in)
    session.add(perm)
    session.commit()
    session.refresh(perm)
    return perm


@permissions_router.get("/{id}", dependencies=read_dep, response_model=PermissionPublic)
def read_permission(session: SessionDep, id: uuid.UUID) -> Any:
    return _get_or_404(session, Permission, id, "Permission")


@permissions_router.patch(
    "/{id}", dependencies=write_dep, response_model=PermissionPublic
)
def update_permission(
    session: SessionDep, id: uuid.UUID, perm_in: PermissionUpdate
) -> Any:
    perm = _get_or_404(session, Permission, id, "Permission")
    data = perm_in.model_dump(exclude_unset=True)
    if "code" in data:
        other = session.exec(
            select(Permission).where(Permission.code == data["code"])
        ).first()
        if other and other.id != id:
            raise HTTPException(status_code=409, detail="Permission already exists")
    _check_scope(data.get("code", perm.code), data.get("scope", perm.scope))
    perm.sqlmodel_update(data)
    session.add(perm)
    session.commit()
    session.refresh(perm)
    return perm


@permissions_router.delete("/{id}", dependencies=write_dep, response_model=Message)
def delete_permission(session: SessionDep, id: uuid.UUID) -> Any:
    session.delete(_get_or_404(session, Permission, id, "Permission"))
    session.commit()
    return Message(message="Permission deleted successfully")


# ---------------- roles ----------------
@roles_router.get("/", dependencies=read_dep, response_model=RolesPublic)
def list_roles(session: SessionDep, params: ListParamsDep) -> Any:
    """Platform roles. Paginated; sort_by: name, description."""
    roles, count = paginate(
        session,
        select(Role).where(col(Role.tenant_id).is_(None)),
        params,
        {"name": Role.name, "description": Role.description},
        ("name", "asc"),
        Role.id,
        search=[Role.name, Role.description],
    )
    return RolesPublic(data=[_role_public(r) for r in roles], count=count)


def _role_public(role: Role) -> RolePublic:
    return RolePublic.model_validate(role, update={"permissions": role.permissions})


@roles_router.post("/", dependencies=write_dep, response_model=RolePublic)
def create_role(session: SessionDep, role_in: RoleCreate) -> Any:
    if session.exec(
        select(Role).where(Role.name == role_in.name, col(Role.tenant_id).is_(None))
    ).first():
        raise HTTPException(status_code=409, detail="Role already exists")
    role = Role(name=role_in.name, description=role_in.description)
    for code in role_in.permission_codes:
        perm = session.exec(select(Permission).where(Permission.code == code)).first()
        if not perm:
            raise HTTPException(status_code=404, detail=f"Permission {code} not found")
        role.permissions.append(perm)
    session.add(role)
    session.commit()
    session.refresh(role)
    return _role_public(role)


@roles_router.get("/{id}", dependencies=read_dep, response_model=RolePublic)
def read_role(session: SessionDep, id: uuid.UUID) -> Any:
    return _role_public(_get_or_404(session, Role, id, "Role"))


@roles_router.patch("/{id}", dependencies=write_dep, response_model=RolePublic)
def update_role(session: SessionDep, id: uuid.UUID, role_in: RoleUpdate) -> Any:
    role = _get_or_404(session, Role, id, "Role")
    data = role_in.model_dump(exclude_unset=True)
    if "name" in data:
        other = session.exec(
            select(Role).where(Role.name == data["name"], col(Role.tenant_id).is_(None))
        ).first()
        if other and other.id != id:
            raise HTTPException(status_code=409, detail="Role already exists")
    role.sqlmodel_update(data)
    session.add(role)
    session.commit()
    session.refresh(role)
    return _role_public(role)


@roles_router.delete("/{id}", dependencies=write_dep, response_model=Message)
def delete_role(session: SessionDep, id: uuid.UUID) -> Any:
    session.delete(_get_or_404(session, Role, id, "Role"))
    session.commit()
    return Message(message="Role deleted successfully")


@roles_router.post(
    "/{id}/permissions/{permission_id}",
    dependencies=write_dep,
    response_model=RolePublic,
)
def add_permission_to_role(
    session: SessionDep, id: uuid.UUID, permission_id: uuid.UUID
) -> Any:
    role = _get_or_404(session, Role, id, "Role")
    perm = _get_or_404(session, Permission, permission_id, "Permission")
    if perm not in role.permissions:
        role.permissions.append(perm)
        session.add(role)
        session.commit()
        session.refresh(role)
    return _role_public(role)


@roles_router.delete(
    "/{id}/permissions/{permission_id}",
    dependencies=write_dep,
    response_model=RolePublic,
)
def remove_permission_from_role(
    session: SessionDep, id: uuid.UUID, permission_id: uuid.UUID
) -> Any:
    role = _get_or_404(session, Role, id, "Role")
    perm = _get_or_404(session, Permission, permission_id, "Permission")
    if perm in role.permissions:
        role.permissions.remove(perm)
        session.add(role)
        session.commit()
        session.refresh(role)
    return _role_public(role)


# ---------------- user <-> role ----------------
@user_roles_router.get(
    "/{user_id}/roles", dependencies=read_dep, response_model=list[RolePublic]
)
def list_user_roles(session: SessionDep, user_id: uuid.UUID) -> Any:
    user = _get_or_404(session, User, user_id, "User")
    return [_role_public(r) for r in user.roles]


@user_roles_router.post(
    "/{user_id}/roles/{role_id}",
    dependencies=write_dep,
    response_model=list[RolePublic],
)
def assign_role_to_user(
    session: SessionDep, user_id: uuid.UUID, role_id: uuid.UUID
) -> Any:
    user = _get_or_404(session, User, user_id, "User")
    role = _get_or_404(session, Role, role_id, "Role")
    if role not in user.roles:
        user.roles.append(role)
        session.add(user)
        session.commit()
        session.refresh(user)
    return [_role_public(r) for r in user.roles]


@user_roles_router.delete(
    "/{user_id}/roles/{role_id}",
    dependencies=write_dep,
    response_model=list[RolePublic],
)
def remove_role_from_user(
    session: SessionDep, user_id: uuid.UUID, role_id: uuid.UUID
) -> Any:
    user = _get_or_404(session, User, user_id, "User")
    role = _get_or_404(session, Role, role_id, "Role")
    if role in user.roles:
        user.roles.remove(role)
        session.add(user)
        session.commit()
        session.refresh(user)
    return [_role_public(r) for r in user.roles]


@roles_router.put(
    "/{id}/permissions", dependencies=write_dep, response_model=RolePublic
)
def set_role_permissions(
    session: SessionDep, id: uuid.UUID, body: PermissionCodes
) -> Any:
    """Replace the role's permission set (used by the permission tree UI)."""
    role = _get_or_404(session, Role, id, "Role")
    perms = session.exec(
        select(Permission).where(col(Permission.code).in_(body.codes))
    ).all()
    missing = set(body.codes) - {p.code for p in perms}
    if missing:
        raise HTTPException(
            status_code=404, detail=f"Unknown permissions: {sorted(missing)}"
        )
    role.permissions = list(perms)
    session.add(role)
    session.commit()
    session.refresh(role)
    return _role_public(role)


# 平台空间别名：/platform/users|roles|permissions/...（仅超级用户）
platform_router = platform_api_router(
    user_roles_router, roles_router, permissions_router
)
