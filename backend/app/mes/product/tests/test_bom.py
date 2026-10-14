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
    # status / version 是系统字段，载荷里的值被忽略
    v2 = m.post("bom", {"product_id": p["id"], "status": "active", "version": 9})
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
    # 客户端传的确认人 / 确认时间被忽略，一律用当前操作人和当前时间
    r = m.c.post(
        f"{BOM}/{v1['id']}/activate",
        headers=m.h,
        json={"confirmed_by": "mallory", "confirmed_at": "2000-01-01T00:00:00Z"},
    )
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
    l1 = b.line(v1, 10, qty="1.2345678", uom_id=b.g, per_basis="die", scrap_rate=0.02)
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
    assert first["qty"] == 1.234568 and first["per_basis"] == "die"
    assert first["scrap_rate"] == 0.02 and first["uom_id"] == b.g
    assert [s["priority"] for s in first["substitutes"]] == [1, 2]
    assert t["lines"][1]["consume_mode"] == "mounted"
    # 复制出来的草稿可以改，原版本不变
    m.patch("bom_line", first["id"], {"qty": 3})
    assert b.tree(bom_id=v1["id"])["lines"][0]["qty"] == 1.234568
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
    # 质量单位允许小数，四舍五入到 6 位
    ln = b.line(v, 10, qty="0.0000005", uom_id=b.g)
    assert ln["qty"] == 0.000001
    b.line(v, 11, 422, qty=0)
    b.line(v, 12, 422, qty="abc")
    b.line(v, 13, 422, scrap_rate=1)
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
    err = b.act(sb2, "activate", 422)
    assert "3 levels" in err["detail"][0]["msg"]
    # 循环：RAW 的新版本引用 FG → FG → SEMI → … 先被深度或循环拦下
    rb2 = b.act(rb, "copy")
    b.line(rb2, 20, component_type="product", component_product_id=fg["id"])
    err = b.act(rb2, "activate", 422)
    assert "circular" in err["detail"][0]["msg"] or "levels" in err["detail"][0]["msg"]
    # 直接两点循环：A ↔ B
    a, c = b.product("A"), b.product("C")
    ab = b.bom(a)
    b.line(ab, 10, component_type="product", component_product_id=c["id"])
    b.act(ab, "activate")
    cb = b.bom(c)
    b.line(cb, 10, component_type="product", component_product_id=a["id"])
    err = b.act(cb, "activate", 422)
    assert "circular" in err["detail"][0]["msg"]
    assert b.get(cb)["status"] == "draft"


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
        env = {**os.environ, "MIGRATION_DATABASE_URL": url}
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
    assert line["qty"] == 2.5 and line["operation_id"] == op["id"]
    assert [x["material_id"] for x in line["substitutes"]] == [b.mats[1]["id"]]
    # 旧产品版本的 BOM 不变
    assert b.get(v1)["status"] == "active"
    # 没有生效 BOM：不复制
    q1 = b.product("NOBOM")
    b.bom(q1)
    q2 = m.action("product", q1["id"], "new-version")
    assert m.list("bom", product=q2["id"])["count"] == 0
