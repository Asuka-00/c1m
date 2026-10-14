"""B7 客户来料：开批填写、校验、拆批继承、合批客户不同 422、客户批号互查、追溯带出、严格载荷。"""

from typing import Any

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.mes.execution.tests.test_exec import EXEC
from app.mes.execution.tests.test_split_merge import _line, merge, split, uid
from app.mes.lot.customer import inherit_customer

API = EXEC[: -len("/exec")]


def _start(f: Any, status: int = 200, **lot: Any) -> Any:
    return f.post(
        f"{API}/work-order/{f.wo['id']}/start", {"lots": [{"qty": 4, **lot}]}, status
    )


def test_customer_lot_start_split_merge_lookup_trace(
    client: TestClient, db: Session
) -> None:
    f = _line(client, db)
    c1 = f.m.post("customer", {"code": "C1", "name": "Cust 1"})
    c2 = f.m.post("customer", {"code": "C2", "name": "Cust 2"})
    # 严格载荷：系统 / 未知字段 422
    for k in ("id", "created_at", "foo"):
        r = client.post(
            f"{API}/customer", headers=f.m.h, json={"code": "X", "name": "x", k: "1"}
        )
        assert r.status_code == 422, (k, r.text)
    # 开批校验
    e = _start(f, 422, ownership="customer")["detail"]
    assert any("customer_id" in str(x) for x in e)
    _start(f, 422, ownership="own", customer_id=c1["id"])
    _start(f, 422, customer_lot_no="CL-0")
    (a,) = _start(
        f, customer_lot_no=" CL-1 ", ownership="customer", customer_id=c1["id"]
    )["data"]
    assert (a["customer_lot_no"], a["ownership"], a["customer_id"]) == (
        "CL-1",
        "customer",
        c1["id"],
    )
    assert a["created_at"].endswith("Z")
    (b,) = _start(
        f, customer_lot_no="CL-2", ownership="customer", customer_id=c2["id"]
    )["data"]
    (own,) = f.start(4)
    assert own["ownership"] == "own" and own["customer_id"] is None
    # 拆批继承
    f.stage(a, "move_in", equipment_id=f.eq["id"])
    (ch,) = split(f, a, [{"unit_ids": uid(f, a, 0, 1)}])["children"]
    c = f.lot(ch)
    assert (c["customer_lot_no"], c["ownership"], c["customer_id"]) == (
        "CL-1",
        "customer",
        c1["id"],
    )
    # 合批：客户不同 422 customer_mismatch（自有 vs 客户来料也算不同）
    for x in (b, own):
        f.stage(x, "move_in", equipment_id=f.eq["id"])
        d = merge(f, a, [x], 422)["detail"]
        assert d["code"] == "customer_mismatch" and d["lot_code"] == x["code"], d
    # 同客户可合，目标保留自己的客户字段
    r = merge(f, a, [ch])
    assert f.lot(a)["customer_lot_no"] == "CL-1"
    assert r is not None
    # 互查
    url = f"{EXEC}/customer-lots"
    got = client.get(url, headers=f.m.h, params={"customer_lot_no": "CL-1"}).json()
    assert {x["lot_no"] for x in got["data"]} == {a["code"], ch["code"]}
    assert got["data"][0]["customer"] == "C1"
    got = client.get(url, headers=f.m.h, params={"lot_no": b["code"]}).json()
    assert [x["customer_lot_no"] for x in got["data"]] == ["CL-2"]
    assert client.get(url, headers=f.m.h).status_code == 422
    # 列表关键字搜索
    lst = client.get(f"{API}/lot", headers=f.m.h, params={"q": "CL-2"}).json()
    assert [x["code"] for x in lst["data"]] == [b["code"]]
    # 追溯：目标与正反向批次带出客户批号
    t = client.get(
        f"{EXEC}/trace", headers=f.m.h, params={"kind": "lot", "code": a["code"]}
    ).json()
    assert t["target"]["customer_lot_no"] == "CL-1"
    assert any(x["customer_lot_no"] == "CL-1" for x in t["forward"]["lots"])
    t = client.get(
        f"{EXEC}/trace", headers=f.m.h, params={"kind": "lot", "code": ch["code"]}
    ).json()
    assert t["backward"]["lots"][0]["customer"] == "C1"
    t = client.get(
        f"{EXEC}/trace",
        headers=f.m.h,
        params={"kind": "customer_lot", "code": "CL-1"},
    ).json()
    assert {x["lot_no"] for x in t["lots"]} == {a["code"], ch["code"]}
    r = client.get(
        f"{EXEC}/trace", headers=f.m.h, params={"kind": "customer_lot", "code": "NO"}
    )
    assert r.status_code == 404


def test_material_lot_customer_and_inherit_helper(
    client: TestClient, db: Session
) -> None:
    f = _line(client, db)
    m = f.m
    c1 = m.post("customer", {"code": "C1", "name": "Cust 1"})
    base = {"material_id": f.mat["id"], "qty_remaining": 3, "uom_id": m.fx("uom")}
    for body in (
        {"code": "MLX", "ownership": "customer"},
        {"code": "MLY", "customer_id": c1["id"]},
    ):
        r = client.post(f"{API}/material_lot", headers=m.h, json={**base, **body})
        assert r.status_code == 422, r.text
    ml = m.post(
        "material_lot",
        {**base, "code": "ML1", "ownership": "customer", "customer_id": c1["id"]},
    )
    assert (ml["ownership"], ml["customer_id"]) == ("customer", c1["id"])
    assert m.post("material_lot", {**base, "code": "ML2"})["ownership"] == "own"
    # B5 复用的继承函数
    parent = {"customer_lot_no": "X", "ownership": "customer", "customer_id": c1["id"]}
    assert inherit_customer(parent) == parent
    assert inherit_customer({})["ownership"] == "own"
