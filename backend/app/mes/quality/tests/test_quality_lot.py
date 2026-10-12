"""MES phase 4: quality (no SPC) + lot/wafer rules."""

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.testing.mes import API, Mes


def test_dc_plan_and_sampling(client: TestClient, db: Session) -> None:
    m = Mes(client, db)
    nm = m.post("uom", {"code": "NM", "name": "nm", "dimension": "length"})
    op = m.post(
        "operation", {"code": "CD", "name": "CD", "operation_type": "metrology"}
    )
    mi = m.post(
        "measurement_item",
        {"code": "GATE-CD", "name": "Gate CD", "uom_id": nm["id"], "precision": 2},
    )
    plan = m.post(
        "dc_plan", {"code": "DC-CD", "name": "CD plan", "operation_id": op["id"]}
    )
    m.post(
        "dc_plan_item",
        {
            "dc_plan_id": plan["id"],
            "measurement_item_id": mi["id"],
            "sites": 9,
            "lsl": 42,
            "target": 45,
            "usl": 48,
        },
    )
    m.post(
        "dc_plan_item", {"dc_plan_id": plan["id"], "measurement_item_id": mi["id"]}, 409
    )
    mi2 = m.post("measurement_item", {"code": "X", "name": "X"})
    m.post(
        "dc_plan_item",
        {
            "dc_plan_id": plan["id"],
            "measurement_item_id": mi2["id"],
            "lsl": 5,
            "usl": 1,
        },
        422,
    )
    m.post(
        "dc_plan_item",
        {"dc_plan_id": plan["id"], "measurement_item_id": mi2["id"], "sites": 0},
        422,
    )
    m.action("dc_plan", plan["id"], "status", {"status": "active"})
    m.post(
        "dc_plan_item",
        {"dc_plan_id": plan["id"], "measurement_item_id": mi2["id"]},
        409,
    )  # locked
    v2 = m.action("dc_plan", plan["id"], "new-version")
    assert m.list("dc_plan_item", dc_plan_id=v2["id"])["data"][0]["sites"] == 9
    base = {
        "code": "S1",
        "name": "S1",
        "operation_id": op["id"],
        "dc_plan_id": plan["id"],
    }
    m.post("sampling_rule", {**base, "level": "wafer"}, 422)  # wafer_count / selection
    m.post(
        "sampling_rule",
        {
            **base,
            "level": "wafer",
            "wafer_count": 3,
            "wafer_selection": "fixed",
            "fixed_slots": "1,13",
        },
        422,
    )
    m.post(
        "sampling_rule",
        {
            **base,
            "level": "wafer",
            "wafer_count": 3,
            "wafer_selection": "fixed",
            "fixed_slots": "1,13,30",
        },
        422,
    )
    m.post("sampling_rule", {**base, "lot_frequency": 0}, 422)
    m.post(
        "sampling_rule",
        {
            **base,
            "level": "wafer",
            "wafer_count": 3,
            "wafer_selection": "fixed",
            "fixed_slots": "1,13,25",
            "lot_frequency": 4,
        },
    )
    assert m.list("sampling_rule", level="wafer")["count"] == 1


def test_defect_and_reason_codes(client: TestClient, db: Session) -> None:
    m = Mes(client, db)
    m.post(
        "defect_code",
        {
            "code": "PRT",
            "name": "Particle",
            "category": "particle",
            "severity": "major",
            "is_killer": True,
        },
    )
    m.post("defect_code", {"code": "X", "name": "x", "category": "alien"}, 422)
    m.post(
        "reason_code",
        {"code": "EQ-DOWN", "name": "Equipment down", "reason_type": "hold"},
    )
    m.post(
        "reason_code",
        {"code": "EQ-DOWN", "name": "Equipment repaired", "reason_type": "release"},
    )  # unique per type
    m.post(
        "reason_code", {"code": "EQ-DOWN", "name": "dup", "reason_type": "hold"}, 409
    )
    assert m.list("reason_code", reason_type="hold")["count"] == 1
    assert m.list("defect_code", is_killer="true")["count"] == 1


def test_lot_types_priorities_split_merge(client: TestClient, db: Session) -> None:
    m = Mes(client, db)
    hot = m.post(
        "lot_priority", {"code": "HOT", "name": "Hot", "level": 1, "is_hot": True}
    )
    m.post("lot_priority", {"code": "BAD", "name": "x", "level": 0}, 422)
    lot_rule = m.post(
        "code_rule",
        {"code": "LOT", "name": "Lot", "target": "lot", "pattern": "PL{YY}{SEQ}"},
    )
    waf_rule = m.post(
        "code_rule",
        {
            "code": "WAF",
            "name": "Wafer",
            "target": "wafer",
            "pattern": "{LOT}.{SLOT:2}",
        },
    )
    m.post(
        "lot_type", {"code": "BAD", "name": "x", "lot_id_rule_id": waf_rule["id"]}, 422
    )
    lt = m.post(
        "lot_type",
        {
            "code": "PROD",
            "name": "Production",
            "default_priority_id": hot["id"],
            "lot_id_rule_id": lot_rule["id"],
            "wafer_id_rule_id": waf_rule["id"],
        },
    )
    assert lt["lot_id_rule_label"] == "LOT · Lot" and lt["max_wafers"] == 25
    lot = m.action("code-rule", lot_rule["id"], "preview", {"count": 1})["codes"][0]
    wafers = m.action(
        "code-rule", waf_rule["id"], "preview", {"count": 25, "context": {"LOT": lot}}
    )["codes"]
    assert wafers[0] == f"{lot}.01" and wafers[-1] == f"{lot}.25"
    m.post(
        "split_merge_rule",
        {"code": "SM", "name": "x", "lot_type_id": lt["id"], "max_children": 1},
        422,
    )
    m.post(
        "split_merge_rule",
        {
            "code": "SM",
            "name": "Prod rule",
            "lot_type_id": lt["id"],
            "max_children": 4,
            "min_wafers": 5,
        },
    )


def test_qtime_rules(client: TestClient, db: Session) -> None:
    m = Mes(client, db)
    ops = [
        m.post("operation", {"code": c, "name": c})["id"]
        for c in ("CLEAN", "FURNACE", "OTHER")
    ]
    r1 = m.post("route", {"code": "R1", "name": "R1"})
    r2 = m.post("route", {"code": "R2", "name": "R2"})
    s10 = m.post(
        "route_step", {"route_id": r1["id"], "seq": 10, "operation_id": ops[0]}
    )
    s20 = m.post(
        "route_step", {"route_id": r1["id"], "seq": 20, "operation_id": ops[1]}
    )
    x10 = m.post(
        "route_step", {"route_id": r2["id"], "seq": 10, "operation_id": ops[2]}
    )
    base = {"code": "Q1", "name": "Clean→furnace", "route_id": r1["id"]}
    m.post(
        "qtime_rule",
        {
            **base,
            "from_step_id": s10["id"],
            "to_step_id": s20["id"],
            "max_minutes": 240,
            "action": "rework",
        },
    )
    m.post(
        "qtime_rule",
        {
            **base,
            "code": "Q2",
            "from_step_id": s20["id"],
            "to_step_id": s10["id"],
            "max_minutes": 1,
        },
        422,
    )
    m.post(
        "qtime_rule",
        {
            **base,
            "code": "Q2",
            "from_step_id": s10["id"],
            "to_step_id": x10["id"],
            "max_minutes": 1,
        },
        422,
    )
    m.post(
        "qtime_rule",
        {**base, "code": "Q2", "from_step_id": s10["id"], "to_step_id": s20["id"]},
        422,
    )
    m.post(
        "qtime_rule",
        {
            **base,
            "code": "Q2",
            "from_step_id": s10["id"],
            "to_step_id": s20["id"],
            "min_minutes": 60,
            "max_minutes": 30,
        },
        422,
    )
    rows = m.list("qtime_rule", route_id=r1["id"])["data"]
    assert rows[0]["from_step_label"] == "10 · CLEAN" and rows[0]["action"] == "rework"
    meta = client.get(f"{API}/_meta", headers=m.h).json()
    q = next(e for e in meta["entities"] if e["code"] == "qtime_rule")
    assert next(f for f in q["fields"] if f["name"] == "to_step")["depends"] == "route"
