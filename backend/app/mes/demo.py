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


def _rows(rows: list[Any]) -> list[Any]:
    """Heterogeneous literal tables (keeps the type checker out of the data)."""
    return rows


def add(entity: str, **values: Any) -> None:
    DEMO.append((entity, values))


# ---------------- P1: common + org ----------------
add("dict_type", code="WAFER_GRADE", name="Wafer grade (DEMO)")
for i, (c, n, val) in enumerate(
    [("PRIME", "Prime", "P"), ("TEST", "Test", "T"), ("MON", "Monitor", "M")]
):
    add(
        "dict_item",
        dict_type=("dict_type", "WAFER_GRADE"),
        code=c,
        name=n,
        value=val,
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
for c, n, tp in _rows(
    [
        ("PHOTO", "Photolithography", "fab"),
        ("ETCH", "Etch", "fab"),
        ("DIFF", "Diffusion / furnace", "fab"),
        ("THIN", "Thin film (CVD/PVD)", "fab"),
        ("CMP", "CMP", "fab"),
        ("METRO", "Metrology", "fab"),
    ]
):
    add("area", code=c, name=n, site=("site", "FAB12"), area_type=tp)
add("area", code="PROBE", name="Wafer probe", site=("site", "TEST1"), area_type="test")
for c, n, area, kind, parent in _rows(
    [
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
        ("CMP-POL", "CMP polish WC", "CMP", "workcenter", "CMP-BAY"),
        ("MT-BAY", "Metrology bay", "METRO", "bay", None),
        ("MT-CD", "CD-SEM cell", "METRO", "cell", "MT-BAY"),
    ]
):
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
for d, tp, sh in _rows(
    [
        ("2026-10-09", "workday", "D,N"),
        ("2026-10-10", "holiday", "D,N"),
        ("2026-10-11", "workday", "D,N"),
        ("2026-10-12", "maintenance", "D"),
    ]
):
    add(
        "calendar_day",
        work_calendar=("work_calendar", "FAB12-2026"),
        day=d,
        day_type=tp,
        shifts=sh,
        note="National Day" if tp == "holiday" else None,
    )


# ---------------- P2: product/material + equipment ----------------
for c, n, sym, d in _rows(
    [
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
        ("MJCM2", "Millijoule / cm²", "mJ/cm²", "energy_density"),
    ]
):
    add("uom", code=c, name=n, symbol=sym, dimension=d)
for a, b, fct in _rows(
    [
        ("L", "ML", 1000),
        ("GAL", "L", 3.785411784),
        ("KG", "G", 1000),
        ("NM", "A", 10),
    ]
):
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
for c, n, fam, node, die in _rows(
    [
        ("MCU-A100", "MCU A100 (DEMO)", "MCU", "N40", 1450),
        ("MCU-B200", "MCU B200 (DEMO)", "MCU", "N40", 980),
        ("PM-X10", "PMIC X10 (DEMO)", "PMIC", "N28", 2210),
    ]
):
    add(
        "product",
        code=c,
        name=n,
        family=("product_family", fam),
        tech_node=("tech_node", node),
        gross_die=die,
        uom=("uom", "WFR"),
    )
add(
    "product",
    code="MON-PARTICLE",
    name="Particle monitor wafer (DEMO)",
    product_type="monitor",
    gross_die=0,
    uom=("uom", "WFR"),
)
for c, n, cat in _rows(
    [
        ("RAW-WFR", "Raw silicon wafers", "wafer"),
        ("CHEM", "Wet chemicals", "chemical"),
        ("GAS", "Process gases", "gas"),
        ("PR", "Photoresists", "photoresist"),
        ("SLURRY", "CMP slurries", "slurry"),
    ]
):
    add("material_type", code=c, name=n, category=cat)
for c, n, mt, u, life in _rows(
    [
        ("SI300-P", "300mm prime Si wafer", "RAW-WFR", "WFR", None),
        ("H2SO4-96", "Sulfuric acid 96%", "CHEM", "L", 365),
        ("NF3", "Nitrogen trifluoride", "GAS", "KG", None),
        ("PR-ARF-01", "ArF photoresist", "PR", "L", 180),
        ("SL-CU-01", "Cu CMP slurry", "SLURRY", "L", 120),
    ]
):
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
for c, layer, g in _rows(
    [
        ("RT-A100-AA", "AA", "binary"),
        ("RT-A100-PO", "PO", "psm"),
        ("RT-A100-M1", "M1", "psm"),
    ]
):
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
for c, n, cat, v, mdl in _rows(
    [
        ("SCANNER", "ArF immersion scanner", "process", "ASML", "NXT:1980Di"),
        ("TRACK", "Coater/developer", "process", "TEL", "Lithius Pro"),
        ("DRYETCH", "Conductor etcher", "process", "LAM", "Kiyo"),
        ("FURNACE", "Vertical furnace", "process", "KOKUSAI", "AdvancedAce"),
        ("CVD", "PECVD", "process", "AMAT", "Producer"),
        ("CMP", "CMP polisher", "process", "AMAT", "Reflexion LK"),
        ("CDSEM", "CD-SEM", "metrology", "Hitachi", "CG6300"),
        ("OVL", "Overlay metrology", "metrology", "KLA", "Archer 750"),
    ]
):
    add("equipment_type", code=c, name=n, category=cat, vendor=v, model=mdl)
for c, n, et, area in _rows(
    [
        ("G-SCAN", "Scanners", "SCANNER", "PHOTO"),
        ("G-TRACK", "Tracks", "TRACK", "PHOTO"),
        ("G-ETCH", "Poly etch", "DRYETCH", "ETCH"),
        ("G-FURN", "Furnaces", "FURNACE", "DIFF"),
        ("G-CVD", "PECVD", "CVD", "THIN"),
        ("G-CMP", "CMP", "CMP", "CMP"),
        ("G-CDSEM", "CD-SEM", "CDSEM", "METRO"),
    ]
):
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
for a, b, r in _rows(
    [
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
    ]
):
    add(
        "e10_transition",
        from_state=("e10_state", a),
        to_state=("e10_state", b),
        reason_required=r,
    )
for c, n, et, g, wc, subs in _rows(
    [
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
        (
            "CMP01",
            "CMP 01",
            "CMP",
            "G-CMP",
            "CMP-POL",
            [("P1", "chamber"), ("P2", "chamber")],
        ),
        ("CDS01", "CD-SEM 01", "CDSEM", "G-CDSEM", "MT-CD", []),
    ]
):
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


# ---------------- P3: process ----------------
OPS = [
    ("PH-COAT", "Resist coat", "process", "PHOTO", 6),
    ("PH-EXPO", "Exposure", "process", "PHOTO", 3),
    ("PH-DEV", "Develop", "process", "PHOTO", 5),
    ("PH-CD", "After-develop CD measure", "metrology", "METRO", 4),
    ("PH-OVL", "Overlay measure", "metrology", "METRO", 4),
    ("PH-STRIP", "Resist strip (rework)", "clean", "PHOTO", 8),
    ("DF-OX", "Gate oxidation", "process", "DIFF", 180),
    ("TF-DEP", "PECVD oxide deposition", "process", "THIN", 25),
    ("ET-POLY", "Poly gate etch", "process", "ETCH", 12),
    ("ET-CLN", "Post-etch clean", "clean", "ETCH", 15),
    ("CMP-OX", "Oxide CMP", "process", "CMP", 10),
    ("IN-PART", "Particle inspection", "inspection", "METRO", 5),
]
for c, n, tp, area, mins in OPS:
    add(
        "operation",
        code=c,
        name=n,
        operation_type=tp,
        area=("area", area),
        std_minutes=mins,
    )
add("route", code="RW-PHOTO", name="Photo rework (DEMO)", route_type="rework")
add(
    "route_step",
    route=("route", "RW-PHOTO@1"),
    seq=10,
    operation=("operation", "PH-STRIP"),
)
add(
    "route_step",
    route=("route", "RW-PHOTO@1"),
    seq=20,
    operation=("operation", "IN-PART"),
)
add("route", code="SUB-PHOTO", name="Photo module (DEMO)", route_type="sub")
for i, op in enumerate(["PH-COAT", "PH-EXPO", "PH-DEV"]):
    add(
        "route_step",
        route=("route", "SUB-PHOTO@1"),
        seq=(i + 1) * 10,
        operation=("operation", op),
    )
add(
    "route",
    code="MCU40-MAIN",
    name="MCU 40nm front-end flow (DEMO)",
    route_type="main",
    product_family=("product_family", "MCU"),
)
MAIN = [
    (10, "operation", "DF-OX", {}),
    (20, "operation", "TF-DEP", {}),
    (
        30,
        "sub_route",
        None,
        {"sub_route": ("route", "SUB-PHOTO@1"), "note": "Gate photo"},
    ),
    (40, "operation", "PH-CD", {"rework_route": ("route", "RW-PHOTO@1")}),
    (
        50,
        "operation",
        "PH-OVL",
        {"rework_route": ("route", "RW-PHOTO@1"), "is_optional": True},
    ),
    (60, "operation", "ET-POLY", {}),
    (70, "operation", "ET-CLN", {}),
    (
        80,
        "operation",
        "IN-PART",
        {"branch_condition": "lot_type == 'ENG'", "branch_to_seq": 100},
    ),
    (90, "operation", "CMP-OX", {}),
    (100, "operation", "TF-DEP", {"note": "Cap oxide"}),
]
for seq, st, op, extra in _rows(MAIN):
    add(
        "route_step",
        route=("route", "MCU40-MAIN@1"),
        seq=seq,
        step_type=st,
        **({"operation": ("operation", op)} if op else {}),
        **extra,
    )
ACTIVATE.extend(
    [("route", "RW-PHOTO@1"), ("route", "SUB-PHOTO@1"), ("route", "MCU40-MAIN@1")]
)
for p in ("MCU-A100", "MCU-B200"):
    add(
        "product_route",
        product=("product", f"{p}@1"),
        route=("route", "MCU40-MAIN@1"),
        is_default=True,
        priority=1,
        effective_from="2026-01-01",
    )
for c, n, et, tp, body in _rows(
    [
        (
            "EXP-GATE",
            "Gate exposure 28mJ",
            "SCANNER",
            "production",
            {"dose_mj": 28.0, "focus_um": -0.03, "na": 1.35},
        ),
        (
            "COAT-ARF",
            "ArF resist coat 120nm",
            "TRACK",
            "production",
            {"spin_rpm": 1500, "bake_c": 110},
        ),
        (
            "ETCH-POLY",
            "Poly gate main etch",
            "DRYETCH",
            "production",
            {"rf_w": 600, "pressure_mtorr": 8, "cl2_sccm": 80},
        ),
        (
            "OX-GATE",
            "Dry gate oxide 3nm",
            "FURNACE",
            "production",
            {"temp_c": 850, "o2_slm": 10, "minutes": 45},
        ),
        ("SEASON-ET", "Etch chamber seasoning", "DRYETCH", "clean", {"minutes": 10}),
    ]
):
    add(
        "recipe",
        code=c,
        name=f"{n} (DEMO)",
        equipment_type=("equipment_type", et),
        recipe_type=tp,
        body=body,
    )
    ACTIVATE.append(("recipe", f"{c}@1"))
for rc, eqs in _rows(
    [
        ("EXP-GATE", ["SCN01"]),
        ("COAT-ARF", ["TRK01"]),
        ("ETCH-POLY", ["ETC01", "ETC02"]),
        ("OX-GATE", ["FRN01"]),
        ("SEASON-ET", ["ETC01", "ETC02"]),
    ]
):
    for eq in eqs:
        add(
            "recipe_equipment",
            recipe=("recipe", f"{rc}@1"),
            equipment=("equipment", eq),
            eqp_recipe=f"{rc.replace('-', '_')}_V1",
        )
for c, n, op, rc, tgt, lsl, usl, u in _rows(
    [
        ("DOSE", "Exposure dose", None, "EXP-GATE", 28.0, 27.0, 29.0, "MJCM2"),
        ("GATE-CD", "Gate CD after develop", "PH-CD", None, 45.0, 42.0, 48.0, "NM"),
        ("OVL-X", "Overlay X", "PH-OVL", None, 0.0, -8.0, 8.0, "NM"),
        ("OX-THK", "Gate oxide thickness", "DF-OX", "OX-GATE", 30.0, 28.5, 31.5, "A"),
        (
            "ETCH-RATE",
            "Poly etch rate",
            "ET-POLY",
            "ETCH-POLY",
            2500.0,
            2300.0,
            2700.0,
            "A",
        ),
    ]
):
    add(
        "param_spec",
        code=c,
        name=n,
        target=tgt,
        lsl=lsl,
        usl=usl,
        **({"operation": ("operation", op)} if op else {}),
        **({"recipe": ("recipe", f"{rc}@1")} if rc else {}),
        **({"uom": ("uom", u)} if u else {}),
    )
for eq, op, rc in _rows(
    [
        ("SCN01", "PH-EXPO", "EXP-GATE"),
        ("TRK01", "PH-COAT", "COAT-ARF"),
        ("TRK01", "PH-DEV", None),
        ("ETC01", "ET-POLY", "ETCH-POLY"),
        ("ETC02", "ET-POLY", "ETCH-POLY"),
        ("FRN01", "DF-OX", "OX-GATE"),
        ("CVD01", "TF-DEP", None),
        ("CMP01", "CMP-OX", None),
        ("CDS01", "PH-CD", None),
    ]
):
    add(
        "equipment_capability",
        equipment=("equipment", eq),
        operation=("operation", op),
        qualified_until="2027-06-30",
        **({"recipe": ("recipe", f"{rc}@1")} if rc else {}),
    )
# line-side consumption per step (qty, uom, basis)
MAT_QTY: dict[str, dict[str, Any]] = {
    "NF3": {"qty": 0.2, "uom": ("uom", "KG"), "qty_basis": "per_lot"},
    "SL-CU-01": {"qty": 0.05, "uom": ("uom", "L"), "qty_basis": "per_unit"},
}
for seq, kind, ref, rc in _rows(
    [
        (10, "equipment_group", ("equipment_group", "G-FURN"), "OX-GATE"),
        (20, "equipment_group", ("equipment_group", "G-CVD"), None),
        (40, "equipment", ("equipment", "CDS01"), None),
        (60, "equipment_group", ("equipment_group", "G-ETCH"), "ETCH-POLY"),
        (60, "material", ("material", "NF3"), None),
        (90, "equipment", ("equipment", "CMP01"), None),
        (90, "material", ("material", "SL-CU-01"), None),
    ]
):
    add(
        "step_resource",
        route_step=("route_step", f"MCU40-MAIN@1#{seq}"),
        resource_kind=kind,
        **{kind: ref},
        **({"recipe": ("recipe", f"{rc}@1")} if rc else {}),
        **MAT_QTY.get(ref[1] if kind == "material" else "", {}),
    )
for seq, kind, ref, rc in _rows(
    [
        (10, "equipment_group", ("equipment_group", "G-TRACK"), "COAT-ARF"),
        (20, "equipment", ("equipment", "SCN01"), "EXP-GATE"),
        (20, "reticle", ("reticle", "RT-A100-PO"), None),
        (30, "equipment_group", ("equipment_group", "G-TRACK"), None),
    ]
):
    add(
        "step_resource",
        route_step=("route_step", f"SUB-PHOTO@1#{seq}"),
        resource_kind=kind,
        **{kind: ref},
        **({"recipe": ("recipe", f"{rc}@1")} if rc else {}),
    )


# ---------------- P4: quality + lot/wafer rules ----------------
for c, n, tp, u, prec in _rows(
    [
        ("GATE-CD", "Gate CD", "numeric", "NM", 2),
        ("OVL-X", "Overlay X", "numeric", "NM", 2),
        ("OVL-Y", "Overlay Y", "numeric", "NM", 2),
        ("OX-THK", "Oxide thickness", "numeric", "A", 1),
        ("PART-ADD", "Particle adders", "count", None, 0),
        ("VIS-OK", "Visual inspection", "attribute", None, 0),
    ]
):
    add(
        "measurement_item",
        code=c,
        name=n,
        meas_type=tp,
        precision=prec,
        oos_action={"OVL-X": "rework", "OVL-Y": "rework", "PART-ADD": "warn"}.get(
            c, "auto_hold"
        ),
        **({"uom": ("uom", u)} if u else {}),
    )
add(
    "dc_plan",
    code="DC-PH-CD",
    name="ADI CD plan (DEMO)",
    operation=("operation", "PH-CD"),
)
add(
    "dc_plan_item",
    dc_plan=("dc_plan", "DC-PH-CD@1"),
    measurement_item=("measurement_item", "GATE-CD"),
    seq=10,
    sites=9,
    lsl=42,
    target=45,
    usl=48,
)
add(
    "dc_plan",
    code="DC-PH-OVL",
    name="Overlay plan (DEMO)",
    operation=("operation", "PH-OVL"),
)
for i, mi in enumerate(["OVL-X", "OVL-Y"]):
    add(
        "dc_plan_item",
        dc_plan=("dc_plan", "DC-PH-OVL@1"),
        measurement_item=("measurement_item", mi),
        seq=(i + 1) * 10,
        sites=13,
        lsl=-8,
        target=0,
        usl=8,
    )
add(
    "dc_plan",
    code="DC-OX",
    name="Gate oxide thickness (DEMO)",
    operation=("operation", "DF-OX"),
)
add(
    "dc_plan_item",
    dc_plan=("dc_plan", "DC-OX@1"),
    measurement_item=("measurement_item", "OX-THK"),
    seq=10,
    sites=49,
    lsl=28.5,
    target=30,
    usl=31.5,
)
add(
    "dc_plan",
    code="DC-PART",
    name="Particle monitor (DEMO)",
    operation=("operation", "IN-PART"),
)
add(
    "dc_plan_item",
    dc_plan=("dc_plan", "DC-PART@1"),
    measurement_item=("measurement_item", "PART-ADD"),
    seq=10,
    sites=1,
    usl=30,
)
ACTIVATE.extend(
    [("dc_plan", c) for c in ("DC-PH-CD@1", "DC-PH-OVL@1", "DC-OX@1", "DC-PART@1")]
)
add(
    "sampling_rule",
    code="SR-CD",
    name="CD: every lot, 3 fixed wafers",
    level="wafer",
    operation=("operation", "PH-CD"),
    dc_plan=("dc_plan", "DC-PH-CD@1"),
    lot_frequency=1,
    wafer_count=3,
    wafer_selection="fixed",
    fixed_slots="1,13,25",
)
add(
    "sampling_rule",
    code="SR-OVL",
    name="Overlay: 1 in 4 lots, 2 random wafers",
    level="wafer",
    operation=("operation", "PH-OVL"),
    dc_plan=("dc_plan", "DC-PH-OVL@1"),
    lot_frequency=4,
    wafer_count=2,
    wafer_selection="random",
)
add(
    "sampling_rule",
    code="SR-OX",
    name="Oxide: every lot, first wafer",
    level="wafer",
    operation=("operation", "DF-OX"),
    dc_plan=("dc_plan", "DC-OX@1"),
    lot_frequency=1,
    wafer_count=1,
    wafer_selection="first",
)
add(
    "sampling_rule",
    code="SR-PART",
    name="Particles: 1 in 10 lots",
    level="lot",
    operation=("operation", "IN-PART"),
    dc_plan=("dc_plan", "DC-PART@1"),
    lot_frequency=10,
)
for c, n, cat, sev, killer in _rows(
    [
        ("D-PRT", "Particle", "particle", "major", False),
        ("D-SCR", "Scratch", "scratch", "major", True),
        ("D-BRG", "Bridging", "pattern", "critical", True),
        ("D-RES", "Resist residue", "residue", "minor", False),
        ("D-PIN", "Pinhole", "pattern", "major", False),
        ("D-OPEN", "Electrical open", "electrical", "critical", True),
    ]
):
    add("defect_code", code=c, name=n, category=cat, severity=sev, is_killer=killer)
for c, n, tp, area, cmt in _rows(
    [
        ("SC-BRK", "Wafer broken", "scrap", None, True),
        ("SC-OOS", "Out of spec, not reworkable", "scrap", None, True),
        ("RW-CD", "CD out of spec", "rework", "PHOTO", False),
        ("RW-OVL", "Overlay out of spec", "rework", "PHOTO", False),
        ("HD-EQ", "Equipment abnormal", "hold", None, True),
        ("HD-QT", "Q-Time exceeded", "hold", None, False),
        ("HD-ENG", "Engineering request", "hold", None, True),
        ("RL-OK", "Disposition OK", "release", None, False),
        ("RL-ENG", "Engineering release", "release", None, True),
    ]
):
    add(
        "reason_code",
        code=c,
        name=n,
        reason_type=tp,
        comment_required=cmt,
        **({"area": ("area", area)} if area else {}),
    )
for c, n, lvl, col, hot in _rows(
    [
        ("SH", "Super hot", 1, "#dc2626", True),
        ("HOT", "Hot", 2, "#f97316", True),
        ("NORMAL", "Normal", 5, "#3b82f6", False),
        ("LOW", "Low / filler", 9, "#6b7280", False),
    ]
):
    add("lot_priority", code=c, name=n, level=lvl, color=col, is_hot=hot)
for c, n, cat, pr in _rows(
    [
        ("PROD", "Production lot", "production", "NORMAL"),
        ("ENG", "Engineering lot", "engineering", "HOT"),
        ("MON", "Monitor lot", "monitor", "LOW"),
        ("DUMMY", "Dummy lot", "dummy", "LOW"),
    ]
):
    add(
        "lot_type",
        code=c,
        name=f"{n} (DEMO)",
        category=cat,
        default_priority=("lot_priority", pr),
        lot_id_rule=("code_rule", "LOT_ID"),
        wafer_id_rule=("code_rule", "WAFER_ID"),
        max_wafers=25,
    )
add(
    "split_merge_rule",
    code="SM-PROD",
    name="Production split/merge",
    lot_type=("lot_type", "PROD"),
    max_children=4,
    min_wafers=5,
)
add(
    "split_merge_rule",
    code="SM-ENG",
    name="Engineering split (no merge)",
    lot_type=("lot_type", "ENG"),
    max_children=10,
    min_wafers=1,
    allow_merge=False,
)
add(
    "qtime_rule",
    code="QT-OX-DEP",
    name="Gate oxide → deposition (DEMO)",
    route=("route", "MCU40-MAIN@1"),
    from_step=("route_step", "MCU40-MAIN@1#10"),
    to_step=("route_step", "MCU40-MAIN@1#20"),
    max_minutes=240,
    action="hold",
    reason=("reason_code", "HD-QT"),
)
add(
    "qtime_rule",
    code="QT-ETCH-CLN",
    name="Poly etch → clean (DEMO)",
    route=("route", "MCU40-MAIN@1"),
    from_step=("route_step", "MCU40-MAIN@1#60"),
    to_step=("route_step", "MCU40-MAIN@1#70"),
    min_minutes=5,
    max_minutes=120,
    action="rework",
)


# products go active last: activation needs an active default route
ACTIVATE.extend([("product", "MCU-A100@1"), ("product", "MCU-B200@1")])

# ---------------- work orders + lot start ----------------
add(
    "code_rule",
    code="WO_NO",
    name="Work order no. (DEMO)",
    target="work_order",
    pattern="WO{YY}{MM}{SEQ}",
    seq_width=4,
    seq_reset="monthly",
)
add(
    "work_order",
    code="WO-DEMO-01",
    product=("product", "MCU-A100@1"),
    lot_type=("lot_type", "PROD"),
    planned_qty=50,
    over_start_limit_pct=4,
    customer="ACME Semi (DEMO)",
    order_ref="PO-2026-0815",
)
add(
    "work_order",
    code="WO-DEMO-02",
    product=("product", "MCU-B200@1"),
    lot_type=("lot_type", "PROD"),
    planned_qty=25,
    remarks="Draft – not released yet (DEMO)",
)
# ---------------- execution: checks, E10, line-side material, tools ----------------
for trig, st in (("track_in", "PRD-RUN"), ("track_out", "SBY-IDLE")):
    add("e10_auto_rule", trigger=trig, to_state=("e10_state", st))
CHECK_RULES: list[tuple[str, str, str, str, dict[str, Any]]] = [
    (
        "CR-E10",
        "Equipment available (E10 SBY/PRD)",
        "e10_available",
        "block",
        {"allowed": ["SBY", "PRD"]},
    ),
    ("CR-CAP", "Equipment qualified for operation", "eqp_capability", "block", {}),
    ("CR-RCP", "Recipe active + enabled on tool", "recipe_active", "block", {}),
    ("CR-RET", "Reticle available", "reticle_available", "block", {}),
    ("CR-MAT", "Line-side material sufficient", "material_sufficient", "block", {}),
    ("CR-TOOL", "Tool available + life", "tool_life", "block", {"expiry_warn_days": 7}),
    ("CR-CARR", "Carrier usable", "carrier_available", "warn", {}),
    ("CR-QT", "Q-Time window", "qtime", "block", {}),
    ("CR-HOLD", "Lot not on hold", "lot_hold", "block", {}),
    ("CR-WO", "Work order active", "wo_status", "block", {}),
    ("CR-DC", "DC data complete", "dc_complete", "block", {}),
    ("CR-OOS", "Out-of-spec values", "oos", "warn", {}),
    ("CR-SMP", "Sampling decision", "sampling", "warn", {}),
]
for c, n, tp, sev, prm in CHECK_RULES:
    add(
        "check_rule",
        code=c,
        name=f"{n} (DEMO)",
        check_type=tp,
        severity=sev,
        params=prm,
    )
CHECK_PLANS = [
    ("CP-MI", "Standard move-in", ["CR-HOLD", "CR-WO", "CR-QT"]),
    (
        "CP-TI",
        "Standard track-in",
        ["CR-E10", "CR-CAP", "CR-RCP", "CR-TOOL", "CR-CARR", "CR-MAT"],
    ),
    (
        "CP-TI-LITHO",
        "Litho track-in (+ reticle)",
        ["CR-E10", "CR-CAP", "CR-RCP", "CR-RET"],
    ),
    ("CP-TO", "Standard track-out", ["CR-SMP", "CR-DC", "CR-OOS", "CR-MAT"]),
]
for c, n, rules in CHECK_PLANS:
    add("check_plan", code=c, name=f"{n} (DEMO)")
    for i, r in enumerate(rules):
        add(
            "check_plan_item",
            check_plan=("check_plan", c),
            check_rule=("check_rule", r),
            seq=(i + 1) * 10,
        )
for prod in ("MCU-A100", "MCU-B200"):
    for trig, plan in (
        ("move_in", "CP-MI"),
        ("track_in", "CP-TI"),
        ("track_out", "CP-TO"),
    ):
        add(
            "check_binding",
            check_plan=("check_plan", plan),
            trigger=trig,
            scope="product",
            product=("product", f"{prod}@1"),
        )
# most specific wins: the exposure step uses the litho plan instead of CP-TI
add(
    "check_binding",
    check_plan=("check_plan", "CP-TI-LITHO"),
    trigger="track_in",
    scope="route_step",
    route_step=("route_step", "SUB-PHOTO@1#20"),
)
for c, mat, qty, u, exp, loc in _rows(
    [
        ("ML-NF3-0001", "NF3", 1.5, "KG", "2027-03-31", "ETCH bay gas cabinet 2"),
        ("ML-NF3-0002", "NF3", 0.1, "KG", "2026-12-31", "ETCH bay gas cabinet 1"),
        ("ML-SLCU-0001", "SL-CU-01", 20.0, "L", "2026-12-15", "CMP slurry room"),
        ("ML-PR-0001", "PR-ARF-01", 3.8, "L", "2026-11-30", "PHOTO fridge A"),
    ]
):
    add(
        "material_lot",
        code=c,
        material=("material", mat),
        qty_remaining=qty,
        initial_qty=qty,
        uom=("uom", u),
        expiry_date=exp,
        location=loc,
    )
add("fixture", code="PAD-CMP", name="CMP polishing pad", kind="tool", max_uses=500)
for c, sn, used, _mx, exp in _rows(
    [
        ("PAD-0001", "IC1010-A1", 120, None, "2027-06-30"),
        ("PAD-0002", "IC1010-A2", 470, None, "2027-06-30"),
        ("PAD-0003", "IC1010-A3", 500, None, "2027-06-30"),
    ]
):
    add(
        "tool",
        code=c,
        fixture=("fixture", "PAD-CMP"),
        serial_no=sn,
        usage_count=used,
        expiry_date=exp,
        tool_status="pending_maintenance" if used >= 500 else "available",
    )
add(
    "step_resource",
    route_step=("route_step", "MCU40-MAIN@1#90"),
    resource_kind="fixture",
    fixture=("fixture", "PAD-CMP"),
)

# ---------------- backend (quantity tracking) ----------------
add("area", code="ASSY", name="Assembly", site=("site", "TEST1"), area_type="assembly")
for c, n in (
    ("PK-DA", "Die attach"),
    ("PK-WB", "Wire bond"),
    ("PK-MOLD", "Molding"),
    ("PK-FT", "Final test"),
):
    add(
        "operation",
        code=c,
        name=n,
        operation_type="process",
        area=("area", "ASSY"),
        std_minutes=30,
    )
add("route", code="PKG-MAIN", name="QFN assembly flow (DEMO)", route_type="main")
for i, op in enumerate(["PK-DA", "PK-WB", "PK-MOLD", "PK-FT"]):
    add(
        "route_step",
        route=("route", "PKG-MAIN@1"),
        seq=(i + 1) * 10,
        operation=("operation", op),
        auto_move_in=True,  # arrives at the station automatically
        auto_move_out=op != "PK-FT",
    )
ACTIVATE.append(("route", "PKG-MAIN@1"))
add(
    "product",
    code="PKG-A100",
    name="MCU A100 QFN-48 package (DEMO)",
    family=("product_family", "MCU"),
    tech_node=("tech_node", "N40"),
    uom=("uom", "WFR"),
    tracking_level="quantity",
)
add(
    "product_route",
    product=("product", "PKG-A100@1"),
    route=("route", "PKG-MAIN@1"),
    is_default=True,
    priority=1,
)
ACTIVATE.append(("product", "PKG-A100@1"))
for trig, plan in (("move_in", "CP-MI"), ("track_out", "CP-TO")):
    add(
        "check_binding",
        check_plan=("check_plan", plan),
        trigger=trig,
        scope="product",
        product=("product", "PKG-A100@1"),
    )
add(
    "lot_type",
    code="ASSY",
    name="Assembly lot (DEMO)",
    category="production",
    default_priority=("lot_priority", "NORMAL"),
    lot_id_rule=("code_rule", "LOT_ID"),
    wafer_id_rule=("code_rule", "WAFER_ID"),
    max_wafers=5000,
)
add(
    "work_order",
    code="WO-DEMO-03",
    product=("product", "PKG-A100@1"),
    lot_type=("lot_type", "ASSY"),
    planned_qty=2000,
    remarks="Assembly – quantity tracked (DEMO)",
)

# released + started after seeding: (wo, [(qty, carrier code | None)])
STARTS: list[tuple[str, list[tuple[int, str | None]]]] = [
    ("WO-DEMO-01", [(25, "FP0001"), (15, None)]),
    ("WO-DEMO-03", [(1000, None)]),
]


# ---------------- helpers ----------------
def _resolve(session: Session, tid: uuid.UUID, ref: Ref) -> Any:
    ent, key = ref
    if ent == "route_step":  # "ROUTE@v#seq"
        rkey, _, seq = key.partition("#")
        st = TABLES["route_step"]
        rid = _resolve(session, tid, ("route", rkey))
        return (
            conn(session)
            .execute(
                sa.select(st.c.id).where(st.c.route_id == rid, st.c.seq == int(seq))
            )
            .scalar()
        )
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
        elif f:
            v = refs.get(k) if f.type == "ref" else coerce(f, values.get(k))
            col = t.c[f.column]
            stmt = stmt.where(col.is_(None) if v is None else col == v)
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
    from app.mes import wo as wos

    for code, lots in STARTS:
        w = _resolve(session, tid, ("work_order", code))
        row = (
            conn(session)
            .execute(
                sa.select(TABLES["work_order"]).where(TABLES["work_order"].c.id == w)
            )
            .mappings()
            .first()
        )
        if not row or row["started_qty"]:
            continue
        if row["wo_status"] == "draft":
            wos.transition(session, tid, row["id"], "release", admin)
        wos.start(
            session,
            tid,
            row["id"],
            [
                {"qty": q, "carrier_id": c and _resolve(session, tid, ("carrier", c))}
                for q, c in lots
            ],
            admin,
            demo=True,
        )
    _run_exec(session, tid, admin)
    return n


# lot 1: through the photo sub-route to ADI CD (OOS -> auto hold);
# lot 2: tracked in at gate oxide; assembly lot: scrap at die attach
EXEC_DEMO: list[tuple[int, str, str | None, str | None, Any]] = [
    # (lot index, stage, equipment, recipe, extra)
    (0, "move_in", "FRN01", None, None),
    (0, "track_in", "FRN01", "OX-GATE", None),
    (0, "track_out", None, None, {"OX-THK": 30.1}),
    (0, "move_out", None, None, None),
    (0, "move_in", "CVD01", None, None),
    (0, "track_in", "CVD01", None, None),
    (0, "track_out", None, None, None),
    (0, "move_out", None, None, None),
    (0, "move_in", "TRK01", None, None),
    (0, "track_in", "TRK01", "COAT-ARF", None),
    (0, "track_out", None, None, None),
    (0, "move_out", None, None, None),
    (0, "move_in", "SCN01", None, None),
    (0, "track_in", "SCN01", "EXP-GATE", {"reticle": "RT-A100-PO"}),
    (0, "track_out", None, None, None),
    (0, "move_out", None, None, None),
    (0, "move_in", "TRK01", None, None),
    (0, "track_in", "TRK01", None, None),
    (0, "track_out", None, None, None),
    (0, "move_out", None, None, None),
    (0, "move_in", "CDS01", None, None),
    (0, "track_in", "CDS01", None, None),
    (0, "track_out", None, None, {"GATE-CD": 45.2, "_oos": 49.3}),
    (1, "move_in", "FRN01", None, None),
    (1, "track_in", "FRN01", "OX-GATE", None),
    (2, "move_in", None, None, None),
    (2, "track_in", None, None, None),
    (2, "track_out", None, None, {"_scrap": 12}),
]


def _run_exec(session: Session, tid: uuid.UUID, admin: Any) -> None:
    from app.mes import execution as ex

    lt = TABLES["lot"]
    lots = []
    for wo in ("WO-DEMO-01", "WO-DEMO-03"):
        w = _resolve(session, tid, ("work_order", wo))
        lots += [
            dict(r)
            for r in conn(session)
            .execute(sa.select(lt).where(lt.c.work_order_id == w).order_by(lt.c.code))
            .mappings()
        ]
    h = TABLES["lot_history"]
    acted = (
        conn(session)
        .execute(
            sa.select(sa.func.count()).where(
                h.c.lot_id.in_([x["id"] for x in lots]), h.c.action != "start"
            )
        )
        .scalar()
    )
    if len(lots) < 3 or acted:
        return
    for i, stage, eq, rc, extra in EXEC_DEMO:
        lot = lots[i]
        body: dict[str, Any] = {}
        if eq:
            body["equipment_id"] = _resolve(session, tid, ("equipment", eq))
        if rc:
            body["recipe_id"] = _resolve(session, tid, ("recipe", f"{rc}@1"))
        extra = extra or {}
        if extra.get("reticle"):
            body["reticle_id"] = _resolve(session, tid, ("reticle", extra["reticle"]))
        if stage == "track_out":
            cx = ex.context(session, tid, lot["id"])
            dc = cx["dc"]
            vals = []
            if dc["sampled"]:
                units = dc["unit_ids"] or [None]
                for it in dc["items"]:
                    for k, u in enumerate(units):
                        v = extra.get(it["code"], it["target"] or 0)
                        if k == 0 and "_oos" in extra:
                            v = extra["_oos"]
                        vals.append(
                            {
                                "measurement_item_id": it["measurement_item_id"],
                                "unit_id": u,
                                "value": v,
                            }
                        )
            body["dc"] = vals
            if extra.get("_scrap"):
                body["scrap"] = [
                    {
                        "qty": extra["_scrap"],
                        "reason_id": _resolve(session, tid, ("reason_code", "SC-BRK")),
                    }
                ]
        ex.run_stage(session, tid, lot["id"], stage, body, admin)


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
                with c.begin_nested():
                    r = c.execute(sa.delete(t).where(t.c.tenant_id == tid, demo))
                total += r.rowcount
                progress = progress or r.rowcount > 0
            except IntegrityError:
                continue
        if not progress:
            break
    session.commit()
    return total
