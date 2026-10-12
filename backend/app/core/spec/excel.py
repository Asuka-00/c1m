"""xlsx export / import per entity (openpyxl).

Sheet layout: row 1 = column keys (field names, `version`/`status` for versioned
data, `attr:<code>` for custom attributes). References are written/read as the
target's code (`CODE` = active-or-latest version, `CODE@2` = exact version);
targets without a code use their id. Import upserts by the natural key and is
all-or-nothing.
"""

import io
import json
import uuid
from typing import Any

import sqlalchemy as sa
from fastapi import HTTPException
from openpyxl import Workbook, load_workbook
from sqlmodel import Session

from app.core.spec.engine import ENTITIES, Entity
from app.core.spec.service import (
    all_rows,
    attr_defs,
    conn,
    create_row,
    table,
    to_json,
    update_row,
)

MAX_ROWS = 5000


def _ref_code(
    session: Session, tenant_id: uuid.UUID, target: Entity, ids: set[Any]
) -> dict[Any, str]:
    if not ids:
        return {}
    t = table(target)
    if not target.has_code:
        return {i: str(i) for i in ids}
    cols = [t.c.id, t.c.code] + ([t.c.version] if target.versioned else [])
    out = {}
    for r in (
        conn(session)
        .execute(sa.select(*cols).where(t.c.tenant_id == tenant_id, t.c.id.in_(ids)))
        .mappings()
    ):
        out[r["id"]] = f"{r['code']}@{r['version']}" if target.versioned else r["code"]
    return out


def columns(session: Session, tenant_id: uuid.UUID, e: Entity) -> list[str]:
    cols = [f.name for f in e.all_fields]
    if e.versioned:
        cols += ["version", "status"]
    cols += [f"attr:{d['code']}" for d in attr_defs(session, tenant_id, e)]
    return cols


def export_xlsx(session: Session, tenant_id: uuid.UUID, e: Entity) -> bytes:
    rows = all_rows(session, e, tenant_id, MAX_ROWS)
    cols = columns(session, tenant_id, e)
    refs = {
        f.name: _ref_code(
            session,
            tenant_id,
            ENTITIES[f.ref or ""],
            {r[f.column] for r in rows if r[f.column]},
        )
        for f in e.all_fields
        if f.type == "ref"
    }
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = e.code[:31]
    ws.append(cols)
    for r in rows:
        line: list[Any] = []
        for c in cols:
            if c.startswith("attr:"):
                line.append((r.get("attrs") or {}).get(c[5:]))
                continue
            f = e.field(c)
            if f and f.type == "ref":
                line.append(refs[f.name].get(r[f.column]))
            elif f and f.type == "json":
                line.append(
                    json.dumps(r[f.column]) if r[f.column] is not None else None
                )
            else:
                v = r[f.column if f else c]
                line.append(to_json(v) if f and f.type in ("date", "time") else v)
        ws.append(line)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _resolve(session: Session, tenant_id: uuid.UUID, target: Entity, raw: str) -> Any:
    t = table(target)
    c = conn(session)
    if not target.has_code:
        try:
            return uuid.UUID(raw)
        except ValueError:
            return None
    code, _, ver = raw.partition("@")
    stmt = sa.select(t.c.id).where(t.c.tenant_id == tenant_id, t.c.code == code.strip())
    if target.versioned:
        if ver:
            stmt = stmt.where(t.c.version == int(ver))
        else:
            stmt = stmt.order_by(
                sa.case((t.c.status == "active", 0), else_=1), t.c.version.desc()
            )
    return c.execute(stmt.limit(1)).scalar()


def import_xlsx(
    session: Session, tenant_id: uuid.UUID, e: Entity, data: bytes, user: Any
) -> dict[str, int]:
    if e.readonly:
        raise HTTPException(status_code=405, detail="Read-only entity")
    try:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as ex:  # noqa: BLE001 - any parse error is a bad upload
        raise HTTPException(status_code=400, detail="Not a valid .xlsx file") from ex
    ws = wb.worksheets[0]
    it = ws.iter_rows(values_only=True)
    header = [str(h).strip() if h is not None else "" for h in next(it, ())]
    if not header or not any(header):
        raise HTTPException(status_code=400, detail="Empty sheet")
    known = set(columns(session, tenant_id, e)) | {""}
    unknown = [h for h in header if h not in known]
    if unknown:
        raise HTTPException(
            status_code=422, detail=f"Unknown columns: {', '.join(unknown)}"
        )
    errors: list[dict[str, Any]] = []
    created = updated = 0
    t = table(e)
    nested = session.begin_nested()
    for n, values in enumerate(it, start=2):
        if n > MAX_ROWS + 1:
            errors.append({"row": n, "msg": f"too many rows (max {MAX_ROWS})"})
            break
        raw = dict(zip(header, values, strict=False))
        if all(v in (None, "") for v in raw.values()):
            continue
        payload: dict[str, Any] = {}
        attrs: dict[str, Any] = {}
        try:
            for k, v in raw.items():
                if not k or k == "status":
                    continue
                if k.startswith("attr:"):
                    if v not in (None, ""):
                        attrs[k[5:]] = v
                    continue
                f = e.field(k)
                if f and f.type == "ref" and v not in (None, ""):
                    rid = _resolve(session, tenant_id, ENTITIES[f.ref or ""], str(v))
                    if rid is None:
                        raise ValueError(f"{k}: '{v}' not found")
                    payload[f.column] = rid
                elif f and f.type == "json" and isinstance(v, str) and v.strip():
                    payload[k] = json.loads(v)
                else:
                    payload[k] = v
            if attrs:
                payload["attrs"] = attrs
            key_cols = [
                (fld.column if (fld := e.field(k)) else k) for k in e.natural_key
            ]
            key_vals = [
                payload.get(c, payload.get(c.removesuffix("_id"))) for c in key_cols
            ]
            existing = None
            if all(v not in (None, "") for v in key_vals):
                stmt = sa.select(t.c.id).where(t.c.tenant_id == tenant_id)
                for c, v in zip(key_cols, key_vals, strict=True):
                    column: Any = t.c[c]
                    stmt = stmt.where(column == (int(str(v)) if c == "version" else v))
                existing = conn(session).execute(stmt).scalar()
            if existing:
                update_row(
                    session,
                    tenant_id,
                    e,
                    existing,
                    payload,
                    user,
                    commit=False,
                    action="import",
                )
                updated += 1
            else:
                create_row(session, tenant_id, e, payload, user, commit=False)
                created += 1
        except HTTPException as ex:
            d = ex.detail
            msg = (
                "; ".join(x.get("msg", "") for x in d)
                if isinstance(d, list)
                else str(d)
            )
            errors.append({"row": n, "msg": msg})
        except (ValueError, TypeError) as ex:
            errors.append({"row": n, "msg": str(ex)})
    if errors:
        nested.rollback()
        session.rollback()
        raise HTTPException(
            status_code=422, detail={"message": "Import failed", "errors": errors[:50]}
        )
    nested.commit()
    session.commit()
    return {"created": created, "updated": updated}
