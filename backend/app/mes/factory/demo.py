"""Factory demo data (dictionaries, code rules, sites, areas, work centers, shifts, calendars)."""

from app.mes.common.demo import _rows, add

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
