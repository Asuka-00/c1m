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
