"""出站用量对比 BOM 标准用量（只警告不拦截），以及领料归属工单对出站扣料的影响。"""

from typing import Any

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.mes.execution.tests.test_exec import Line


def _setup(f: Line, bom_qty: float) -> None:
    """工步 10 每片耗 2 个物料；工单锁定的 BOM 在该工序标准用量为 ``bom_qty`` / 片。"""
    m = f.m
    uom = m.fx("uom")
    f.sql(
        "INSERT INTO mes_step_resource (id, tenant_id, route_step_id, resource_kind,"
        " material_id, qty, uom_id, qty_basis) VALUES (gen_random_uuid(), :t, :s,"
        " 'material', :m, 2, :u, 'per_unit')",
        t=m.tid,
        s=f.steps[10]["id"],
        m=f.mat["id"],
        u=uom,
    )
    bom = m.post("bom", {"code": "B1", "name": "b", "product_id": f.product["id"]})
    m.post(
        "bom_line",
        {
            "bom_id": bom["id"],
            "operation_id": f.ops[0]["id"],
            "material_id": f.mat["id"],
            "qty": bom_qty,
            "uom_id": uom,
            "qty_basis": "per_unit",
            "scrap_rate": 0,
        },
    )
    m.action("bom", bom["id"], "status", {"status": "active"})
    # 测试工单在建 Line 时已下达，这里直接补上锁定的 BOM
    f.sql(
        "UPDATE mes_work_order SET bom_id = :b WHERE id = :w",
        b=bom["id"],
        w=f.wo["id"],
    )


def _bom_results(r: Any) -> list[dict[str, Any]]:
    return [x for x in r["results"] if x["check_type"] == "bom_over"]


def test_over_bom_warns_but_does_not_block(client: TestClient, db: Session) -> None:
    f = Line(client, db)
    _setup(f, bom_qty=1)  # 标准 1 / 片 × 2 片 = 2，实际 4
    f.m.post(
        "material_lot",
        {
            "code": "ML1",
            "material_id": f.mat["id"],
            "qty_remaining": 10,
            "uom_id": f.m.fx("uom"),
        },
    )
    (lot,) = f.start(2)
    f.stage(lot, "move_in", equipment_id=f.eq["id"])
    f.stage(lot, "track_in", equipment_id=f.eq["id"])
    r = f.stage(lot, "track_out")
    (w,) = _bom_results(r)
    assert w["result"] == "warn" and "over the BOM quantity" in w["message"]
    assert w["data"]["over"][0]["actual"] == 4 and w["data"]["over"][0]["plan"] == 2
    # 出站扣料明细：物料批反向追溯据此查询
    (use,) = f.sql("SELECT qty FROM mes_lot_material_use")
    assert use[0] == 4


def test_within_bom_has_no_warning(client: TestClient, db: Session) -> None:
    f = Line(client, db)
    _setup(f, bom_qty=2)  # 标准 2 / 片 × 2 片 = 4，实际 4
    f.m.post(
        "material_lot",
        {
            "code": "ML1",
            "material_id": f.mat["id"],
            "qty_remaining": 10,
            "uom_id": f.m.fx("uom"),
        },
    )
    (lot,) = f.start(2)
    f.stage(lot, "move_in", equipment_id=f.eq["id"])
    f.stage(lot, "track_in", equipment_id=f.eq["id"])
    assert _bom_results(f.stage(lot, "track_out")) == []


def test_lot_issued_to_other_work_order_is_not_consumed(
    client: TestClient, db: Session
) -> None:
    f = Line(client, db)
    m = f.m
    _setup(f, bom_qty=2)
    other = m.post(
        "work_order",
        {"product_id": f.product["id"], "lot_type_id": f.lt["id"], "planned_qty": 5},
    )
    uom = m.fx("uom")
    mine = m.post(
        "material_lot",
        {
            "code": "MINE",
            "material_id": f.mat["id"],
            "qty_remaining": 10,
            "uom_id": uom,
        },
    )
    f.sql(  # 模拟领料确认：这一批归属另一个工单
        "UPDATE mes_material_lot SET work_order_id = :w WHERE id = :i",
        w=other["id"],
        i=mine["id"],
    )
    m.post(
        "material_lot",
        {
            "code": "FREE",
            "material_id": f.mat["id"],
            "qty_remaining": 10,
            "uom_id": uom,
        },
    )
    (lot,) = f.start(2)
    cx = f.ctx(lot)
    assert [o["code"] for o in cx["materials"][0]["options"]] == ["FREE"]
