"""系统配置接口：平台默认值、租户覆盖值、公开品牌配置。"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, col, select

from app.core.deps import SessionDep
from app.core.tenant import set_tenant
from app.platform.auth.deps import (
    CurrentTenant,
    CurrentUser,
    platform_api_router,
    require_permissions,
    resolve_tenant,
)
from app.platform.config.models import ConfigGroup, ConfigItem, TenantConfigValue
from app.platform.config.schemas import (
    ConfigGroupPublic,
    ConfigGroupsPublic,
    ConfigGroupUpdate,
    ConfigItemPublic,
)
from app.platform.config.service import ConfigValidationError, validate_value
from app.platform.console.service import record_platform_audit
from app.platform.files.models import UploadedFile
from app.platform.files.service import FILE_PREFIX, release_values
from app.platform.tenants.models import Tenant
from app.platform.tenants.service import TenantContext

router = APIRouter(tags=["config"])


# ---------------- helpers ----------------
def _groups(session: Session) -> list[ConfigGroup]:
    return list(
        session.exec(select(ConfigGroup).order_by(col(ConfigGroup.sort_order))).all()
    )


def _get_group(session: Session, code: str) -> ConfigGroup:
    g = session.exec(select(ConfigGroup).where(ConfigGroup.code == code)).first()
    if not g:
        raise HTTPException(status_code=404, detail="Config group not found")
    return g


def platform_value(item: ConfigItem) -> Any:
    """配置项的平台值（未设置时回退默认值）。"""
    return item.value if item.value is not None else item.default_value


def _overrides(
    session: Session, tenant_id: uuid.UUID
) -> dict[uuid.UUID, TenantConfigValue]:
    """Tenant overrides (RLS context must be the tenant; the WHERE is the app filter)."""
    rows = session.exec(
        select(TenantConfigValue).where(TenantConfigValue.tenant_id == tenant_id)
    ).all()
    return {r.item_id: r for r in rows}


def _check_file(
    session: Session, item: ConfigItem, value: Any, tenant_id: uuid.UUID | None
) -> None:
    """image/file values pointing at our uploads must belong to the same owner
    (the tenant itself, or the platform)."""
    if item.value_type not in ("image", "file") or not isinstance(value, str):
        return
    if not value.startswith(FILE_PREFIX):
        return
    try:
        fid = uuid.UUID(value.removeprefix(FILE_PREFIX))
    except ValueError:
        raise ConfigValidationError("is not a valid file reference")
    f = session.get(UploadedFile, fid)
    if not f or (f.tenant_id is not None and f.tenant_id != tenant_id):
        raise ConfigValidationError("refers to a file you do not own")


def _apply(
    session: Session,
    group: ConfigGroup,
    values: dict[str, Any],
    tenant_id: uuid.UUID | None,
) -> list[tuple[ConfigItem, Any]]:
    """Validate all values first (all-or-nothing); 422 lists every failing item."""
    items = {i.code: i for i in group.items}
    errors: list[dict[str, Any]] = []
    out: list[tuple[ConfigItem, Any]] = []
    for code, raw in values.items():
        item = items.get(code)
        if not item:
            errors.append({"loc": ["values", code], "msg": "unknown config item"})
            continue
        if tenant_id is not None and not item.tenant_overridable:
            errors.append(
                {"loc": ["values", code], "msg": "cannot be overridden by a tenant"}
            )
            continue
        try:
            if raw is None:
                out.append((item, None))  # 重置
                continue
            v = validate_value(item, raw)
            _check_file(session, item, v, tenant_id)
            out.append((item, v))
        except ConfigValidationError as e:
            errors.append({"loc": ["values", code], "msg": f"{item.name} {e}"})
    if errors:
        raise HTTPException(status_code=422, detail=errors)
    return out


def _item_public(
    item: ConfigItem, ov: TenantConfigValue | None = None, tenant: bool = False
) -> ConfigItemPublic:
    pv = platform_value(item)
    return ConfigItemPublic.model_validate(
        item,
        update={
            "value": ov.value if ov is not None else pv,
            "platform_value": pv if tenant else None,
            "overridden": ov is not None,
        },
    )


# ---------------- platform defaults ----------------
@router.get(
    "/config/groups",
    dependencies=[Depends(require_permissions("config:read"))],
    response_model=ConfigGroupsPublic,
)
def list_platform_config(session: SessionDep) -> Any:
    """Platform-level values (= defaults inherited by every tenant)."""
    groups = _groups(session)
    data = [
        ConfigGroupPublic.model_validate(
            g, update={"items": [_item_public(i) for i in g.items]}
        )
        for g in groups
    ]
    return ConfigGroupsPublic(data=data, count=len(data))


@router.patch(
    "/config/groups/{code}",
    dependencies=[Depends(require_permissions("config:write"))],
    response_model=ConfigGroupPublic,
)
def update_platform_config(
    session: SessionDep, code: str, body: ConfigGroupUpdate
) -> Any:
    """Bulk-update platform values of a group; `null` resets an item to its default."""
    group = _get_group(session, code)
    old: list[Any] = []
    for item, value in _apply(session, group, body.values, None):
        old.append(item.value)
        item.value = item.default_value if value is None else value
        session.add(item)
    session.commit()
    release_values(session, old, None)  # 回收被替换 / 删除的上传文件
    session.refresh(group)
    return ConfigGroupPublic.model_validate(
        group, update={"items": [_item_public(i) for i in group.items]}
    )


# ---------------- tenant overrides ----------------
def _tenant_ctx(*codes: str):  # type: ignore[no-untyped-def]
    def dep(ctx: CurrentTenant) -> TenantContext:
        if not ctx.can(*codes):
            raise HTTPException(status_code=403, detail="Not enough permissions")
        return ctx

    return Depends(dep)


TenantConfigReader = Annotated[TenantContext, _tenant_ctx("config:read")]
TenantConfigWriter = Annotated[TenantContext, _tenant_ctx("config:write")]


def _tenant_groups(session: Session, tenant_id: uuid.UUID) -> list[ConfigGroupPublic]:
    ovs = _overrides(session, tenant_id)
    out = []
    for g in _groups(session):
        items = [
            _item_public(i, ovs.get(i.id), tenant=True)
            for i in g.items
            if i.tenant_overridable
        ]
        if items:
            out.append(ConfigGroupPublic.model_validate(g, update={"items": items}))
    return out


@router.get("/tenants/current/config", response_model=ConfigGroupsPublic)
def get_tenant_config(session: SessionDep, ctx: TenantConfigReader) -> Any:
    """Effective config of the current tenant (X-Tenant-ID): overridable items with
    `value` (effective), `platform_value` (inherited) and `overridden`."""
    data = _tenant_groups(session, ctx.id)
    return ConfigGroupsPublic(data=data, count=len(data))


@router.patch("/tenants/current/config/{code}", response_model=ConfigGroupPublic)
def update_tenant_config(
    session: SessionDep, ctx: TenantConfigWriter, code: str, body: ConfigGroupUpdate
) -> Any:
    """Set tenant overrides for a group; `null` removes the override (inherit again)."""
    group = _get_group(session, code)
    changes = _apply(session, group, body.values, ctx.id)
    ovs = _overrides(session, ctx.id)
    set_tenant(session, ctx.id)  # 插入需要 RLS 的 WITH CHECK 租户上下文
    old: list[Any] = []
    for item, value in changes:
        ov = ovs.get(item.id)
        if ov:
            old.append(ov.value)
        if value is None:
            if ov:
                session.delete(ov)
        elif ov:
            ov.value = value
            session.add(ov)
        else:
            session.add(
                TenantConfigValue(tenant_id=ctx.id, item_id=item.id, value=value)
            )
    session.commit()
    release_values(session, old, ctx.id)  # 回收被替换 / 删除 / 重置的上传文件
    return next(
        (g for g in _tenant_groups(session, ctx.id) if g.code == code),
        ConfigGroupPublic.model_validate(group, update={"items": []}),
    )


@router.delete(
    "/tenants/current/config/{code}/{item_code}", response_model=ConfigGroupPublic
)
def reset_tenant_config_item(
    session: SessionDep, ctx: TenantConfigWriter, code: str, item_code: str
) -> Any:
    """Reset one item to the platform value (delete the tenant override)."""
    return update_tenant_config(
        session, ctx, code, ConfigGroupUpdate(values={item_code: None})
    )


# ---------------- public ----------------
@router.get("/config/public", response_model=dict[str, dict[str, Any]])
def public_config(
    session: SessionDep, tenant: Annotated[str | None, Query(max_length=100)] = None
) -> Any:
    """Unauthenticated: effective `is_public` values by group (branding for the
    sign-in page). `?tenant=<slug>` applies that tenant's overrides; unknown or
    inactive slugs silently get the platform defaults (no existence oracle)."""
    ovs: dict[uuid.UUID, TenantConfigValue] = {}
    if tenant:
        t = session.exec(select(Tenant).where(Tenant.slug == tenant)).first()
        if t and t.status == "active":
            set_tenant(session, t.id)
            ovs = _overrides(session, t.id)
    out: dict[str, dict[str, Any]] = {}
    for g in _groups(session):
        vals = {
            i.code: (ovs[i.id].value if i.id in ovs else platform_value(i))
            for i in g.items
            if i.is_public
        }
        if vals:
            out[g.code] = vals
    return out


# ---------------- platform space (superuser only) ----------------
# 平台控制台：平台默认值（与 /config/groups 同一实现）与任意租户的品牌覆盖。
# 租户覆盖表受 RLS 保护：显式 resolve_tenant 进入目标租户，写操作记入平台操作日志。
platform_router = platform_api_router()


@platform_router.get("/config/groups", response_model=ConfigGroupsPublic)
def platform_list_defaults(session: SessionDep) -> Any:
    """Platform defaults inherited by every tenant."""
    return list_platform_config(session)


@platform_router.patch("/config/groups/{code}", response_model=ConfigGroupPublic)
def platform_update_defaults(
    session: SessionDep, user: CurrentUser, code: str, body: ConfigGroupUpdate
) -> Any:
    record_platform_audit(
        session,
        user,
        "config.update",
        "config",
        code,
        None,
        {"items": sorted(body.values)},
    )
    return update_platform_config(session, code, body)


def _platform_tenant(
    session: SessionDep, user: CurrentUser, tenant_id: uuid.UUID
) -> TenantContext:
    if not session.get(Tenant, tenant_id):
        raise HTTPException(status_code=404, detail="Tenant not found")
    return resolve_tenant(session, user, tenant_id)


@platform_router.get("/tenants/{tenant_id}/branding", response_model=ConfigGroupsPublic)
def platform_get_branding(
    session: SessionDep, user: CurrentUser, tenant_id: uuid.UUID
) -> Any:
    """Tenant-overridable config (branding) of any tenant."""
    return get_tenant_config(session, _platform_tenant(session, user, tenant_id))


@platform_router.patch(
    "/tenants/{tenant_id}/branding/{code}", response_model=ConfigGroupPublic
)
def platform_update_branding(
    session: SessionDep,
    user: CurrentUser,
    tenant_id: uuid.UUID,
    code: str,
    body: ConfigGroupUpdate,
) -> Any:
    """Set / reset (null) branding overrides of any tenant."""
    ctx = _platform_tenant(session, user, tenant_id)
    record_platform_audit(
        session,
        user,
        "tenant.branding",
        "config",
        code,
        tenant_id,
        {"items": sorted(body.values)},
    )
    return update_tenant_config(session, ctx, code, body)
