"""出货单（只出已入库批次、可出货数、履历与追溯）、来料接收单（待检物料批与 IQC 判定）。"""

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.mes.execution.tests.test_exec import API, Line
from app.mes.warehouse.tests.test_receiving import Store, _msgs
from app.testing.mes import Mes


def _act(m: Mes, path: str, rid: str, action: str, status: int = 200) -> Any:
    r = m.c.post(f"{API}/{path}/{rid}/transition", headers=m.h, json={"action": action})
    assert r.status_code == status, r.text
    return r.json()


def _stored_lot(s: Store, good: int = 4, scrap: int = 1) -> dict[str, Any]:
    (lot,) = s.finished(good + scrap)
    rc = s.receipt((lot, good, scrap))
    s.act(rc, "submit")
    s.act(rc, "confirm")
    lot = s.f.lot(lot)
    assert lot["lot_status"] == "stored"
    return lot  # type: ignore[no-any-return]


def test_shipment_flow(client: TestClient, db: Session) -> None:
    s = Store(client, db)
    m = s.m
    lot = _stored_lot(s)  # 良品 4
    (unreceived,) = s.finished(2)  # 完工但未入库
    sh = m.post("shipment", {"code": "SH1", "customer": "ACME"})
    assert sh["issue_status"] == "draft"

    def line(
        shipment: dict[str, Any], lot_: dict[str, Any], qty: int, status: int
    ) -> Any:
        return m.post(
            "shipment_line",
            {"shipment_id": shipment["id"], "lot_id": lot_["id"], "qty": qty},
            status,
        )

    # 只有已入库批次可出货（批次状态机错误：detail 为对象）
    assert line(sh, unreceived, 1, 422)["detail"]["lot_status"] == "completed"
    assert "only 4 left to ship" in _msgs(line(sh, lot, 5, 422))
    assert line(sh, lot, 3, 200)["product_id"] == lot["product_id"]
    assert _act(m, "shipment", sh["id"], "confirm")["issue_status"] == "confirmed"
    lot = s.f.lot(lot)
    assert lot["shipped_qty"] == 3 and lot["lot_status"] == "stored"
    # 已出 3，只剩 1
    sh2 = m.post("shipment", {"code": "SH2", "customer": "ACME"})
    assert "only 1 left to ship" in _msgs(line(sh2, lot, 2, 422))
    line(sh2, lot, 1, 200)
    # 已确认的出货单不能改 / 删 / 再确认
    m.delete("shipment", sh["id"], 422)
    assert "cannot confirm" in _msgs(_act(m, "shipment", sh["id"], "confirm", 422))
    assert "add at least one line" in _msgs(
        _act(
            m,
            "shipment",
            m.post("shipment", {"code": "SH3", "customer": "X"})["id"],
            "confirm",
            422,
        )
    )
    _act(m, "shipment", sh2["id"], "confirm")
    assert s.f.lot(lot)["shipped_qty"] == 4
    hist = m.list("lot_history", lot=lot["id"], page_size=100)["data"]
    assert [h["action"] for h in hist].count("ship") == 2
    # 追溯：批次正向能看到出货记录（客户 / 数量）
    r = client.get(
        f"{API}/exec/trace", headers=m.h, params={"kind": "lot", "code": lot["code"]}
    )
    assert r.status_code == 200, r.text
    shipped = r.json()["forward"]["shipments"]
    assert [(x["shipment"], x["customer"], x["qty"]) for x in shipped] == [
        ("SH1", "ACME", 3),
        ("SH2", "ACME", 1),
    ]


def test_material_receipt_and_iqc(client: TestClient, db: Session) -> None:
    f = Line(client, db)
    m = f.m
    uom = m.fx("uom")
    mt = m.post("material_type", {"code": "MT2", "name": "mt", "category": "gas"})
    mat = m.post(
        "material",
        {
            "code": "GAS",
            "name": "gas",
            "material_type_id": mt["id"],
            "uom_id": uom,
            "shelf_life_days": 30,
        },
    )
    rc = m.post("material_receipt", {"code": "IN1", "supplier": "VendorA"})
    assert "add at least one line" in _msgs(
        _act(m, "material-receipt", rc["id"], "confirm", 422)
    )

    def line(**kw: Any) -> dict[str, Any]:
        return m.post(
            "material_receipt_line",
            {
                "material_receipt_id": rc["id"],
                "material_id": mat["id"],
                "uom_id": uom,
                **kw,
            },
        )

    a = line(qty=5, supplier_lot="SL-9")
    b = line(qty=2, expiry_date="2030-01-01")
    m.post(
        "material_receipt_line",
        {
            "material_receipt_id": rc["id"],
            "material_id": mat["id"],
            "uom_id": uom,
            "qty": 0,
        },
        422,
    )

    def iqc(line_: dict[str, Any], result: str, status: int = 200) -> Any:
        r = m.c.post(
            f"{API}/material-receipt/lines/{line_['id']}/iqc",
            headers=m.h,
            json={"result": result},
        )
        assert r.status_code == status, r.text
        return r.json()

    assert "confirm the receipt first" in _msgs(iqc(a, "pass", 422))
    assert (
        _act(m, "material-receipt", rc["id"], "confirm")["issue_status"] == "confirmed"
    )
    # 每行生成待检（hold）物料批；未填有效期按保质期推算
    la = m.list("material_lot", q="IN1-1")["data"][0]
    assert (la["ml_status"], la["qty_remaining"], la["supplier_lot"]) == (
        "hold",
        5,
        "SL-9",
    )
    assert la["expiry_date"] == str(datetime.now(UTC).date() + timedelta(days=30))
    assert m.list("material_lot", q="IN1-2")["data"][0]["expiry_date"] == "2030-01-01"
    # IQC：合格可用，不合格拒收；不能重复判定
    assert iqc(a, "pass")["iqc_result"] == "pass"
    assert m.list("material_lot", q="IN1-1")["data"][0]["ml_status"] == "available"
    assert iqc(b, "fail")["iqc_result"] == "fail"
    assert m.list("material_lot", q="IN1-2")["data"][0]["ml_status"] == "rejected"
    assert "already judged" in _msgs(iqc(a, "fail", 422))
    iqc(a, "maybe", 422)
    # 已确认的接收单不能取消
    assert "cannot cancel" in _msgs(
        _act(m, "material-receipt", rc["id"], "cancel", 422)
    )
