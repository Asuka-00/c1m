"""Generic validation: field rules, custom attributes, CRUD validator registry, edit locks."""

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
    """API payload (field names, `<ref>_id` or `<ref>`) -> column values; 422 on error."""
    errors: list[tuple[str, str]] = []
    values: Row = {}
    for f in e.all_fields:
        key = f.column if f.column in data else f.name if f.name in data else None
        if key is None or f.system:
            continue
        try:
            values[f.column] = coerce(f, data[key])
        except (ValueError, TypeError) as ex:
            errors.append((f.name, f"{f.name}: {ex}"))
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
    for f in e.all_fields:
        if merged.get(f.column) not in (None, ""):
            continue
        if f.required:
            errors.append((f.name, f"{f.name}: required"))
        for k, allowed in (f.required_when or {}).items():
            cur = merged.get(by_name[k].column)
            active = cur not in (None, "") if "*" in allowed else cur in allowed
            if active:
                cond = "set" if "*" in allowed else str(cur)
                errors.append((f.name, f"{f.name}: required when {k} = {cond}"))
    # refs must exist in this tenant (RLS would hide others anyway)
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
        # no cycles: walk up from the new parent
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
        # validators may derive values (e.g. inherited equipment type)
        for k, v in merged.items():
            if before.get(k) != v:
                values[k] = v
    if errors:
        raise http_422(errors)
    return values


def attr_defs(session: Session, tenant_id: uuid.UUID, e: Entity) -> list[Row]:
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
    if d.get("dict_type_id"):
        return dict_values(session, tenant_id, d["dict_type_id"])
    return [o.strip() for o in (d.get("options") or "").split(",") if o.strip()]


def validate_attrs(
    session: Session, tenant_id: uuid.UUID, e: Entity, attrs: Any
) -> list[tuple[str, str]]:
    """Custom attribute values (row.attrs JSON) against the tenant's attr_defs."""
    if e.code in ("attr_def", "audit_log"):
        return []
    attrs = attrs or {}
    if not isinstance(attrs, dict):
        return [("attrs", "attrs: must be an object")]
    defs = {d["code"]: d for d in attr_defs(session, tenant_id, e)}
    errs: list[tuple[str, str]] = []
    for k in attrs:
        if k not in defs and not k.startswith("_"):  # "_x": system tags (demo)
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
    """Nearest versioned ancestor via cascade refs (e.g. step -> route)."""
    for f in e.all_fields:
        if f.type == "ref" and f.cascade and f.name != "parent" and row.get(f.column):
            pe = ENTITIES[f.ref or ""]
            prow = get_row(session, pe, tenant_id, row[f.column])
            if pe.versioned:
                return pe, prow
            return locking_parent(session, tenant_id, pe, prow)
    return None


def check_editable(session: Session, tenant_id: uuid.UUID, e: Entity, row: Row) -> None:
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
