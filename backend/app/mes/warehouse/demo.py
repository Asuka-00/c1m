"""仓储演示数据（入库单号规则、仓库、库位）。"""

from app.mes.common.demo import add

# ---------------- warehouse: code rule, warehouses, locations ----------------
add(
    "code_rule",
    code="RCV_NO",
    name="Receipt no. (DEMO)",
    target="receipt",
    pattern="RCV{YY}{MM}{SEQ}",
    seq_width=4,
    seq_reset="monthly",
)
WAREHOUSES = [
    ("WH-FG", "Wafer FG store (DEMO)", "FAB12", "finished_goods", "Chen"),
    ("WH-QA", "Quarantine store (DEMO)", "FAB12", "quarantine", "Lin"),
    ("WH-ASSY", "Assembly FG store (DEMO)", "TEST1", "finished_goods", "Wang"),
]
for c, n, site, tp, keeper in WAREHOUSES:
    add(
        "warehouse",
        code=c,
        name=n,
        site=("site", site),
        warehouse_type=tp,
        keeper=keeper,
    )
LOCATIONS = [
    ("FG-N2-01", "N2 cabinet 01", "WH-FG", "dry_cabinet", 24),
    ("FG-N2-02", "N2 cabinet 02", "WH-FG", "dry_cabinet", 24),
    ("FG-R-A01", "Rack A-01", "WH-FG", "rack", 40),
    ("QA-B-01", "Hold bin 01", "WH-QA", "bin", 10),
    ("AS-R-01", "Assembly rack 01", "WH-ASSY", "rack", None),
]
for c, n, wh, tp, cap in LOCATIONS:
    add(
        "storage_location",
        code=c,
        name=f"{n} (DEMO)",
        warehouse=("warehouse", wh),
        location_type=tp,
        capacity=cap,
    )
