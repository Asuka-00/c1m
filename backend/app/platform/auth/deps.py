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
    user = session.get(User, token_data.sub)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_current_active_superuser(current_user: CurrentUser) -> User:
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=403, detail="The user doesn't have enough privileges"
        )
    return current_user


def require_permissions(*codes: str) -> Callable[[User], User]:
    """Platform-level permission check (superusers bypass). For tenant-scoped
    endpoints use require_tenant_permissions, which also includes the user's
    permissions from their membership in the current tenant."""
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
    """Validate access to tenant_id, set the RLS context, compute effective perms."""
    from app.platform.rbac.service import user_permission_codes

    tenant = session.get(Tenant, tenant_id)
    member = get_membership(session, tenant_id, user.id) if tenant else None
    if not tenant or (not member and not user.is_superuser):
        # do not reveal whether the tenant exists
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
    """Tenant resolution order: X-Tenant-ID header > `tid` JWT claim > the user's
    only membership. Otherwise 400."""
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
    """Tenant-scoped permission check. Tenant comes from X-Tenant-ID/JWT
    (default) or from the {tenant_id} path parameter (from_path=True)."""
    return _tenant_checker(get_path_tenant if from_path else get_current_tenant, codes)
