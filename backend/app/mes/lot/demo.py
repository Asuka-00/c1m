from app.mes.common.demo import ACTIVATE, _rows, add

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
