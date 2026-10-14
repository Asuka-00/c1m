"""P2-B9 设备报警：主数据唯一、set 联动 Hold / E10（trigger=equipment）、未登记只记录、
幂等（active 同 ALID / 同事件号）、终态跳过、清除不自动解除、按批次反查、严格载荷、
先查权限、UTC Z、raw 返回。"""

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings
from app.mes.execution.tests.test_split_merge import _line
from app.mes.product.tests.test_bom import _member

EQP = f"{settings.API_V1_STR}/mes/eqp"


def _setup(client: TestClient, db: Session) -> Any:
    f = _line(client, db)
    lot, idle = f.start(2, 2)
    f.stage(lot, "move_in", equipment_id=f.eq["id"])
    et = f.eq["equipment_type_id"]
    f.m.post(
        "alarm_code",
        {
            "equipment_type_id": et,
            "alid": "1001",
            "severity": "major",
            "action": "hold_both",
            "target_e10_state_id": f.st["DOWN"]["id"],
            "text_en": "Chamber pressure high",
        },
    )
    return f, lot, idle


def _set(f: Any, status: int = 200, eq: Any = None, **body: Any) -> Any:
    return f.post(f"{EQP}/{(eq or f.eq)['id']}/alarms", body, status)


def test_alarm_set_links_holds_e10_and_clear(client: TestClient, db: Session) -> None:
    f, lot, idle = _setup(client, db)
    m = f.m
    # 主数据：同类型同 ALID 重复 → 409/422（部分唯一索引）
    r = client.post(
        m.url("alarm_code"),
        headers=m.h,
        json={
            "equipment_type_id": f.eq["equipment_type_id"],
            "alid": "1001",
            "severity": "info",
            "action": "none",
        },
    )
    assert r.status_code in (409, 422), r.text
    # hold_equipment 未配目标状态 → 422
    r = client.post(
        m.url("alarm_code"),
        headers=m.h,
        json={
            "equipment_type_id": f.eq["equipment_type_id"],
            "alid": "2002",
            "severity": "info",
            "action": "hold_equipment",
        },
    )
    assert r.status_code == 422, r.text
    at = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    r = _set(
        f,
        alid=" 1001 ",
        raw={"S5F1": {"ALCD": 132}},
        occurred_at=at,
        external_event_id="EV-1",
    )
    assert r["duplicate"] is False
    a = r["data"]
    assert a["alarm_status"] == "active" and a["unregistered"] is False
    assert a["set_at"].endswith("Z") and a["raw"] == {"S5F1": {"ALCD": 132}}
    assert [x["lot_code"] for x in a["lots"]] == [lot["code"]]
    assert len(a["hold_ids"]["holds"]) == 1
    assert a["e10_change"] == {"from": "SBY", "to": "DOWN"}
    hold = m.list("lot_hold", lot=lot["id"])["data"][0]
    assert hold["source"] == "equipment"
    rc = m.list("reason_code", code="equipment_alarm")["data"]
    assert hold["reason_id"] == rc[0]["id"]
    assert f.lot(idle)["on_hold"] is False  # 不在该设备上的批次不受影响
    eh = m.list("e10_history", equipment=f.eq["id"])["data"]
    assert any(x["source"] == "equipment" for x in eh)
    # 幂等：同 active ALID / 同事件号 → 已有记录，不新增 Hold
    for body in ({"alid": "1001"}, {"alid": "1001", "external_event_id": "EV-1"}):
        d = _set(f, **body)
        assert d["duplicate"] is True and d["data"]["id"] == a["id"]
    assert m.list("lot_hold", lot=lot["id"])["count"] == 1
    assert m.list("alarm_lot", alarm_log=a["id"])["count"] == 1
    # 按批次反查
    r = client.get(f"{EQP}/alarms", headers=m.h, params={"lot_id": lot["id"]})
    assert r.status_code == 200 and r.json()["count"] == 1
    # 清除：不自动解除 Hold；同清除事件号重放返回原记录；再清除 200 cleared=false（D55）
    url = f"{EQP}/alarms/{a['id']}/clear"
    c = f.post(url, {"comment": "fixed", "external_event_id": "CL-1"})
    assert c["cleared"] is True and c["data"]["alarm_status"] == "cleared"
    assert c["data"]["cleared_at"].endswith("Z")
    assert f.lot(lot)["on_hold"] is True
    rp = f.post(url, {"external_event_id": "CL-1"})
    assert rp["duplicate"] is True and rp["cleared"] is False
    assert rp["data"]["cleared_at"] == c["data"]["cleared_at"]
    again = f.post(url, {"comment": "x"})
    assert again["cleared"] is False and again["data"]["comment"] == "fixed"
    # 清除后同 ALID 再报：新的一次发生，正常联动（再 Hold 一次）
    n2 = _set(f, alid="1001")["data"]
    assert n2["id"] != a["id"] and len(n2["hold_ids"]["holds"]) == 1
    assert m.list("lot_hold", lot=lot["id"])["count"] == 2
    assert client.get(f"{EQP}/alarms/{a['id']}", headers=m.h).json()["raw"]
    r = client.get(f"{EQP}/alarms/{f.lot(lot)['id']}", headers=m.h)
    assert r.status_code == 404 and r.json()["detail"]["code"] == "alarm_not_found"


def test_alarm_unregistered_strict_perm(client: TestClient, db: Session) -> None:
    f, lot, _idle = _setup(client, db)
    m = f.m
    a = _set(f, alid="9999", alarm_text="unknown")["data"]
    assert a["unregistered"] is True and a["action"] == "none"
    # D55 OQ-3：未登记也写在制批关联，但不 Hold、不切 E10
    assert [x["lot_code"] for x in a["lots"]] == [lot["code"]]
    assert f.lot(lot)["on_hold"] is False and a["e10_change"] is None
    r = client.get(f"{EQP}/alarms", headers=m.h, params={"unregistered": True})
    assert r.json()["count"] == 1
    # D30：source 422；未知字段 422；未来时间 422 time_in_future；偏移换算成 Z
    for bad in ({"alid": "1", "source": "eap"}, {"alid": "1", "foo": 1}):
        _set(f, 422, **bad)
    fut = (datetime.now(UTC) + timedelta(minutes=10)).isoformat()
    d = _set(f, 422, alid="3", set_at=fut)["detail"]
    assert d[0]["code"] == "time_in_future"
    near = (datetime.now(UTC) + timedelta(minutes=4)).isoformat()
    _set(f, alid="3", set_at=near)  # 5 分钟以内接受
    r = _set(f, alid="4", set_at="2026-01-01T08:00:00+08:00")
    assert r["data"]["set_at"] == "2026-01-01T00:00:00Z"
    _set(f, 422, alid="5", lot_ids=[f.eq["id"]])
    # 先查权限（D34）：只读成员带非法体也是 403
    h = _member(client, db, m)
    r = client.post(f"{EQP}/{f.eq['id']}/alarms", headers=h, json={"foo": 1})
    assert r.status_code == 403
    assert client.get(f"{EQP}/alarms", headers=h).status_code in (200, 403)


def test_alarm_explicit_lot_ids(client: TestClient, db: Session) -> None:
    f, lot, idle = _setup(client, db)
    f.m.post(
        "alarm_code",
        {
            "equipment_type_id": f.eq["equipment_type_id"],
            "alid": "7",
            "severity": "minor",
            "action": "hold_lot",
        },
    )
    # 上报带入的 waiting 批次也关联并 Hold
    a = _set(f, alid="7", lot_ids=[idle["id"]])["data"]
    assert {x["lot_code"] for x in a["lots"]} == {lot["code"], idle["code"]}
    assert len(a["hold_ids"]["holds"]) == 2
