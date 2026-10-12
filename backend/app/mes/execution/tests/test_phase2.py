"""二期：内置管控开关（卡控规则 severity = off）、返工上限、跳站、在制报废 / 补数、Q-Time 扫描。"""

from typing import Any

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.mes.execution.tests.test_exec import EXEC, Line, _dc, _dc_line, _msgs


def _ready(f: Line, *lots: dict[str, Any]) -> None:
    for x in lots:
        f.stage(x, "move_in", equipment_id=f.eq["id"])
        f.stage(x, "track_in", equipment_id=f.eq["id"])


# ---------------- phase 1: EDC control switch ----------------
def test_oos_switch_off_per_step(client: TestClient, db: Session) -> None:
    f, items = _dc_line(client, db, {"A": "auto_hold"})
    a, b = f.start(1, 1)
    _ready(f, a)
    r = f.stage(a, "track_out", dc=_dc(items, 5))
    assert r["oos_action"] == "auto_hold" and r["lot"]["on_hold"]
    # 工步级绑定 oos = off：覆盖产品级，超规只记录不处置
    plan = f.bind(
        "track_out",
        ("oos", "off", {}),
        scope="route_step",
        route_step_id=f.steps[10]["id"],
    )
    _ready(f, b)
    r = f.stage(b, "track_out", dc=_dc(items, 5))
    assert r["oos_action"] is None and not r["lot"]["on_hold"]
    res = f.m.list("dc_result", lot=b["id"])["data"][0]
    assert res["is_oos"] and res["oos_action"] is None
    logs = f.m.list("check_log", lot=b["id"], check_type="oos")["data"]
    assert logs and "disabled" in logs[0]["message"]
    assert plan["id"]


# ---------------- phase 2: rework limit + jump ----------------
def _to_move_out(f: Line, lot: dict[str, Any]) -> None:
    _ready(f, lot)
    f.stage(lot, "track_out")


def test_rework_limit_and_switch(client: TestClient, db: Session) -> None:
    f = Line(client, db, {20: {"rework_return": "same_step", "max_rework": 1}})
    a, b = f.start(1, 1)
    f.run_step(a)  # -> 20
    _to_move_out(f, a)
    f.stage(a, "move_out", rework=True)  # 1st rework ok
    f.run_step(a)  # RW#10 -> back to 20
    assert f.lot(a)["rework_count"] == 1
    _to_move_out(f, a)
    assert "rework limit" in _msgs(f.stage(a, "move_out", 409, rework=True))
    r = f.stage(a, "move_out", rework=True, override=True, override_reason="MRB ok")
    assert r["lot"]["rework_count"] == 2
    # 开关：工步绑定 rework_limit = off 后不限次数
    f.bind(
        "move_out",
        ("rework_limit", "off", {}),
        scope="route_step",
        route_step_id=f.steps[20]["id"],
    )
    f.run_step(a)
    _to_move_out(f, a)
    f.stage(a, "move_out", rework=True)
    assert f.ctx(a)["step"]["route"].startswith("RW")
    assert b["id"]


def test_jump_step(client: TestClient, db: Session) -> None:
    f = Line(client, db)
    (a,) = f.start(1)
    jr = f.m.post("reason_code", {"code": "JMP", "name": "j", "reason_type": "jump"})
    body = {"to_step_id": f.steps[40]["id"], "reason_id": jr["id"]}
    url = f"/api/v1/mes/exec/lots/{a['id']}/jump"
    bad = {**body, "reason_id": f.reasons["hold"]["id"]}
    assert "jump reason" in _msgs(f.post(url, bad, 422))
    r = f.post(url, {**body, "comment": "skip litho rework"})
    assert r["next_step"]["seq"] == 40 and f.ctx(a)["step"]["seq"] == 40
    h = f.m.list("lot_history", lot=a["id"], action="jump")["data"][0]
    assert h["details"]["from_seq"] == 10 and h["comment"] == "skip litho rework"
    f.stage(a, "move_in", equipment_id=f.eq["id"])
    assert "only waiting" in _msgs(f.post(url, body, 422))
    # 跳站触发时机的卡控（如 lot_hold）可配置
    (b,) = f.start(1)
    f.bind("jump", ("wo_status", "block", {}))
    f.post(f"/api/v1/mes/work-order/{f.wo['id']}/transition", {"action": "hold"})
    assert f.post(f"/api/v1/mes/exec/lots/{b['id']}/jump", body, 409)


# ---------------- phase 3: in-process scrap / bonus ----------------
def test_in_process_scrap_bonus(client: TestClient, db: Session) -> None:
    f = Line(client, db)
    (a,) = f.start(10)
    url = f"/api/v1/mes/exec/lots/{a['id']}/adjust"
    sc = f.reasons["scrap"]["id"]
    ws = f.m.list("wafer", lot=a["id"], sort_by="code", sort_order="asc")["data"]
    # 晶圆级：按片报废；补数不支持
    r = f.post(url, {"kind": "scrap", "unit_ids": [ws[0]["id"]], "reason_id": sc})
    assert r["lot"]["qty"] == 9 and r["lot"]["scrapped_qty"] == 1
    bad = f.post(url, {"kind": "bonus", "qty": 1, "reason_id": sc}, 422)
    assert "bonus" in _msgs(bad)
    # 原因代码类型必须匹配
    hold = f.reasons["hold"]["id"]
    f.post(url, {"kind": "scrap", "unit_ids": [ws[1]["id"]], "reason_id": hold}, 422)
    # 数量上限（默认 10%）：一次报废 2 片超限，阻断可放行
    two = [ws[1]["id"], ws[2]["id"]]
    assert "exceeds" in _msgs(
        f.post(url, {"kind": "scrap", "unit_ids": two, "reason_id": sc}, 409)
    )
    body = {"kind": "scrap", "unit_ids": two, "reason_id": sc}
    r = f.post(url, {**body, "override": True, "override_reason": "MRB"})
    assert r["lot"]["qty"] == 7
    # 开关：adjust 触发时机绑定 qty_adjust_limit = off
    f.bind("adjust", ("qty_adjust_limit", "off", {}))
    rest = [w["id"] for w in ws[3:]]
    r = f.post(url, {"kind": "scrap", "unit_ids": rest, "reason_id": sc})
    assert r["lot"]["lot_status"] == "scrapped" and r["lot"]["qty"] == 0
    hs = f.m.list("lot_history", lot=a["id"], action="scrap")["count"]
    assert hs == 3


def test_bonus_quantity_lot(client: TestClient, db: Session) -> None:
    f = Line(client, db, {"product": {"tracking_level": "quantity"}})
    (a,) = f.start(100)
    bonus = f.m.post("reason_code", {"code": "BN", "name": "b", "reason_type": "bonus"})
    url = f"/api/v1/mes/exec/lots/{a['id']}/adjust"
    r = f.post(url, {"kind": "bonus", "qty": 5, "reason_id": bonus["id"]})
    assert r["lot"]["qty"] == 105 and f.lot(a)["bonus_qty"] == 5
    sc = f.reasons["scrap"]["id"]
    r = f.post(url, {"kind": "scrap", "qty": 3, "reason_id": sc})
    assert r["lot"]["qty"] == 102
    assert f.m.list("lot_history", lot=a["id"], action="bonus")["count"] == 1


# ---------------- phase 4: Q-Time monitor / sweep / switch ----------------
def test_qtime_sweep_and_switch(client: TestClient, db: Session) -> None:
    f = Line(client, db)
    f.m.post(
        "qtime_rule",
        {
            "code": "QT",
            "name": "q",
            "route_id": f.route["id"],
            "from_step_id": f.steps[10]["id"],
            "to_step_id": f.steps[20]["id"],
            "max_minutes": 30,
            "reason_id": f.reasons["hold"]["id"],
        },
    )
    a, b = f.start(1, 1)
    for x in (a, b):
        f.run_step(x)
    f.sql(
        "UPDATE mes_lot_history SET at = at - interval '2 hours' WHERE lot_id = :a AND action = 'move_out'",
        a=a["id"],
    )
    mon = client.get(f"{EXEC}/qtime/monitor", headers=f.m.h).json()["data"]
    row = {r["lot"]: r for r in mon}
    assert row[a["code"]]["exceeded"] and not row[b["code"]]["exceeded"]
    assert row[b["code"]]["remaining"] > 0
    # 开关关闭（工步级 off）：扫描不处置
    f.bind(
        "move_in",
        ("qtime", "off", {}),
        scope="route_step",
        route_step_id=f.steps[20]["id"],
    )
    r = f.post(f"{EXEC}/qtime/sweep", {})
    assert r["actions"] == [] and not f.lot(a)["on_hold"]
    # 打开后：扫描自动 Hold，且幂等
    f.sql("UPDATE mes_check_binding SET is_active = false")
    r = f.post(f"{EXEC}/qtime/sweep", {})
    assert r["actions"] == [{"lot": a["code"], "action": "hold"}]
    assert f.lot(a)["on_hold"] and not f.lot(b)["on_hold"]
    assert f.post(f"{EXEC}/qtime/sweep", {})["actions"] == []


# ---------------- phase 5: equipment E10 manual / PM / downtime ----------------
EQP = "/api/v1/mes/eqp"


def test_e10_manual_change_and_history(client: TestClient, db: Session) -> None:
    f = Line(client, db)
    url = f"{EQP}/{f.eq['id']}/e10"
    r = f.post(url, {"to_state_id": f.st["DOWN"]["id"]})
    assert (r["from"], r["to"]) == ("SBY", "DOWN")
    # 迁移表外：DOWN -> PRD 不允许
    assert "not allowed" in _msgs(f.post(url, {"to_state_id": f.st["PRD"]["id"]}, 422))
    # 迁移要求原因：需要 e10 类型原因代码
    f.sql(
        "UPDATE mes_e10_transition SET reason_required = true WHERE to_state_id = :s",
        s=f.st["SBY"]["id"],
    )
    f.post(url, {"to_state_id": f.st["SBY"]["id"]}, 422)
    rc = f.m.post("reason_code", {"code": "E10R", "name": "r", "reason_type": "e10"})
    f.post(url, {"to_state_id": f.st["SBY"]["id"], "reason_id": rc["id"]})
    # 自动迁移同样记履历
    (a,) = f.start(1)
    f.run_step(a)
    hs = f.m.list("e10_history", equipment=f.eq["id"], sort_by="at", sort_order="asc")
    assert [h["source"] for h in hs["data"]] == ["manual", "manual", "auto", "auto"]
    board = client.get(f"{EQP}/board", headers=f.m.h).json()["data"]
    row = next(b for b in board if b["code"] == "EQ1")
    assert row["state"]["code"] == "SBY" and {n["code"] for n in row["next"]} == {
        "PRD",
        "DOWN",
    }


def test_pm_due_check_and_switch(client: TestClient, db: Session) -> None:
    f = Line(client, db)
    plan = f.m.post(
        "pm_plan",
        {"code": "PM-L", "name": "pm", "equipment_id": f.eq["id"], "interval_lots": 1},
    )
    f.m.post("pm_plan", {"code": "PM-X", "name": "x"}, 422)  # 无设备 / 周期
    f.bind("track_in", ("pm_due", "block", {}))
    a, b = f.start(1, 1)
    f.run_step(a)  # 第 1 批：0 < 1，未到期
    f.stage(b, "move_in", equipment_id=f.eq["id"])
    bad = f.stage(b, "track_in", 409, equipment_id=f.eq["id"])
    assert "PM overdue" in _msgs(bad)
    # 登记 PM 后放行
    r = f.post(f"{EQP}/pm/{plan['id']}/complete", {"equipment_id": f.eq["id"]})
    assert not r["pm"][0]["due"]
    f.stage(b, "track_in", equipment_id=f.eq["id"])
    # 开关：同一工步绑定 pm_due = off
    (c,) = f.start(1)
    f.stage(c, "move_in", equipment_id=f.eq["id"])
    f.sql("UPDATE mes_pm_record SET done_at = done_at - interval '1 day'")
    f.bind(
        "track_in",
        ("pm_due", "off", {}),
        scope="route_step",
        route_step_id=f.steps[10]["id"],
    )
    f.stage(c, "track_in", equipment_id=f.eq["id"])
    # 停机记录：结束须晚于开始
    rc = f.m.post("reason_code", {"code": "DT", "name": "d", "reason_type": "downtime"})
    f.m.post(
        "downtime",
        {
            "equipment_id": f.eq["id"],
            "start_at": "2026-10-01T10:00:00Z",
            "end_at": "2026-10-01T09:00:00Z",
            "reason_id": rc["id"],
        },
        422,
    )


# ---------------- phase 6: recipe ↔ equipment control ----------------
def test_recipe_match_and_switch(client: TestClient, db: Session) -> None:
    f = Line(client, db)
    f.bind("track_in", ("recipe_match", "block", {"require_report": True}))
    a, b, c = f.start(1, 1, 1)
    rc = f.recipe["id"]
    for x in (a, b, c):
        f.stage(x, "move_in", equipment_id=f.eq["id"])
    # 未映射到设备
    bad = f.stage(a, "track_in", 409, equipment_id=f.eq["id"], recipe_id=rc)
    assert "not enabled on EQ1" in _msgs(bad)
    f.sql(
        "INSERT INTO mes_recipe_equipment (id, tenant_id, recipe_id, equipment_id,"
        " eqp_recipe, is_enabled, ideal_uph) VALUES (gen_random_uuid(), :t, :r, :e,"
        " 'EQ-RC-01', true, 25)",
        t=f.m.tid,
        r=rc,
        e=f.eq["id"],
    )
    # 必须上报设备端配方名；不一致阻断
    assert "not reported" in _msgs(
        f.stage(a, "track_in", 409, equipment_id=f.eq["id"], recipe_id=rc)
    )
    assert "differs" in _msgs(
        f.stage(
            a, "track_in", 409, equipment_id=f.eq["id"], recipe_id=rc, eqp_recipe="X"
        )
    )
    f.stage(a, "track_in", equipment_id=f.eq["id"], recipe_id=rc, eqp_recipe="EQ-RC-01")
    # 开关：工步级 off
    f.bind(
        "track_in",
        ("recipe_match", "off", {}),
        scope="route_step",
        route_step_id=f.steps[10]["id"],
    )
    f.stage(b, "track_in", equipment_id=f.eq["id"], recipe_id=rc, eqp_recipe="X")


# ---------------- phase 7: traceability ----------------
def test_trace_backward_forward(client: TestClient, db: Session) -> None:
    from app.mes.execution.tests.test_split_merge import _line, split, uid

    f = _line(client, db)
    m = f.m
    f.sql(
        "INSERT INTO mes_step_resource (id, tenant_id, route_step_id, resource_kind,"
        " material_id, qty, uom_id, qty_basis) VALUES (gen_random_uuid(), :t, :s,"
        " 'material', :m, 1, :u, 'per_unit')",
        t=m.tid,
        s=f.steps[10]["id"],
        m=f.mat["id"],
        u=m.fx("uom"),
    )
    m.post(
        "material_lot",
        {
            "code": "MLT",
            "material_id": f.mat["id"],
            "qty_remaining": 100,
            "uom_id": m.fx("uom"),
            "expiry_date": "2030-01-01",
        },
    )
    (lot,) = f.start(4)
    f.run_step(lot)
    f.stage(lot, "move_in", equipment_id=f.eq2["id"])
    (ch,) = split(f, lot, [{"unit_ids": uid(f, lot, 0, 1)}])["children"]

    def tr(kind: str, code: str) -> Any:
        r = client.get(
            f"{EXEC}/trace", headers=m.h, params={"kind": kind, "code": code}
        )
        assert r.status_code == 200, r.text
        return r.json()

    # 子批反向：来源母批、经过的设备、消耗的物料
    t = tr("lot", ch["code"])
    assert [x["code"] for x in t["backward"]["lots"]] == [lot["code"]]
    assert {s["equipment"] for s in t["backward"]["steps"]} == {"EQ1"}
    assert t["backward"]["materials"][0]["material_lot"] == "MLT"
    # 母批正向：产出子批
    assert [x["code"] for x in tr("lot", lot["code"])["forward"]["lots"]] == [
        ch["code"]
    ]
    # 物料批：消耗它的批次及其下游
    u = tr("material_lot", "MLT")["lots"]
    assert u[0]["code"] == lot["code"] and u[0]["forward"][0]["code"] == ch["code"]
    assert [x["code"] for x in tr("equipment", "EQ1")["lots"]] == [lot["code"]]
    w = m.list("wafer", lot=ch["id"])["data"][0]
    assert tr("wafer", w["code"])["target"]["lot"] == ch["code"]
    r = client.get(f"{EXEC}/trace", headers=m.h, params={"kind": "lot", "code": "NOPE"})
    assert r.status_code == 404


# ---------------- phase 8: hold filter / batch release ----------------
def test_active_holds_and_batch_release(client: TestClient, db: Session) -> None:
    f = Line(client, db)
    a, b, c = f.start(1, 1, 1)
    hr = f.reasons["hold"]["id"]
    for x in (a, b, c):
        f.post(f"{EXEC}/lots/{x['id']}/hold", {"reason_id": hr})
    rows = client.get(f"{EXEC}/holds/active", headers=f.m.h).json()["data"]
    assert len(rows) == 3 and rows[0]["source"] == "manual"
    other = f.m.post("reason_code", {"code": "HX", "name": "x", "reason_type": "hold"})
    q = client.get(
        f"{EXEC}/holds/active", headers=f.m.h, params={"reason_id": other["id"]}
    )
    assert q.json()["data"] == []
    ids = [r["id"] for r in rows[:2]]
    # 需要释放类原因代码
    f.post(f"{EXEC}/holds/release-batch", {"hold_ids": ids, "reason_id": hr}, 422)
    rel = f.reasons["release"]["id"]
    r = f.post(f"{EXEC}/holds/release-batch", {"hold_ids": ids, "reason_id": rel})
    assert len(r["released"]) == 2 and r["failed"] == []
    # 已释放的再次释放：逐条失败，不影响其他
    r = f.post(
        f"{EXEC}/holds/release-batch",
        {"hold_ids": [ids[0], rows[2]["id"]], "reason_id": rel},
    )
    assert r["released"] == [rows[2]["id"]] and len(r["failed"]) == 1
    assert not any(f.lot(x)["on_hold"] for x in (a, b, c))


# ---------------- Q-Time additions: pre-expiry warning + background sweep ----------------
def test_qtime_warn_and_all_tenant_sweep(client: TestClient, db: Session) -> None:
    from app.mes.execution.service import sweep_all_tenants

    f = Line(client, db)
    f.m.post(
        "qtime_rule",
        {
            "code": "QW",
            "name": "q",
            "route_id": f.route["id"],
            "from_step_id": f.steps[10]["id"],
            "to_step_id": f.steps[20]["id"],
            "max_minutes": 60,
            "warn_minutes": 45,
            "reason_id": f.reasons["hold"]["id"],
        },
    )
    a, b = f.start(1, 1)
    for x in (a, b):
        f.run_step(x)
    f.sql(
        "UPDATE mes_lot_history SET at = at - interval '50 minutes' WHERE lot_id = :a AND action = 'move_out'",
        a=a["id"],
    )
    f.sql(
        "UPDATE mes_lot_history SET at = at - interval '2 hours' WHERE lot_id = :b AND action = 'move_out'",
        b=b["id"],
    )
    mon = client.get(f"{EXEC}/qtime/monitor", headers=f.m.h).json()["data"]
    row = {r["lot"]: r for r in mon}
    assert row[a["code"]]["warn"] and not row[a["code"]]["exceeded"]
    assert row[b["code"]]["exceeded"] and not row[b["code"]]["warn"]
    assert f.ctx(a)["qtime"][0]["warn"]
    # 后台扫描（全部租户）：超时批次自动 Hold，预警批次不处置
    import uuid as _uuid

    r = sweep_all_tenants([_uuid.UUID(str(f.m.tid))])
    assert r["tenants"] == 1
    assert r["actions"] >= 1
    assert f.lot(b)["on_hold"] and not f.lot(a)["on_hold"]


# ---------------- phase 9: WIP dashboard / output / OEE ----------------
def test_wip_output_oee_reports(client: TestClient, db: Session) -> None:
    f = Line(client, db)
    a, b = f.start(2, 3)
    f.run_step(a)
    f.post(f"{EXEC}/lots/{b['id']}/hold", {"reason_id": f.reasons["hold"]["id"]})
    g = lambda u, **p: client.get(f"{EXEC}/reports/{u}", headers=f.m.h, params=p)  # noqa: E731
    w = g("wip").json()
    assert w["total_lots"] == 2 and w["total_qty"] == 5 and w["on_hold"] == 1
    assert {x["step_seq"] for x in w["by_step"]} == {10, 20}
    assert w["aging"][0]["lot"] in (a["code"], b["code"])
    out = g("output").json()["data"]
    assert len(out) == 7 and sum(d["moves"] for d in out) == 1
    assert sum(d["move_qty"] for d in out) == 2
    # OEE：UPH 缺失时不计算性能稼动率
    rows = {r["equipment"]: r for r in g("oee").json()["data"]}
    eq1 = rows["EQ1"]
    assert eq1["good"] == 2 and eq1["quality"] == 1.0
    assert eq1["uph_missing"] and eq1["performance"] is None and eq1["oee"] is None
    assert eq1["availability"] is not None and 0 <= eq1["availability"] <= 1
    # 设备 UPH 维护后可计算
    f.m.patch("equipment", f.eq["id"], {"ideal_uph": 3600})
    eq1 = {r["equipment"]: r for r in g("oee").json()["data"]}["EQ1"]
    assert eq1["performance"] is not None and eq1["oee"] is not None
    assert g("oee", date_from="2026-10-10", date_to="2026-10-01").status_code == 422
