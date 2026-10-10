"""Small, clearly-marked demo dataset (default tenant). Every row carries
``attrs._demo = true`` and demo codes/names mention DEMO where visible.

    uv run python scripts/mes_demo.py seed     # idempotent
    uv run python scripts/mes_demo.py remove
"""

import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.mes.core import ENTITIES, TABLES
from app.mes.service import coerce, conn, create_row, set_status
from app.models import Tenant, User
from app.tenancy import set_tenant

Ref = tuple[str, str]  # (entity, natural key "CODE" / "CODE@v")
DEMO: list[tuple[str, dict[str, Any]]] = []
ACTIVATE: list[Ref] = []


def add(entity: str, **values: Any) -> None:
    DEMO.append((entity, values))


# ---------------- P1: common + org ----------------
add("dict_type", code="WAFER_GRADE", name="Wafer grade (DEMO)")
for i, (c, n) in enumerate([("PRIME", "Prime"), ("TEST", "Test"), ("MON", "Monitor")]):
    add(
        "dict_item",
        dict_type=("dict_type", "WAFER_GRADE"),
        code=c,
        name=n,
        sort_order=i,
    )
add(
    "code_rule",
    code="LOT_ID",
    name="Production lot ID (DEMO)",
    target="lot",
    pattern="DM{YY}{MM}{SEQ}",
    seq_width=4,
    seq_reset="monthly",
)
add(
    "code_rule",
    code="WAFER_ID",
    name="Wafer ID (DEMO)",
    target="wafer",
    pattern="{LOT}.{SLOT:2}",
    seq_width=2,
)
add(
    "code_rule",
    code="FOUP_ID",
    name="FOUP ID (DEMO)",
    target="carrier",
    pattern="FP{SEQ36}",
    seq_width=4,
)
add(
    "attr_def",
    entity_type="site",
    code="cleanroom_class",
    name="Clean room class",
    data_type="select",
    options="ISO 3,ISO 4,ISO 5",
)
add(
    "site",
    code="FAB12",
    name="Fab 12 (DEMO)",
    timezone="Asia/Taipei",
    address="Hsinchu Science Park",
    attrs={"cleanroom_class": "ISO 4"},
)
add("site", code="TEST1", name="Test house 1 (DEMO)", timezone="Asia/Taipei")
for c, n, tp in [
    ("PHOTO", "Photolithography", "fab"),
    ("ETCH", "Etch", "fab"),
    ("DIFF", "Diffusion / furnace", "fab"),
    ("THIN", "Thin film (CVD/PVD)", "fab"),
    ("CMP", "CMP", "fab"),
    ("METRO", "Metrology", "fab"),
]:
    add("area", code=c, name=n, site=("site", "FAB12"), area_type=tp)
add("area", code="PROBE", name="Wafer probe", site=("site", "TEST1"), area_type="test")
for c, n, area, kind, parent in [
    ("PH-BAY1", "Photo bay 1", "PHOTO", "bay", None),
    ("PH-SCAN", "Scanner WC", "PHOTO", "workcenter", "PH-BAY1"),
    ("PH-TRACK", "Track WC", "PHOTO", "workcenter", "PH-BAY1"),
    ("ET-BAY1", "Etch bay 1", "ETCH", "bay", None),
    ("ET-DRY", "Dry etch WC", "ETCH", "workcenter", "ET-BAY1"),
    ("ET-WET", "Wet clean WC", "ETCH", "workcenter", "ET-BAY1"),
    ("DF-BAY1", "Furnace bay", "DIFF", "bay", None),
    ("DF-FURN", "Furnace WC", "DIFF", "workcenter", "DF-BAY1"),
    ("TF-BAY1", "Thin film bay", "THIN", "bay", None),
    ("TF-CVD", "CVD WC", "THIN", "workcenter", "TF-BAY1"),
    ("CMP-BAY", "CMP bay", "CMP", "bay", None),
    ("MT-BAY", "Metrology bay", "METRO", "bay", None),
    ("MT-CD", "CD-SEM cell", "METRO", "cell", "MT-BAY"),
]:
    add(
        "workcenter",
        code=c,
        name=n,
        area=("area", area),
        kind=kind,
        **({"parent": ("workcenter", parent)} if parent else {}),
    )
add(
    "shift",
    code="D",
    name="Day shift",
    site=("site", "FAB12"),
    start_time="08:00",
    end_time="20:00",
    sort_order=1,
)
add(
    "shift",
    code="N",
    name="Night shift",
    site=("site", "FAB12"),
    start_time="20:00",
    end_time="08:00",
    crosses_midnight=True,
    sort_order=2,
)
add(
    "work_calendar",
    code="FAB12-2026",
    name="Fab 12 calendar 2026 (DEMO)",
    site=("site", "FAB12"),
    year=2026,
)
for d, tp, sh in [
    ("2026-10-09", "workday", "D,N"),
    ("2026-10-10", "holiday", "D,N"),
    ("2026-10-11", "workday", "D,N"),
    ("2026-10-12", "maintenance", "D"),
]:
    add(
        "calendar_day",
        work_calendar=("work_calendar", "FAB12-2026"),
        day=d,
        day_type=tp,
        shifts=sh,
        note="National Day" if tp == "holiday" else None,
    )


# ---------------- helpers ----------------
def _resolve(session: Session, tid: uuid.UUID, ref: Ref) -> Any:
    ent, key = ref
    e = ENTITIES[ent]
    t = TABLES[ent]
    code, _, ver = key.partition("@")
    col = t.c.code if e.has_code else t.c[e.label_field]
    stmt = sa.select(t.c.id).where(t.c.tenant_id == tid, col == code)
    if e.versioned:
        stmt = stmt.where(t.c.version == int(ver or 1))
    return conn(session).execute(stmt).scalar()


def _exists(
    session: Session,
    tid: uuid.UUID,
    ent: str,
    values: dict[str, Any],
    refs: dict[str, Any],
) -> bool:
    e = ENTITIES[ent]
    t = TABLES[ent]
    stmt = sa.select(t.c.id).where(t.c.tenant_id == tid)
    for k in e.natural_key:
        f = e.field(k)
        if k == "version":
            stmt = stmt.where(t.c.version == int(values.get("version") or 1))
        elif f and f.type == "ref":
            stmt = stmt.where(t.c[f.column] == refs.get(k))
        elif f:
            stmt = stmt.where(t.c[f.column] == coerce(f, values.get(k)))
    return conn(session).execute(stmt).first() is not None


def default_tenant(session: Session) -> uuid.UUID:
    t = session.exec(select(Tenant).where(Tenant.slug == "default")).one()
    set_tenant(session, t.id)
    return t.id


def seed(session: Session) -> int:
    tid = default_tenant(session)
    admin = session.exec(select(User).where(User.is_superuser)).first()
    n = 0
    for ent, raw in DEMO:
        values: dict[str, Any] = {}
        for k, v in raw.items():
            if isinstance(v, tuple):
                rid = _resolve(session, tid, v)
                assert rid, f"{ent}.{k}: {v} not found"
                values[f"{k}_id"] = rid
                values.setdefault("_refs", {})[k] = rid
            else:
                values[k] = v
        refs = values.pop("_refs", {})
        if _exists(session, tid, ent, values, refs):
            continue
        values["attrs"] = {**(values.get("attrs") or {}), "_demo": True}
        create_row(session, tid, ENTITIES[ent], values, admin)
        n += 1
    for ref in ACTIVATE:
        rid = _resolve(session, tid, ref)
        row = (
            conn(session)
            .execute(
                sa.select(TABLES[ref[0]].c.status).where(TABLES[ref[0]].c.id == rid)
            )
            .scalar()
        )
        if row == "draft":
            set_status(session, tid, ENTITIES[ref[0]], rid, "active", admin)
    return n


def remove(session: Session) -> int:
    """Delete every row tagged attrs._demo (children first; retries for FKs)."""
    tid = default_tenant(session)
    c = conn(session)
    total = 0
    pending = [e for e in ENTITIES.values() if e.code != "audit_log" and not e.internal]
    for _ in range(len(pending) + 1):
        progress = False
        for e in reversed(pending):
            t = TABLES[e.code]
            demo = sa.cast(t.c.attrs, JSONB)["_demo"].astext == "true"
            try:
                with session.begin_nested():
                    r = c.execute(sa.delete(t).where(t.c.tenant_id == tid, demo))
                total += r.rowcount
                progress = progress or r.rowcount > 0
            except IntegrityError:
                continue
        if not progress:
            break
    session.commit()
    return total
