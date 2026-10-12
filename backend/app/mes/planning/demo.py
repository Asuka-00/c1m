from app.mes.common.demo import add

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

# released + started after seeding: (wo, [(qty, carrier code | None)])
STARTS: list[tuple[str, list[tuple[int, str | None]]]] = [
    ("WO-DEMO-01", [(25, "FP0001"), (15, None)]),
    ("WO-DEMO-03", [(1000, None), (600, None)]),
]
