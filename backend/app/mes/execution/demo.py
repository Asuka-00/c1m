"""执行演示数据（检查规则/方案、线边物料、工具、装配线）及演示作业。"""

import uuid
from datetime import date, timedelta
from typing import Any

import sqlalchemy as sa
from sqlmodel import Session

from app.core.spec.base import conn
from app.core.spec.engine import TABLES
from app.mes.common.demo import ACTIVATE, _resolve, _rows, add
from app.mes.execution.checks.types import chambers_of

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
    ("CR-CHMB", "Chamber selected", "chamber_required", "block", {}),
    ("CR-BATCH", "Batch: same step", "batch_same_step", "block", {}),
    ("CR-SORT", "Sort keeps wafer order", "sort_order", "warn", {}),
    ("CR-CARR-CLN", "Carrier cleaning due", "carrier_clean", "warn", {}),
    ("CR-CARR-USE", "Carrier usage limit", "carrier_usage", "block", {}),
    (
        "CR-CHMB-E10",
        "Chamber available (E10 SBY/PRD)",
        "chamber_available",
        "block",
        {},
    ),
    ("CR-QT", "Q-Time window", "qtime", "block", {}),
    ("CR-PM", "Equipment PM not overdue", "pm_due", "block", {}),
    ("CR-RCP-MAP", "Recipe ↔ equipment mapping", "recipe_match", "warn", {}),
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
        [
            "CR-E10",
            "CR-CAP",
            "CR-RCP",
            "CR-TOOL",
            "CR-CARR",
            "CR-MAT",
            "CR-CHMB",
            "CR-CHMB-E10",
            "CR-BATCH",
            "CR-CARR-CLN",
            "CR-CARR-USE",
        ],
    ),
    (
        "CP-TI-LITHO",
        "Litho track-in (+ reticle)",
        ["CR-E10", "CR-CAP", "CR-RCP", "CR-RET"],
    ),
    ("CP-SORT", "Wafer sort", ["CR-SORT"]),
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
        ("sort", "CP-SORT"),
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
for c, sn, used, mx, exp in _rows(
    [
        ("PAD-0001", "IC1010-A1", 120, 500, "2027-06-30"),
        ("PAD-0002", "IC1010-A2", 470, 500, "2026-10-15"),
        ("PAD-0003", "IC1010-A3", 500, 500, "2027-06-30"),
    ]
):
    add(
        "tool",
        code=c,
        fixture=("fixture", "PAD-CMP"),
        serial_no=sn,
        usage_count=used,
        max_usage=mx,
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
    "split_merge_rule",
    code="SM-ASSY",
    name="Assembly split/merge (DEMO)",
    lot_type=("lot_type", "ASSY"),
    max_children=5,
    min_wafers=50,
)
add(
    "work_order",
    code="WO-DEMO-03",
    due_date=date.today() + timedelta(days=2),
    product=("product", "PKG-A100@1"),
    lot_type=("lot_type", "ASSY"),
    planned_qty=2000,
    remarks="Assembly – quantity tracked (DEMO)",
)


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
    from app.mes.execution import service as ex

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
            if stage == "track_in":
                # 带腔体的设备默认选第一个腔体
                chs = chambers_of(session, tid, {"id": body["equipment_id"]})
                body["chamber_ids"] = [str(c["id"]) for c in chs[:1]]
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
    if len(lots) > 3:  # split / merge example on the second assembly lot
        from app.mes.execution import service as sm

        lot = lots[3]
        r = sm.split(
            session,
            tid,
            lot["id"],
            {
                "children": [{"qty": 200}, {"qty": 100}],
                "comment": "Split for line balance (DEMO)",
            },
            admin,
        )
        sm.merge(
            session,
            tid,
            lot["id"],
            {
                "source_lot_ids": [r["children"][1]["id"]],
                "comment": "Re-merge after rework check (DEMO)",
            },
            admin,
        )
