"""P2 撤销单位转换（D41 / bom.md Q4，TRF-11 / 11b / 11c、RBAC-04）。"""

from typing import Any

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.mes.execution.tests.test_exec import EXEC
from app.mes.execution.tests.test_split_merge import _line
from app.mes.execution.tests.test_transform import TF, _body, _maps, _start, _wafers
from app.mes.map.tests.test_map_import import MAP
from app.mes.product.tests.test_bom import _member


def _transform(f: Any, lot: Any) -> Any:
    ws = _wafers(f, lot)
    src = []
    for w in ws:
        m = f.c.get(f"{MAP}/substrates/{w['code']}", headers=f.m.h).json()
        src.append({"wafer_id": w["id"], "qty": m["good_qty"]})
    return f.post(TF, _body(f, [lot], src)), src


def test_transform_undo(client: TestClient, db: Session) -> None:
    f = _line(client, db)
    lot = _start(f)
    _maps(f, [w["code"] for w in _wafers(f, lot)])
    r, src = _transform(f, lot)
    tid, (ch,) = r["transform"]["id"], r["children"]
    url = f"{TF}/{tid}/undo"
    # 权限先于请求体（D34）；未知字段 422
    hm = _member(client, db, f.m)
    f.post(url, {"bogus": 1}, 403, h=hm)
    f.post(url, {"bogus": 1}, 422)
    # TRF-11b：子批进站后不能撤销
    f.stage(ch, "move_in", equipment_id=f.eq["id"])
    d = f.post(url, {}, 409)["detail"]
    assert d["code"] == "transform_undo_blocked"
    assert d["lots"] == [
        {"lot_id": ch["id"], "lot_code": ch["code"], "reason": "lot_status"}
    ]
    assert f.lot(lot)["lot_status"] == "converted"


def test_transform_undo_restores_and_retransform(
    client: TestClient, db: Session
) -> None:
    f = _line(client, db)
    lot = _start(f)
    _maps(f, [w["code"] for w in _wafers(f, lot)])
    r, src = _transform(f, lot)
    tid, (ch,) = r["transform"]["id"], r["children"]
    # TRF-11：撤销（不带请求体也可以）
    res = f.c.post(f"{TF}/{tid}/undo", headers=f.m.h)
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["removed_children"] == [ch["code"]]
    assert out["parents"][0]["lot_status"] == "waiting"
    assert f.lot(lot)["lot_status"] == "waiting"
    ws = f.m.list("wafer", lot=lot["id"])["data"]
    assert {w["wafer_status"] for w in ws} == {"waiting"}
    assert f.c.get(f"{EXEC}/lots/{ch['id']}", headers=f.m.h).status_code == 404
    m = f.m
    assert m.list("unit_transform_input", unit_transform=tid)["count"] == 0
    assert m.list("unit_origin", child_lot=ch["id"])["count"] == 0
    assert m.list("lot_genealogy", parent_lot=lot["id"])["count"] == 0
    hs = m.list("lot_history", lot=lot["id"], action="transform_undo")["data"]
    assert len(hs) == 1 and hs[0]["at"].endswith("Z")
    # 再撤一次：转换已不存在
    f.post(f"{TF}/{tid}/undo", {}, 404)
    # TRF-11c：撤销后可以再次转换，谱系无残留
    r2 = f.post(TF, _body(f, [lot], src))
    assert f.lot(lot)["lot_status"] == "converted"
    g = m.list("lot_genealogy", parent_lot=lot["id"])["data"]
    assert [x["child_lot_id"] for x in g] == [r2["children"][0]["id"]]
