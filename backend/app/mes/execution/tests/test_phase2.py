"""二期：内置管控开关（卡控规则 severity = off）、返工上限、跳站、在制报废 / 补数、Q-Time 扫描。"""

from typing import Any

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.mes.execution.tests.test_exec import Line, _dc, _dc_line


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
