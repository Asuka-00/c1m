"""B1 验收（D28，bom.md v1.1）：BOM 版本、明细、替代料、生效 / 作废、复制、两级树、
深度与循环校验、6 位小数与计件整数、权限；开批锁定版本、拆批沿用、合批版本校验。"""

from typing import Any

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.mes.execution.tests.test_split_merge import _line, merge, split, uid
from app.platform.users import service as crud
from app.platform.users.schemas import UserCreate
from app.testing.mes import API, Mes
from app.testing.utils import (
    login_name,
    random_email,
    random_lower_string,
    username_for,
)

BOM = f"{API}/bom"


class B:
    """BOM 测试小工具：主数据 + 便捷操作。"""

    def __init__(self, m: Mes) -> None:
        self.m = m
        self.ea = m.fx("uom")  # count
        self.g = m.post("uom", {"code": "G", "name": "gram", "dimension": "mass"})["id"]
        mt = m.post(
            "material_type", {"code": "MT", "name": "mt", "category": "consumable"}
        )
        self.mats = [
            m.post(
                "material",
                {
                    "code": f"M{i}",
                    "name": f"m{i}",
                    "material_type_id": mt["id"],
                    "uom_id": self.ea,
                },
            )
            for i in range(4)
        ]

    def product(self, code: str) -> Any:
        return self.m.post("product", {"code": code, "name": code})

    def bom(self, product: Any, status: int = 200) -> Any:
        return self.m.post("bom", {"product_id": product["id"]}, status)

    def line(self, bom: Any, n: int, status: int = 200, **kw: Any) -> Any:
        body = {
            "bom_id": bom["id"],
            "line_no": n,
            "component_type": "material",
            "material_id": self.mats[0]["id"],
            "qty": 1,
            "uom_id": self.ea,
            "consume_mode": "issue",
            **kw,
        }
        return self.m.post("bom_line", body, status)

    def act(self, bom: Any, verb: str, status: int = 200, h: Any = None) -> Any:
        r = self.m.c.post(f"{BOM}/{bom['id']}/{verb}", headers=h or self.m.h)
        assert r.status_code == status, r.text
        return r.json()

    def get(self, bom: Any) -> Any:
        r = self.m.c.get(f"{API}/bom/{bom['id']}", headers=self.m.h)
        assert r.status_code == 200, r.text
        return r.json()

    def tree(self, **params: Any) -> Any:
        r = self.m.c.get(f"{BOM}/tree", headers=self.m.h, params=params)
        assert r.status_code == 200, r.text
        return r.json()


def _member(client: TestClient, db: Session, m: Mes) -> dict[str, str]:
    email, pw = random_email(), random_lower_string()
    crud.create_user(
        session=db,
        user_create=UserCreate(email=email, username=username_for(email), password=pw),
    )
    client.post(
        f"{API[:-4]}/tenants/{m.tid}/members",
        headers=m.h,
        json={"username": login_name(email), "roles": ["member"]},
    )
    tok = client.post(
        f"{API[:-4]}/login/access-token",
        data={"username": login_name(email), "password": pw},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {tok}", "X-Tenant-ID": m.tid}


def test_bom_versions_lifecycle(client: TestClient, db: Session) -> None:
    """版本自动递增；生效记确认人 / 时间；新版本生效旧版本 superseded；生效后只读。"""
    m = Mes(client, db)
    b = B(m)
    p = b.product("FG")
    v1 = b.bom(p)
    assert (v1["version"], v1["status"], v1["effective_at"]) == (1, "draft", None)
    # status / version 是系统字段：P1 严格载荷，传了就 422（bom.md §12）
    err = m.post("bom", {"product_id": p["id"], "status": "active", "version": 9}, 422)
    assert {d["loc"][-1] for d in err["detail"]} == {"status", "version"}
    v2 = m.post("bom", {"product_id": p["id"]})
    assert (v2["version"], v2["status"]) == (2, "draft")
    # 生效时间只能由 activate 决定：载荷里给了就 422
    err = m.post(
        "bom", {"product_id": p["id"], "effective_at": "2026-10-14T00:00:00Z"}, 422
    )
    assert err["detail"][0]["loc"][-1] == "effective_at" or "effective_at" in str(err)
    m.patch("bom", v2["id"], {"effective_at": "2026-10-14T00:00:00Z"}, 422)
    # 无明细不能生效
    assert "at least one line" in b.act(v1, "activate", 422)["detail"][0]["msg"]
    ln = b.line(v1, 10)
    sub = m.post(
        "bom_line_substitute",
        {"bom_line_id": ln["id"], "material_id": b.mats[1]["id"], "priority": 1},
    )
    # 客户端传确认人 / 确认时间：422（D4 / D32）；一律用当前操作人和当前时间
    r = m.c.post(
        f"{BOM}/{v1['id']}/activate",
        headers=m.h,
        json={"confirmed_by": "mallory", "confirmed_at": "2000-01-01T00:00:00Z"},
    )
    assert r.status_code == 422, r.text
    r = m.c.post(f"{BOM}/{v1['id']}/activate", headers=m.h)
    assert r.status_code == 200, r.text
    a1 = r.json()
    assert a1["confirmed_by"] != "mallory"
    assert not a1["confirmed_at"].startswith("2000")
    me = m.c.get(f"{API[:-4]}/users/me", headers=m.h).json()
    assert a1["confirmed_by"] in (me.get("username"), me.get("email"))
    assert a1["status"] == "active" and a1["confirmed_by"] and a1["confirmed_at"]
    assert a1["effective_at"]
    # 生效后只读：主表、明细、替代料都不能改 / 删 / 加
    m.patch("bom", v1["id"], {"description": "x"}, 409)
    m.patch("bom_line", ln["id"], {"qty": 2}, 409)
    m.delete("bom_line", ln["id"], 409)
    b.line(v1, 20, 409)
    m.patch("bom_line_substitute", sub["id"], {"priority": 2}, 409)
    m.delete("bom", v1["id"], 409)
    b.act(v1, "activate", 409)
    # 新版本生效 → 旧版本 superseded，同产品只有一个 active
    b.line(v2, 10, material_id=b.mats[2]["id"])
    b.act(v2, "activate")
    assert b.get(v1)["status"] == "superseded"
    act = m.list("bom", product=p["id"], status="active")["data"]
    assert [x["id"] for x in act] == [v2["id"]]
    b.act(v1, "void", 409)  # superseded 不能作废
    # 作废：draft / active 可以；作废后产品没有生效版本
    v3 = b.bom(p)
    assert b.act(v3, "void")["status"] == "void"
    assert b.act(v2, "void")["status"] == "void"
    assert m.list("bom", product=p["id"], status="active")["count"] == 0
    # 草稿可删
    v4 = b.bom(p)
    m.delete("bom", v4["id"])
    # 审计
    logs = m.list("audit_log", entity_type="bom")["data"]
    assert {"activate", "void", "copy"} & {x["action"] for x in logs} >= {
        "activate",
        "void",
    }


def test_bom_copy_new_version(client: TestClient, db: Session) -> None:
    """复制成新版本：任何状态都可复制，明细与替代料一起复制，版本号接着最大号。"""
    m = Mes(client, db)
    b = B(m)
    p = b.product("FG")
    v1 = b.bom(p)
    l1 = b.line(v1, 10, qty="1.234568", uom_id=b.g, per_basis="die", scrap_rate=0.02)
    b.line(v1, 20, material_id=b.mats[3]["id"], consume_mode="mounted")
    m.post(
        "bom_line_substitute",
        {"bom_line_id": l1["id"], "material_id": b.mats[1]["id"], "priority": 1},
    )
    m.post(
        "bom_line_substitute",
        {"bom_line_id": l1["id"], "material_id": b.mats[2]["id"], "priority": 2},
    )
    b.act(v1, "activate")
    v2 = b.act(v1, "copy")
    assert (v2["version"], v2["status"], v2["copied_from_id"]) == (2, "draft", v1["id"])
    t = b.tree(bom_id=v2["id"])
    assert [x["line_no"] for x in t["lines"]] == [10, 20]
    first = t["lines"][0]
    assert first["qty"] == "1.234568" and first["per_basis"] == "die"
    assert first["scrap_rate"] == "0.02" and first["uom_id"] == b.g
    assert [s["priority"] for s in first["substitutes"]] == [1, 2]
    assert t["lines"][1]["consume_mode"] == "mounted"
    # 复制出来的草稿可以改，原版本不变
    m.patch("bom_line", first["id"], {"qty": 3})
    assert b.tree(bom_id=v1["id"])["lines"][0]["qty"] == "1.234568"
    v3 = b.act(v2, "copy")
    assert v3["version"] == 3


def test_bom_line_rules(client: TestClient, db: Session) -> None:
    """6 位小数、计件单位必须整数、组件类型对应字段、损耗率范围、consume_mode 必填、替代料。"""
    m = Mes(client, db)
    b = B(m)
    p = b.product("FG")
    semi = b.product("SEMI")
    v = b.bom(p)
    # 计件单位（count）用量必须是整数
    err = b.line(v, 10, 422, qty="1.5")
    assert "whole number" in err["detail"][0]["msg"]
    # 质量单位允许小数，最多 6 位（D49：超出 422，不静默舍入）
    err = b.line(v, 10, 422, qty="0.0000005", uom_id=b.g)
    assert err["detail"][0]["type"] == "value_error"  # D60 通用 CRUD
    b.line(v, 10, 422, qty="1.1234567", uom_id=b.g)
    ok = b.line(v, 14, qty="1.1000000", uom_id=b.g)  # 去尾零后 1 位，允许
    assert ok["qty"] == "1.1"
    ln = b.line(v, 10, qty="0.000001", uom_id=b.g)
    assert ln["qty"] == "0.000001"
    b.line(v, 11, 422, qty=0)
    b.line(v, 12, 422, qty="abc")
    b.line(v, 13, 422, scrap_rate=1.5)
    b.line(v, 13, 422, scrap_rate=-0.01)
    assert b.line(v, 13, scrap_rate=1)["scrap_rate"] == "1"
    # consume_mode 没有默认值
    r = m.c.post(
        f"{API}/bom-line",
        headers=m.h,
        json={
            "bom_id": v["id"],
            "line_no": 14,
            "material_id": b.mats[0]["id"],
            "qty": 1,
            "uom_id": b.ea,
        },
    )
    assert r.status_code == 422 and "consume_mode" in r.text
    # 行号唯一
    b.line(v, 10, 409, uom_id=b.g)
    # 半成品行：必须给 component_product，物料被清空；不能引用自己
    b.line(v, 20, 422, component_type="product", material_id=None)
    sl = b.line(v, 20, component_type="product", component_product_id=semi["id"])
    assert sl["material_id"] is None and sl["component_product_id"] == semi["id"]
    b.line(v, 21, 422, component_type="product", component_product_id=p["id"])
    # 替代料：只用于物料行；不能与主料相同；优先级唯一
    m.post(
        "bom_line_substitute",
        {"bom_line_id": sl["id"], "material_id": b.mats[1]["id"], "priority": 1},
        422,
    )
    m.post(
        "bom_line_substitute",
        {"bom_line_id": ln["id"], "material_id": b.mats[0]["id"], "priority": 1},
        422,
    )
    m.post(
        "bom_line_substitute",
        {"bom_line_id": ln["id"], "material_id": b.mats[1]["id"], "priority": 1},
    )
    dup = m.post(
        "bom_line_substitute",
        {"bom_line_id": ln["id"], "material_id": b.mats[2]["id"], "priority": 1},
        409,
    )["detail"]
    assert (dup["code"], dup["field"], dup["priority"]) == ("duplicate", "priority", 1)
    assert dup["bom_line_id"] == ln["id"]
    dup = m.post(
        "bom_line_substitute",
        {"bom_line_id": ln["id"], "material_id": b.mats[1]["id"], "priority": 2},
        409,
    )["detail"]
    assert dup["field"] == "material" and dup["material"] == b.mats[1]["id"]
    # 改产品不允许
    m.patch("bom", v["id"], {"product_id": semi["id"]}, 422)
    # 可选工序（bom.md §11：引用工序而不是流程步骤）
    op = m.post("operation", {"code": "OP-DA", "name": "die attach"})
    ol = b.line(v, 30, uom_id=b.g, operation_id=op["id"])
    assert ol["operation_id"] == op["id"] and ol["operation_label"].startswith("OP-DA")


def test_bom_tree_depth_and_cycles(client: TestClient, db: Session) -> None:
    """两级树展开半成品的生效版本；激活时深度 > 2 或循环引用 → 422。"""
    m = Mes(client, db)
    b = B(m)
    fg, semi, raw = b.product("FG"), b.product("SEMI"), b.product("RAW")
    sb = b.bom(semi)
    b.line(sb, 10, material_id=b.mats[1]["id"])
    b.act(sb, "activate")
    fb = b.bom(fg)
    b.line(fb, 10, component_type="product", component_product_id=semi["id"])
    b.line(fb, 20)
    b.act(fb, "activate")
    t = b.tree(product_id=fg["id"])
    assert t["bom"]["id"] == fb["id"] and t["level"] == 1
    child = t["lines"][0]["child"]
    assert child["bom"]["id"] == sb["id"] and child["level"] == 2
    assert child["lines"][0]["material_id"] == b.mats[1]["id"]
    assert t["lines"][1]["child"] is None
    # 没有生效版本的产品：空树
    assert b.tree(product_id=raw["id"]) == {"bom": None, "lines": []}
    r = m.c.get(f"{BOM}/tree", headers=m.h)
    assert r.status_code == 422
    # 第三层：SEMI 的新版本引用 RAW（RAW 有 BOM）→ FG 会展开成 3 层，拒绝
    rb = b.bom(raw)
    b.line(rb, 10)
    b.act(rb, "activate")
    sb2 = b.act(sb, "copy")
    b.line(sb2, 20, component_type="product", component_product_id=raw["id"])
    err = b.act(sb2, "activate", 409)["detail"]
    assert err["code"] == "bom_depth_exceeded"
    assert {d["product"] for d in err["details"]} == {"SEMI", "FG"}
    # RAW 的新版本引用 FG（FG 生效 BOM 有半成品行）→ 逐行接口直接 422
    rb2 = b.act(rb, "copy")
    err = b.line(rb2, 20, 422, component_type="product", component_product_id=fg["id"])
    assert err["detail"][0]["type"] == "bom_depth_exceeded"
    # 写入时对方还没指回来：C 先生效（只有物料）；A 草稿引用 C、C 新草稿引用 A（A 尚未生效）
    a, c = b.product("A"), b.product("C")
    cb = b.bom(c)
    b.line(cb, 10)
    b.act(cb, "activate")
    ab = b.bom(a)
    b.line(ab, 10, component_type="product", component_product_id=c["id"])
    cb2 = b.act(cb, "copy")
    b.line(cb2, 20, component_type="product", component_product_id=a["id"])
    b.act(ab, "activate")
    err = b.act(cb2, "activate", 409)["detail"]
    assert err["code"] == "bom_cycle"
    assert {d["product"] for d in err["details"]} == {"A", "C"}
    assert b.get(cb2)["status"] == "draft"


def test_bom_activate_d47(client: TestClient, db: Session) -> None:
    """D47：A 生效引用 B；B 新草稿加半成品行 → 生效 409 bom_depth_exceeded，详情含 A。"""
    m = Mes(client, db)
    b = B(m)
    a, bp, x = b.product("A"), b.product("B"), b.product("X")
    xb = b.bom(x)
    b.line(xb, 10)
    b.act(xb, "activate")
    bb = b.bom(bp)
    b.line(bb, 10)
    b.act(bb, "activate")
    ab = b.bom(a)
    b.line(ab, 10, component_type="product", component_product_id=bp["id"])
    b.act(ab, "activate")
    bb2 = b.act(bb, "copy")
    b.line(bb2, 20, component_type="product", component_product_id=x["id"])
    err = b.act(bb2, "activate", 409)["detail"]
    assert err["code"] == "bom_depth_exceeded"
    det = {d["product"]: d for d in err["details"]}
    assert set(det) == {"A", "B"}
    assert det["A"]["bom_id"] == ab["id"] and det["A"]["bom_version"] == 1
    assert b.get(bb2)["status"] == "draft"
    # 方向 1：被引用的半成品其生效 BOM 后来有了半成品行（A 作废后 B v2 生效）
    b.act(ab, "void")
    b.act(bb2, "activate")
    a2 = b.act(ab, "copy")
    err = b.act(a2, "activate", 409)["detail"]
    assert err["code"] == "bom_depth_exceeded"
    assert {d["product"] for d in err["details"]} == {"A", "B"}


def test_bom_permissions(client: TestClient, db: Session) -> None:
    """成员（只读）能看不能写：通用接口与生效 / 复制 / 作废都 403。"""
    m = Mes(client, db)
    b = B(m)
    p = b.product("FG")
    v = b.bom(p)
    b.line(v, 10)
    hm = _member(client, db, m)
    r = client.get(f"{BOM}/tree", headers=hm, params={"bom_id": v["id"]})
    assert r.status_code == 200
    assert client.get(f"{API}/bom", headers=hm).status_code == 200
    r = client.post(f"{API}/bom", headers=hm, json={"product_id": p["id"]})
    assert r.status_code == 403
    r = client.patch(f"{API}/bom-line/{v['id']}", headers=hm, json={"qty": 2})
    assert r.status_code == 403
    for verb in ("activate", "copy", "void"):
        b.act(v, verb, 403, h=hm)
    meta = client.get(f"{API}/_meta", headers=m.h).json()
    ent = {e["code"]: e for e in meta["entities"]}
    assert ent["bom_line"]["write"] == "mes.bom:write"
    assert ent["bom_line_substitute"]["read"] == "mes.bom:read"
    qty = next(f for f in ent["bom_line"]["fields"] if f["name"] == "qty")
    assert qty["scale"] == 6
    assert qty["decimal_places"] == 6


def _bom_for(f: Any, product: Any) -> Any:
    b = B.__new__(B)
    b.m = f.m
    b.ea = f.m.fx("uom")
    b.mats = [f.mat]
    v = b.bom(product)
    b.line(v, 10)
    return b, v


def test_lot_start_locks_bom(client: TestClient, db: Session) -> None:
    """开批锁定当时生效版本；没有时锁空并提示；新版本生效不影响在制批；开关打开时拒绝。"""
    f = _line(client, db)
    out = f.post(f"{API}/work-order/{f.wo['id']}/start", {"lots": [{"qty": 2}]})
    (l0,) = out["data"]
    assert l0["bom_id"] is None and out["warnings"][0]["code"] == "no_active_bom"
    b, v1 = _bom_for(f, f.product)
    b.act(v1, "activate")
    out = f.post(f"{API}/work-order/{f.wo['id']}/start", {"lots": [{"qty": 2}]})
    (l1,) = out["data"]
    assert l1["bom_id"] == v1["id"] and out["warnings"] == []
    assert f.lot(l1)["bom_id"] == v1["id"]
    h = f.m.list("lot_history", lot=l1["id"], action="start")["data"]
    assert h[0]["details"]["bom_version"] == 1
    v2 = b.act(v1, "copy")
    b.act(v2, "activate")
    assert f.lot(l1)["bom_id"] == v1["id"]  # 在制批不受影响
    (l2,) = f.start(2)
    assert l2["bom_id"] == v2["id"]
    # 被批次锁定的版本不能删除（已非草稿）；作废后批次仍保留引用
    b.act(v2, "void")
    assert f.lot(l2)["bom_id"] == v2["id"]
    # 开关：bom_required 规则（严重度非 off）→ 没有生效 BOM 时拒绝开批
    rule = f.m.post(
        "check_rule",
        {
            "code": "BOMREQ",
            "name": "bom required",
            "check_type": "bom_required",
            "severity": "block",
        },
    )
    r = f.post(
        f"{API}/work-order/{f.wo['id']}/start", {"lots": [{"qty": 2}]}, status=422
    )
    assert "no active BOM" in str(r)
    # warn：放行开批，warnings 带 no_active_bom（D1）
    f.m.patch("check_rule", rule["id"], {"severity": "warn"})
    out = f.post(f"{API}/work-order/{f.wo['id']}/start", {"lots": [{"qty": 2}]})
    assert out["data"][0]["bom_id"] is None
    assert [w["code"] for w in out["warnings"]] == ["no_active_bom"]
    # off：不检查
    f.m.patch("check_rule", rule["id"], {"severity": "off"})
    out = f.post(f"{API}/work-order/{f.wo['id']}/start", {"lots": [{"qty": 2}]})
    assert out["data"][0]["bom_id"] is None


def test_split_inherits_and_merge_checks_bom(client: TestClient, db: Session) -> None:
    """拆批子批沿用母批版本；合批版本不同（含一空一非空）422 并写明两边版本；两个空可合。"""
    f = _line(client, db)
    a0, b0 = f.start(4, 4)  # 都没有 BOM
    r = merge(f, a0, [b0])
    assert r["lot"]["qty"] == 8
    bb, v1 = _bom_for(f, f.product)
    bb.act(v1, "activate")
    (l1,) = f.start(4)
    r = split(f, l1, [{"unit_ids": uid(f, l1, 0, 1)}])
    (ch,) = r["children"]
    assert f.lot(ch)["bom_id"] == v1["id"]
    # 同版本可合
    merge(f, l1, [ch])
    # 一空一非空：拒绝
    err = merge(f, l1, [a0], 422)["detail"]
    assert err["code"] == "bom_mismatch"
    assert (err["target_bom_version"], err["source_bom_version"]) == ("v1", "none")
    assert "v1" in err["message"] and "none" in err["message"]
    # 版本不同：拒绝（强制放行也不行）
    v2 = bb.act(v1, "copy")
    bb.act(v2, "activate")
    (l2,) = f.start(4)
    err = merge(f, l1, [l2], 422, override=True, override_reason="x")["detail"]
    assert (err["target_bom_version"], err["source_bom_version"]) == ("v1", "v2")
    # 合批候选里标出原因
    cands = f.ctx(l1)["sm"]["candidates"]
    probs = {c["code"]: c["problems"] for c in cands}
    assert any("different BOM version" in p for p in probs[l2["code"]])


def test_migration_0012_0013_up_down() -> None:
    """0012（可重复执行）：升级建三张表、lot.bom_id 和部分唯一索引；降级全部删除，可再升级。"""
    import os
    import subprocess
    from pathlib import Path

    from sqlalchemy import create_engine, inspect, text
    from sqlalchemy.engine import make_url

    from app.core.config import settings

    base = make_url(settings.migration_database_url)
    name = f"{base.database}_mig_b1"
    server = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with server.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        c.execute(text(f'CREATE DATABASE "{name}"'))
    url = base.set(database=name).render_as_string(hide_password=False)
    backend = Path(__file__).resolve().parents[4]

    def alembic(*args: str) -> None:
        env = {
            **os.environ,
            "MIGRATION_DATABASE_URL": url,
            "ALEMBIC_ALLOW_DB_MISMATCH": "1",
        }
        r = subprocess.run(
            ["alembic", *args], cwd=backend, env=env, capture_output=True, text=True
        )
        assert r.returncode == 0, r.stderr[-2000:]

    eng = create_engine(url)

    def state() -> tuple[set[str], bool, bool]:
        with eng.connect() as c:
            i = inspect(c)
            tabs = {t for t in i.get_table_names() if t.startswith("mes_bom")}
            col = any(x["name"] == "bom_id" for x in i.get_columns("mes_lot"))
            if tabs:  # 0013：明细引用工序
                lc = {x["name"] for x in i.get_columns("mes_bom_line")}
                assert "operation_id" in lc and "route_step_id" not in lc
            idx = bool(
                tabs
                and any(
                    x["name"] == "uq_mes_bom_active" for x in i.get_indexes("mes_bom")
                )
            )
            return tabs, col, idx

    try:
        alembic("upgrade", "head")
        assert state() == (
            {"mes_bom", "mes_bom_line", "mes_bom_line_substitute"},
            True,
            True,
        )
        alembic("stamp", "0011_qtime_rule_active_no_scrap")
        alembic("upgrade", "head")  # 已存在时再升级：不报错
        alembic("downgrade", "0011_qtime_rule_active_no_scrap")
        assert state() == (set(), False, False)
        alembic("stamp", "head")
        alembic("downgrade", "0011_qtime_rule_active_no_scrap")  # 已不在时再降级
        alembic("upgrade", "head")
        assert state()[1]
    finally:
        eng.dispose()
        with server.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        server.dispose()


def test_product_new_version_copies_active_bom(client: TestClient, db: Session) -> None:
    """产品出新版本：当前生效 BOM 复制成新版本下的草稿（含明细、替代料）；没有生效就不复制。"""
    m = Mes(client, db)
    b = B(m)
    p1 = b.product("FG")
    op = m.post("operation", {"code": "OP1", "name": "op"})
    v1 = b.bom(p1)
    ln = b.line(v1, 10, qty="2.5", uom_id=b.g, operation_id=op["id"])
    m.post(
        "bom_line_substitute",
        {"bom_line_id": ln["id"], "material_id": b.mats[1]["id"], "priority": 1},
    )
    b.act(v1, "activate")
    b.bom(p1)  # 另一个草稿不参与
    p2 = m.action("product", p1["id"], "new-version")
    assert p2["version"] == 2
    boms = m.list("bom", product=p2["id"])["data"]
    assert len(boms) == 1
    nb = boms[0]
    assert (nb["version"], nb["status"], nb["copied_from_id"]) == (1, "draft", v1["id"])
    t = b.tree(bom_id=nb["id"])
    (line,) = t["lines"]
    assert line["qty"] == "2.5" and line["operation_id"] == op["id"]
    assert [x["material_id"] for x in line["substitutes"]] == [b.mats[1]["id"]]
    # 旧产品版本的 BOM 不变
    assert b.get(v1)["status"] == "active"
    # 没有生效 BOM：不复制
    q1 = b.product("NOBOM")
    b.bom(q1)
    q2 = m.action("product", q1["id"], "new-version")
    assert m.list("bom", product=q2["id"])["count"] == 0


# ---------------- PUT /mes/bom/{id}/lines（整单替换，F3 v1.1 第 13 条） ----------------
def _put(m: Mes, bom: Any, body: Any, status: int, h: Any = None) -> Any:
    r = m.c.put(f"{BOM}/{bom['id']}/lines", headers=h or m.h, json=body)
    assert r.status_code == status, r.text
    return r.json()


def _ml(b: B, n: int, mat: int = 0, **kw: Any) -> dict[str, Any]:
    return {
        "line_no": n,
        "component_type": "material",
        "material_id": b.mats[mat]["id"],
        "qty": 1,
        "uom_id": b.ea,
        "consume_mode": "issue",
        **kw,
    }


def _locs(err: Any) -> list[list[Any]]:
    return [d["loc"] for d in err["detail"]]


def test_bom_put_lines_replace(client: TestClient, db: Session) -> None:
    """整单替换：明细 + 替代料一起写入；再 PUT 替换掉旧的；空列表清空。"""
    m = Mes(client, db)
    b = B(m)
    fg, semi = b.product("FG"), b.product("SEMI")
    sb = b.bom(semi)
    b.line(sb, 10, material_id=b.mats[3]["id"])
    b.act(sb, "activate")
    v = b.bom(fg)
    old = b.line(v, 10)
    body = {
        "lines": [
            _ml(
                b,
                10,
                0,
                qty=2.5,
                uom_id=b.g,
                substitutes=[
                    {"material_id": b.mats[1]["id"], "priority": 1},
                    {"material_id": b.mats[2]["id"], "priority": 2, "remark": "x"},
                ],
            ),
            {
                "line_no": 20,
                "component_type": "product",
                "component_product_id": semi["id"],
                "qty": 1,
                "uom_id": b.ea,
                "consume_mode": "issue",
            },
        ]
    }
    out = _put(m, v, body, 200)
    assert out["id"] == v["id"] and out["status"] == "draft"
    assert [ln["line_no"] for ln in out["lines"]] == [10, 20]
    assert out["lines"][0]["id"] != old["id"]
    assert out["lines"][0]["qty"] == "2.5"
    assert [s["priority"] for s in out["lines"][0]["substitutes"]] == [1, 2]
    assert out["lines"][1]["material_id"] is None
    assert out["lines"][1]["substitutes"] == []
    assert m.c.get(f"{API}/bom-line/{old['id']}", headers=m.h).status_code == 404
    # 再 PUT：旧明细与替代料都被替换
    out2 = _put(
        m,
        v,
        {
            "lines": [
                _ml(
                    b,
                    30,
                    1,
                    substitutes=[{"material_id": b.mats[0]["id"], "priority": 5}],
                )
            ]
        },
        200,
    )
    assert [ln["line_no"] for ln in out2["lines"]] == [30]
    subs = m.c.get(f"{API}/bom-line-substitute", headers=m.h).json()
    assert {s["priority"] for s in subs["data"]} == {5}
    assert _put(m, v, {"lines": []}, 200)["lines"] == []


def test_bom_put_lines_errors(client: TestClient, db: Session) -> None:
    """D34 顺序（403 → 404 → 409 / 422）、422 路径、整单原子性。"""
    m = Mes(client, db)
    b = B(m)
    fg = b.product("FG")
    v = b.bom(fg)
    b.line(v, 10)
    hm = _member(client, db, m)
    # 无权限：合法 / 非法请求体、不存在的 BOM 都 403，不带字段明细
    for bad in ({"lines": []}, {"lines": [{"nope": 1}]}, {"x": 1}):
        err = _put(m, v, bad, 403, h=hm)
        assert err == {"detail": "Not enough permissions"}
    _put(m, {"id": "00000000-0000-0000-0000-000000000000"}, {"lines": []}, 403, h=hm)
    _put(m, {"id": "00000000-0000-0000-0000-000000000000"}, {"lines": []}, 404)
    # 严格载荷：未知字段 / 类型错误按 Pydantic 定位
    err = _put(m, v, {"lines": [_ml(b, 10, bom_id=v["id"])]}, 422)
    assert _locs(err) == [["body", "lines", 0, "bom_id"]]
    err = _put(
        m,
        v,
        {"lines": [_ml(b, 10, substitutes=[{"material_id": "x", "priority": 1}])]},
        422,
    )
    assert _locs(err) == [["body", "lines", 0, "substitutes", 0, "material_id"]]
    assert _locs(_put(m, v, {}, 422)) == [["body", "lines"]]
    # 业务校验：第二行 qty 非法 → 422 定位到 lines[1]，第一行也没写入
    before = b.get(v)
    err = _put(m, v, {"lines": [_ml(b, 10, 1), _ml(b, 20, qty=-1)]}, 422)
    assert _locs(err) == [["body", "lines", 1, "qty"]]
    lines = m.c.get(f"{API}/bom-line", headers=m.h, params={"bom_id": v["id"]}).json()
    assert [(x["line_no"], x["material_id"]) for x in lines["data"]] == [
        (10, b.mats[0]["id"])
    ]
    assert b.get(v)["updated_at"] == before["updated_at"]
    # 必填缺失：通用字段名换成列名
    err = _put(m, v, {"lines": [{"line_no": 10, "component_type": "material"}]}, 422)
    assert ["body", "lines", 0, "material_id"] in _locs(err)
    assert ["body", "lines", 0, "uom_id"] in _locs(err)
    # 替代料：与主料相同 → lines[0].substitutes[1].material_id；同行重复优先级
    err = _put(
        m,
        v,
        {
            "lines": [
                _ml(
                    b,
                    10,
                    substitutes=[
                        {"material_id": b.mats[1]["id"], "priority": 1},
                        {"material_id": b.mats[0]["id"], "priority": 2},
                    ],
                )
            ]
        },
        422,
    )
    assert _locs(err) == [["body", "lines", 0, "substitutes", 1, "material_id"]]
    err = _put(
        m,
        v,
        {
            "lines": [
                _ml(b, 10),
                _ml(
                    b,
                    10,
                    substitutes=[
                        {"material_id": b.mats[1]["id"], "priority": 1},
                        {"material_id": b.mats[2]["id"], "priority": 1},
                    ],
                ),
            ]
        },
        422,
    )
    assert _locs(err) == [
        ["body", "lines", 1, "line_no"],
        ["body", "lines", 1, "substitutes", 1, "priority"],
    ]
    # 非草稿 409（生效后、作废后）
    b.act(v, "activate")
    err = _put(m, v, {"lines": [_ml(b, 10)]}, 409)
    assert "only draft" in err["detail"]
    assert len(b.tree(bom_id=v["id"])["lines"]) == 1


def test_bom_structure_rules(client: TestClient, db: Session) -> None:
    """bom_cycle（自己 / 间接）与 bom_depth_exceeded：整单接口与逐行接口。"""
    m = Mes(client, db)
    b = B(m)
    a, c, d, raw = b.product("A"), b.product("C"), b.product("D"), b.product("RAW")

    def pl(p: Any, n: int = 10) -> dict[str, Any]:
        return {
            "line_no": n,
            "component_type": "product",
            "component_product_id": p["id"],
            "qty": 1,
            "uom_id": b.ea,
            "consume_mode": "issue",
        }

    def code(err: Any) -> tuple[str, list[Any]]:
        return err["detail"][0]["type"], err["detail"][0]["loc"]

    rb = b.bom(raw)
    b.line(rb, 10)
    b.act(rb, "activate")
    a1 = b.bom(a)  # A 先有只含物料的生效版本（D48：被引用的半成品须有生效 BOM）
    b.line(a1, 10)
    b.act(a1, "activate")
    cb = b.bom(c)  # C 生效：C → A
    b.line(cb, 10, component_type="product", component_product_id=a["id"])
    b.act(cb, "activate")
    ab = b.bom(a)
    # 自己引用自己
    err = _put(m, ab, {"lines": [_ml(b, 10), pl(a, 20)]}, 422)
    assert code(err) == ("bom_cycle", ["body", "lines", 1, "component_product_id"])
    err = b.line(ab, 10, 422, component_type="product", component_product_id=a["id"])
    assert code(err) == ("bom_cycle", ["body", "component_product_id"])
    # 间接：A → C，而 C 的生效 BOM 引用 A
    err = _put(m, ab, {"lines": [pl(c)]}, 422)
    assert code(err) == ("bom_cycle", ["body", "lines", 0, "component_product_id"])
    err = b.line(ab, 10, 422, component_type="product", component_product_id=c["id"])
    assert code(err) == ("bom_cycle", ["body", "component_product_id"])
    # 三级：D → C，C 的生效 BOM 里已有半成品行
    db_ = b.bom(d)
    err = _put(m, db_, {"lines": [pl(c)]}, 422)
    assert code(err) == (
        "bom_depth_exceeded",
        ["body", "lines", 0, "component_product_id"],
    )
    err = b.line(db_, 10, 422, component_type="product", component_product_id=c["id"])
    assert code(err) == ("bom_depth_exceeded", ["body", "component_product_id"])
    # 逐行修改同样校验
    ln = b.line(db_, 10, component_type="product", component_product_id=raw["id"])
    r = m.c.patch(
        f"{API}/bom-line/{ln['id']}",
        headers=m.h,
        json={"component_product_id": c["id"]},
    )
    assert (
        r.status_code == 422 and r.json()["detail"][0]["type"] == "bom_depth_exceeded"
    )
    # 合法：引用只有物料的半成品
    out = _put(m, db_, {"lines": [pl(raw)]}, 200)
    assert out["lines"][0]["component_product_id"] == raw["id"]


def test_bom_d48(client: TestClient, db: Session) -> None:
    """D48：引用无生效 BOM 的半成品不能生效；被引用的唯一生效版本不能作废（被替代可以）；
    PATCH 只改用量时不重跑结构校验。"""
    m = Mes(client, db)
    b = B(m)
    a, bp, x = b.product("A"), b.product("B"), b.product("X")
    ab = b.bom(a)
    ln = b.line(ab, 10, component_type="product", component_product_id=bp["id"])
    err = b.act(ab, "activate", 409)["detail"]
    assert err["code"] == "bom_component_no_active"
    det = {d["product"]: d for d in err["details"]}
    assert det["B"]["bom_id"] is None and det["B"]["bom_version"] is None
    assert det["A"]["bom_id"] == ab["id"]
    bb = b.bom(bp)
    b.line(bb, 10)
    b.act(bb, "activate")
    b.act(ab, "activate")
    # B v1 被 A 引用：不能作废
    err = b.act(bb, "void", 409)["detail"]
    assert err["code"] == "bom_referenced"
    assert [(d["product"], d["bom_id"]) for d in err["details"]] == [("A", ab["id"])]
    assert b.get(bb)["status"] == "active"
    # 被新版本替代不受影响；新的唯一生效版本仍不能作废
    bb2 = b.act(bb, "copy")
    b.act(bb2, "activate")
    assert b.get(bb)["status"] == "superseded"
    assert b.act(bb2, "void", 409)["detail"]["code"] == "bom_referenced"
    # 引用方作废后可以作废；草稿作废不受影响
    b.act(ab, "void")
    b.act(bb2, "void")
    xd = b.bom(x)
    b.act(xd, "void")
    # PATCH：结构已失效（X 引用的 B 现在生效 BOM 有半成品行），只改 qty 不拦
    bb3 = b.act(bb, "copy")
    xb = b.bom(x)
    b.line(xb, 10)
    b.act(xb, "activate")
    d = b.product("D")
    db_ = b.bom(d)
    dl = b.line(db_, 10, component_type="product", component_product_id=bp["id"])
    b.line(bb3, 20, component_type="product", component_product_id=x["id"])
    b.act(bb3, "activate")  # B 生效版本现在有半成品行 → D 草稿那行结构失效
    r = m.c.patch(f"{API}/bom-line/{dl['id']}", headers=m.h, json={"qty": 3})
    assert r.status_code == 200, r.text
    r = m.c.patch(
        f"{API}/bom-line/{dl['id']}",
        headers=m.h,
        json={"component_product_id": bp["id"], "component_type": "product"},
    )
    assert r.status_code == 200, r.text  # 值没变：视为未改动，不重跑
    r = m.c.patch(
        f"{API}/bom-line/{dl['id']}",
        headers=m.h,
        json={"component_type": "material", "material_id": b.mats[0]["id"]},
    )
    assert r.status_code == 200, r.text
    r = m.c.patch(
        f"{API}/bom-line/{dl['id']}",
        headers=m.h,
        json={"component_type": "product", "component_product_id": bp["id"]},
    )
    assert r.json()["detail"][0]["type"] == "bom_depth_exceeded"
    assert ln["id"]


def test_bom_line_decimals_d49(client: TestClient, db: Session) -> None:
    """D49：qty ≤ 6 位小数、scrap_rate ≤ 4 位，超出 422 value_error，不静默舍入。"""
    m = Mes(client, db)
    b = B(m)
    v = b.bom(b.product("FG"))
    assert b.line(v, 10, uom_id=b.g, qty=1.123456)["qty"] == "1.123456"
    err = b.line(v, 20, 422, uom_id=b.g, qty=1.1234567)
    assert [(d["loc"], d["type"]) for d in err["detail"]] == [
        (["body", "qty"], "value_error")
    ]
    assert b.line(v, 30, uom_id=b.g, qty="1.5")["qty"] == "1.5"
    assert b.line(v, 40, scrap_rate=0.0125)["scrap_rate"] == "0.0125"
    err = b.line(v, 50, 422, scrap_rate=0.01255)
    assert err["detail"][0]["loc"] == ["body", "scrap_rate"]
    assert err["detail"][0]["code"] == "value_error"
    assert err["detail"][0]["ctx"] == {"max_places": 4}  # D72
    ln = b.line(v, 60)
    r = m.c.patch(f"{API}/bom-line/{ln['id']}", headers=m.h, json={"qty": 2.0000001})
    assert r.status_code == 422 and r.json()["detail"][0]["type"] == "value_error"
    err = _put(
        m,
        v,
        {"lines": [_ml(b, 10, uom_id=b.g, qty=1.5), _ml(b, 20, scrap_rate=0.01255)]},
        422,
    )
    assert _locs(err) == [["body", "lines", 1, "scrap_rate"]]
    assert err["detail"][0]["type"] == "value_error"
    err = _put(m, v, {"lines": [_ml(b, 10, uom_id=b.g, qty="1.1234567")]}, 422)
    assert _locs(err) == [["body", "lines", 0, "qty"]]
    out = _put(m, v, {"lines": [_ml(b, 10, uom_id=b.g, qty="1.123456")]}, 200)
    assert out["lines"][0]["qty"] == "1.123456"


def test_bom_line_decimals_d49_edges(client: TestClient, db: Session) -> None:
    """D49 补充：尾随零不计位数；科学计数按数值计；scrap_rate 0..1；qty > 0。"""
    m = Mes(client, db)
    b = B(m)
    v = b.bom(b.product("FG"))
    n = iter(range(10, 1000, 10))

    def ok(**kw: Any) -> Any:
        return b.line(v, next(n), uom_id=b.g, **kw)

    def bad(t: str, **kw: Any) -> None:
        err = b.line(v, next(n), 422, uom_id=b.g, **kw)
        assert err["detail"][0]["type"] == t, err

    assert ok(qty="1.5000000")["qty"] == "1.5"
    assert ok(qty=1.50000000)["qty"] == "1.5"
    assert ok(scrap_rate="0.01250000")["scrap_rate"] == "0.0125"
    assert ok(qty="1e-6")["qty"] == "0.000001"
    assert ok(qty=1e-6)["qty"] == "0.000001"
    bad("value_error", qty="1e-7")
    bad("value_error", qty=1e-7)
    bad("value_error", qty="1.2E-7")
    bad("value_error", scrap_rate="1.5e-5")
    for sr in (0, "0", 1, "1", "1.0000"):
        ok(scrap_rate=sr)
    bad("value_error", scrap_rate=-0.0001)
    bad("value_error", scrap_rate="1.0001")
    bad("value_error", qty=0)
    bad("value_error", qty="0.000000")
    bad("value_error", qty=-1)
    bad("value_error", qty="-0.5")


def test_bom_put_lines_string_decimals(client: TestClient, db: Session) -> None:
    """整单接口：qty / scrap_rate 以字符串提交；位数按原始字符串计。"""
    m = Mes(client, db)
    b = B(m)
    v = b.bom(b.product("FG"))
    out = _put(
        m, v, {"lines": [_ml(b, 10, uom_id=b.g, qty="1.5000000", scrap_rate="0")]}, 200
    )
    assert (out["lines"][0]["qty"], out["lines"][0]["scrap_rate"]) == ("1.5", "0")
    out = _put(m, v, {"lines": [_ml(b, 10, uom_id=b.g, qty="2", scrap_rate="1")]}, 200)
    assert out["lines"][0]["scrap_rate"] == "1"
    for k, val in (("qty", "1e-7"), ("qty", 1e-7), ("scrap_rate", "0.01255")):
        err = _put(m, v, {"lines": [_ml(b, 10, uom_id=b.g, **{k: val})]}, 422)
        assert _locs(err) == [["body", "lines", 0, k]]
        assert err["detail"][0]["type"] == "value_error"
    err = _put(m, v, {"lines": [_ml(b, 10, qty="abc")]}, 422)
    assert _locs(err) == [["body", "lines", 0, "qty"]]


def test_bom_d49_qa_findings(client: TestClient, db: Session) -> None:
    """QA：scrap_rate=1 合法；qty=0.0000001 先报 value_error（不先舍入成 0）。"""
    m = Mes(client, db)
    b = B(m)
    v = b.bom(b.product("FG"))
    assert b.line(v, 10, scrap_rate=1)["scrap_rate"] == "1"
    assert b.line(v, 20, scrap_rate="1")["scrap_rate"] == "1"
    for i, q in enumerate(("0.0000001", 0.0000001)):
        err = b.line(v, 30 + i, 422, uom_id=b.g, qty=q)
        assert [(d["loc"], d["type"]) for d in err["detail"]] == [
            (["body", "qty"], "value_error")
        ]
        err = _put(m, v, {"lines": [_ml(b, 10, uom_id=b.g, qty=q)]}, 422)
        assert [(d["loc"], d["type"]) for d in err["detail"]] == [
            (["body", "lines", 0, "qty"], "value_error")
        ]
    out = _put(m, v, {"lines": [_ml(b, 10, scrap_rate=1)]}, 200)
    assert out["lines"][0]["scrap_rate"] == "1"


def test_bom_d50_decimal_strings(client: TestClient, db: Session) -> None:
    """D50：P1 新接口（整单 PUT、两级树）小数字段输出定点字符串；D72 起通用接口也是字符串。"""
    from app.core.spec.serialize import dec_str

    assert [dec_str(x) for x in ("1E-6", 1e-6, "2.000", 100, "-0.0", "1.50")] == [
        "0.000001",
        "0.000001",
        "2",
        "100",
        "0",
        "1.5",
    ]
    m = Mes(client, db)
    b = B(m)
    v = b.bom(b.product("FG"))
    body = {
        "lines": [
            _ml(b, 10, uom_id=b.g, qty="123456789012.123456", scrap_rate="0.0150"),
            _ml(b, 20, 1, uom_id=b.g, qty=1e-6, scrap_rate=0),
            _ml(b, 30, 2, qty=2),
        ]
    }
    out = _put(m, v, body, 200)
    got = [(x["qty"], x["scrap_rate"]) for x in out["lines"]]
    assert got == [("123456789012.123456", "0.015"), ("0.000001", "0"), ("2", "0")]
    t = b.tree(bom_id=v["id"])
    assert [(x["qty"], x["scrap_rate"]) for x in t["lines"]] == got
    # D72：通用接口的定点数也输出字符串（D50）
    lst = m.c.get(f"{API}/bom-line", headers=m.h, params={"bom_id": v["id"]}).json()
    assert {x["qty"] for x in lst["data"]} == {"123456789012.123456", "0.000001", "2"}


def test_bom_put_lines_extra_field_unknown_field(
    client: TestClient, db: Session
) -> None:
    """D65：行里多余字段（pydantic extra_forbidden）→ code unknown_field，type 保留。"""
    m = Mes(client, db)
    b = B(m)
    v = b.bom(b.product("FGX"))
    err = _put(m, v, {"lines": [_ml(b, 10, foo=1)]}, 422)
    d = next(x for x in err["detail"] if x["loc"][-1] == "foo")
    assert d["loc"] == ["body", "lines", 0, "foo"]
    assert d["type"] == "extra_forbidden" and d["code"] == "unknown_field"
