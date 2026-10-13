"""三期：晶圆级履历与晶圆图等。"""

from typing import Any

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.mes.execution.tests.test_exec import EXEC


def test_wafer_map_and_wafer_history(client: TestClient, db: Session) -> None:
    from app.mes.execution.tests.test_split_merge import _line, split, uid

    f = _line(client, db)
    (lot,) = f.start(4)
    f.run_step(lot)

    def get(path: str) -> Any:
        r = client.get(f"{EXEC}{path}", headers=f.m.h)
        assert r.status_code == 200, r.text
        return r.json()

    wm = get(f"/lots/{lot['id']}/wafer-map")
    filled = [x for x in wm["slots"] if x["wafer"]]
    assert len(filled) == 4 and wm["capacity"] >= 4
    w0 = filled[0]["wafer"]
    # 拆批后：子批中的晶圆仍能看到母批阶段的履历
    (ch,) = split(f, lot, [{"unit_ids": uid(f, lot, 0, 1)}])["children"]
    child_map = get(f"/lots/{ch['id']}/wafer-map")
    wid = next(x["wafer"]["id"] for x in child_map["slots"] if x["wafer"])
    hist = get(f"/wafers/{wid}/history")["data"]
    actions = {h["action"] for h in hist}
    assert {"start", "track_in"} <= actions
    assert {str(h["lot_id"]) for h in hist} >= {str(lot["id"])}
    assert get(f"/wafers/{w0['id']}/history")["data"]
    r = client.get(f"{EXEC}/wafers/{lot['id']}/history", headers=f.m.h)
    assert r.status_code == 404


def test_chamber_select_checks_and_e10(client: TestClient, db: Session) -> None:
    from app.mes.execution.tests.test_exec import Line, _msgs

    f = Line(client, db)
    f.bind(
        "track_in",
        ("chamber_required", "block", {}),
        ("chamber_available", "block", {}),
    )
    pm = [
        f.m.post(
            "equipment",
            {
                "code": f"EQ1-PM{i}",
                "name": f"pm{i}",
                "unit_kind": "chamber",
                "parent_id": f.eq["id"],
            },
        )
        for i in (1, 2)
    ]
    a, b, c = f.start(1, 1, 1)

    def e10(eid: str) -> Any:
        return client.get(f.m.url("equipment", eid), headers=f.m.h).json()[
            "e10_state_id"
        ]

    # 未选腔体 → 拦截
    f.stage(a, "move_in", equipment_id=f.eq["id"])
    assert "select a chamber" in _msgs(
        f.stage(a, "track_in", 409, equipment_id=f.eq["id"])
    )
    # 腔体 DOWN → 拦截
    f.sql(
        "UPDATE mes_equipment SET e10_state_id = :s WHERE id = :e",
        s=f.st["DOWN"]["id"],
        e=pm[1]["id"],
    )
    assert "DOWN" in _msgs(
        f.stage(a, "track_in", 409, equipment_id=f.eq["id"], chamber_ids=[pm[1]["id"]])
    )
    # 其他设备的腔体 → 422
    f.stage(b, "move_in", equipment_id=f.eq2["id"])
    f.stage(b, "track_in", 422, equipment_id=f.eq2["id"], chamber_ids=[pm[0]["id"]])
    # 选 PM1 → 通过，腔体 E10 随 Track In / Out 迁移
    f.stage(a, "track_in", equipment_id=f.eq["id"], chamber_ids=[pm[0]["id"]])
    assert e10(pm[0]["id"]) == f.st["PRD"]["id"]
    ctx = client.get(f"{EXEC}/lots/{c['id']}", headers=f.m.h).json()
    eq1 = next(e for e in ctx["equipment"] if e["id"] == f.eq["id"])
    assert [x["code"] for x in eq1["chambers"]] == ["EQ1-PM1", "EQ1-PM2"]
    f.stage(a, "track_out")
    assert e10(pm[0]["id"]) == f.st["SBY"]["id"]
    hist = f.m.list("lot_history", lot=a["id"], action="track_in")["data"][0]
    assert hist["details"]["chambers"] == ["EQ1-PM1"]
    # 规则严重度为 off → 管控关闭
    f.sql("UPDATE mes_check_rule SET severity = 'off'")
    f.stage(c, "move_in", equipment_id=f.eq["id"])
    f.stage(c, "track_in", equipment_id=f.eq["id"])


def test_recipe_run_snapshot(client: TestClient, db: Session) -> None:
    from app.mes.execution.tests.test_exec import Line

    f = Line(client, db)
    f.sql(
        """UPDATE mes_recipe SET body = '{"temp": 950, "time_s": 60}' WHERE id = :r""",
        r=f.recipe["id"],
    )
    f.m.post(
        "param_spec",
        {
            "code": "TEMP",
            "name": "temp",
            "recipe_id": f.recipe["id"],
            "uom_id": f.m.fx("uom"),
            "target": 950,
            "lsl": 940,
            "usl": 960,
        },
    )
    (a,) = f.start(1)
    f.stage(a, "move_in", equipment_id=f.eq["id"])
    f.stage(a, "track_in", equipment_id=f.eq["id"], recipe_id=f.recipe["id"])
    # 之后改动配方参数不影响已记录的快照
    f.sql(
        """UPDATE mes_recipe SET body = '{"temp": 999}' WHERE id = :r""",
        r=f.recipe["id"],
    )
    run = f.m.list("lot_recipe_run", lot=a["id"])["data"]
    assert len(run) == 1 and run[0]["track_out_at"] is None
    assert run[0]["params"] == {"temp": 950, "time_s": 60}
    assert run[0]["recipe_version"] == f.recipe["version"]
    assert [p["code"] for p in run[0]["param_specs"]] == ["TEMP"]
    f.stage(a, "track_out")
    run = f.m.list("lot_recipe_run", lot=a["id"])["data"]
    assert run[0]["track_out_at"] is not None


def test_batch_track_in_out(client: TestClient, db: Session) -> None:
    from app.mes.execution.tests.test_exec import Line

    f = Line(client, db)
    f.bind("track_in", ("batch_same_step", "block", {}))
    a, b, c = f.start(1, 1, 1)

    def batch(stage: str, ids: list[Any], status: int = 200, **kw: Any) -> Any:
        r = client.post(
            f"{EXEC}/batch/{stage}",
            headers=f.m.h,
            json={"lot_ids": [x["id"] for x in ids], **kw},
        )
        assert r.status_code == status, r.text
        return r.json()

    for x in (a, b):
        f.stage(x, "move_in", equipment_id=f.eq["id"])
    cand = client.get(
        f"{EXEC}/batch/track_in/candidates",
        headers=f.m.h,
        params={"equipment_id": f.eq["id"]},
    ).json()
    assert {x["id"] for x in cand["lots"]} == {a["id"], b["id"]}
    # c 未进站 → 422
    batch("track_in", [a, c], 422, equipment_id=f.eq["id"])
    # c 换到下一工步后再进站：工步不同 → 整体阻断，均未执行
    f.run_step(c)
    f.stage(c, "move_in", equipment_id=f.eq["id"])
    r = batch("track_in", [a, b, c], 409, equipment_id=f.eq["id"])
    assert r["detail"]["code"] == "batch_blocked"
    assert f.lot(a)["lot_status"] == "moved_in"
    out = batch("track_in", [a, b], equipment_id=f.eq["id"])
    assert [i["ok"] for i in out["items"]] == [True, True]
    assert {f.lot(x)["lot_status"] for x in (a, b)} == {"running"}
    out = batch("track_out", [a, b])
    assert {f.lot(x)["lot_status"] for x in (a, b)} == {"tracked_out"}
    # 严重度 off → 不同工步也可批量
    f.sql("UPDATE mes_check_rule SET severity = 'off'")
    f.stage(a, "move_out")
    f.stage(a, "move_in", equipment_id=f.eq["id"])
    f.stage(b, "move_out")
    batch("track_in", [a, c], equipment_id=f.eq["id"])


def test_carrier_change_clean_and_checks(client: TestClient, db: Session) -> None:
    from app.mes.execution.tests.test_exec import Line, _msgs

    f = Line(client, db)
    ct = f.m.post(
        "carrier_type",
        {
            "code": "FX",
            "name": "foup",
            "category": "foup",
            "capacity": 25,
            "clean_interval_days": 7,
        },
    )
    c1, c2 = (
        f.m.post(
            "carrier",
            {
                "code": f"C{i}",
                "name": f"c{i}",
                "carrier_type_id": ct["id"],
                "max_uses": 2,
            },
        )
        for i in (1, 2)
    )
    f.bind(
        "track_in",
        ("carrier_usage", "block", {}),
        ("carrier_clean", "block", {}),
    )
    (a,) = f.start(1)

    def post(path: str, body: dict[str, Any], status: int = 200) -> Any:
        r = client.post(f"{EXEC}{path}", headers=f.m.h, json=body)
        assert r.status_code == status, r.text
        return r.json()

    post(f"/lots/{a['id']}/carrier", {"carrier_id": c1["id"]})
    assert f.lot(a)["carrier_id"] == c1["id"]
    f.sql("UPDATE mes_carrier SET use_count = 2 WHERE id = :c", c=c1["id"])
    f.stage(a, "move_in", equipment_id=f.eq["id"])
    assert "clean first" in _msgs(f.stage(a, "track_in", 409, equipment_id=f.eq["id"]))
    # 装着批次的载具不能清洗；换到 C2 后清洗 C1
    post(f"/carriers/{c1['id']}/clean", {}, 422)
    post(f"/lots/{a['id']}/carrier", {"carrier_id": c2["id"]})
    post(f"/carriers/{c1['id']}/clean", {"comment": "wet clean"})
    board = {
        r["code"]: r
        for r in client.get(f"{EXEC}/carriers/board", headers=f.m.h).json()["data"]
    }
    assert board["C1"]["use_count"] == 0 and board["C1"]["lot"] is None
    assert board["C2"]["lot"] == a["code"]
    ev = f.m.list("carrier_event", carrier=c1["id"])["data"]
    assert {e["event"] for e in ev} == {"load", "unload", "clean"}
    # C2 清洗超期 → 拦截；通过后使用次数 +1
    f.sql(
        "UPDATE mes_carrier SET last_cleaned_at = now() - interval '8 days' WHERE id = :c",
        c=c2["id"],
    )
    assert "overdue" in _msgs(f.stage(a, "track_in", 409, equipment_id=f.eq["id"]))
    f.sql("UPDATE mes_carrier SET last_cleaned_at = now() WHERE id = :c", c=c2["id"])
    f.stage(a, "track_in", equipment_id=f.eq["id"])
    assert board["C2"]["use_count"] == 0
    after = client.get(f"{EXEC}/carriers/board", headers=f.m.h).json()["data"]
    assert next(r for r in after if r["code"] == "C2")["use_count"] == 1
    # 运行中不能换载具
    post(f"/lots/{a['id']}/carrier", {"carrier_id": c1["id"]}, 422)


def test_wafer_sorter(client: TestClient, db: Session) -> None:
    from app.mes.execution.tests.test_exec import _msgs
    from app.mes.execution.tests.test_split_merge import _line

    f = _line(client, db)
    ct = f.m.post(
        "carrier_type",
        {"code": "FS", "name": "foup", "category": "foup", "capacity": 25},
    )
    c1, c2 = (
        f.m.post("carrier", {"code": f"S{i}", "name": "s", "carrier_type_id": ct["id"]})
        for i in (1, 2)
    )
    f.bind("sort", ("sort_order", "block", {}))
    (lot,) = f.start(3)

    def post(path: str, body: dict[str, Any], status: int = 200) -> Any:
        r = client.post(f"{EXEC}{path}", headers=f.m.h, json=body)
        assert r.status_code == status, r.text
        return r.json()

    post(f"/lots/{lot['id']}/carrier", {"carrier_id": c1["id"]})
    ws = sorted(f.m.list("wafer", lot=lot["id"])["data"], key=lambda w: w["code"])

    def m(*slots: int) -> list[dict[str, Any]]:
        return [
            {"wafer_id": w["id"], "slot": s} for w, s in zip(ws, slots, strict=False)
        ]

    post(f"/lots/{lot['id']}/sort", {"slots": m(1, 1, 2)}, 422)
    post(f"/lots/{lot['id']}/sort", {"slots": m(1, 2)}, 422)
    # 打乱顺序 → 拦截；保持顺序移入 S2 的 5/6/7 槽 → 通过
    assert "order" in _msgs(post(f"/lots/{lot['id']}/sort", {"slots": m(3, 2, 1)}, 409))
    post(f"/lots/{lot['id']}/sort", {"slots": m(5, 6, 7), "carrier_id": c2["id"]})
    assert f.lot(lot)["carrier_id"] == c2["id"]
    got = {w["code"]: w["slot"] for w in f.m.list("wafer", lot=lot["id"])["data"]}
    assert sorted(got.values()) == [5, 6, 7]
    assert f.m.list("lot_history", lot=lot["id"], action="sort")["count"] == 1
    assert f.m.list("carrier_event", carrier=c2["id"], event="sort")["count"] == 1
    # 规则关闭 → 可打乱顺序
    f.sql("UPDATE mes_check_rule SET severity = 'off'")
    post(f"/lots/{lot['id']}/sort", {"slots": m(3, 2, 1)})


def test_yield_report(client: TestClient, db: Session) -> None:
    from app.mes.execution.tests.test_exec import Line

    f = Line(client, db, {"product": {"tracking_level": "quantity"}})
    (lot,) = f.start(100)
    sr = f.reasons["scrap"]["id"]
    f.stage(lot, "move_in")
    f.stage(lot, "track_in", equipment_id=f.eq["id"])
    f.stage(lot, "track_out", scrap=[{"qty": 10, "reason_id": sr}])

    def rep(group: str) -> Any:
        r = client.get(f"{EXEC}/reports/yield", headers=f.m.h, params={"group": group})
        assert r.status_code == 200, r.text
        return r.json()

    op = rep("operation")
    assert op["rows"] == [
        {"key": "OP1", "name": "o1", "good": 90, "scrap": 10, "yield": 0.9}
    ]
    assert op["pareto"][0]["qty"] == 10 and op["pareto"][0]["cum_pct"] == 1.0
    assert rep("lot")["rows"][0]["key"] == lot["code"]
    assert rep("product")["total"]["yield"] == 0.9


def test_wo_board_due_warnings(client: TestClient, db: Session) -> None:
    from datetime import date, timedelta

    from app.mes.execution.tests.test_exec import Line

    f = Line(client, db)
    (a,) = f.start(2)
    wo = f.lot(a)["work_order_id"]

    def board() -> Any:
        r = client.get("/api/v1/mes/work-order/board", headers=f.m.h)
        assert r.status_code == 200, r.text
        return next(x for x in r.json()["data"] if x["id"] == wo)

    def due(days: int) -> None:
        f.sql(
            "UPDATE mes_work_order SET due_date = :d WHERE id = :w",
            d=date.today() + timedelta(days=days),
            w=wo,
        )

    b = board()
    assert b["risk"] == "none" and b["wip"] == 2 and b["lots"] == 1
    assert b["wip_by_op"] == [{"operation": "OP1", "qty": 2}]
    due(2)
    assert board()["risk"] == "at_risk"
    due(10)
    assert board()["risk"] == "ok"
    due(-1)
    assert board()["risk"] == "overdue" and board()["days_left"] == -1


def test_wo_due_notify_dedupe_and_switch(client: TestClient, db: Session) -> None:
    import uuid as _uuid
    from datetime import date, timedelta

    from app.mes.execution.service import sweep_all_tenants
    from app.mes.execution.tests.test_exec import Line
    from app.platform.notification.tests.test_notification import _sub_all, _types

    f = Line(client, db)
    _sub_all(f)
    (a,) = f.start(2)
    wo = f.lot(a)["work_order_id"]
    tid = [_uuid.UUID(str(f.m.tid))]
    f.sql(
        "UPDATE mes_work_order SET due_date = :d WHERE id = :w",
        d=date.today() + timedelta(days=1),
        w=wo,
    )
    sweep_all_tenants(tid)
    sweep_all_tenants(tid)
    assert _types(f).count("mes.wo_due") == 1
    f.sql(
        "UPDATE mes_work_order SET due_date = :d WHERE id = :w",
        d=date.today() - timedelta(days=1),
        w=wo,
    )
    f.m.post(
        "check_rule",
        {"code": "WD", "name": "wd", "check_type": "wo_due", "severity": "off"},
    )
    sweep_all_tenants(tid)
    assert "mes.wo_overdue" not in _types(f)


# ---------------- 8: engineering change ----------------
def test_change_order_route_switch_and_due(client: TestClient, db: Session) -> None:
    from datetime import timedelta

    from app.core.spec.base import now
    from app.core.tenant import set_tenant
    from app.mes.execution.tests.test_exec import API, Line
    from app.mes.process.service import apply_due

    f = Line(client, db)
    a, b = f.start(2, 3)
    f.run_step(a)
    f.stage(b, "move_in", equipment_id=f.eq["id"])
    v2 = f.m.action("route", f.route["id"], "new-version")
    co = f.m.post(
        "change_order",
        {
            "code": "ECN1",
            "name": "e",
            "change_type": "route",
            "route_id": v2["id"],
            "wip_rule": "switch_new",
        },
    )
    out = f.post(f"{API}/change-order/{co['id']}/release", {})["data"]
    assert out["ecn_status"] == "applied"
    assert out["result"]["switched"] == [a["code"]]
    assert out["result"]["kept"] == [b["code"]]
    la = f.lot(a)
    assert la["route_id"] == v2["id"]
    step20 = f.sql(
        "SELECT id FROM mes_route_step WHERE route_id = :r AND seq = 20", r=v2["id"]
    )[0][0]
    assert la["current_step_id"] == str(step20)
    assert f.lot(b)["route_id"] == f.route["id"]
    g = lambda e, i: client.get(f.m.url(e, i), headers=f.m.h).json()  # noqa: E731
    assert g("route", f.route["id"])["status"] == "inactive"
    assert g("work_order", f.wo["id"])["route_id"] == v2["id"]
    f.m.patch("change_order", co["id"], {"name": "x"}, status=422)

    # 未到生效时间：发布后待生效，定时扫描到期生效（沿用旧版本）
    v3 = f.m.action("route", v2["id"], "new-version")
    co2 = f.m.post(
        "change_order",
        {
            "code": "ECN2",
            "name": "e",
            "change_type": "route",
            "route_id": v3["id"],
            "effective_at": (now() + timedelta(hours=1)).isoformat(),
        },
    )
    out = f.post(f"{API}/change-order/{co2['id']}/release", {})["data"]
    assert out["ecn_status"] == "released"
    set_tenant(db, f.m.tid)
    assert apply_due(db, f.m.tid, now() + timedelta(hours=2)) == 1
    db.commit()
    assert g("change_order", co2["id"])["ecn_status"] == "applied"
    assert f.lot(a)["route_id"] == v2["id"]


# ---------------- 9: future hold ----------------
def test_future_hold_triggers_at_move_in_and_switch(
    client: TestClient, db: Session
) -> None:
    from app.mes.execution.tests.test_exec import Line

    f = Line(client, db)
    a, b = f.start(2, 2)
    fh = f.m.post(
        "future_hold",
        {"lot_id": a["id"], "route_step_id": f.steps[20]["id"], "comment": "check"},
    )
    assert fh["fh_status"] == "active"
    other = f.m.post("route", {"code": "R2", "name": "r2"})
    st = f.m.post(
        "route_step",
        {
            "route_id": other["id"],
            "seq": 10,
            "operation_id": f.steps[10]["operation_id"],
        },
    )
    f.m.post("future_hold", {"lot_id": a["id"], "route_step_id": st["id"]}, status=422)

    f.run_step(a)
    out = f.stage(a, "move_in", equipment_id=f.eq["id"])
    assert out["future_hold"] and out["lot"]["on_hold"]
    assert out["lot"]["lot_status"] == "waiting"
    holds = client.get(
        f"{EXEC}/holds", headers=f.m.h, params={"lot_id": a["id"]}
    ).json()["data"]
    assert holds[0]["hold_type"] == "future"
    f.post(
        f"{EXEC}/holds/{holds[0]['id']}/release",
        {"reason_id": f.reasons["release"]["id"]},
    )
    f.stage(a, "move_in", equipment_id=f.eq["id"])
    assert f.lot(a)["lot_status"] == "moved_in"
    f.m.patch("future_hold", fh["id"], {"comment": "x"}, status=422)

    # 管控关闭：不触发
    f.bind("move_in", ("future_hold", "off", {}))
    f.m.post("future_hold", {"lot_id": b["id"], "route_step_id": f.steps[20]["id"]})
    f.run_step(b)
    f.stage(b, "move_in", equipment_id=f.eq["id"])
    assert not f.lot(b)["on_hold"]


# ---------------- 10: priority / hot lot ----------------
def test_hot_lot_priority_queue_and_limit(client: TestClient, db: Session) -> None:
    from app.mes.execution.tests.test_exec import Line

    f = Line(client, db)
    a, b, c = f.start(2, 2, 2)
    hot = f.m.post(
        "lot_priority", {"code": "HOT", "name": "h", "level": 2, "is_hot": True}
    )
    out = f.post(
        f"{EXEC}/lots/{c['id']}/priority", {"priority_id": hot["id"], "comment": "x"}
    )
    assert out["lot"]["priority_id"] == hot["id"]
    q = client.get(f"{EXEC}/queue", headers=f.m.h).json()["data"]
    assert q[0]["code"] == c["code"] and q[0]["hot"]
    f.post(f"{EXEC}/lots/{c['id']}/priority", {"priority_id": hot["id"]}, status=409)
    # 急件上限 1：第二个急件被阻断
    f.bind("priority", ("hot_lot_limit", "block", {"max": 1}))
    r = f.post(
        f"{EXEC}/lots/{b['id']}/priority", {"priority_id": hot["id"]}, status=409
    )
    assert r["detail"]["code"] == "check_blocked"
