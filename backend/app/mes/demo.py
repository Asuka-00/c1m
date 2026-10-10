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


# ---------------- P2: product/material + equipment ----------------
for c, n, sym, d in [
    ("EA", "Each", "ea", "count"),
    ("WFR", "Wafer", "wfr", "count"),
    ("L", "Liter", "L", "volume"),
    ("ML", "Milliliter", "mL", "volume"),
    ("GAL", "US gallon", "gal", "volume"),
    ("KG", "Kilogram", "kg", "mass"),
    ("G", "Gram", "g", "mass"),
    ("SCCM", "Std. cubic cm / min", "sccm", "volume"),
    ("MIN", "Minute", "min", "time"),
    ("NM", "Nanometer", "nm", "length"),
    ("A", "Angstrom", "Å", "length"),
]:
    add("uom", code=c, name=n, symbol=sym, dimension=d)
for a, b, fct in [
    ("L", "ML", 1000),
    ("GAL", "L", 3.785411784),
    ("KG", "G", 1000),
    ("NM", "A", 10),
]:
    add("uom_conversion", from_uom=("uom", a), to_uom=("uom", b), factor=fct)
add("tech_node", code="N28", name="28 nm HKMG (DEMO)", feature_nm=28, wafer_size="300")
add("tech_node", code="N40", name="40 nm LP (DEMO)", feature_nm=40, wafer_size="300")
add(
    "product_family",
    code="MCU",
    name="Microcontrollers",
    tech_node=("tech_node", "N40"),
)
add(
    "product_family",
    code="PMIC",
    name="Power management",
    tech_node=("tech_node", "N28"),
)
for c, n, fam, node, die in [
    ("MCU-A100", "MCU A100 (DEMO)", "MCU", "N40", 1450),
    ("MCU-B200", "MCU B200 (DEMO)", "MCU", "N40", 980),
    ("PM-X10", "PMIC X10 (DEMO)", "PMIC", "N28", 2210),
]:
    add(
        "product",
        code=c,
        name=n,
        family=("product_family", fam),
        tech_node=("tech_node", node),
        gross_die=die,
        uom=("uom", "WFR"),
    )
    ACTIVATE.append(("product", c))
add(
    "product",
    code="MON-PARTICLE",
    name="Particle monitor wafer (DEMO)",
    product_type="monitor",
    gross_die=0,
    uom=("uom", "WFR"),
)
for c, n, cat in [
    ("RAW-WFR", "Raw silicon wafers", "wafer"),
    ("CHEM", "Wet chemicals", "chemical"),
    ("GAS", "Process gases", "gas"),
    ("PR", "Photoresists", "photoresist"),
    ("SLURRY", "CMP slurries", "slurry"),
]:
    add("material_type", code=c, name=n, category=cat)
for c, n, mt, u, life in [
    ("SI300-P", "300mm prime Si wafer", "RAW-WFR", "WFR", None),
    ("H2SO4-96", "Sulfuric acid 96%", "CHEM", "L", 365),
    ("NF3", "Nitrogen trifluoride", "GAS", "KG", None),
    ("PR-ARF-01", "ArF photoresist", "PR", "L", 180),
    ("SL-CU-01", "Cu CMP slurry", "SLURRY", "L", 120),
]:
    add(
        "material",
        code=c,
        name=n,
        material_type=("material_type", mt),
        uom=("uom", u),
        shelf_life_days=life,
    )
add(
    "carrier_type",
    code="FOUP25",
    name="FOUP 25-slot 300mm",
    category="foup",
    capacity=25,
    wafer_size="300",
    clean_interval_days=30,
)
add(
    "carrier_type",
    code="FOSB25",
    name="FOSB shipping box",
    category="fosb",
    capacity=25,
    wafer_size="300",
)
add(
    "carrier_type",
    code="RPOD",
    name="Reticle SMIF pod",
    category="pod",
    capacity=1,
    wafer_size="300",
)
for i in range(1, 7):
    add(
        "carrier",
        code=f"FP{i:04d}",
        name=f"FOUP {i} (DEMO)",
        carrier_type=("carrier_type", "FOUP25"),
        max_uses=500,
        status_code="dirty" if i == 5 else "available",
    )
for c, layer, g in [
    ("RT-A100-AA", "AA", "binary"),
    ("RT-A100-PO", "PO", "psm"),
    ("RT-A100-M1", "M1", "psm"),
]:
    add(
        "reticle",
        code=c,
        name=f"MCU-A100 {layer} mask (DEMO)",
        product=("product", "MCU-A100"),
        layer=layer,
        grade=g,
        max_shots=250000,
    )
add(
    "fixture",
    code="PC-A100-01",
    name="Probe card A100 #1",
    kind="probe_card",
    max_uses=1_000_000,
)
for c, n, cat, v, mdl in [
    ("SCANNER", "ArF immersion scanner", "process", "ASML", "NXT:1980Di"),
    ("TRACK", "Coater/developer", "process", "TEL", "Lithius Pro"),
    ("DRYETCH", "Conductor etcher", "process", "LAM", "Kiyo"),
    ("FURNACE", "Vertical furnace", "process", "KOKUSAI", "AdvancedAce"),
    ("CVD", "PECVD", "process", "AMAT", "Producer"),
    ("CMP", "CMP polisher", "process", "AMAT", "Reflexion LK"),
    ("CDSEM", "CD-SEM", "metrology", "Hitachi", "CG6300"),
    ("OVL", "Overlay metrology", "metrology", "KLA", "Archer 750"),
]:
    add("equipment_type", code=c, name=n, category=cat, vendor=v, model=mdl)
for c, n, et, area in [
    ("G-SCAN", "Scanners", "SCANNER", "PHOTO"),
    ("G-TRACK", "Tracks", "TRACK", "PHOTO"),
    ("G-ETCH", "Poly etch", "DRYETCH", "ETCH"),
    ("G-FURN", "Furnaces", "FURNACE", "DIFF"),
    ("G-CVD", "PECVD", "CVD", "THIN"),
    ("G-CMP", "CMP", "CMP", "CMP"),
    ("G-CDSEM", "CD-SEM", "CDSEM", "METRO"),
]:
    add(
        "equipment_group",
        code=c,
        name=n,
        equipment_type=("equipment_type", et),
        area=("area", area),
    )
for i, (c, n, cat, col, init) in enumerate(
    [
        ("PRD-RUN", "Productive", "PRD", "#16a34a", False),
        ("SBY-IDLE", "Standby – no WIP", "SBY", "#eab308", True),
        ("SBY-WAIT", "Standby – waiting operator", "SBY", "#facc15", False),
        ("ENG-TEST", "Engineering test", "ENG", "#3b82f6", False),
        ("SDT-PM", "Preventive maintenance", "SDT", "#f97316", False),
        ("UDT-DOWN", "Unscheduled repair", "UDT", "#dc2626", False),
        ("NST-OFF", "Not scheduled", "NST", "#6b7280", False),
    ]
):
    add(
        "e10_state",
        code=c,
        name=n,
        e10_category=cat,
        color=col,
        is_initial=init,
        sort_order=i,
    )
for a, b, r in [
    ("SBY-IDLE", "PRD-RUN", False),
    ("PRD-RUN", "SBY-IDLE", False),
    ("SBY-IDLE", "SBY-WAIT", False),
    ("SBY-WAIT", "PRD-RUN", False),
    ("SBY-IDLE", "SDT-PM", True),
    ("SDT-PM", "SBY-IDLE", False),
    ("PRD-RUN", "UDT-DOWN", True),
    ("SBY-IDLE", "UDT-DOWN", True),
    ("UDT-DOWN", "ENG-TEST", False),
    ("ENG-TEST", "SBY-IDLE", False),
    ("SBY-IDLE", "NST-OFF", True),
    ("NST-OFF", "SBY-IDLE", False),
]:
    add(
        "e10_transition",
        from_state=("e10_state", a),
        to_state=("e10_state", b),
        reason_required=r,
    )
for c, n, et, g, wc, subs in [
    (
        "SCN01",
        "Scanner 01",
        "SCANNER",
        "G-SCAN",
        "PH-SCAN",
        [("LP1", "load_port"), ("LP2", "load_port"), ("WS1", "chamber")],
    ),
    (
        "TRK01",
        "Track 01",
        "TRACK",
        "G-TRACK",
        "PH-TRACK",
        [("LP1", "load_port"), ("COT1", "chamber"), ("DEV1", "chamber")],
    ),
    (
        "ETC01",
        "Poly etcher 01",
        "DRYETCH",
        "G-ETCH",
        "ET-DRY",
        [
            ("LP1", "load_port"),
            ("LP2", "load_port"),
            ("PM1", "chamber"),
            ("PM2", "chamber"),
            ("PM3", "chamber"),
        ],
    ),
    (
        "ETC02",
        "Poly etcher 02",
        "DRYETCH",
        "G-ETCH",
        "ET-DRY",
        [("LP1", "load_port"), ("PM1", "chamber"), ("PM2", "chamber")],
    ),
    ("FRN01", "Furnace 01", "FURNACE", "G-FURN", "DF-FURN", [("TUBE", "chamber")]),
    (
        "CVD01",
        "PECVD 01",
        "CVD",
        "G-CVD",
        "TF-CVD",
        [("PM1", "chamber"), ("PM2", "chamber")],
    ),
    ("CMP01", "CMP 01", "CMP", "G-CMP", None, [("P1", "chamber"), ("P2", "chamber")]),
    ("CDS01", "CD-SEM 01", "CDSEM", "G-CDSEM", "MT-CD", []),
]:
    add(
        "equipment",
        code=c,
        name=f"{n} (DEMO)",
        unit_kind="main",
        equipment_type=("equipment_type", et),
        equipment_group=("equipment_group", g),
        initial_state=("e10_state", "SBY-IDLE"),
        **({"workcenter": ("workcenter", wc)} if wc else {}),
    )
    for sc, kind in subs:
        add(
            "equipment",
            code=f"{c}-{sc}",
            name=f"{n} {sc}",
            unit_kind=kind,
            parent=("equipment", c),
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
