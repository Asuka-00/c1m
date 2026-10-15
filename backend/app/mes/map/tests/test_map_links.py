"""D39 坐标图关联批次 / 设备 / 工序、按晶圆记录自动关联批次、请求体 10MB 上限（413，
先查权限）；D-15e-1 多出列逐行报 extra_columns；迁移 0023。"""

import json
import uuid
from typing import Any

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.mes.execution.tests.test_split_merge import _line
from app.mes.execution.tests.test_transform import MAP, _fx, _start, _wafers
from app.mes.product.tests.test_bom import _member


def _post(f: Any, url: str, body: Any, status: int = 200, h: Any = None) -> Any:
    r = f.c.post(f"{MAP}{url}", headers=h or f.m.h, json=body)
    assert r.status_code == status, r.text
    return r.json()


def _map_for(codes: list[str]) -> str:
    return _fx("map_ok.csv").replace("WF001-01", codes[0]).replace("WF001-02", codes[1])


def test_map_links_and_auto_lot(client: TestClient, db: Session) -> None:
    f = _line(client, db)
    _post(f, "/bin-sets/import", {"content": _fx("bin_definition_demo.csv")})
    lot = _start(f)
    ws = [w["code"] for w in _wafers(f, lot)]
    # 给了但不存在：422，loc 指向字段（preview 与 import 一样）
    for k in ("lot_id", "equipment_id", "operation_id"):
        for url in ("/import/preview", "/import"):
            body = {"content": _map_for(ws), k: str(uuid.uuid4())}
            d = _post(f, url, body, 422)["detail"]
            assert d[0]["loc"] == ["body", k], d
    # 不给批次：按晶圆记录自动关联其所在批次
    r = _post(f, "/import", {"content": _map_for(ws), "equipment_id": f.eq["id"]})
    for x in r["data"]:
        assert x["lot_id"] == lot["id"] and x["equipment_id"] == f.eq["id"]
        assert x["operation_id"] is None
    # 基板号与批次号相同、但没有这片晶圆：不按批次号匹配 → 空
    r = _post(f, "/import", {"content": _map_for([lot["code"], "NOPE-01"])})
    assert all(x["lot_id"] is None for x in r["data"])
    # 显式给批次：用给定的
    other = _start(f)
    r = _post(f, "/import", {"content": _map_for(ws), "lot_id": other["id"]})
    assert all(x["lot_id"] == other["id"] for x in r["data"])
    # 未知字段仍 422
    d = _post(f, "/import", {"content": _map_for(ws), "wafer_id": "x"}, 422)
    assert d["detail"][0]["loc"] == ["body", "wafer_id"]


def test_map_body_10mb_413_after_permission(client: TestClient, db: Session) -> None:
    f = _line(client, db)
    big = json.dumps({"content": "x" * (10 * 1024 * 1024 + 1)})
    for url in ("/import/preview", "/import"):
        r = f.c.post(
            f"{MAP}{url}",
            headers={**f.m.h, "Content-Type": "application/json"},
            content=big,
        )
        assert r.status_code == 413, r.text
        assert r.json()["detail"]["code"] == "payload_too_large"
        # 无权限：先 403
        h = _member(client, db, f.m)
        r = f.c.post(
            f"{MAP}{url}",
            headers={**h, "Content-Type": "application/json"},
            content=big,
        )
        assert r.status_code == 403, r.text
    # 10MB 以内照常解析（这里因内容不合法得到逐行错误，而不是 413）
    r = _post(f, "/import/preview", {"content": "x" * (1024 * 1024)}, 200)
    assert r["ok"] is False


def test_extra_columns_rejected(client: TestClient, db: Session) -> None:
    """D-15e-1：文件第 11 行末尾多一列 → extra_columns（row_no 3 / file_line 11）。"""
    f = _line(client, db)
    lines = _fx("bin_definition_demo.csv").splitlines()
    lines[5] += ",extra"  # 第 6 行 = 第 2 个数据行
    d = _post(f, "/bin-sets/import", {"content": "\n".join(lines)}, 422)["detail"]
    assert d["code"] == "bin_set_invalid"
    e = [x for x in d["errors"] if x["code"] == "extra_columns"]
    assert (e[0]["row_no"], e[0]["file_line"]) == (2, 6), d
    _post(f, "/bin-sets/import", {"content": _fx("bin_definition_demo.csv")})
    lines = _fx("map_ok.csv").splitlines()
    lines[10] += ",extra"
    bad = "\n".join(lines)
    pv = _post(f, "/import/preview", {"content": bad})
    assert pv["ok"] is False
    e = [x for x in pv["errors"] if x["code"] == "extra_columns"]
    assert len(e) == 1 and (e[0]["row_no"], e[0]["file_line"]) == (3, 11), pv
    d = _post(f, "/import", {"content": bad}, 422)["detail"]
    assert d["code"] == "map_invalid"
    assert any(x["code"] == "extra_columns" for x in d["errors"])


def _unquote(line: str, k: int) -> str:
    v = line.split(",")
    v[k] = '"' + v[k]  # 引号不配对
    return ",".join(v)


def test_unbalanced_quote_bad_csv(client: TestClient, db: Session) -> None:
    """D-eab-1：引号不配对 → 行错误 bad_csv，而不是 bad_int / required。"""
    f = _line(client, db)
    lines = _fx("bin_definition_demo.csv").splitlines()
    lines[5] = _unquote(lines[5], 1)
    d = _post(f, "/bin-sets/import", {"content": "\n".join(lines)}, 422)["detail"]
    assert d["code"] == "bin_set_invalid"
    e = [x for x in d["errors"] if x["file_line"] == 6]
    assert [x["code"] for x in e] == ["bad_csv"], d
    assert e[0]["row_no"] == 2
    _post(f, "/bin-sets/import", {"content": _fx("bin_definition_demo.csv")})
    for k, bare in ((2, False), (1, True)):
        lines = _fx("map_ok.csv").splitlines()
        if bare:  # 裸引号：W1,3"x,...
            v = lines[10].split(",")
            v[k] = v[k] + '"x'
            lines[10] = ",".join(v)
        else:
            lines[10] = _unquote(lines[10], k)
        bad = "\n".join(lines)
        pv = _post(f, "/import/preview", {"content": bad})
        assert pv["ok"] is False
        e = [x for x in pv["errors"] if x["file_line"] == 11]
        assert [x["code"] for x in e] == ["bad_csv"], pv
        assert e[0]["row_no"] == 3
        assert not any(x["code"] in ("bad_int", "required") for x in pv["errors"])
        d = _post(f, "/import", {"content": bad}, 422)["detail"]
        assert d["code"] == "map_invalid"
        assert any(x["code"] == "bad_csv" for x in d["errors"])
    # 原样文件照常通过
    assert _post(f, "/import/preview", {"content": _fx("map_ok.csv")})["ok"] is True


def test_migration_0023_up_down() -> None:
    from app.mes.equipment.tests.test_qual import _migration_roundtrip

    cols = ("lot_id", "equipment_id", "operation_id")

    def check(i: Any) -> tuple[frozenset[str], int, int]:
        have = frozenset(
            c["name"] for c in i.get_columns("mes_substrate_map") if c["name"] in cols
        )
        fks = sum(
            1
            for k in i.get_foreign_keys("mes_substrate_map")
            if k["constrained_columns"][0] in cols
        )
        ix = sum(
            1
            for x in i.get_indexes("mes_substrate_map")
            if x["column_names"][0] in cols
        )
        return have, fks, ix

    _migration_roundtrip("0022_unit_transform", "d39", check, ("mes_substrate_map",))
