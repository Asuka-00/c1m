"""现场作业视图：派工队列排序 / 筛选、首页概览、Q-Time 监控的产品与流程列。"""

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.mes.execution.tests.test_exec import EXEC, Line


def test_queue_home_and_qtime_columns(client: TestClient, db: Session) -> None:
    f = Line(client, db)
    f.m.post(
        "qtime_rule",
        {
            "code": "QT-D",
            "name": "q",
            "route_id": f.route["id"],
            "from_step_id": f.steps[10]["id"],
            "to_step_id": f.steps[20]["id"],
            "max_minutes": 30,
            "reason_id": f.reasons["hold"]["id"],
        },
    )
    a, b, c = f.start(1, 1, 1)
    for x in (a, b):
        f.run_step(x)
    # a 已超时（剩余为负）应排在 b 前；c 被 Hold 排最后
    f.sql(
        "UPDATE mes_lot_history SET at = at - interval '2 hours' "
        "WHERE lot_id = :a AND action = 'move_out'",
        a=a["id"],
    )
    f.sql("UPDATE mes_lot SET on_hold = true WHERE id = :c", c=c["id"])
    h = f.m.h
    q = client.get(f"{EXEC}/queue", headers=h).json()["data"]
    codes = [r["code"] for r in q]
    assert codes.index(a["code"]) < codes.index(b["code"]) < codes.index(c["code"])
    ra = next(r for r in q if r["code"] == a["code"])
    assert ra["qtime_remaining"] < 0 and ra["product"] and ra["step_seq"] == 20
    held = client.get(f"{EXEC}/queue", headers=h, params={"on_hold": True})
    assert [r["code"] for r in held.json()["data"]] == [c["code"]]
    home = client.get(f"{EXEC}/home", headers=h).json()
    assert home["wip_lots"] == 3 and home["on_hold"] == 1
    assert home["qtime_exceeded"] == 1
    mon = client.get(f"{EXEC}/qtime/monitor", headers=h).json()["data"]
    assert mon[0]["product"] and mon[0]["route"] == f.route["code"]


def test_wip_filters_and_oee_trend(client: TestClient, db: Session) -> None:
    f = Line(client, db)
    f.start(1, 1)
    h = f.m.h
    w = client.get(f"{EXEC}/reports/wip", headers=h).json()
    assert w["total_lots"] == 2 and w["by_product"][0]["product_id"]
    pid = w["by_product"][0]["product_id"]
    assert (
        client.get(f"{EXEC}/reports/wip", headers=h, params={"product_id": pid}).json()[
            "total_lots"
        ]
        == 2
    )
    other = "00000000-0000-0000-0000-000000000000"
    w2 = client.get(f"{EXEC}/reports/wip", headers=h, params={"product_id": other})
    assert w2.json()["total_lots"] == 0
    tr = client.get(f"{EXEC}/reports/oee-trend", headers=h).json()["data"]
    assert len(tr) == 7 and {"day", "availability", "oee"} <= set(tr[0])
    long = client.get(
        f"{EXEC}/reports/oee-trend",
        headers=h,
        params={"date_from": "2026-01-01", "date_to": "2026-06-30"},
    )
    assert long.status_code == 422
