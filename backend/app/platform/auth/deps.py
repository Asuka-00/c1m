"""认证与授权依赖：当前用户、平台权限、租户解析与租户权限。"""

import uuid
from collections.abc import Callable
from typing import Annotated, Any

import jwt
from fastapi import Depends, Header, HTTPException, status
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
def resolve_tenant(session: Session, user: User, tenant_id: uuid.UUID) -> TenantContext:
    """校验对租户的访问，设置 RLS 上下文并计算有效权限。

    Raises:
        HTTPException: 租户不存在 / 已停用，或用户不是成员且非平台管理员（403/404）。
    """
    from app.platform.rbac.service import user_permission_codes

    tenant = session.get(Tenant, tenant_id)
    member = get_membership(session, tenant_id, user.id) if tenant else None
    if not tenant or (not member and not user.is_superuser):
        # 不暴露租户是否存在
        raise HTTPException(status_code=404, detail="Tenant not found")
    if tenant.status != "active" and not user.is_superuser:
        raise HTTPException(status_code=403, detail="Tenant is suspended")
    set_tenant(session, tenant.id)
    perms = user_permission_codes(user) | member_permission_codes(member)
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
    tenant_id: uuid.UUID, session: SessionDep, current_user: CurrentUser
) -> TenantContext:
    """从路径参数 ``{tenant_id}`` 解析租户（用于租户管理接口）。"""
    return resolve_tenant(session, current_user, tenant_id)


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
