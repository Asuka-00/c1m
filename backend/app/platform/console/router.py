"""平台管理控制台接口：``/api/v1/platform/...``，仅超级用户（路由级依赖，其余用户 403）。

- 平台用户 / 角色 / 权限 / 菜单、租户成员与品牌、平台配置由各自模块的 ``platform_router`` 提供；
- 本模块：租户管理（列表、创建、停用、套餐、到期）、以租户身份进入；
- 跨租户审计：逐租户显式 ``set_tenant`` 读取 RLS 数据并合并，读取行为本身记入平台操作日志；
- 登录日志、平台操作日志、通知渠道开关、平台配置默认值。
"""

import uuid
from datetime import timedelta
from typing import Any, Literal

import sqlalchemy as sa
from fastapi import HTTPException, Query
from sqlmodel import col, func, select

from app.core import security
from app.core.config import settings
from app.core.deps import SessionDep
from app.core.models import Message
from app.core.pagination import ListParamsDep, paginate
from app.core.tenant import set_tenant
from app.platform.auth.deps import CurrentUser, platform_api_router
from app.platform.auth.schemas import Token
from app.platform.config.models import ConfigGroup, ConfigItem
from app.platform.console.models import LoginLog, PlatformAudit
from app.platform.console.schemas import (
    ChannelPublic,
    ChannelsPublic,
    ChannelUpdate,
    CrossTenantAudit,
    CrossTenantAudits,
    LoginLogsPublic,
    PlatformAuditsPublic,
    PlatformTenant,
    PlatformTenantCreate,
    PlatformTenants,
    PlatformTenantUpdate,
)
from app.platform.console.service import record_platform_audit
from app.platform.notification.service import channels as list_registered_channels
from app.platform.rbac.models import MemberRole, Role
from app.platform.tenants.models import Tenant, TenantMember
from app.platform.tenants.service import create_tenant, get_membership
from app.platform.users import service as crud
from app.platform.users.models import User

router = platform_api_router()


def _tenant_or_404(session: SessionDep, tenant_id: uuid.UUID) -> Tenant:
    t = session.get(Tenant, tenant_id)
    if not t:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return t


def _owners(session: SessionDep, ids: list[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
    if not ids:
        return {}
    rows = session.exec(
        select(TenantMember.tenant_id, User.email)
        .join(User, col(User.id) == col(TenantMember.user_id))
        .join(MemberRole, col(MemberRole.member_id) == col(TenantMember.id))
        .join(Role, col(Role.id) == col(MemberRole.role_id))
        .where(col(TenantMember.tenant_id).in_(ids), Role.name == "owner")
    ).all()
    out: dict[uuid.UUID, list[str]] = {}
    for tid, email in rows:
        out.setdefault(tid, []).append(email)
    return out


def _public(session: SessionDep, tenants: list[Tenant]) -> list[PlatformTenant]:
    ids = [t.id for t in tenants]
    counts = (
        dict(
            session.exec(
                select(TenantMember.tenant_id, func.count())
                .where(col(TenantMember.tenant_id).in_(ids))
                .group_by(col(TenantMember.tenant_id))
            ).all()
        )
        if ids
        else {}
    )
    owners = _owners(session, ids)
    return [
        PlatformTenant.model_validate(
            t,
            update={
                "member_count": counts.get(t.id, 0),
                "owners": sorted(owners.get(t.id, [])),
            },
        )
        for t in tenants
    ]


# ---------------- tenants ----------------
@router.get("/tenants", response_model=PlatformTenants)
def list_platform_tenants(
    session: SessionDep,
    params: ListParamsDep,
    status: Literal["active", "suspended"] | None = None,
    plan: Literal["trial", "standard", "enterprise"] | None = None,
) -> Any:
    """All tenants. Paginated; sort_by: name, slug, status, plan, expires_at, created_at;
    q: name/slug; filters: status, plan."""
    stmt = select(Tenant)
    if status:
        stmt = stmt.where(Tenant.status == status)
    if plan:
        stmt = stmt.where(Tenant.plan == plan)
    data, count = paginate(
        session,
        stmt,
        params,
        {
            "name": Tenant.name,
            "slug": Tenant.slug,
            "status": Tenant.status,
            "plan": Tenant.plan,
            "expires_at": Tenant.expires_at,
            "created_at": Tenant.created_at,
        },
        ("slug", "asc"),
        Tenant.id,
        search=[Tenant.name, Tenant.slug],
    )
    return PlatformTenants(data=_public(session, list(data)), count=count)


@router.post("/tenants", response_model=PlatformTenant)
def create_platform_tenant(
    session: SessionDep, user: CurrentUser, body: PlatformTenantCreate
) -> Any:
    """Create a tenant (with owner/admin/member role templates) and optional owner."""
    if session.exec(select(Tenant).where(Tenant.slug == body.slug)).first():
        raise HTTPException(status_code=409, detail="Tenant slug already exists")
    owner = None
    if body.owner_email:
        owner = crud.get_user_by_email(session=session, email=body.owner_email)
        if not owner:
            raise HTTPException(status_code=404, detail="Owner user not found")
    t = create_tenant(session, body.name, body.slug, owner=owner)
    t.plan = body.plan
    t.expires_at = body.expires_at
    session.add(t)
    record_platform_audit(
        session,
        user,
        "tenant.create",
        "tenant",
        t.id,
        t.id,
        {"slug": t.slug, "plan": t.plan, "owner": body.owner_email},
    )
    session.commit()
    session.refresh(t)
    return _public(session, [t])[0]


@router.get("/tenants/{tenant_id}", response_model=PlatformTenant)
def read_platform_tenant(session: SessionDep, tenant_id: uuid.UUID) -> Any:
    return _public(session, [_tenant_or_404(session, tenant_id)])[0]


@router.patch("/tenants/{tenant_id}", response_model=PlatformTenant)
def update_platform_tenant(
    session: SessionDep,
    user: CurrentUser,
    tenant_id: uuid.UUID,
    body: PlatformTenantUpdate,
) -> Any:
    """Update name / status (enable/disable) / plan / expires_at (null = never)."""
    t = _tenant_or_404(session, tenant_id)
    data = body.model_dump(exclude_unset=True)
    t.sqlmodel_update(data)
    session.add(t)
    record_platform_audit(
        session,
        user,
        "tenant.update",
        "tenant",
        t.id,
        t.id,
        {k: str(v) if v is not None else None for k, v in data.items()},
    )
    session.commit()
    session.refresh(t)
    return _public(session, [t])[0]


@router.delete("/tenants/{tenant_id}", response_model=Message)
def delete_platform_tenant(
    session: SessionDep, user: CurrentUser, tenant_id: uuid.UUID
) -> Any:
    t = _tenant_or_404(session, tenant_id)
    record_platform_audit(
        session, user, "tenant.delete", "tenant", t.id, None, {"slug": t.slug}
    )
    session.delete(t)
    session.commit()
    return Message(message="Tenant deleted successfully")


@router.post("/tenants/{tenant_id}/enter", response_model=Token)
def enter_tenant(session: SessionDep, user: CurrentUser, tenant_id: uuid.UUID) -> Any:
    """以租户身份进入：签发绑定该租户（`tid`）的短期模拟令牌（`imp`，有效期
    IMPERSONATION_EXPIRE_MINUTES）。模拟令牌只能访问该租户、不能调用平台接口；始终记入平台操作日志。"""
    t = _tenant_or_404(session, tenant_id)
    record_platform_audit(
        session,
        user,
        "tenant.enter",
        "tenant",
        t.id,
        t.id,
        {"slug": t.slug, "member": get_membership(session, t.id, user.id) is not None},
    )
    session.commit()
    return Token(
        access_token=security.create_access_token(
            user.id,
            expires_delta=timedelta(minutes=settings.IMPERSONATION_EXPIRE_MINUTES),
            tenant_id=t.id,
            impersonation=True,
        )
    )


@router.post("/tenants/{tenant_id}/exit", response_model=Message)
def exit_tenant(session: SessionDep, user: CurrentUser, tenant_id: uuid.UUID) -> Any:
    """退出租户模拟（前端恢复原令牌后调用），记入平台操作日志。"""
    t = _tenant_or_404(session, tenant_id)
    record_platform_audit(
        session, user, "tenant.exit", "tenant", t.id, t.id, {"slug": t.slug}
    )
    session.commit()
    return Message(message="ok")


# ---------------- notification channels ----------------
def _channel_items(session: SessionDep) -> dict[str, ConfigItem]:
    items = session.exec(
        select(ConfigItem).join(ConfigGroup).where(ConfigGroup.code == "notification")
    ).all()
    return {i.code: i for i in items}


@router.get("/notify-channels", response_model=ChannelsPublic)
def list_channels(session: SessionDep) -> Any:
    items = _channel_items(session)
    data = [
        ChannelPublic(
            code=c["code"],
            label=c["label"],
            enabled=(i := items.get(f"{c['code']}_enabled")) is None
            or i.value is not False,
        )
        for c in list_registered_channels()
    ]
    return ChannelsPublic(data=data, count=len(data))


@router.put("/notify-channels/{code}", response_model=ChannelPublic)
def set_channel(
    session: SessionDep, user: CurrentUser, code: str, body: ChannelUpdate
) -> Any:
    ch = next((c for c in list_registered_channels() if c["code"] == code), None)
    item = _channel_items(session).get(f"{code}_enabled")
    if not ch or not item:
        raise HTTPException(status_code=404, detail="Channel not found")
    item.value = body.enabled
    session.add(item)
    record_platform_audit(
        session,
        user,
        "channel.update",
        "channel",
        code,
        None,
        {"enabled": body.enabled},
    )
    session.commit()
    return ChannelPublic(code=code, label=ch["label"], enabled=body.enabled)


# ---------------- logs ----------------
@router.get("/login-log", response_model=LoginLogsPublic)
def list_login_log(
    session: SessionDep, params: ListParamsDep, success: bool | None = None
) -> Any:
    """Paginated; sort_by: created_at, email; q: email/ip; filter: success."""
    stmt = select(LoginLog)
    if success is not None:
        stmt = stmt.where(LoginLog.success == success)
    data, count = paginate(
        session,
        stmt,
        params,
        {"created_at": LoginLog.created_at, "email": LoginLog.email},
        ("created_at", "desc"),
        LoginLog.id,
        search=[LoginLog.email, LoginLog.ip],
    )
    return LoginLogsPublic(data=data, count=count)


@router.get("/ops-log", response_model=PlatformAuditsPublic)
def list_ops_log(
    session: SessionDep, params: ListParamsDep, action: str | None = None
) -> Any:
    """Platform op log. Paginated; sort_by: created_at, action; q: actor/action/target; filter: action."""
    stmt = select(PlatformAudit)
    if action:
        stmt = stmt.where(PlatformAudit.action == action)
    data, count = paginate(
        session,
        stmt,
        params,
        {"created_at": PlatformAudit.created_at, "action": PlatformAudit.action},
        ("created_at", "desc"),
        PlatformAudit.id,
        search=[
            PlatformAudit.actor_email,
            PlatformAudit.action,
            PlatformAudit.target_id,
        ],
    )
    return PlatformAuditsPublic(data=data, count=count)


@router.get("/audit", response_model=CrossTenantAudits)
def cross_tenant_audit(
    session: SessionDep,
    user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    q: str | None = None,
    tenant_id: uuid.UUID | None = None,
    action: str | None = None,
) -> Any:
    """Business audit log across tenants (newest first).

    RLS stays on: each tenant is read under its own explicit `set_tenant`, then the
    pages are merged. The read itself is recorded in the platform op log."""
    from app.core.spec.engine import TABLES

    t = TABLES["audit_log"]
    tenants = (
        [_tenant_or_404(session, tenant_id)]
        if tenant_id
        else list(session.exec(select(Tenant)).all())
    )
    names = {x.id: x.name for x in tenants}
    cond: list[Any] = []
    if q:
        like = f"%{q}%"
        cond.append(sa.or_(t.c.record_code.ilike(like), t.c.user_email.ilike(like)))
    if action:
        cond.append(t.c.action == action)
    need = page * page_size
    rows: list[Any] = []
    total = 0
    try:
        for x in tenants:
            set_tenant(session, x.id)
            conn = session.connection()
            total += conn.execute(
                sa.select(sa.func.count()).select_from(t).where(*cond)
            ).scalar_one()
            rows += (
                conn.execute(
                    sa.select(t)
                    .where(*cond)
                    .order_by(t.c.created_at.desc())
                    .limit(need)
                )
                .mappings()
                .all()
            )
    finally:
        set_tenant(session, None)
    rows.sort(key=lambda r: r["created_at"], reverse=True)
    out = [
        CrossTenantAudit(
            id=str(r["id"]),
            tenant_id=str(r["tenant_id"]),
            tenant_name=names.get(r["tenant_id"], ""),
            entity_type=r["entity_type"],
            action=r["action"],
            record_code=r["record_code"],
            user_email=r["user_email"],
            changes=r["changes"],
            created_at=r["created_at"],
        )
        for r in rows[need - page_size : need]
    ]
    record_platform_audit(
        session,
        user,
        "audit.cross_tenant_read",
        "audit_log",
        None,
        tenant_id,
        {"tenants": len(tenants), "page": page, "q": q},
    )
    session.commit()
    return CrossTenantAudits(data=out, count=total)
