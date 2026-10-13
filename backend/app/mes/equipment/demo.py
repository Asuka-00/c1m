"""设备演示数据（类型、组、E10 状态、工具）。"""

from app.mes.common.demo import _rows, add

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
            initial_state=("e10_state", "SBY-IDLE"),
        )
for c, n, et, days, lots in _rows(
    [
        ("PM-SCAN-W", "Scanner weekly PM", "SCANNER", 7, None),
        ("PM-ETCH-RF", "Etch chamber clean / 50 lots", "DRYETCH", 30, 50),
        ("PM-FURN-M", "Furnace monthly PM", "FURNACE", 30, None),
    ]
):
    add(
        "pm_plan",
        code=c,
        name=n,
        equipment_type=("equipment_type", et),
        interval_days=days,
        interval_lots=lots,
        warn_days=3,
    )
