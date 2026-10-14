"""B8 按 bin 拆批：坐标图 bin 数量、排除类按 bin_type、check_split 守恒、子批带 bin_code
并继承客户、die 坐标反查、事件记下坐标图版本与定义集版本、人工录入需原因码、分组输出、
严格载荷与先查权限、0 基路径、带 Z 时间；D41 Q-Time 起点沿用母批（取最早）；迁移 0024。"""

import uuid
from datetime import timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.mes.execution.tests.test_exec import EXEC
from app.mes.execution.tests.test_split_merge import _line
from app.mes.execution.tests.test_transform import MAP, _maps, _start, _wafers
from app.mes.product.tests.test_bom import _member

BS = f"{EXEC}/bin-split"


def _setup(f: Any, **lot: Any) -> tuple[Any, list[Any]]:
    a = _start(f, **lot)
    ws = _wafers(f, a)
    _maps(f, [w["code"] for w in ws])  # 样例图：2 片晶圆、bin 1/2/3/E（E=edge 排除）
    return a, ws


def test_bin_split_map_customer_coords(client: TestClient, db: Session) -> None:
    f = _line(client, db)
    c1 = f.m.post("customer", {"code": "C1", "name": "Cust 1"})
    a, ws = _setup(
        f, ownership="customer", customer_id=c1["id"], customer_lot_no="CL-1"
    )
    body = {"input_lot_ids": [a["id"]]}
    pv = f.post(f"{BS}/preview", body)
    by = {x["wafer"]: x for x in pv["inputs"]}
    w1 = by[ws[0]["code"]]
    assert w1["bin_source"] == "map" and w1["bin_set"] == {
        "code": "BINSET-DEMO",
        "version": 1,
    }
    assert w1["split_counts"] == {"1": 24, "2": 4, "3": 4} and w1["excluded_qty"] == 4
    assert all(x["conserved"] for x in pv["inputs"])
    assert [(o["bin_code"], o["qty"]) for o in pv["outputs"]] == [
        ("1", 44),
        ("2", 7),
        ("3", 13),
    ]
    # 分组：bin 2、3 合成一个子批；漏掉 bin → 422 bin_split_unassigned
    d = f.post(f"{BS}/preview", {**body, "outputs": [{"bin_codes": ["1"]}]}, 422)
    assert d["detail"]["code"] == "bin_split_unassigned"
    assert d["detail"]["bin_codes"] == ["2", "3"]
    d = f.post(
        f"{BS}/preview",
        {**body, "outputs": [{"bin_codes": ["1", "E"]}, {"bin_codes": ["1"]}]},
        422,
    )["detail"]
    assert [x["loc"] for x in d] == [
        ["body", "outputs", 0, "bin_codes", 1],
        ["body", "outputs", 1, "bin_codes", 0],
    ], d
    # 有坐标图不许人工录入
    mb = [{"wafer_id": ws[0]["id"], "bins": [{"bin_code": "1", "qty": 1}]}]
    d = f.post(f"{BS}/preview", {**body, "manual_bins": mb}, 422)["detail"]
    assert d[0]["loc"] == ["body", "manual_bins", 0, "wafer_id"], d
    r = f.post(
        BS, {**body, "outputs": [{"bin_codes": ["1"]}, {"bin_codes": ["2", "3"]}]}
    )
    good, bad = r["children"]
    assert (good["bin_code"], good["qty"]) == ("1", 44)
    assert (bad["bin_code"], bad["qty"]) == ("2,3", 20)
    for ch in (good, bad):
        c = f.lot(ch)
        assert (c["customer_id"], c["customer_lot_no"]) == (c1["id"], "CL-1")
        # 未给 route：留在母批当前工步
        assert c["current_step_id"] == a["current_step_id"]
        assert c["lot_status"] == "waiting" and c["tracking_level"] == "quantity"
    assert f.lot(a)["lot_status"] == "converted"
    t = r["transform"]
    assert t["transform_type"] == "bin_split" and t["at"].endswith("Z")
    assert t["source"] == "manual" and t["external_event_id"] is None
    ins = f.m.list("unit_transform_input", unit_transform=t["id"])["data"]
    assert {x["bin_set_version"] for x in ins} == {1}
    assert all(x["bin_set_id"] and x["substrate_map_id"] for x in ins)
    assert {x["bin_counts"]["E"] for x in ins} == {4}
    # 每颗 die 可反查：坐标 + bin 码 + 母晶圆
    og = f.m.list("unit_origin", child_lot=bad["id"], page_size=100)["data"]
    assert len(og) == 20 and {o["bin_code"] for o in og} == {"2", "3"}
    assert all(o["die_row"] is not None and o["parent_wafer_id"] for o in og)
    cells = {
        (c["row"], c["col"]): c["bin_code"]
        for c in f.c.get(f"{MAP}/substrates/{ws[0]['code']}", headers=f.m.h).json()[
            "cells"
        ]
    }
    for o in og:
        if o["parent_wafer_id"] == ws[0]["id"]:
            assert cells[(o["die_row"], o["die_col"])] == o["bin_code"]
    assert f.m.list("lot", bin_code="1")["count"] == 1
    tr = f.c.get(
        f"{EXEC}/trace", headers=f.m.h, params={"kind": "lot", "code": good["code"]}
    ).json()
    assert len(tr["backward"]["origins"]) == 44


def test_bin_split_manual_and_errors(client: TestClient, db: Session) -> None:
    f = _line(client, db, {"product": {"gross_die": 10}})
    a = _start(f)
    wa = _wafers(f, a)
    body = {"input_lot_ids": [a["id"]]}
    d = f.post(f"{BS}/preview", body, 422)["detail"]
    assert d[0]["loc"] == ["body", "manual_bins"], d

    def mb(q1: int) -> list[Any]:
        return [
            {
                "wafer_id": w["id"],
                "bins": [{"bin_code": "1", "qty": q1}, {"bin_code": "2", "qty": 2}],
            }
            for w in wa
        ]

    d = f.post(f"{BS}/preview", {**body, "manual_bins": mb(8)}, 422)["detail"]
    assert d[0]["loc"] == ["body", "reason_id"], d
    rs = f.reasons["scrap"]["id"]
    d = f.post(f"{BS}/preview", {**body, "manual_bins": mb(7), "reason_id": rs}, 422)
    assert d["detail"]["code"] == "bin_split_qty_mismatch"
    assert d["detail"]["loc"] == ["body", "manual_bins", 0, "bins"]
    r = f.post(BS, {**body, "manual_bins": mb(8), "reason_id": rs})
    assert [(c["bin_code"], c["qty"]) for c in r["children"]] == [("1", 16), ("2", 4)]
    og = f.m.list("unit_origin", child_lot=r["children"][0]["id"])["data"]
    assert {(o["qty"], o["bin_code"], o["die_row"]) for o in og} == {(8, "1", None)}
    # 严格载荷 / 先查权限
    for k in ("source", "external_event_id", "transform_type"):
        d = f.post(f"{BS}/preview", {**body, k: "x"}, 422)["detail"]
        assert d[0]["loc"] == ["body", k], d
    bad = {**body, "manual_bins": [{"wafer_id": wa[0]["id"], "bins": [{"q": 1}]}]}
    d = f.post(f"{BS}/preview", bad, 422)["detail"]
    assert ["body", "manual_bins", 0, "bins", 0, "q"] in [x["loc"] for x in d]
    r2 = f.c.post(BS, headers=_member(client, db, f.m), json={"bad": 1})
    assert r2.status_code == 403 and "loc" not in r2.text


def test_d41_qtime_carried_to_children(client: TestClient, db: Session) -> None:
    """D41：子批沿用母批已开始计时的 Q-Time 起点；多个母批取最早。"""
    f = _line(client, db, {"product": {"gross_die": 10}})
    f.m.post(
        "qtime_rule",
        {
            "code": "QT",
            "name": "q",
            "route_id": f.route["id"],
            "from_step_id": f.steps[10]["id"],
            "to_step_id": f.steps[20]["id"],
            "max_minutes": 600,
        },
    )
    a, b = _start(f), _start(f)
    for x in (a, b):
        f.run_step(x)  # 10 → 20，Q-Time 开始计时
    # 把 a 的起点往前挪 120 分钟、b 往前 30 分钟
    for x, mins in ((a, 120), (b, 30)):
        f.sql(
            "UPDATE mes_lot_history SET at = at - make_interval(mins => :m) "
            "WHERE lot_id = :l AND action = 'move_out'",
            m=mins,
            l=x["id"],
        )
    q = {x["rule"]: x for x in f.ctx(a)["qtime"]}["QT"]
    assert q["minutes"] >= 119
    ws = [w for x in (a, b) for w in _wafers(f, x)]
    mbins = [{"wafer_id": w["id"], "bins": [{"bin_code": "1", "qty": 10}]} for w in ws]
    r = f.post(
        BS,
        {
            "input_lot_ids": [a["id"], b["id"]],
            "manual_bins": mbins,
            "reason_id": f.reasons["scrap"]["id"],
        },
    )
    (ch,) = r["children"]
    cq = {x["rule"]: x for x in f.ctx(ch)["qtime"]}["QT"]
    # 取最早（a 的）起点，不是重新开始，也不是 b 的
    assert cq["minutes"] >= 119, cq
    # B5 单位转换同样沿用（子批从新路线首工步开始，起点仍是母批的）
    c = _start(f)
    f.run_step(c)
    f.sql(
        "UPDATE mes_lot_history SET at = at - interval '45 minutes' "
        "WHERE lot_id = :l AND action = 'move_out'",
        l=c["id"],
    )
    src = [{"wafer_id": w["id"], "qty": 10} for w in _wafers(f, c)]
    r = f.post(
        f"{EXEC}/transform",
        {
            "transform_type": "dicing",
            "input_lot_ids": [c["id"]],
            "outputs": [
                {
                    "product_id": f.product["id"],
                    "route_id": f.route["id"],
                    "track_unit_kind": "die",
                    "sources": src,
                }
            ],
        },
    )
    (tc,) = r["children"]
    pc = f.sql(
        "SELECT max(at) FROM mes_lot_history WHERE lot_id = :l AND action = 'move_out'",
        l=c["id"],
    )[0][0]
    from sqlalchemy import text

    from app.mes.lot.service import qtime_clock

    db.connection().execute(
        text("SELECT set_config('app.current_tenant', :t, true)"), {"t": f.m.tid}
    )
    got = qtime_clock(
        db, uuid.UUID(f.m.tid), uuid.UUID(tc["id"]), uuid.UUID(f.steps[10]["id"]), None
    )
    assert got is not None and abs(got - pc) < timedelta(seconds=1)


def test_migration_0024_up_down() -> None:
    from app.mes.equipment.tests.test_qual import _migration_roundtrip

    want = {
        ("mes_lot", "bin_code"),
        ("mes_unit_transform_input", "bin_set_id"),
        ("mes_unit_transform_input", "bin_set_version"),
        ("mes_unit_transform_input", "bin_counts"),
        ("mes_unit_transform_output", "bin_code"),
        ("mes_unit_origin", "bin_code"),
    }

    def check(i: Any) -> tuple[frozenset[Any], int]:
        have = frozenset(
            (t, c["name"])
            for t in {x[0] for x in want}
            for c in i.get_columns(t)
            if (t, c["name"]) in want
        )
        fk = sum(
            1
            for k in i.get_foreign_keys("mes_unit_transform_input")
            if k["constrained_columns"] == ["bin_set_id"]
        )
        return have, fk

    _migration_roundtrip(
        "0023_substrate_map_links",
        "b8",
        check,
        ("bin_code", "bin_set_id", "bin_set_version", "bin_counts"),
    )
