"""B5 单位转换与谱系：坐标图良品 / 毛片数提示 / 人工录入需原因、逐片守恒（复用 check_split）、
子批继承客户、母批 converted、die 坐标位置映射、追溯、严格载荷（含 source /
external_event_id 422）、先查权限（D34）、错误路径 0 基（D38）、迁移 0022。"""

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings
from app.mes.execution.tests.test_exec import EXEC
from app.mes.execution.tests.test_split_merge import _line
from app.mes.product.tests.test_bom import _member

API = EXEC[: -len("/exec")]
MAP = f"{settings.API_V1_STR}/mes/map"
FX = Path(__file__).resolve().parents[2] / "map" / "tests" / "fixtures"
TF = f"{EXEC}/transform"


def _fx(name: str) -> str:
    return (FX / name).read_text(encoding="utf-8")


def _start(f: Any, qty: int = 2, **lot: Any) -> Any:
    r = f.post(f"{API}/work-order/{f.wo['id']}/start", {"lots": [{"qty": qty, **lot}]})
    return r["data"][0]


def _wafers(f: Any, lot: Any) -> list[Any]:
    return [u for u in f.ctx(lot)["units"] if u.get("unit_kind", "wafer") == "wafer"]


def _maps(f: Any, codes: list[str]) -> None:
    """用 B4 样例坐标图（WF001-01 / WF001-02）换成真实晶圆号后导入。"""
    for url, body in (
        ("/bin-sets/import", _fx("bin_definition_demo.csv")),
        (
            "/import",
            _fx("map_ok.csv")
            .replace("WF001-01", codes[0])
            .replace("WF001-02", codes[1]),
        ),
    ):
        r = f.c.post(f"{MAP}{url}", headers=f.m.h, json={"content": body})
        assert r.status_code == 200, r.text


def _body(f: Any, lots: list[Any], sources: list[Any], **kw: Any) -> Any:
    return {
        "transform_type": "dicing",
        "input_lot_ids": [x["id"] for x in lots],
        "outputs": [
            {
                "product_id": f.product["id"],
                "route_id": f.route["id"],
                "track_unit_kind": "die",
                "sources": sources,
            }
        ],
        **kw,
    }


def test_transform_map_customer_origin_trace(client: TestClient, db: Session) -> None:
    f = _line(client, db)
    c1 = f.m.post("customer", {"code": "C1", "name": "Cust 1"})
    lot = _start(f, ownership="customer", customer_id=c1["id"], customer_lot_no="CL-1")
    ws = _wafers(f, lot)
    _maps(f, [w["code"] for w in ws])
    good = {}
    for w in ws:
        m = f.c.get(f"{MAP}/substrates/{w['code']}", headers=f.m.h).json()
        good[w["id"]] = m["good_qty"]
    src = [{"wafer_id": wid, "qty": q} for wid, q in good.items()]
    # 预览：来源 map、子批数量 = 良品合计
    pv = f.post(f"{TF}/preview", _body(f, [lot], src))
    assert {x["good_source"] for x in pv["inputs"]} == {"map"}
    assert pv["outputs"][0]["qty"] == sum(good.values()) and pv["warnings"] == []
    # 守恒不符：复用 B4 check_split → 422 map_qty_mismatch
    bad = [dict(src[0], qty=src[0]["qty"] - 1), src[1]]
    d = f.post(f"{TF}/preview", _body(f, [lot], bad), 422)["detail"]
    assert d["code"] == "map_qty_mismatch", d
    # 有坐标图时不许人工录入；错误路径 0 基
    mg = [{"wafer_id": ws[0]["id"], "good_qty": 1}]
    d = f.post(f"{TF}/preview", _body(f, [lot], src, manual_good=mg), 422)["detail"]
    assert d[0]["loc"] == ["body", "manual_good", 0, "wafer_id"], d
    # 来源不是输入晶圆
    x = [*src, {"wafer_id": f.product["id"], "qty": 1}]
    d = f.post(f"{TF}/preview", _body(f, [lot], x), 422)["detail"]
    assert d[0]["loc"] == ["body", "outputs", 0, "sources", 2, "wafer_id"], d
    # 提交
    r = f.post(TF, _body(f, [lot], src, comment="dice"))
    (ch,) = r["children"]
    assert ch["qty"] == sum(good.values()) and ch["tracking_level"] == "quantity"
    c = f.lot(ch)
    assert (c["customer_id"], c["customer_lot_no"], c["ownership"]) == (
        c1["id"],
        "CL-1",
        "customer",
    )
    assert c["lot_status"] == "waiting"
    assert f.lot(lot)["lot_status"] == "converted"
    t = r["transform"]
    assert t["source"] == "manual" and t["external_event_id"] is None
    assert t["at"].endswith("Z")
    ins = f.m.list("unit_transform_input", unit_transform=t["id"])["data"]
    assert {x["good_source"] for x in ins} == {"map"} and len(ins) == 2
    assert all(x["substrate_map_id"] for x in ins)
    og = f.m.list("unit_origin", child_lot=ch["id"], page_size=100)
    assert og["count"] == sum(good.values())
    assert all(o["die_row"] is not None for o in og["data"])
    g = f.m.list("lot_genealogy", parent_lot=lot["id"])["data"]
    assert g[0]["relation"] == "transform"
    assert f.m.list("lot_history", lot=ch["id"], action="transform")["count"] == 1
    # 母批已 converted：不能再转换 / 投站
    d = f.post(TF, _body(f, [lot], src), 422)["detail"]
    assert "converted" in str(d)
    # 追溯：晶圆 → die 去向（含坐标）
    tr = f.c.get(
        f"{EXEC}/trace", headers=f.m.h, params={"kind": "wafer", "code": ws[0]["code"]}
    )
    assert tr.status_code == 200, tr.text
    dies = tr.json()["forward"]["dies"]
    assert dies and dies[0]["child_lot"] == ch["code"]
    assert {"die_row", "die_col", "parent_wafer"} <= set(dies[0])


def test_transform_gross_die_manual_strip(client: TestClient, db: Session) -> None:
    f = _line(client, db, {"product": {"gross_die": 10}})
    a = _start(f)
    wa = _wafers(f, a)
    # 无坐标图：用毛片数 + 提示
    src = [{"wafer_id": w["id"], "qty": 10} for w in wa]
    pv = f.post(f"{TF}/preview", _body(f, [a], src))
    assert [w["code"] for w in pv["warnings"]] == ["no_map_gross_die"] * 2
    d = f.post(f"{TF}/preview", _body(f, [a], src[:1]), 422)["detail"]
    assert d["code"] == "transform_qty_mismatch", d
    # 人工录入需原因码
    mg = [{"wafer_id": wa[0]["id"], "good_qty": 7, "fail_qty": 3}]
    s2 = [{"wafer_id": wa[0]["id"], "qty": 7}, src[1]]
    d = f.post(f"{TF}/preview", _body(f, [a], s2, manual_good=mg), 422)["detail"]
    assert d[0]["loc"] == ["body", "reason_id"], d
    body = _body(f, [a], s2, manual_good=mg, reason_id=f.reasons["scrap"]["id"])
    body["outputs"][0] |= {"track_unit_kind": "strip", "qty": 2}
    r = f.post(TF, body)
    (ch,) = r["children"]
    assert ch["qty"] == 2
    strips = f.ctx(ch)["units"]
    assert [u["code"] for u in strips] == [f"{ch['code']}-S01", f"{ch['code']}-S02"]
    ins = f.m.list("unit_transform_input", lot=a["id"])["data"]
    assert sorted(x["good_source"] for x in ins) == ["gross_die", "manual"]


def test_transform_strict_perm_and_mismatch(client: TestClient, db: Session) -> None:
    f = _line(client, db)
    c1 = f.m.post("customer", {"code": "C1", "name": "Cust 1"})
    a = _start(f, ownership="customer", customer_id=c1["id"], customer_lot_no="CL-1")
    b = _start(f, ownership="customer", customer_id=c1["id"], customer_lot_no="CL-2")
    src = [{"wafer_id": _wafers(f, a)[0]["id"], "qty": 1}]
    d = f.post(f"{TF}/preview", _body(f, [a, b], src), 422)["detail"]
    assert d["code"] == "customer_lot_mismatch", d
    for k in ("source", "external_event_id", "foo"):
        d = f.post(f"{TF}/preview", _body(f, [a], src, **{k: "x"}), 422)["detail"]
        assert d[0]["loc"] == ["body", k], d
    d = f.post(f"{TF}/preview", _body(f, [a], src, transform_type="bin_split"), 422)
    assert d["detail"][0]["loc"] == ["body", "transform_type"]
    d = f.post(f"{TF}/preview", _body(f, [a, a], src), 422)["detail"]
    assert d[0]["loc"] == ["body", "input_lot_ids", 1], d
    # 无权限：先 403，不暴露字段错误
    h = _member(client, db, f.m)
    r = f.c.post(TF, headers=h, json={"bad": 1})
    assert r.status_code == 403, r.text
    assert "loc" not in r.text


def test_migration_0022_up_down() -> None:
    """0022 可重复执行；四张表与部分唯一索引，与表定义一致。"""
    from app.mes.equipment.tests.test_qual import _migration_roundtrip

    names = (
        "mes_unit_transform",
        "mes_unit_transform_input",
        "mes_unit_transform_output",
        "mes_unit_origin",
    )

    def check(i: Any) -> tuple[frozenset[str], bool]:
        have = frozenset(set(names) & set(i.get_table_names()))
        idx = "mes_unit_transform" in have and any(
            x["name"] == "uq_mes_unit_transform_event"
            for x in i.get_indexes("mes_unit_transform")
        )
        return have, idx

    _migration_roundtrip("0021_substrate_map", "b5", check, names)
