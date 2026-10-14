"""B4 坐标图导入：bin 定义集 + 版本、preview 逐行报错（row_no / file_line）、commit、
原点 / 轴向取自文件头、bin_type 决定排除类、两级守恒、重复导入新版本、按基板查询、
严格载荷与 source / external_event_id 拒绝、先查权限（D34）、迁移 0021。"""

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings
from app.mes.product.tests.test_bom import _member
from app.testing.mes import Mes

MAP = f"{settings.API_V1_STR}/mes/map"
FX = Path(__file__).parent / "fixtures"


def _fx(name: str) -> str:
    return (FX / name).read_text(encoding="utf-8")


def _post(m: Mes, url: str, content: str, status: int = 200, **kw: Any) -> Any:
    r = m.c.post(f"{MAP}{url}", headers=m.h, json={"content": content, **kw})
    assert r.status_code == status, r.text
    return r.json()


def _bins(m: Mes) -> Any:
    return _post(
        m, "/bin-sets/import", _fx("bin_definition_demo.csv"), file_name="b.csv"
    )


def test_bin_set_and_map_import_query(client: TestClient, db: Session) -> None:
    m = Mes(client, db)
    # 定义集不存在：坐标图 422 bin_set_not_found
    d = _post(m, "/import/preview", _fx("map_ok.csv"), 422)["detail"]
    assert d["code"] == "bin_set_not_found", d
    pv = _post(m, "/bin-sets/import/preview", _fx("bin_definition_demo.csv"))
    assert pv["ok"] and pv["bin_set"] == {"code": "BINSET-DEMO", "version": 1}
    assert pv["excluded_bin_codes"] == ["E"]
    bs = _bins(m)
    assert (bs["code"], bs["version"], len(bs["definitions"])) == ("BINSET-DEMO", 1, 4)
    assert bs["created_at"].endswith("Z")
    # 同一定义集同版本不能重复导入
    d = _post(m, "/bin-sets/import", _fx("bin_definition_demo.csv"), 422)["detail"]
    assert d["code"] == "bin_set_invalid" and d["errors"][0]["code"] == "bin_set_exists"
    pv = _post(m, "/import/preview", _fx("map_ok.csv"))
    assert pv["ok"] and pv["errors"] == []
    subs = {x["code"]: x for x in pv["substrates"]}
    assert set(subs) == {"WF001-01", "WF001-02"}
    for x in subs.values():
        assert (x["rows"], x["cols"], x["total_qty"], x["map_version"]) == (6, 6, 36, 1)
        # 坐标图层守恒：总数 = 各 bin 之和（含排除类）
        assert sum(x["bin_counts"].values()) == x["total_qty"]
        assert x["excluded_qty"] == x["bin_counts"].get("E", 0)
    r = _post(m, "/import", _fx("map_ok.csv"), file_name="map_ok.csv")
    assert len(r["data"]) == 2
    w = m.c.get(f"{MAP}/substrates/WF001-01", headers=m.h).json()
    assert (w["origin_location"], w["x_axis"], w["y_axis"]) == ("UL", "right", "down")
    assert (w["bin_set_code"], w["bin_set_version"]) == ("BINSET-DEMO", 1)
    assert len(w["cells"]) == 36 and w["cells"][0] == {
        "row": 0,
        "col": 0,
        "bin_code": "E",
    }
    assert w["created_at"].endswith("Z") and w["versions"] == [1]
    imp = m.list("map_import")["data"]
    assert imp[0]["source"] == "manual" and imp[0]["external_event_id"] is None
    assert any(x["imported_at"].endswith("Z") for x in imp)
    # 重复导入：新版本，旧版本保留；原点 / 轴向按新文件头存
    flipped = _fx("map_ok.csv").replace("origin_location=UL", "origin_location=LR")
    flipped = flipped.replace("x_axis=right", "x_axis=left").replace(
        "y_axis=down", "y_axis=up"
    )
    _post(m, "/import", flipped)
    w2 = m.c.get(f"{MAP}/substrates/WF001-01", headers=m.h).json()
    assert w2["map_version"] == 2 and w2["versions"] == [1, 2]
    assert (w2["origin_location"], w2["x_axis"], w2["y_axis"]) == ("LR", "left", "up")
    w1 = m.c.get(
        f"{MAP}/substrates/WF001-01", headers=m.h, params={"version": 1}
    ).json()
    assert w1["origin_location"] == "UL"
    assert m.c.get(f"{MAP}/substrates/NOPE", headers=m.h).status_code == 404
    # 拆批层守恒：子批合计 + 排除数 = 坐标图总数
    url = f"{MAP}/maps/{w['id']}/split-check"
    ok = m.c.post(url, headers=m.h, json={"children_qty": 36 - w["excluded_qty"]})
    assert ok.status_code == 200 and ok.json()["ok"]
    bad = m.c.post(url, headers=m.h, json={"children_qty": 36})
    assert bad.status_code == 422 and bad.json()["detail"]["code"] == "map_qty_mismatch"
    # 通用接口只读
    r = m.c.post(f"{settings.API_V1_STR}/mes/substrate-map", headers=m.h, json={})
    assert r.status_code in (403, 405, 422), r.text


def test_excluded_by_bin_type_not_code(client: TestClient, db: Session) -> None:
    """排除类由 bin_type（edge / unusable）决定，与 bin 码无关。"""
    m = Mes(client, db)
    _post(
        m,
        "/bin-sets/import",
        "# bin_definition_set=BS2\n# version=3\nbin_code,bin_type,description\n"
        "G,good,ok\nX9,edge,rim\nE,fail,not edge\nU,unusable,ink\n",
    )
    content = (
        "# substrate_type=strip\n# origin_location=LL\n# x_axis=right\n# y_axis=up\n"
        "# bin_definition_set=BS2\n# bin_definition_version=3\n# rows=2\n# cols=3\n"
        "substrate_id,row,col,bin_code\n"
        "S1,0,0,X9\nS1,0,1,G\nS1,0,2,E\nS1,1,0,U\nS1,1,1,G\nS1,1,2,G\n"
    )
    (x,) = _post(m, "/import/preview", content)["substrates"]
    assert (x["total_qty"], x["good_qty"], x["excluded_qty"]) == (6, 3, 2)
    assert x["bin_counts"] == {"E": 1, "G": 3, "U": 1, "X9": 1}
    # 行列范围（文件头 rows / cols）
    bad = content + "S1,2,0,G\nS1,0,3,G\n"
    errs = _post(m, "/import/preview", bad)["errors"]
    assert [(e["code"], e["row_no"], e["file_line"]) for e in errs] == [
        ("out_of_range", 7, 16),
        ("out_of_range", 8, 17),
    ]
    # 引用的版本不存在
    d = _post(m, "/import/preview", content.replace("version=3", "version=4"), 422)
    assert d["detail"]["code"] == "bin_set_not_found"


def test_bad_files_row_no_and_file_line(client: TestClient, db: Session) -> None:
    m = Mes(client, db)
    _bins(m)
    for name, code, row_no, line in (
        ("map_bad_duplicate_coord.csv", "duplicate_coord", 11, 19),
        ("map_bad_unknown_bin.csv", "unknown_bin", 15, 23),
    ):
        pv = _post(m, "/import/preview", _fx(name))
        assert not pv["ok"]
        assert [(e["code"], e["row_no"], e["file_line"]) for e in pv["errors"]] == [
            (code, row_no, line)
        ], pv["errors"]
        d = _post(m, "/import", _fx(name), 422)["detail"]
        assert d["code"] == "map_invalid" and d["errors"][0]["row_no"] == row_no
    assert m.list("substrate_map")["count"] == 0
    # 文件头缺失 / 非法
    pv = _post(m, "/import/preview", "substrate_id,row,col,bin_code\nA,0,0,1\n")
    assert {e["field"] for e in pv["errors"]} >= {
        "origin_location",
        "bin_definition_set",
    }


def test_strict_payload_and_permission_first(client: TestClient, db: Session) -> None:
    m = Mes(client, db)
    _bins(m)
    for k, v in (
        ("source", "manual"),
        ("source", "eap"),
        ("external_event_id", "E1"),
        ("foo", 1),
    ):
        for url in ("/import", "/import/preview", "/bin-sets/import"):
            d = _post(m, url, _fx("map_ok.csv"), 422, **{k: v})["detail"]
            assert any(x["loc"][-1] == k for x in d), (k, d)
    assert m.list("substrate_map")["count"] == 0
    h = _member(client, db, m)  # 只读成员
    for url in (
        "/import",
        "/import/preview",
        "/bin-sets/import",
        "/bin-sets/import/preview",
    ):
        r = client.post(
            f"{MAP}{url}",
            headers={**h, "Content-Type": "application/json"},
            content="{bad",
        )
        assert r.status_code == 403 and "loc" not in r.text, r.text
        r = client.post(f"{MAP}{url}", headers=h, json={"source": "eap"})
        assert r.status_code == 403 and "loc" not in r.text, r.text
    # 只读成员可以查询
    _post(m, "/import", _fx("map_ok.csv"))
    assert client.get(f"{MAP}/substrates/WF001-02", headers=h).status_code == 200


def test_migration_0021_up_down() -> None:
    """0021 可重复执行、可降级；表定义与迁移一致。"""
    from app.mes.equipment.tests.test_qual import _migration_roundtrip

    names = (
        "mes_map_import",
        "mes_bin_set",
        "mes_bin_definition",
        "mes_substrate_map",
        "mes_map_cell",
    )

    def check(i: Any) -> tuple[Any, ...]:
        have = set(i.get_table_names())
        idx = "mes_map_import" in have and any(
            x["name"] == "uq_mes_map_import_event"
            for x in i.get_indexes("mes_map_import")
        )
        return tuple(n in have for n in names) + (idx,)

    _migration_roundtrip("0020_lot_customer_lot_index", "b4", check, names)
