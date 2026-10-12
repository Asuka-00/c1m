"""Quality demo data (measurement items, DC plans, sampling, defect/reason codes)."""

from app.mes.common.demo import ACTIVATE, _rows, add

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
