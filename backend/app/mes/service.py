"""Generic CRUD / tree / versioning / audit / custom attributes for MES entities.

Everything runs on the request Session's connection, so the tenant RLS context
(``app.current_tenant``) applies to every statement; queries additionally filter
by ``tenant_id`` (app-layer isolation).
"""

import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime, time
from typing import Any

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.mes.core import (
    ENTITIES,
    ENUMS,
    STATUS_TRANSITIONS,
    STATUSES,
    TABLES,
    Entity,
    F,
)

Row = dict[str, Any]
Validator = Callable[[Session, uuid.UUID, Entity, Row, Row | None], None]
VALIDATORS: dict[str, list[Validator]] = {}
SYSTEM_COLS = {"created_at", "updated_at", "created_by", "updated_by"}


class MesError(Exception):
    def __init__(self, errors: list[tuple[str, str]]) -> None:
        super().__init__("; ".join(m for _, m in errors))
        self.errors = errors


def http_422(errors: list[tuple[str, str]]) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail=[
            {"loc": ["body", f], "msg": m, "type": "value_error"} for f, m in errors
        ],
    )


def validator(*codes: str) -> Callable[[Validator], Validator]:
    def deco(fn: Validator) -> Validator:
        for c in codes:
            VALIDATORS.setdefault(c, []).append(fn)
        return fn

    return deco


def get_entity(code: str, *, api: bool = True) -> Entity:
    e = ENTITIES.get(code.replace("-", "_"))
    if not e or (api and e.internal):
        raise HTTPException(status_code=404, detail="Unknown entity")
    return e


def now() -> datetime:
    return datetime.now(UTC)


def table(e: Entity) -> sa.Table:
    return TABLES[e.code]


def conn(session: Session) -> sa.Connection:
    return session.connection()


# ---------------- (de)serialization ----------------
def to_json(v: Any) -> Any:
    if isinstance(v, uuid.UUID):
        return str(v)
    if isinstance(v, datetime | date | time):
        return v.isoformat()
    return v


def coerce(f: F, v: Any) -> Any:
    """Raw JSON/xlsx value -> python value for column `f` (raises ValueError)."""
    if v is None or (isinstance(v, str) and v.strip() == "" and f.type != "json"):
        return None
    match f.type:
        case "str" | "text":
            s = str(v).strip() if f.type == "str" else str(v)
            if f.type == "str" and len(s) > f.max_length:
                raise ValueError(f"at most {f.max_length} characters")
            return s
        case "int":
            if isinstance(v, bool) or (isinstance(v, float) and not v.is_integer()):
                raise ValueError("must be an integer")
            return int(v)
        case "float":
            if isinstance(v, bool):
                raise ValueError("must be a number")
            return float(v)
        case "bool":
            if isinstance(v, bool):
                return v
            if str(v).lower() in ("true", "1", "yes", "y"):
                return True
            if str(v).lower() in ("false", "0", "no", "n"):
                return False
            raise ValueError("must be true/false")
        case "enum":
            allowed = [k for k, _ in ENUMS[f.enum or ""]]
            if str(v) not in allowed:
                raise ValueError(f"must be one of: {', '.join(allowed)}")
            return str(v)
        case "date":
            if isinstance(v, datetime):
                return v.date()
            return v if isinstance(v, date) else date.fromisoformat(str(v)[:10])
        case "time":
            if isinstance(v, datetime):
                return v.time()
            return v if isinstance(v, time) else time.fromisoformat(str(v))
        case "ref":
            return v if isinstance(v, uuid.UUID) else uuid.UUID(str(v))
        case "json":
            return v
    return v


def ref_labels(
    session: Session, tenant_id: uuid.UUID, target: Entity, ids: set[Any]
) -> dict[Any, str]:
    if not ids:
        return {}
    t = table(target)
    cols = [t.c.id, t.c[target.label_field if target.label_field in t.c else "id"]]
    if target.has_code:
        cols.append(t.c.name)
    if target.versioned:
        cols.append(t.c.version)
    extra = target.field(target.label_ref) if target.label_ref else None
    if extra:
        cols.append(t.c[extra.column])
    rows = list(
        conn(session)
        .execute(sa.select(*cols).where(t.c.tenant_id == tenant_id, t.c.id.in_(ids)))
        .mappings()
    )
    extra_codes: dict[Any, str] = {}
    if extra:
        et = table(ENTITIES[extra.ref or ""])
        eids = {r[extra.column] for r in rows if r[extra.column]}
        if eids:
            extra_codes = {
                x["id"]: x["code"]
                for x in conn(session)
                .execute(sa.select(et.c.id, et.c.code).where(et.c.id.in_(eids)))
                .mappings()
            }
    out: dict[Any, str] = {}
    for r in rows:
        lbl = str(to_json(r[cols[1].name]))
        if extra and r[extra.column] in extra_codes:
            lbl += f" · {extra_codes[r[extra.column]]}"
        if target.versioned:
            lbl += f" v{r['version']}"
        if target.has_code and r["name"] and target.label_field == "code":
            lbl += f" · {r['name']}"
        out[r["id"]] = lbl
    return out


def serialize(
    session: Session, tenant_id: uuid.UUID, e: Entity, rows: list[Row]
) -> list[Row]:
    out = [{k: to_json(v) for k, v in r.items() if k != "tenant_id"} for r in rows]
    for f in e.all_fields:
        if f.type != "ref":
            continue
        target = ENTITIES[f.ref or ""]
        labels = ref_labels(
            session, tenant_id, target, {r[f.column] for r in rows if r[f.column]}
        )
        for src, dst in zip(rows, out, strict=True):
            dst[f"{f.name}_label"] = labels.get(src[f.column])
    return out


# ---------------- queries ----------------
def sortable(e: Entity) -> dict[str, Any]:
    t = table(e)
    out = {
        f.name: t.c[f.column]
        for f in e.all_fields
        if f.type not in ("json", "ref", "text")
    }
    for c in ("created_at", "updated_at", "version", "status"):
        if c in t.c:
            out[c] = t.c[c]
    return out


def base_select(e: Entity, tenant_id: uuid.UUID) -> sa.Select[Any]:
    t = table(e)
    return sa.select(t).where(t.c.tenant_id == tenant_id)


def apply_filters(
    e: Entity, stmt: sa.Select[Any], filters: dict[str, str]
) -> sa.Select[Any]:
    t = table(e)
    for name, raw in filters.items():
        if name == "status" and e.versioned:
            stmt = stmt.where(t.c.status == raw)
            continue
        f = e.field(name) or next((x for x in e.all_fields if x.column == name), None)
        if not f or f.type in ("json", "text"):
            continue
        if f.type == "ref" and raw == "null":
            stmt = stmt.where(t.c[f.column].is_(None))
            continue
        try:
            v = coerce(f, raw)
        except ValueError as ex:
            raise http_422([(name, f"{name} {ex}")]) from ex
        stmt = stmt.where(t.c[f.column] == v)
    return stmt


def search(e: Entity, stmt: sa.Select[Any], q: str | None) -> sa.Select[Any]:
    if not q:
        return stmt
    t = table(e)
    esc = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    cols = [t.c[f.column] for f in e.all_fields if f.search]
    if not cols:
        return stmt
    return stmt.where(sa.or_(*(c.ilike(f"%{esc}%", escape="\\") for c in cols)))


def list_rows(
    session: Session,
    e: Entity,
    tenant_id: uuid.UUID,
    *,
    q: str | None,
    filters: dict[str, str],
    sort_by: str | None,
    sort_order: str,
    offset: int,
    limit: int,
) -> tuple[list[Row], int]:
    t = table(e)
    stmt = search(e, apply_filters(e, base_select(e, tenant_id), filters), q)
    c = conn(session)
    count = c.execute(
        sa.select(sa.func.count()).select_from(stmt.subquery())
    ).scalar_one()
    cols = sortable(e)
    key = sort_by or e.sort_default
    if key not in cols:
        raise HTTPException(
            status_code=422, detail=f"sort_by must be one of: {', '.join(sorted(cols))}"
        )
    order = sort_order if sort_by else ("desc" if key in ("created_at",) else "asc")
    col = cols[key]
    stmt = stmt.order_by(
        col.desc().nulls_last() if order == "desc" else col.asc().nulls_last(),
        *([t.c.version] if e.versioned else []),
        t.c.id,
    )
    rows = [dict(r) for r in c.execute(stmt.offset(offset).limit(limit)).mappings()]
    return rows, int(count)


def get_row(session: Session, e: Entity, tenant_id: uuid.UUID, rid: uuid.UUID) -> Row:
    t = table(e)
    r = (
        conn(session)
        .execute(base_select(e, tenant_id).where(t.c.id == rid))
        .mappings()
        .first()
    )
    if not r:
        raise HTTPException(status_code=404, detail="Record not found")
    return dict(r)


def all_rows(
    session: Session, e: Entity, tenant_id: uuid.UUID, limit: int = 5000
) -> list[Row]:
    t = table(e)
    stmt = base_select(e, tenant_id).order_by(
        t.c[sortable(e).get(e.sort_default, t.c.id).name], t.c.id
    )
    return [dict(r) for r in conn(session).execute(stmt.limit(limit)).mappings()]


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
        if key is None:
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
    for f in e.all_fields:
        if f.required and merged.get(f.column) in (None, ""):
            errors.append((f.name, f"{f.name}: required"))
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
        for fn in VALIDATORS.get(e.code, []):
            try:
                fn(session, tenant_id, e, merged, existing)
            except MesError as ex:
                errors += ex.errors
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


# ---------------- audit ----------------
def audit(
    session: Session,
    tenant_id: uuid.UUID,
    e: Entity,
    action: str,
    row: Row,
    user: Any,
    changes: Row | None = None,
) -> None:
    if e.code == "audit_log":
        return
    code = row.get("code") or row.get(e.label_field) or row.get("id")
    if e.versioned:
        code = f"{code} v{row.get('version')}"
    conn(session).execute(
        sa.insert(TABLES["audit_log"]).values(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            entity_type=e.code,
            action=action,
            record_id=str(row.get("id")),
            record_code=str(to_json(code))[:200],
            changes={
                k: [to_json(a), to_json(b)] for k, (a, b) in (changes or {}).items()
            },
            user_email=getattr(user, "email", None),
            created_at=now(),
            created_by=getattr(user, "id", None),
        )
    )


def diff(old: Row | None, new: Row) -> Row:
    return {
        k: (None if old is None else old.get(k), v)
        for k, v in new.items()
        if k not in SYSTEM_COLS and k != "id" and (old is None or old.get(k) != v)
    }


def integrity(ex: IntegrityError) -> HTTPException:
    msg = str(ex.orig)
    if "unique" in msg.lower() or "duplicate" in msg.lower():
        return HTTPException(
            status_code=409, detail="A record with the same key already exists"
        )
    if "foreign key" in msg.lower():
        return HTTPException(
            status_code=409, detail="Record is referenced by other records"
        )
    return HTTPException(status_code=409, detail="Constraint violation")


# ---------------- writes ----------------
def create_row(
    session: Session,
    tenant_id: uuid.UUID,
    e: Entity,
    data: Row,
    user: Any,
    *,
    commit: bool = True,
) -> Row:
    if e.readonly:
        raise HTTPException(status_code=405, detail="Read-only entity")
    values = validate(session, tenant_id, e, data, None)
    lp = locking_parent(session, tenant_id, e, values)
    if lp and lp[1]["status"] != "draft":
        raise HTTPException(
            status_code=409, detail=f"Parent {lp[0].code} is not a draft"
        )
    rid = uuid.uuid4()
    values.update(
        id=rid,
        tenant_id=tenant_id,
        created_at=now(),
        updated_at=now(),
        created_by=getattr(user, "id", None),
        updated_by=getattr(user, "id", None),
    )
    if e.versioned:
        values["version"] = (
            int(data["version"])
            if data.get("version")
            else _next_version(session, tenant_id, e, values.get("code"))
        )
        values["status"] = "draft"
    try:
        with session.begin_nested():
            conn(session).execute(sa.insert(table(e)).values(**values))
    except IntegrityError as ex:
        raise integrity(ex) from ex
    row = get_row(session, e, tenant_id, rid)
    audit(
        session,
        tenant_id,
        e,
        "create",
        row,
        user,
        diff(None, {k: v for k, v in row.items() if k != "tenant_id"}),
    )
    if commit:
        session.commit()
    return row


def update_row(
    session: Session,
    tenant_id: uuid.UUID,
    e: Entity,
    rid: uuid.UUID,
    data: Row,
    user: Any,
    *,
    commit: bool = True,
    action: str = "update",
) -> Row:
    old = get_row(session, e, tenant_id, rid)
    check_editable(session, tenant_id, e, old)
    values = validate(session, tenant_id, e, data, old)
    if not values:
        return old
    values.update(updated_at=now(), updated_by=getattr(user, "id", None))
    t = table(e)
    try:
        with session.begin_nested():
            conn(session).execute(
                sa.update(t)
                .where(t.c.id == rid, t.c.tenant_id == tenant_id)
                .values(**values)
            )
    except IntegrityError as ex:
        raise integrity(ex) from ex
    new = get_row(session, e, tenant_id, rid)
    audit(
        session, tenant_id, e, action, new, user, diff(old, {k: new[k] for k in values})
    )
    if commit:
        session.commit()
    return new


def delete_row(
    session: Session, tenant_id: uuid.UUID, e: Entity, rid: uuid.UUID, user: Any
) -> None:
    old = get_row(session, e, tenant_id, rid)
    check_editable(session, tenant_id, e, old)
    t = table(e)
    try:
        with session.begin_nested():
            conn(session).execute(
                sa.delete(t).where(t.c.id == rid, t.c.tenant_id == tenant_id)
            )
    except IntegrityError as ex:
        raise integrity(ex) from ex
    audit(session, tenant_id, e, "delete", old, user)
    session.commit()


def _next_version(session: Session, tenant_id: uuid.UUID, e: Entity, code: Any) -> int:
    t = table(e)
    cur = (
        conn(session)
        .execute(
            sa.select(sa.func.max(t.c.version)).where(
                t.c.tenant_id == tenant_id, t.c.code == code
            )
        )
        .scalar()
    )
    return int(cur or 0) + 1


def set_status(
    session: Session,
    tenant_id: uuid.UUID,
    e: Entity,
    rid: uuid.UUID,
    status: str,
    user: Any,
) -> Row:
    if not e.versioned:
        raise HTTPException(status_code=404, detail="Entity is not versioned")
    if status not in STATUSES:
        raise http_422([("status", f"status must be one of: {', '.join(STATUSES)}")])
    old = get_row(session, e, tenant_id, rid)
    if status not in STATUS_TRANSITIONS[old["status"]]:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot change status from {old['status']} to {status}",
        )
    t = table(e)
    c = conn(session)
    if status == "active":
        for fn in VALIDATORS.get(f"{e.code}:activate", []):
            try:
                fn(session, tenant_id, e, old, old)
            except MesError as ex:
                raise http_422(ex.errors) from ex
        # one active version per code
        for r in c.execute(
            sa.select(t.c.id, t.c.version).where(
                t.c.tenant_id == tenant_id,
                t.c.code == old["code"],
                t.c.status == "active",
                t.c.id != rid,
            )
        ).mappings():
            c.execute(
                sa.update(t)
                .where(t.c.id == r["id"])
                .values(status="inactive", updated_at=now())
            )
            audit(
                session,
                tenant_id,
                e,
                "status",
                {**old, "id": r["id"], "version": r["version"]},
                user,
                {"status": ("active", "inactive")},
            )
    c.execute(
        sa.update(t)
        .where(t.c.id == rid)
        .values(status=status, updated_at=now(), updated_by=getattr(user, "id", None))
    )
    new = get_row(session, e, tenant_id, rid)
    audit(
        session, tenant_id, e, "status", new, user, {"status": (old["status"], status)}
    )
    session.commit()
    return new


def _copy_children(
    session: Session,
    tenant_id: uuid.UUID,
    e: Entity,
    old_id: Any,
    new_id: Any,
    user: Any,
) -> None:
    c = conn(session)
    for ce in ENTITIES.values():
        for f in ce.all_fields:
            if f.type == "ref" and f.cascade and f.ref == e.code and f.name != "parent":
                ct = table(ce)
                for r in c.execute(
                    sa.select(ct).where(
                        ct.c.tenant_id == tenant_id, ct.c[f.column] == old_id
                    )
                ).mappings():
                    nid = uuid.uuid4()
                    vals = {
                        **dict(r),
                        "id": nid,
                        f.column: new_id,
                        "created_at": now(),
                        "updated_at": now(),
                        "created_by": getattr(user, "id", None),
                    }
                    c.execute(sa.insert(ct).values(**vals))
                    _copy_children(session, tenant_id, ce, r["id"], nid, user)


def new_version(
    session: Session, tenant_id: uuid.UUID, e: Entity, rid: uuid.UUID, user: Any
) -> Row:
    """Copy a version (with its child rows) as the next draft version."""
    if not e.versioned:
        raise HTTPException(status_code=404, detail="Entity is not versioned")
    old = get_row(session, e, tenant_id, rid)
    nid = uuid.uuid4()
    vals = {
        **old,
        "id": nid,
        "version": _next_version(session, tenant_id, e, old["code"]),
        "status": "draft",
        "created_at": now(),
        "updated_at": now(),
        "created_by": getattr(user, "id", None),
        "updated_by": getattr(user, "id", None),
    }
    conn(session).execute(sa.insert(table(e)).values(**vals))
    _copy_children(session, tenant_id, e, rid, nid, user)
    new = get_row(session, e, tenant_id, nid)
    audit(
        session,
        tenant_id,
        e,
        "new_version",
        new,
        user,
        {"version": (old["version"], new["version"])},
    )
    session.commit()
    return new


def tree(session: Session, tenant_id: uuid.UUID, e: Entity) -> list[Row]:
    if not e.tree:
        raise HTTPException(status_code=404, detail="Entity is not hierarchical")
    rows = serialize(session, tenant_id, e, all_rows(session, e, tenant_id))
    by_parent: dict[Any, list[Row]] = {}
    for r in rows:
        by_parent.setdefault(r.get("parent_id"), []).append(r)

    def build(pid: Any) -> list[Row]:
        return [{**r, "children": build(r["id"])} for r in by_parent.get(pid, [])]

    return build(None)
