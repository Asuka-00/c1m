"""通用校验：字段规则、自定义属性、CRUD 校验器注册表、编辑锁（版本锁定）。"""

import uuid
from collections.abc import Callable
from datetime import date
from typing import Any

import sqlalchemy as sa
from fastapi import HTTPException
from sqlmodel import Session

from app.core.spec.base import Row, Validator, conn, table
from app.core.spec.engine import (
    ENTITIES,
    TABLES,
    Entity,
)
from app.core.spec.errors import MesError, http_422
from app.core.spec.query import get_row
from app.core.spec.serialize import coerce

VALIDATORS: dict[str, list[Validator]] = {}


def validator(*codes: str) -> Callable[[Validator], Validator]:
    """注册实体的 CRUD 校验器（装饰器）。

    编码可带阶段后缀：``"route:activate"``（激活时）、``"work_order:prefill"``（预填）、
    ``"x:delete"``（删除前）。

    Args:
        *codes: 实体编码（可带后缀）。
    """

    def deco(fn: Validator) -> Validator:
        for c in codes:
            VALIDATORS.setdefault(c, []).append(fn)
        return fn

    return deco


# ---------------- validation ----------------
def validate(
    session: Session,
    tenant_id: uuid.UUID,
    e: Entity,
    data: Row,
    existing: Row | None,
) -> Row:
    """校验 API 载荷并转换为列值。

    接受字段名、``<ref>_id`` 或 ``<ref>``（编码）形式；检查必填、类型、枚举、引用存在、
    自定义属性，并运行已注册的实体校验器。

    Args:
        session: 数据库会话。
        tenant_id: 租户 id。
        e: 实体规格。
        data: 载荷。
        existing: 更新时的原行（新增为 None）。

    Returns:
        列值字典。

    Raises:
        HTTPException: 校验失败（422，字段错误列表）。
    """
    # 原始载荷校验器（在类型 / 枚举转换前，可直接抛 HTTPException 给出结构化错误）
    for fn in VALIDATORS.get(f"{e.code}:payload", []):
        fn(session, tenant_id, e, data, existing)
    errors: list[tuple[Any, ...]] = []
    values: Row = {}
    for f in e.all_fields:
        key = f.column if f.column in data else f.name if f.name in data else None
        if key is None or f.system:
            continue
        try:
            values[f.column] = coerce(f, data[key])
        except (ValueError, TypeError) as ex:
            code = getattr(ex, "code", None)
            ctx = getattr(ex, "ctx", None)
            errors.append(
                (f.name, f"{f.name}: {ex}", code, ctx)
                if ctx
                else (f.name, f"{f.name}: {ex}", code)
                if code
                else (f.name, f"{f.name}: {ex}")
            )
    if "attrs" in data:
        values["attrs"] = data["attrs"]
    merged = {**(existing or {}), **values}
    if existing is None:
        for f in e.all_fields:
            if merged.get(f.column) is None and f.default is not None:
                merged[f.column] = values[f.column] = f.default
    if not errors:
        before = dict(merged)
        for fn in VALIDATORS.get(f"{e.code}:prefill", []):
            try:
                fn(session, tenant_id, e, merged, existing)
            except MesError as ex:
                errors += ex.errors
        values.update({k: v for k, v in merged.items() if before.get(k) != v})
    for f in e.all_fields:
        if f.default_from and merged.get(f.column) in (None, ""):
            src = merged.get(f.default_from)
            if src not in (None, ""):
                merged[f.column] = values[f.column] = src
    by_name = {f.name: f for f in e.all_fields}
    bad_type = {x[0] for x in errors}
    for f in e.all_fields:
        if merged.get(f.column) not in (None, "") or f.name in bad_type:
            continue
        if f.required:
            errors.append((f.name, f"{f.name}: required"))
        for k, allowed in (f.required_when or {}).items():
            cur = merged.get(by_name[k].column)
            active = cur not in (None, "") if "*" in allowed else cur in allowed
            if active:
                cond = "set" if "*" in allowed else str(cur)
                errors.append((f.name, f"{f.name}: required when {k} = {cond}"))
    # 引用目标必须属于本租户（其他租户的行本来也被 RLS 隐藏）
    for f in e.all_fields:
        v = values.get(f.column)
        if f.type == "ref" and v is not None:
            tt = table(ENTITIES[f.ref or ""])
            hit = (
                conn(session)
                .execute(
                    sa.select(tt.c.id).where(tt.c.tenant_id == tenant_id, tt.c.id == v)
                )
                .first()
            )
            if not hit:
                errors.append((f.name, f"{f.name}: referenced record not found"))
    if e.tree and values.get("parent_id") is not None and existing is not None:
        # 禁止成环：从新的父节点向上遍历
        seen, cur = {existing["id"]}, values["parent_id"]
        t = table(e)
        while cur is not None:
            if cur in seen:
                errors.append(("parent", "parent: would create a cycle"))
                break
            seen.add(cur)
            cur = (
                conn(session)
                .execute(sa.select(t.c.parent_id).where(t.c.id == cur))
                .scalar()
            )
    errors += validate_attrs(session, tenant_id, e, merged.get("attrs"))
    if not errors:
        before = dict(merged)
        for fn in VALIDATORS.get(e.code, []):
            try:
                fn(session, tenant_id, e, merged, existing)
            except MesError as ex:
                errors += ex.errors
        # 校验器可推导字段值（如继承的设备类型）
        for k, v in merged.items():
            if before.get(k) != v:
                values[k] = v
    if errors:
        raise http_422(errors)
    return values


def attr_defs(session: Session, tenant_id: uuid.UUID, e: Entity) -> list[Row]:
    """租户为该实体定义的自定义属性。"""
    ad = ENTITIES.get("attr_def")
    if not ad or ad.code not in TABLES:
        return []
    t = table(ad)
    return [
        dict(r)
        for r in conn(session)
        .execute(
            sa.select(t)
            .where(t.c.tenant_id == tenant_id, t.c.entity_type == e.code)
            .order_by(t.c.sort_order, t.c.code)
        )
        .mappings()
    ]


def dict_values(session: Session, tenant_id: uuid.UUID, dict_type_id: Any) -> list[str]:
    """数据字典的有效取值。"""
    t = TABLES["dict_item"]
    return [
        r[0]
        for r in conn(session).execute(
            sa.select(t.c.code).where(
                t.c.tenant_id == tenant_id,
                t.c.dict_type_id == dict_type_id,
                t.c.is_active.is_not(False),
            )
        )
    ]


def attr_options(session: Session, tenant_id: uuid.UUID, d: Row) -> list[str]:
    """自定义属性的可选值（字典或固定选项）。"""
    if d.get("dict_type_id"):
        return dict_values(session, tenant_id, d["dict_type_id"])
    return [o.strip() for o in (d.get("options") or "").split(",") if o.strip()]


def validate_attrs(
    session: Session, tenant_id: uuid.UUID, e: Entity, attrs: Any
) -> list[tuple[str, str]]:
    """按租户自定义属性定义校验 ``row.attrs``，返回字段错误列表。"""
    if e.code in ("attr_def", "audit_log"):
        return []
    attrs = attrs or {}
    if not isinstance(attrs, dict):
        return [("attrs", "attrs: must be an object")]
    defs = {d["code"]: d for d in attr_defs(session, tenant_id, e)}
    errs: list[tuple[str, str]] = []
    for k in attrs:
        if k not in defs and not k.startswith("_"):  # "_x"：系统标记（如演示数据）
            errs.append((f"attrs.{k}", f"attrs.{k}: unknown attribute"))
    for code, d in defs.items():
        v = attrs.get(code)
        if v in (None, ""):
            if d["required"]:
                errs.append((f"attrs.{code}", f"{d['name']}: required"))
            continue
        ok = True
        match d["data_type"]:
            case "number":
                ok = isinstance(v, int | float) and not isinstance(v, bool)
            case "boolean":
                ok = isinstance(v, bool)
            case "date":
                try:
                    date.fromisoformat(str(v))
                except ValueError:
                    ok = False
            case "select":
                ok = str(v) in attr_options(session, tenant_id, d)
            case _:
                ok = isinstance(v, str) and len(v) <= 500
        if not ok:
            errs.append(
                (f"attrs.{code}", f"{d['name']}: invalid {d['data_type']} value")
            )
    return errs


# ---------------- versioning / locks ----------------
def locking_parent(
    session: Session, tenant_id: uuid.UUID, e: Entity, row: Row
) -> tuple[Entity, Row] | None:
    """沿级联引用找到最近的版本化祖先（如 工步 → 路线），无则 None。"""
    for f in e.all_fields:
        if f.type == "ref" and f.cascade and f.name != "parent" and row.get(f.column):
            pe = ENTITIES[f.ref or ""]
            prow = get_row(session, pe, tenant_id, row[f.column])
            if pe.versioned:
                return pe, prow
            return locking_parent(session, tenant_id, pe, prow)
    return None


def check_editable(session: Session, tenant_id: uuid.UUID, e: Entity, row: Row) -> None:
    """检查行是否可编辑。

    版本化数据仅 draft 可改；子表随其版本化祖先锁定。

    Raises:
        HTTPException: 已激活 / 停用的版本不可修改（409）。
    """
    if e.readonly:
        raise HTTPException(status_code=405, detail="Read-only entity")
    if e.versioned and row.get("status", "draft") != "draft":
        raise HTTPException(
            status_code=409,
            detail="Only draft versions can be changed; create a new version",
        )
    lp = locking_parent(session, tenant_id, e, row)
    if lp and lp[1]["status"] != "draft":
        raise HTTPException(
            status_code=409,
            detail=f"Parent {lp[0].code} {lp[1].get('code', '')} v{lp[1]['version']} is not a draft",
        )
