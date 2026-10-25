"""站内通知：订阅 CRUD / 校验 / 权限、按角色与用户解析接收人、去重、已读，以及 MES 事件接入。"""

import uuid
from typing import Any

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings
from app.core.tenant import set_tenant
from app.mes.execution.tests.test_exec import Line, _dc, _dc_line
from app.platform.notification import service as svc
from app.platform.users import service as crud
from app.platform.users.schemas import UserCreate
from app.testing.utils import (
    login_name,
    random_email,
    random_lower_string,
    username_for,
)

API = settings.API_V1_STR
EQP = f"{API}/mes/eqp"
EXEC = f"{API}/mes/exec"


def _roles(c: TestClient, h: dict[str, str], tid: str) -> dict[str, str]:
    rs = c.get(f"{API}/tenants/{tid}/roles", headers=h).json()["data"]
    return {r["name"]: r["id"] for r in rs}


def _sub_all(f: Line) -> None:
    """租户 owner 角色订阅全部可订阅的 MES 事件（定向事件除外）。"""
    c, h, tid = f.c, f.m.h, str(f.m.tid)
    meta = c.get(f"{API}/notification-meta", headers=h).json()
    owner = _roles(c, h, tid)["owner"]
    for e in meta["event_types"]:
        if e["code"].startswith("mes.") and not e["direct"]:
            r = c.post(
                f"{API}/notification-subscriptions",
                headers=h,
                json={"name": e["code"], "event_type": e["code"], "role_ids": [owner]},
            )
            assert r.status_code == 200, r.text


def _mine(f: Line, **params: Any) -> dict[str, Any]:
    r = f.c.get(f"{API}/notifications", headers=f.m.h, params=params)
    assert r.status_code == 200, r.text
    return r.json()  # type: ignore[no-any-return]


def _types(f: Line) -> list[str]:
    return [n["event_type"] for n in _mine(f, page_size=100)["data"]]


def test_subscription_crud_validation_permission(
    client: TestClient, db: Session
) -> None:
    f = Line(client, db)
    h, tid = f.m.h, str(f.m.tid)
    meta = client.get(f"{API}/notification-meta", headers=h).json()
    codes = {e["code"] for e in meta["event_types"]}
    assert {"mes.qtime_warn", "mes.oos", "mes.pm_overdue", "mes.eqp_down"} <= codes
    assert [c["code"] for c in meta["channels"]] == ["in_app"]
    url = f"{API}/notification-subscriptions"
    # 校验：未知事件 / 定向事件不可订阅 / 无接收人 / 未知渠道
    owner = _roles(client, h, tid)["owner"]
    assert {e["code"] for e in meta["event_types"] if e["direct"]} == {"mes.ncr_review"}
    for body in (
        {"name": "x", "event_type": "nope", "role_ids": [owner]},
        {"name": "x", "event_type": "mes.ncr_review", "role_ids": [owner]},
        {"name": "x", "event_type": "mes.oos"},
        {
            "name": "x",
            "event_type": "mes.oos",
            "user_ids": [str(uuid.uuid4())],
            "channels": ["sms"],
        },
    ):
        assert client.post(url, headers=h, json=body).status_code == 422
    s = client.post(
        url,
        headers=h,
        json={
            "name": "OOS",
            "event_type": "mes.oos",
            "role_ids": [_roles(client, h, tid)["owner"]],
        },
    ).json()
    assert s["is_active"] and s["channels"] == ["in_app"]
    r = client.put(
        f"{url}/{s['id']}", headers=h, json={**s, "name": "OOS2", "is_active": False}
    )
    assert r.status_code == 200 and r.json()["name"] == "OOS2"
    lst = client.get(url, headers=h, params={"q": "OOS2"}).json()
    assert lst["count"] == 1
    # 成员（只读角色）无配置权限
    email, pw = random_email(), random_lower_string()
    crud.create_user(
        session=db,
        user_create=UserCreate(email=email, username=username_for(email), password=pw),
    )
    client.post(
        f"{API}/tenants/{tid}/members",
        headers=h,
        json={"username": login_name(email), "roles": ["member"]},
    )
    tok = client.post(
        f"{API}/login/access-token",
        data={"username": login_name(email), "password": pw},
    ).json()["access_token"]
    mh = {"Authorization": f"Bearer {tok}", "X-Tenant-ID": tid}
    assert client.get(url, headers=mh).status_code == 403
    assert client.get(f"{API}/notifications/summary", headers=mh).status_code == 200
    assert client.delete(f"{url}/{s['id']}", headers=h).status_code == 200
    assert client.get(url, headers=h).json()["count"] == 0


def test_notify_dedupe_recipients_read(client: TestClient, db: Session) -> None:
    f = Line(client, db)
    _sub_all(f)
    tid = uuid.UUID(str(f.m.tid))
    set_tenant(db, tid)
    lot = {"id": uuid.uuid4(), "code": "L-X"}
    kw: dict[str, Any] = {
        "title": "t",
        "object_type": "lot",
        "object_id": lot["id"],
        "object_code": "L-X",
        "dedupe_key": "k1",
    }
    assert svc.notify(db, tid, "mes.lot_hold", **kw)
    assert svc.notify(db, tid, "mes.lot_hold", **kw) is None  # 去重
    assert svc.notify(db, tid, "mes.oos", **{**kw, "dedupe_key": None})
    db.commit()
    s = client.get(f"{API}/notifications/summary", headers=f.m.h).json()
    assert s["unread"] == 2 and len(s["latest"]) == 2
    d = _mine(f, severity="critical")["data"]
    assert [n["event_type"] for n in d] == ["mes.oos"]
    assert _mine(f, q="L-X")["count"] == 2
    client.post(f"{API}/notifications/read", headers=f.m.h, json={"ids": [d[0]["id"]]})
    assert _mine(f, is_read=False)["count"] == 1
    # 铃铛只列待确认的通知
    s = client.get(f"{API}/notifications/summary", headers=f.m.h).json()
    assert s["unread"] == 1 and [n["event_type"] for n in s["latest"]] == [
        "mes.lot_hold"
    ]
    client.post(f"{API}/notifications/read", headers=f.m.h, json={})
    s = client.get(f"{API}/notifications/summary", headers=f.m.h).json()
    assert s["unread"] == 0 and s["latest"] == []


def test_mes_events_qtime_oos_e10_pm(client: TestClient, db: Session) -> None:
    from app.mes.execution.service import sweep_all_tenants

    f, items = _dc_line(client, db, {"B": "auto_hold"})
    _sub_all(f)
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
    a, b, c = f.start(1, 1, 1)
    # OOS + 自动 Hold
    f.stage(c, "move_in", equipment_id=f.eq["id"])
    f.stage(c, "track_in", equipment_id=f.eq["id"])
    f.stage(c, "track_out", dc=_dc(items, 5))
    ts = _types(f)
    assert ts.count("mes.oos") == 1 and ts.count("mes.lot_hold") == 1
    hold = next(n for n in _mine(f)["data"] if n["event_type"] == "mes.lot_hold")
    assert hold["object_code"] == c["code"] and hold["link"].endswith(str(c["id"]))
    for x in (a, b):
        f.stage(x, "move_in", equipment_id=f.eq["id"])
        f.stage(x, "track_in", equipment_id=f.eq["id"])
        f.stage(x, "track_out", dc=_dc(items, 1.5))
        f.stage(x, "move_out")
    f.sql(
        "UPDATE mes_lot_history SET at = at - interval '50 minutes' WHERE lot_id = :a AND action = 'move_out'",
        a=a["id"],
    )
    f.sql(
        "UPDATE mes_lot_history SET at = at - interval '2 hours' WHERE lot_id = :b AND action = 'move_out'",
        b=b["id"],
    )
    # PM 超期
    f.m.post(
        "pm_plan",
        {"code": "PM-L", "name": "pm", "equipment_id": f.eq["id"], "interval_lots": 1},
    )
    tid = uuid.UUID(str(f.m.tid))
    for _ in range(3):  # 重复扫描不重复通知
        sweep_all_tenants([tid])
        f.post(f"{EXEC}/qtime/sweep", {})
    ts = _types(f)
    assert ts.count("mes.qtime_warn") == 1
    assert ts.count("mes.qtime_exceeded") == 1
    assert ts.count("mes.lot_hold") == 1  # Q-Time Hold 不再单独发 lot_hold
    assert ts.count("mes.pm_overdue") == 1
    # 设备宕机 + 停机记录
    f.post(f"{EQP}/{f.eq['id']}/e10", {"to_state_id": f.st["DOWN"]["id"]})
    rc = f.m.post("reason_code", {"code": "DT", "name": "d", "reason_type": "downtime"})
    f.m.post(
        "downtime",
        {
            "equipment_id": f.eq["id"],
            "start_at": "2026-10-01T08:00:00Z",
            "reason_id": rc["id"],
        },
    )
    ts = _types(f)
    assert ts.count("mes.eqp_down") == 1 and ts.count("mes.downtime") == 1
    eq = next(n for n in _mine(f)["data"] if n["event_type"] == "mes.eqp_down")
    assert eq["object_type"] == "equipment" and eq["link"] == "/mes/eqp-board"
    # 筛选：事件类型
    assert _mine(f, event_type="mes.oos")["count"] == 1
