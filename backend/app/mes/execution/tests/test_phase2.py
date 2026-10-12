"""二期：内置管控开关（卡控规则 severity = off）、返工上限、跳站、在制报废 / 补数、Q-Time 扫描。"""

from typing import Any

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.mes.execution.tests.test_exec import Line, _dc, _dc_line, _msgs


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
