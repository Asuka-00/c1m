"""认证与授权依赖：当前用户、平台权限、租户解析与租户权限。"""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated, Any

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from pydantic import ValidationError
from sqlmodel import Session

from app.core import security
from app.core.config import settings
from app.core.deps import SessionDep
from app.core.tenant import set_tenant
from app.platform.auth.schemas import TokenPayload
from app.platform.tenants.models import Tenant, TenantMember
from app.platform.tenants.service import (
    TenantContext,
    get_membership,
    member_permission_codes,
)
from app.platform.users.models import User

reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/login/access-token"
)
TokenDep = Annotated[str, Depends(reusable_oauth2)]


def get_token_payload(token: TokenDep) -> TokenPayload:
    """解码并校验 JWT。

    Raises:
        HTTPException: 令牌无效（403）。
    """
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        return TokenPayload(**payload)
    except InvalidTokenError, ValidationError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )


TokenPayloadDep = Annotated[TokenPayload, Depends(get_token_payload)]


def get_current_user(session: SessionDep, token_data: TokenPayloadDep) -> User:
    """当前登录用户。

    Raises:
        HTTPException: 用户不存在（404）或已停用（400）。
    """
    user = session.get(User, token_data.sub)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_current_active_superuser(current_user: CurrentUser) -> User:
    """要求超级用户。

    Raises:
        HTTPException: 非超级用户（403）。
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=403, detail="The user doesn't have enough privileges"
        )
    return current_user


def require_permissions(*codes: str) -> Callable[[User], User]:
    """平台级权限校验依赖（超级用户直接通过）。

    租户范围的接口请使用 :func:`require_tenant_permissions`，它会合并用户在该租户的角色权限。

    Args:
        *codes: 需要同时具备的权限编码。
    """
    from app.platform.rbac.service import has_permissions

    def checker(current_user: CurrentUser) -> User:
        if not has_permissions(current_user, *codes):
            raise HTTPException(
                status_code=403, detail="The user doesn't have enough privileges"
            )
        return current_user

    return checker


# ---------------- multi-tenancy ----------------
def resolve_tenant(
    session: Session, user: User, tenant_id: uuid.UUID, impersonating: bool = False
) -> TenantContext:
    """校验对租户的访问，设置 RLS 上下文并计算有效权限。

    Args:
        session: 数据库会话。
        user: 当前用户。
        tenant_id: 租户 id。
        impersonating: 令牌是绑定到该租户的模拟令牌（平台“以租户身份进入”），非成员也可访问，
            并获得全部租户权限（等同所有者）。

    Raises:
        HTTPException: 租户不存在 / 已停用，或用户不是成员且非平台管理员（403/404）。
    """
    from app.platform.rbac.service import user_permission_codes

    tenant = session.get(Tenant, tenant_id)
    member = get_membership(session, tenant_id, user.id) if tenant else None
    if not tenant or (not member and not user.is_superuser and not impersonating):
        # 不暴露租户是否存在
        raise HTTPException(status_code=404, detail="Tenant not found")
    if tenant.status != "active" and not user.is_superuser:
        raise HTTPException(status_code=403, detail="Tenant is suspended")
    if tenant.expires_at and not user.is_superuser:
        exp = tenant.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=UTC)
        if exp < datetime.now(UTC):
            raise HTTPException(status_code=403, detail="Tenant has expired")
    set_tenant(session, tenant.id)
    perms = user_permission_codes(user) | member_permission_codes(member)
    if impersonating:  # 平台管理员以租户身份进入：等同租户所有者
        from app.platform.rbac.permissions import TENANT_PERMISSIONS

        perms |= set(TENANT_PERMISSIONS)
    return TenantContext(tenant=tenant, user=user, member=member, permissions=perms)


def get_current_tenant(
    session: SessionDep,
    current_user: CurrentUser,
    token_data: TokenPayloadDep,
    x_tenant_id: Annotated[uuid.UUID | None, Header()] = None,
) -> TenantContext:
    """解析当前租户。

    顺序：请求头 ``X-Tenant-ID`` > JWT ``tid`` 声明 > 用户唯一的租户成员关系；都没有则 400。
    """
    if token_data.imp and token_data.tid:  # 模拟令牌只能访问其绑定的租户
        tid = uuid.UUID(token_data.tid)
        if x_tenant_id is not None and x_tenant_id != tid:
            raise HTTPException(
                status_code=403, detail="Impersonation token is bound to another tenant"
            )
        return resolve_tenant(session, current_user, tid, impersonating=True)
    tenant_id = x_tenant_id
    if tenant_id is None and token_data.tid:
        tenant_id = uuid.UUID(token_data.tid)
    if tenant_id is None:
        from sqlmodel import select

        memberships = session.exec(
            select(TenantMember).where(TenantMember.user_id == current_user.id)
        ).all()
        if len(memberships) != 1:
            raise HTTPException(
                status_code=400,
                detail="X-Tenant-ID header is required (user belongs to multiple or no tenants)",
            )
        tenant_id = memberships[0].tenant_id
    return resolve_tenant(session, current_user, tenant_id)


CurrentTenant = Annotated[TenantContext, Depends(get_current_tenant)]


def get_path_tenant(
    tenant_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
    token_data: TokenPayloadDep,
) -> TenantContext:
    """从路径参数 ``{tenant_id}`` 解析租户（用于租户管理接口）。"""
    if token_data.imp and token_data.tid != str(tenant_id):
        raise HTTPException(
            status_code=403, detail="Impersonation token is bound to another tenant"
        )
    return resolve_tenant(
        session, current_user, tenant_id, impersonating=token_data.imp
    )


PathTenant = Annotated[TenantContext, Depends(get_path_tenant)]


def _tenant_checker(dep: Any, codes: tuple[str, ...]) -> Callable[..., TenantContext]:
    def checker(ctx: TenantContext = Depends(dep)) -> TenantContext:
        if not ctx.can(*codes):
            raise HTTPException(
                status_code=403, detail="The user doesn't have enough privileges"
            )
        return ctx

    return checker


def require_tenant_permissions(
    *codes: str, from_path: bool = False
) -> Callable[..., TenantContext]:
    """租户级权限校验依赖。

    Args:
        *codes: 需要同时具备的权限编码。
        from_path: 为 True 时租户取自路径参数 ``{tenant_id}``，否则取自请求头 / JWT。
    """
    return _tenant_checker(get_path_tenant if from_path else get_current_tenant, codes)


# 平台接口路径（/platform/ 之后的首段）-> 权限资源；GET 需 <资源>:read，其余需 <资源>:write
PLATFORM_RESOURCES: dict[str, str] = {
    "users": "users",
    "roles": "roles",
    "permissions": "roles",
    "permission-tree": "roles",
    "menus": "roles",
    "tenants": "tenants",
    "config": "platform.config",
    "notify-channels": "platform.notify",
    "audit": "platform.audit",
    "login-log": "platform.audit",
    "ops-log": "platform.audit",
}


def platform_permission(method: str, path: str) -> str | None:
    """平台接口所需的权限编码；未登记的路径返回 None（仅超级用户）。

    特例：删除用户需 ``users:delete``；设置用户角色需 ``roles:write``；
    租户品牌属平台配置（``platform.config:*``）；平台审计只读。

    Args:
        method: HTTP 方法。
        path: 路由路径模板（含 ``/platform/``）。
    """
    rest = path.split("/platform/", 1)[-1]
    parts = rest.strip("/").split("/")
    res = PLATFORM_RESOURCES.get(parts[0])
    if res is None:
        return None
    read = method in ("GET", "HEAD", "OPTIONS")
    if parts[0] == "users" and "roles" in parts[1:]:
        res = "roles"
    elif parts[0] == "tenants" and "branding" in parts[1:]:
        res = "platform.config"
    elif parts[0] == "users" and method == "DELETE":
        return "users:delete"
    return f"{res}:{'read' if read else 'write'}"


def platform_codes(user: User) -> set[str]:
    """用户持有的平台作用域权限编码（决定是否显示平台控制台入口）。"""
    from app.platform.rbac.permissions import PLATFORM_PERMISSIONS
    from app.platform.rbac.service import user_permission_codes

    return user_permission_codes(user) & set(PLATFORM_PERMISSIONS)


def require_platform_access(
    request: Request, current_user: CurrentUser, token_data: TokenPayloadDep
) -> User:
    """平台接口授权：超级用户直接通过；其他用户按路径映射的平台权限校验。

    “以租户身份进入”的模拟令牌一律不能调用平台接口。

    Raises:
        HTTPException: 模拟令牌或缺少权限（403）。
    """
    if token_data.imp:
        raise HTTPException(
            status_code=403,
            detail="Exit tenant impersonation to use the platform console",
        )
    if current_user.is_superuser:
        return current_user
    route = request.scope.get("route")
    code = platform_permission(request.method, getattr(route, "path", request.url.path))
    from app.platform.rbac.service import has_permissions

    if code is None or not has_permissions(current_user, code):
        raise HTTPException(
            status_code=403, detail="The user doesn't have enough privileges"
        )
    return current_user


def platform_api_router(*routers: APIRouter) -> APIRouter:
    """构造平台空间路由（``/platform`` 前缀）。

    超级用户或持有对应平台权限的用户可访问，见 :func:`platform_permission`。

    Args:
        *routers: 挂到平台空间下的路由（路径加 ``/platform``）。
    """
    r = APIRouter(
        prefix="/platform",
        tags=["platform"],
        dependencies=[Depends(require_platform_access)],
    )
    for sub in routers:
        r.include_router(sub)
    return r
