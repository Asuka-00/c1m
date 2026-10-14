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
    assert e[0]["loc"] == ["body", "lots", 0, "customer_id"], (
        e
    )  # 与 Pydantic 一致，从 0 开始
    r = f.post(
        f"{API}/work-order/{f.wo['id']}/start",
        {"lots": [{"qty": 1}, {"qty": 1, "ownership": "x"}]},
        422,
    )
    assert r["detail"][0]["loc"][:3] == ["body", "lots", 1], r  # Pydantic 自带校验
    e = f.post(
        f"{API}/work-order/{f.wo['id']}/start",
        {"lots": [{"qty": 1}, {"qty": 1, "customer_lot_no": "X"}]},
        422,
    )["detail"]
    assert e[0]["loc"] == ["body", "lots", 1, "customer_lot_no"], e
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


def test_merge_customer_lot_mismatch(client: TestClient, db: Session) -> None:
    """D36：同客户但客户批号不同 / 一边为空 → 422 customer_lot_mismatch；都为空照常合。"""
    f = _line(client, db)
    c1 = f.m.post("customer", {"code": "C1", "name": "Cust 1"})
    kw = {"ownership": "customer", "customer_id": c1["id"]}
    (a,) = _start(f, customer_lot_no="CL-A", **kw)["data"]
    (b,) = _start(f, customer_lot_no="CL-B", **kw)["data"]
    (n,) = _start(f, **kw)["data"]
    (n2,) = _start(f, **kw)["data"]
    for x in (a, b, n, n2):
        f.stage(x, "move_in", equipment_id=f.eq["id"])
    d = merge(f, a, [b], 422)["detail"]
    assert d["code"] == "customer_lot_mismatch", d
    assert (d["target_customer_lot_no"], d["source_customer_lot_no"]) == (
        "CL-A",
        "CL-B",
    )
    d = merge(f, a, [n], 422)["detail"]
    assert d["code"] == "customer_lot_mismatch" and d["source_customer_lot_no"] is None
    d = merge(f, n, [a], 422)["detail"]
    assert d["target_customer_lot_no"] is None and d["source_customer_lot_no"] == "CL-A"
    # 不可强制放行
    d = merge(f, a, [b], 422, override=True)["detail"]
    assert d["code"] == "customer_lot_mismatch"
    merge(f, n, [n2])  # 两边都为空
    h = client.get(
        f"{API}/lot-history", headers=f.m.h, params={"lot": n2["id"], "page_size": 50}
    ).json()["data"]
    mh = [x for x in h if x["action"] == "merge"]
    assert mh and "customer_lot_no" not in (mh[0]["details"] or {})


def test_migration_0020_customer_lot_index() -> None:
    """0020 可重复执行、可降级；索引与表定义一致。"""
    from app.mes.equipment.tests.test_qual import _migration_roundtrip

    def check(i: Any) -> bool:
        return any(
            x["name"] == "ix_mes_lot_customer_lot_no"
            and x["column_names"][0] == "tenant_id"
            and "upper" in str(x.get("expressions", "")).lower()
            for x in i.get_indexes("mes_lot")
        )

    _migration_roundtrip(
        "0019_customer_material", "d36", check, ("ix_mes_lot_customer_lot_no",)
    )


def test_customer_lot_case_insensitive(client: TestClient, db: Session) -> None:
    """D37：入库只去首尾空格、原样保存；互查 / ?q= / 追溯 / 合批比对不区分大小写（精确匹配）。"""
    f = _line(client, db)
    c1 = f.m.post("customer", {"code": "C1", "name": "Cust 1"})
    kw = {"ownership": "customer", "customer_id": c1["id"]}
    (a,) = _start(f, customer_lot_no="  Ab-01x ", **kw)["data"]
    (b,) = _start(f, customer_lot_no="AB-01X", **kw)["data"]
    assert a["customer_lot_no"] == "Ab-01x"  # 原样保存
    url = f"{EXEC}/customer-lots"
    got = client.get(url, headers=f.m.h, params={"customer_lot_no": "ab-01x"}).json()
    assert {x["lot_no"] for x in got["data"]} == {a["code"], b["code"]}
    # 精确匹配，不做模糊
    assert (
        client.get(url, headers=f.m.h, params={"customer_lot_no": "ab-01"}).json()[
            "data"
        ]
        == []
    )
    lst = client.get(f"{API}/lot", headers=f.m.h, params={"q": "ab-01x"}).json()
    assert {x["code"] for x in lst["data"]} == {a["code"], b["code"]}
    lst = client.get(f"{API}/lot", headers=f.m.h, params={"q": "ab-0"}).json()
    assert a["code"] not in {x["code"] for x in lst["data"]}
    t = client.get(
        f"{EXEC}/trace",
        headers=f.m.h,
        params={"kind": "customer_lot", "code": "aB-01X"},
    ).json()
    assert {x["lot_no"] for x in t["lots"]} == {a["code"], b["code"]}
    for x in (a, b):
        f.stage(x, "move_in", equipment_id=f.eq["id"])
    merge(f, a, [b])  # 大小写不同视为同一客户批号
    assert f.lot(a)["customer_lot_no"] == "Ab-01x"


def test_start_error_loc_zero_based(client: TestClient, db: Session) -> None:
    """D38：开批接口所有报错路径与 Pydantic 一致，从 0 开始的数组写法。"""
    f = _line(client, db)
    url = f"{API}/work-order/{f.wo['id']}/start"

    def locs(lots: list[Any]) -> list[Any]:
        return [x["loc"] for x in f.post(url, {"lots": lots}, 422)["detail"]]

    f.sql("UPDATE mes_lot_type SET max_wafers = 3 WHERE id = :i", i=f.lt["id"])
    assert locs([{"qty": 1}, {"qty": 4}]) == [["body", "lots", 1, "qty"]]
    assert locs([{"qty": 2, "slots": [1, 1]}]) == [["body", "lots", 0, "slots"]]
    assert locs([{"qty": 1}, {"qty": 1, "wafer_sources": ["a", "b"]}]) == [
        ["body", "lots", 1, "wafer_sources"]
    ]
    import uuid as _u

    assert locs([{"qty": 1, "carrier_id": str(_u.uuid4())}]) == [
        ["body", "lots", 0, "carrier_id"]
    ]
    assert locs([{"qty": 1}, {"qty": 1, "ownership": "customer"}]) == [
        ["body", "lots", 1, "customer_id"]
    ]


def test_customer_lot_db_upper_eszett(client: TestClient, db: Session) -> None:
    """D-9350-1：查询与合批比对都由数据库算 upper()，ß 等字符两边规则一致。"""
    f = _line(client, db)
    c1 = f.m.post("customer", {"code": "C1", "name": "Cust 1"})
    kw = {"ownership": "customer", "customer_id": c1["id"]}
    (a,) = _start(f, customer_lot_no="straße-01", **kw)["data"]
    (b,) = _start(f, customer_lot_no="STRAßE-01", **kw)["data"]
    url = f"{EXEC}/customer-lots"
    # 大写取数据库的 upper（STRAßE-01）；Python 的 "STRASSE-01" 是另一个字符串，不保证查到
    for v in ("straße-01", "STRAßE-01", "StRaßE-01"):
        got = client.get(url, headers=f.m.h, params={"customer_lot_no": v}).json()
        assert a["code"] in {x["lot_no"] for x in got["data"]}, v
        lst = client.get(f"{API}/lot", headers=f.m.h, params={"q": v}).json()
        assert a["code"] in {x["code"] for x in lst["data"]}, v
    for x in (a, b):
        f.stage(x, "move_in", equipment_id=f.eq["id"])
    merge(f, a, [b])
