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
