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
    assert d["code"] == "transform_undo_blocked" and d["reason"] == "lots_blocked"
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
    # 追溯返回带转换 id（前端在追溯页提供撤销入口）
    tr = f.c.get(
        f"{EXEC}/trace", headers=f.m.h, params={"kind": "lot", "code": lot["code"]}
    ).json()
    assert [x["transform_id"] for x in tr["forward"]["lots"]] == [tid]
    tr = f.c.get(
        f"{EXEC}/trace", headers=f.m.h, params={"kind": "lot", "code": ch["code"]}
    ).json()
    assert [x["transform_id"] for x in tr["backward"]["lots"]] == [tid]
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
    assert out["undone_at"].endswith("Z") and out["undone_by"]
    assert out["carrier_restored"] is False
    assert hs[0]["details"]["carrier_restored"] is False
    # D54-2：转换记录保留并标记撤销，输出已删
    trs = m.list("unit_transform", id=tid)["data"]
    assert len(trs) == 1 and trs[0]["undone_at"].endswith("Z")
    assert m.list("unit_transform_output", unit_transform=tid)["count"] == 0
    # 再撤一次：已撤销 → 409，lots 为空
    d = f.post(f"{TF}/{tid}/undo", {}, 409)["detail"]
    assert d["code"] == "transform_undo_blocked" and d["lots"] == []
    assert d["reason"] == "already_undone"
    # TRF-11c：撤销后可以再次转换，谱系无残留
    r2 = f.post(TF, _body(f, [lot], src))
    assert f.lot(lot)["lot_status"] == "converted"
    g = m.list("lot_genealogy", parent_lot=lot["id"])["data"]
    assert [x["child_lot_id"] for x in g] == [r2["children"][0]["id"]]


def test_migration_0027_up_down() -> None:
    """0027 可重复执行：mes_unit_transform 的三个撤销列。"""
    from app.mes.equipment.tests.test_qual import _migration_roundtrip

    cols = ("undone_at", "undone_by", "undo_reason")

    def check(i: Any) -> tuple[frozenset[str], bool]:
        have = {c["name"] for c in i.get_columns("mes_unit_transform")}
        return frozenset(set(cols) & have), True

    _migration_roundtrip("0026_tool_life", "b6", check, cols)


def test_transform_undo_referenced_child_lists_lots(
    client: TestClient, db: Session
) -> None:
    """D58：子批被其他记录引用（外键）→ 409 lots_blocked，lots 逐批列出引用表（原先为空）。"""
    f = _line(client, db)
    lot = _start(f)
    _maps(f, [w["code"] for w in _wafers(f, lot)])
    r, _src = _transform(f, lot)
    tid, (ch,) = r["transform"]["id"], r["children"]
    # 绕过前置检查：直接在一张 RESTRICT 外键表里引用子批（报警关联批次）
    et = f.eq["equipment_type_id"]
    f.sql(
        "INSERT INTO mes_alarm_log (id, tenant_id, equipment_id, alid, alarm_status, set_at, source) VALUES (gen_random_uuid(), :t, :e, 'X', 'cleared', now(), 'manual')",
        t=f.m.tid,
        e=f.eq["id"],
    )
    f.sql(
        "INSERT INTO mes_alarm_lot (id, tenant_id, alarm_log_id, lot_id) SELECT gen_random_uuid(), :t, id, :l FROM mes_alarm_log WHERE tenant_id = :t AND alid = 'X'",
        t=f.m.tid,
        l=ch["id"],
    )
    d = f.post(f"{TF}/{tid}/undo", {}, 409)["detail"]
    assert d["code"] == "transform_undo_blocked" and d["reason"] == "lots_blocked"
    assert d["lots"] == [
        {
            "lot_id": ch["id"],
            "lot_code": ch["code"],
            "reason": "referenced",
            "tables": ["mes_alarm_lot"],
        }
    ]
    assert f.lot(lot)["lot_status"] == "converted"  # 整体回滚
    assert et
