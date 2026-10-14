"""B2 验收（D28，bom.md v1.1 §3 / §10 / §11）：单位换算精度与计件整数；用料记录
（source / usage_type）；出站按工序累计比对 BOM 计划用量（返工不计、换算后比较），
超量只提示、写批次履历 bom_over_consumption。"""

from typing import Any

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.mes.execution.tests.test_exec import EXEC, Line
from app.testing.mes import API


def _res(f: Line, seq: int, uom: str, qty: float) -> None:
    f.sql(
        "INSERT INTO mes_step_resource (id, tenant_id, route_step_id, resource_kind,"
        " material_id, qty, uom_id, qty_basis) VALUES (gen_random_uuid(), :t, :s,"
        " 'material', :m, :qty, :u, 'per_unit')",
        t=f.m.tid,
        s=f.steps[seq]["id"],
        m=f.mat["id"],
        qty=qty,
        u=uom,
    )


def _get(f: Line, url: str, status: int = 200, **params: Any) -> Any:
    r = f.c.get(url, headers=f.m.h, params=params)
    assert r.status_code == status, r.text
    return r.json()


def test_uom_precision_and_count_units(client: TestClient, db: Session) -> None:
    f = Line(client, db)
    m = f.m
    ea = m.fx("uom")  # count
    box = m.post("uom", {"code": "BOX", "name": "box", "dimension": "count"})["id"]
    g = m.post("uom", {"code": "G", "name": "g", "dimension": "mass"})["id"]
    kg = m.post("uom", {"code": "KG", "name": "kg", "dimension": "mass"})["id"]
    m.post("uom_conversion", {"from_uom_id": box, "to_uom_id": ea, "factor": 3})
    m.post("uom_conversion", {"from_uom_id": kg, "to_uom_id": g, "factor": 1000})
    conv = f"{API}/_convert"
    # 6 位小数四舍五入
    assert _get(f, conv, from_uom=g, to_uom=kg, value=1.2345678)["value"] == 0.001235
    assert _get(f, conv, from_uom=box, to_uom=ea, value=2)["value"] == 6
    # 换算到计件单位不是整数 → 422
    r = _get(f, conv, 422, from_uom=ea, to_uom=box, value=4)
    assert "whole number" in str(r)
    # 计件单位录入非整数 → 422；质量单位可带小数（保留 6 位）
    base = {"material_id": f.mat["id"], "expiry_date": "2030-01-01"}
    r = m.post(
        "material_lot", {**base, "code": "X1", "qty_remaining": 1.5, "uom_id": ea}, 422
    )
    assert "qty_remaining" in str(r)
    ok = m.post(
        "material_lot",
        {**base, "code": "X2", "qty_remaining": 1.23456789, "uom_id": g},
    )
    assert ok["qty_remaining"] == 1.234568 and ok["initial_qty"] == 1.234568
    m.post("material_lot", {**base, "code": "X3", "qty_remaining": 2, "uom_id": ea})


def test_track_out_bom_comparison(client: TestClient, db: Session) -> None:
    f = Line(client, db, {20: {"rework_return": "same_step"}})
    m = f.m
    g = m.post("uom", {"code": "G", "name": "g", "dimension": "mass"})["id"]
    kg = m.post("uom", {"code": "KG", "name": "kg", "dimension": "mass"})["id"]
    m.post("uom_conversion", {"from_uom_id": kg, "to_uom_id": g, "factor": 1000})
    _res(f, 10, g, 1.5)  # OP0：每片 1.5 g
    _res(f, 20, g, 2)  # OP1：每片 2 g
    m.post(
        "material_lot",
        {
            "code": "MLG",
            "material_id": f.mat["id"],
            "qty_remaining": 100,
            "uom_id": g,
            "expiry_date": "2030-01-01",
        },
    )
    bom = m.post("bom", {"product_id": f.product["id"]})
    line = {"bom_id": bom["id"], "component_type": "material", "consume_mode": "issue"}
    # OP0 计划 1 g/片（会超量）；OP1 计划 0.002 kg/片 + 10% 损耗（换算后比较）
    m.post(
        "bom_line",
        {
            **line,
            "line_no": 10,
            "material_id": f.mat["id"],
            "qty": 1,
            "uom_id": g,
            "operation_id": f.ops[0]["id"],
        },
    )
    m.post(
        "bom_line",
        {
            **line,
            "line_no": 20,
            "material_id": f.mat["id"],
            "qty": 0.002,
            "uom_id": kg,
            "scrap_rate": 0.1,
            "operation_id": f.ops[1]["id"],
        },
    )
    r = client.post(f"{API}/bom/{bom['id']}/activate", headers=m.h)
    assert r.status_code == 200, r.text
    (lot,) = f.start(2)
    # OP0：实际 3 g > 计划 2 g → 只提示，出站成功
    f.stage(lot, "move_in", equipment_id=f.eq["id"])
    f.stage(lot, "track_in", equipment_id=f.eq["id"])
    out = f.stage(lot, "track_out")
    assert f.lot(lot)["lot_status"] == "tracked_out"
    (w,) = out["warnings"]
    assert w["code"] == "bom_over_consumption"
    assert [(x["line_no"], x["planned"], x["actual"]) for x in w["lines"]] == [
        (10, 2, 3)
    ]
    h = m.list("lot_history", lot=lot["id"], action="bom_over_consumption")["data"]
    assert len(h) == 1 and h[0]["details"]["lines"][0]["material"] == f.mat["code"]
    f.stage(lot, "move_out")
    # OP1：4 g = 0.004 kg ≤ 2 × 0.002 × 1.1 = 0.0044 kg → 无提示
    f.stage(lot, "move_in", equipment_id=f.eq["id"])
    f.stage(lot, "track_in", equipment_id=f.eq["id"])
    out = f.stage(lot, "track_out")
    assert out["warnings"] == []
    assert [(x["planned"], x["actual"], x["over"]) for x in out["bom_usage"]] == [
        (0.0044, 0.004, False)
    ]
    # 返工后回到同一工步重做：用量记为 rework，不参与比对
    f.stage(lot, "move_out", rework=True)
    f.run_step(lot)
    f.stage(lot, "move_in", equipment_id=f.eq["id"])
    f.stage(lot, "track_in", equipment_id=f.eq["id"])
    out = f.stage(lot, "track_out")
    assert out["warnings"] == [] and out["bom_usage"][0]["actual"] == 0.004
    recs = m.list("material_consumption", lot=lot["id"])["data"]
    assert sorted((float(x["qty"]), x["usage_type"], x["source"]) for x in recs) == [
        (3.0, "normal", "step_resource"),
        (4.0, "normal", "step_resource"),
        (4.0, "rework", "step_resource"),
    ]
    # 用量总览：全部 issue 明细的累计正常用量
    u = _get(f, f"{EXEC}/lots/{lot['id']}/bom-usage")
    assert u["bom_version"] == 1 and u["basis"] == 2
    assert [(x["line_no"], x["actual"], x["over"]) for x in u["lines"]] == [
        (10, 3, True),
        (20, 0.004, False),
    ]
    assert _get(f, f"{EXEC}/lots/{f.wo['id']}/bom-usage", 404)
