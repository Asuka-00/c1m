"""泛半导体阶段 1：单元转换与单元谱系、芯片级晶圆图、Wafer / Die Bank、NCR / MRB、SPC 判异自动 Hold。"""

from typing import Any

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core import error_codes as ec
from app.mes.execution.tests.test_exec import EXEC, Line
from app.platform.users import service as crud
from app.platform.users.schemas import UserCreate
from app.testing.mes import API
from app.testing.utils import (
    login_name,
    random_email,
    random_lower_string,
    username_for,
)


def _codes(r: Any) -> set[int]:
    d = r["detail"]
    return {x["code"] for x in d} if isinstance(d, list) else {d["code"]}


def _bins(f: Line) -> None:
    f.m.post("bin_code", {"code": "1", "name": "pass", "is_good": True})
    f.m.post("bin_code", {"code": "X", "name": "fail", "is_good": False})


def _admin(f: Line, client: TestClient, db: Session) -> dict[str, str]:
    """租户内再加一个管理员（用于多级审批）。"""
    email, pw = random_email(), random_lower_string()
    crud.create_user(
        session=db,
        user_create=UserCreate(email=email, username=username_for(email), password=pw),
    )
    client.post(
        f"{API[:-4]}/tenants/{f.m.tid}/members",
        headers=f.m.h,
        json={"username": login_name(email), "roles": ["admin"]},
    )
    tok = client.post(
        f"{API[:-4]}/login/access-token",
        data={"username": login_name(email), "password": pw},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {tok}", "X-Tenant-ID": f.m.tid}


def _complete(f: Line, lot: dict[str, Any]) -> None:
    for _ in range(4):  # 10 → 20 → SUB#10 → 40
        f.run_step(lot)
    assert f.lot(lot)["lot_status"] == "completed"


# ---------------- 单元转换 ----------------
def test_convert_split_assemble_and_unit_trace(client: TestClient, db: Session) -> None:
    f = Line(client, db)
    (lot,) = f.start(2)
    wafers = f.ctx(lot)["units"]
    url = f"{EXEC}/lots/{lot['id']}/convert"
    assert ec.CONVERT_RATIO in _codes(
        f.post(url, {"to_kind": "die", "per_parent": 2, "per_child": 2}, 422)
    )
    pv = f.post(url, {"to_kind": "die", "per_parent": 3, "preview": True})
    assert pv["count"] == 6 and f.lot(lot)["qty"] == 2
    r = f.post(url, {"to_kind": "die", "per_parent": 3})
    assert r["count"] == 6 and r["codes"][0] == f"{lot['code']}-D0001"
    assert r["lot"]["qty"] == 6 and r["lot"]["tracking_level"] == "unit"
    us = f.ctx(lot)["units"]
    assert len(us) == 6 and {u["unit_kind"] for u in us} == {"die"}
    st = {
        w["code"]: w["wafer_status"] for w in f.m.list("wafer", lot=lot["id"])["data"]
    }
    assert st[wafers[0]["code"]] == "converted"
    # N → 1：每 4 颗合成一条，最后一条不满
    r = f.post(url, {"to_kind": "strip", "per_child": 4})
    assert r["count"] == 2 and f.lot(lot)["qty"] == 2
    gs = f.m.list("unit_genealogy", lot=lot["id"], relation="assemble")["data"]
    per_strip: dict[str, int] = {}
    for g in gs:
        per_strip[g["child_unit_id"]] = per_strip.get(g["child_unit_id"], 0) + 1
    assert len(gs) == 6 and sorted(per_strip.values()) == [2, 4]
    assert f.m.list("lot_history", lot=lot["id"], action="convert")["count"] == 2
    # 正向：晶圆 → 3 颗芯片 → 1~2 条；反向：条 → 芯片 → 晶圆
    t = client.get(
        f"{EXEC}/trace",
        headers=f.m.h,
        params={"kind": "wafer", "code": wafers[0]["code"]},
    ).json()
    fwd = t["units"]["forward"]["units"]
    assert [u["unit_kind"] for u in fwd].count("die") == 3
    assert {u["unit_kind"] for u in fwd if u["level"] == 2} == {"strip"}
    strip = f.ctx(lot)["units"][0]
    t = client.get(
        f"{EXEC}/trace",
        headers=f.m.h,
        params={"kind": "wafer", "code": strip["code"]},
    ).json()
    back = t["units"]["backward"]["units"]
    assert {u["unit_kind"] for u in back if u["level"] == 1} == {"die"}
    assert {u["unit_kind"] for u in back if u["level"] == 2} == {"wafer"}
    # 1 → N：切单按条带实际装入数（4 + 2），而不是每条满 4 颗
    r = f.post(url, {"to_kind": "package", "per_parent": 4})
    assert r["count"] == 6 and f.lot(lot)["qty"] == 6
    # 加工中不能转换；数量级批次不能转换
    f.stage(lot, "move_in", equipment_id=f.eq["id"])
    f.stage(lot, "track_in", equipment_id=f.eq["id"])
    f.post(url, {"to_kind": "unit"}, 422)
    q = Line(client, db, {"product": {"tracking_level": "quantity"}})
    (ql,) = q.start(10)
    assert ec.CONVERT_QUANTITY_LOT in _codes(
        q.post(f"{EXEC}/lots/{ql['id']}/convert", {"to_kind": "die"}, 422)
    )


# ---------------- 晶圆图 + 按图取良品 ----------------
def test_die_map_import_and_convert_by_map(client: TestClient, db: Session) -> None:
    f = Line(client, db)
    _bins(f)
    (lot,) = f.start(2)
    w1, w2 = f.ctx(lot)["units"]
    url = f"{EXEC}/lots/{lot['id']}/die-maps"
    conv = f"{EXEC}/lots/{lot['id']}/convert"
    assert ec.CONVERT_NO_MAP in _codes(
        f.post(conv, {"to_kind": "die", "use_map": True}, 422)
    )
    bad = f.post(
        url,
        {
            "maps": [
                {"unit_code": "NOPE", "dies": [[0, 0, "1"]]},
                {"unit_id": w1["id"], "dies": [[0, 0, "1"], [0, 0, "1"]]},
                {"unit_id": w2["id"], "dies": [[0, 0, "Q"]]},
            ]
        },
        422,
    )
    assert _codes(bad) == {ec.DIE_MAP_UNIT, ec.DIE_MAP_DUPLICATE, ec.DIE_MAP_BINS}
    r = f.post(
        url,
        {
            "test_kind": "cp",
            "source": "cp1.csv",
            "maps": [
                {"unit_id": w1["id"], "dies": [[0, 0, "1"], [1, 0, "X"]]},
                {"unit_code": w2["code"], "dies": [[0, 0, "1"]]},
            ],
        },
    )
    assert [m["yield_pct"] for m in r["maps"]] == [50.0, 100.0]
    # 重测覆盖：旧图不再是当前图
    r = f.post(
        url,
        {
            "maps": [
                {
                    "unit_id": w1["id"],
                    "dies": [[0, 0, "1"], [1, 0, "1"], [0, 1, "X"]],
                }
            ]
        },
    )
    hist = client.get(f"{EXEC}/units/{w1['id']}/die-maps", headers=f.m.h).json()
    assert [m["is_current"] for m in hist["data"]] == [True, False]
    d = client.get(f"{EXEC}/die-maps/{r['maps'][0]['id']}", headers=f.m.h).json()
    assert d["gross"] == 3 and d["good"] == 2 and d["rows"] == 2 and d["cols"] == 2
    assert {x["bin"]: x["count"] for x in d["legend"]} == {"1": 2, "X": 1}
    wm = client.get(f"{EXEC}/lots/{lot['id']}/wafer-map", headers=f.m.h).json()
    assert wm["slots"][0]["wafer"]["die_map"]["good"] == 2
    r = f.post(conv, {"to_kind": "die", "use_map": True})
    assert r["count"] == 3 and r["bad_dies"] == 1
    attrs = sorted(
        (u["attrs"]["x"], u["attrs"]["y"])
        for u in f.m.list("wafer", lot=lot["id"], unit_kind="die")["data"]
    )
    assert attrs == [(0, 0), (0, 0), (1, 0)]


# ---------------- 工步自动转换 ----------------
def test_step_auto_convert_at_track_out(client: TestClient, db: Session) -> None:
    f = Line(
        client,
        db,
        {
            10: {"convert_to": "die", "convert_mode": "map"},
            20: {"convert_to": "strip", "convert_mode": "assemble", "convert_ratio": 2},
        },
    )
    _bins(f)
    a, b = f.start(2, 1)
    eq = {"equipment_id": f.eq["id"]}
    f.stage(a, "move_in", **eq)
    f.stage(a, "track_in", **eq)
    assert f.ctx(a)["step"]["convert"] == {"to_kind": "die", "mode": "map", "ratio": 1}
    # 缺晶圆图：下机整体失败，批次仍在加工
    assert ec.CONVERT_NO_MAP in _codes(f.stage(a, "track_out", 422))
    assert f.lot(a)["lot_status"] == "running"
    w1, w2 = f.ctx(a)["units"]
    f.post(
        f"{EXEC}/lots/{a['id']}/die-maps",
        {
            "maps": [
                {"unit_id": w1["id"], "dies": [[0, 0, "1"], [1, 0, "X"], [2, 0, "1"]]},
                {"unit_id": w2["id"], "dies": [[0, 0, "1"]]},
            ]
        },
    )
    r = f.stage(a, "track_out")
    assert r["converted"] == {"to_kind": "die", "count": 3, "bad_dies": 1}
    assert r["lot"]["qty"] == 3 and r["lot"]["lot_status"] == "tracked_out"
    h = f.m.list("lot_history", lot=a["id"], action="convert")["data"]
    assert len(h) == 1 and h[0]["details"]["auto"] is True
    f.stage(a, "move_out")
    f.stage(a, "move_in", **eq)
    f.stage(a, "track_in", **eq)
    r = f.stage(a, "track_out")
    assert r["converted"] == {"to_kind": "strip", "count": 2, "bad_dies": 0}
    assert {u["unit_kind"] for u in f.ctx(a)["units"]} == {"strip"}
    # 待返工：不转换
    f.stage(b, "move_in", **eq)
    f.stage(b, "track_in", **eq)
    (wb,) = f.ctx(b)["units"]
    r = f.stage(
        b,
        "track_out",
        rework_units=[{"unit_id": wb["id"], "reason_id": f.reasons["rework"]["id"]}],
    )
    assert r["converted"] is None and r["lot"]["tracking_level"] != "unit"


# ---------------- Bank ----------------
def test_bank_in_and_issue(client: TestClient, db: Session) -> None:
    f = Line(client, db)
    bank = f.m.post("bank", {"code": "WB", "name": "wafer bank"})
    a, b = f.start(3, 2)
    f.post(f"{EXEC}/lots/{a['id']}/bank-in", {"bank_id": bank["id"]}, 422)
    for x in (a, b):
        _complete(f, x)
        r = f.post(f"{EXEC}/lots/{x['id']}/bank-in", {"bank_id": bank["id"]})
        assert r["lot"]["lot_status"] == "banked"
    wo = f.m.post(
        "work_order",
        {"product_id": f.product["id"], "lot_type_id": f.lt["id"], "planned_qty": 100},
    )
    f.post(f"{API}/work-order/{wo['id']}/transition", {"action": "release"})
    ua = f.ctx(a)["units"]
    url = f"{EXEC}/bank/issue"
    assert ec.BANK_SOURCES in _codes(
        f.post(
            url,
            {"work_order_id": wo["id"], "lots": [{"lot_id": a["id"]}] * 2},
            422,
        )
    )
    assert ec.BANK_UNITS in _codes(
        f.post(
            url,
            {
                "work_order_id": wo["id"],
                "lots": [{"lot_id": a["id"], "unit_ids": [f.ctx(b)["units"][0]["id"]]}],
            },
            422,
        )
    )
    r = f.post(
        url,
        {
            "work_order_id": wo["id"],
            "lots": [
                {"lot_id": a["id"], "unit_ids": [ua[0]["id"], ua[1]["id"]]},
                {"lot_id": b["id"]},
            ],
        },
    )
    new = r["lot"]
    assert new["qty"] == 4 and new["lot_status"] == "waiting"
    assert {x["lot"]: x["left"] for x in r["sources"]} == {a["code"]: 1, b["code"]: 0}
    assert f.lot(a)["lot_status"] == "banked" and f.lot(a)["qty"] == 1
    assert f.lot(b)["lot_status"] == "issued"
    assert {u["status"] for u in f.ctx(new)["units"]} == {"waiting"}
    g = f.m.list("lot_genealogy", relation="bank_issue")["data"]
    assert len(g) == 2
    # 领用开出的批次不能撤销开批
    f.post(f"{API}/work-order/{wo['id']}/undo-start", {}, 422)
    # 新批次能正常过站
    f.run_step(new)
    # 已领完的批次不能再领
    f.post(url, {"work_order_id": wo["id"], "lots": [{"lot_id": b["id"]}]}, 422)


# ---------------- NCR / MRB ----------------
def test_ncr_review_and_scrap(client: TestClient, db: Session) -> None:
    from app.platform.notification.tests.test_notification import _mine, _sub_all

    f = Line(client, db)
    _sub_all(f)
    h2, h3 = _admin(f, client, db), _admin(f, client, db)
    (lot,) = f.start(3)
    us = f.ctx(lot)["units"]
    url = f"{EXEC}/ncr"
    n = f.post(
        url,
        {
            "lot_id": lot["id"],
            "title": "scratch",
            "severity": "major",
            "unit_ids": [us[0]["id"]],
        },
    )
    ncr = n["ncr"]
    assert ncr["ncr_status"] == "open" and ncr["required_levels"] == 2
    assert ncr["code"].startswith("NCR") and n["hold_active"] and f.lot(lot)["on_hold"]
    nid = ncr["id"]
    assert ec.NCR_SCRAP_REASON in _codes(
        f.post(f"{url}/{nid}/propose", {"disposition": "scrap"}, 422)
    )
    f.post(
        f"{url}/{nid}/propose",
        {"disposition": "scrap", "scrap_reason_id": f.reasons["scrap"]["id"]},
    )
    note = next(
        x
        for x in _mine(f, page_size=100)["data"]
        if x["event_type"] == "mes.ncr_review"
    )
    assert note["link"] == f"/mes/ncr?id={nid}"
    # 提案人不能审批；驳回须备注并回到 open
    assert ec.NCR_SELF_APPROVE in _codes(
        f.post(f"{url}/{nid}/approve", {"decision": "approve"}, 422)
    )
    assert ec.NCR_REJECT_COMMENT in _codes(
        f.post(f"{url}/{nid}/approve", {"decision": "reject"}, 422, h2)
    )
    r = f.post(f"{url}/{nid}/approve", {"decision": "reject", "comment": "why"}, h=h2)
    assert r["ncr"]["ncr_status"] == "open"
    f.post(
        f"{url}/{nid}/propose",
        {"disposition": "scrap", "scrap_reason_id": f.reasons["scrap"]["id"]},
    )
    r = f.post(f"{url}/{nid}/approve", {"decision": "approve"}, h=h2)
    assert r["ncr"]["approved_levels"] == 1 and r["ncr"]["ncr_status"] == "reviewing"
    assert ec.NCR_ALREADY_APPROVED in _codes(
        f.post(f"{url}/{nid}/approve", {"decision": "approve"}, 422, h2)
    )
    r = f.post(f"{url}/{nid}/approve", {"decision": "approve"}, h=h3)
    assert r["ncr"]["ncr_status"] == "closed" and not r["hold_active"]
    assert r["ncr"]["result"]["scrapped"] == 1 and len(r["approvals"]) == 3
    lt = f.lot(lot)
    assert lt["qty"] == 2 and lt["scrapped_qty"] == 1 and not lt["on_hold"]
    st = {u["code"]: u["status"] for u in f.ctx(lot)["units"]}
    assert st[us[0]["code"]] == "scrapped" and st[us[1]["code"]] == "waiting"
    assert f.m.list("audit_log", action="disposition")["count"] == 1
    assert ec.NCR_STATUS in _codes(f.post(f"{url}/{nid}/cancel", {}, 422))


def test_ncr_rework_release_and_cancel(client: TestClient, db: Session) -> None:
    f = Line(client, db)
    h2 = _admin(f, client, db)
    a, b, c = f.start(1, 1, 1)
    url = f"{EXEC}/ncr"
    # 首工步没有返工路线
    n = f.post(url, {"lot_id": a["id"], "title": "t", "severity": "minor"})["ncr"]
    assert ec.NCR_NO_REWORK_ROUTE in _codes(
        f.post(f"{url}/{n['id']}/propose", {"disposition": "rework"}, 422)
    )
    f.post(f"{url}/{n['id']}/propose", {"disposition": "use_as_is", "comment": "ok"})
    r = f.post(f"{url}/{n['id']}/approve", {"decision": "approve"}, h=h2)
    assert r["ncr"]["ncr_status"] == "closed" and not f.lot(a)["on_hold"]
    # 工步 20 有返工路线：批准后 Move Out 进入返工
    f.run_step(b)
    f.stage(b, "move_in", equipment_id=f.eq["id"])
    f.stage(b, "track_in", equipment_id=f.eq["id"])
    f.stage(b, "track_out")
    n = f.post(url, {"lot_id": b["id"], "title": "cd", "severity": "minor"})["ncr"]
    f.post(f"{url}/{n['id']}/propose", {"disposition": "rework"})
    f.post(f"{url}/{n['id']}/approve", {"decision": "approve"}, h=h2)
    assert f.lot(b)["pending_rework"] and not f.lot(b)["on_hold"]
    f.stage(b, "move_out")
    assert f.ctx(b)["step"]["route"].startswith("RW")
    # 取消释放 Hold
    n = f.post(url, {"lot_id": c["id"], "title": "x", "severity": "critical"})["ncr"]
    assert n["required_levels"] == 3
    r = f.post(f"{url}/{n['id']}/cancel", {"comment": "false alarm"})
    assert r["ncr"]["ncr_status"] == "cancelled" and not f.lot(c)["on_hold"]


# ---------------- SPC 判异 ----------------
def _spc_line(
    client: TestClient, db: Session, action: str, rules: str = "1,2"
) -> tuple[Line, dict[str, Any], dict[str, Any]]:
    f = Line(client, db)
    m = f.m
    body: dict[str, Any] = {"code": "CD", "name": "cd", "ooc_action": action}
    if action == "hold_equipment":
        body["ooc_e10_state_id"] = f.st["DOWN"]["id"]
    mi = m.post("measurement_item", body)
    plan = m.post(
        "dc_plan", {"code": "SPC", "name": "spc", "operation_id": f.ops[0]["id"]}
    )
    pi = m.post(
        "dc_plan_item",
        {
            "dc_plan_id": plan["id"],
            "measurement_item_id": mi["id"],
            "lsl": 0,
            "usl": 20,
            "lcl": 7,
            "cl": 10,
            "ucl": 13,
            "ooc_rules": rules,
        },
    )
    m.action("dc_plan", plan["id"], "status", {"status": "active"})
    return f, mi, pi


def _measure(f: Line, lot: dict[str, Any], mi: dict[str, Any], *v: float) -> Any:
    f.stage(lot, "move_in", equipment_id=f.eq["id"])
    f.stage(lot, "track_in", equipment_id=f.eq["id"])
    return f.stage(
        lot,
        "track_out",
        dc=[{"measurement_item_id": mi["id"], "value": x} for x in v],
    )


def test_ooc_rules_warn_and_chart(client: TestClient, db: Session) -> None:
    f, mi, pi = _spc_line(client, db, "warn")
    lots = f.start(*[1] * 10)
    # 规则 2：连续 9 点在中心线同侧（都在控制限内、规格内）
    for x in lots[:8]:
        assert _measure(f, x, mi, 11, 11.2)["ooc_action"] is None
    r = _measure(f, lots[8], mi, 11.1)
    assert r["ooc_action"] == "warn" and not r["lot"]["on_hold"]
    assert any(x["check_type"] == "ooc" for x in r["results"])
    dc = f.m.list("dc_result", lot=lots[8]["id"])["data"][0]
    assert dc["is_ooc"] and dc["ooc_rules"] == "2"
    assert f.m.list("lot_history", lot=lots[8]["id"], action="ooc")["count"] == 1
    # 规则 1：超出 UCL（仍在规格内，OOS 不触发）
    r = _measure(f, lots[9], mi, 15)
    assert r["ooc_action"] == "warn" and r["oos_action"] is None
    ch = client.get(
        f"{EXEC}/spc", headers=f.m.h, params={"dc_plan_item_id": pi["id"]}
    ).json()
    assert ch["limits"]["ucl"] == 13 and ch["rules"] == [1, 2]
    assert len(ch["points"]) == 10 and ch["points"][-1]["rules"] == [1, 2]
    assert ch["points"][0]["mean"] == 11.1 and ch["points"][0]["rules"] == []


def test_ooc_auto_hold_and_equipment_hold(client: TestClient, db: Session) -> None:
    f, mi, _ = _spc_line(client, db, "auto_hold", "1")
    (a,) = f.start(1)
    r = _measure(f, a, mi, 6)
    assert r["ooc_action"] == "auto_hold" and r["lot"]["on_hold"]
    hold = f.m.list("lot_hold", lot=a["id"])["data"][0]
    assert hold["source"] == "ooc" and hold["note"]["key"] == "ooc"
    g, mi2, _ = _spc_line(client, db, "hold_equipment", "1")
    (b,) = g.start(1)
    r = _measure(g, b, mi2, 14)
    assert r["ooc_action"] == "hold_equipment" and r["lot"]["on_hold"]
    assert r["ooc_e10"].get("to") == "DOWN", r["ooc_e10"]
    st = g.sql(
        "SELECT s.code FROM mes_equipment e JOIN mes_e10_state s ON s.id = e.e10_state_id WHERE e.id = :e",
        e=g.eq["id"],
    )[0][0]
    assert st == "DOWN"
    # 管控关闭时不判异
    g.bind("track_out", ("ooc", "off", {}))
    (c,) = g.start(1)
    g.sql(
        "UPDATE mes_equipment SET e10_state_id = :s WHERE id = :e",
        s=g.st["SBY"]["id"],
        e=g.eq["id"],
    )
    assert _measure(g, c, mi2, 14)["ooc_action"] is None
