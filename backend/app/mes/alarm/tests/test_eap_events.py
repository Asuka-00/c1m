"""P2-B11 EAP 事件入口（D54-1 / D55 / D57）与 E10 / 过站 Idempotency-Key（#IK01 / D57）。"""

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings
from app.mes.alarm.tests.test_alarm import _setup
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

EQP = f"{settings.API_V1_STR}/mes/eqp"
EVENTS = f"{settings.API_V1_STR}/mes/eap/events"


def _account(client: TestClient, db: Session, f: Any, role: str) -> dict[str, str]:
    email, pw = random_email(), random_lower_string()
    crud.create_user(
        session=db,
        user_create=UserCreate(email=email, username=username_for(email), password=pw),
    )
    r = client.post(
        f"{API[:-4]}/tenants/{f.m.tid}/members",
        headers=f.m.h,
        json={"username": login_name(email), "roles": [role]},
    )
    assert r.status_code in (200, 201), r.text
    tok = client.post(
        f"{API[:-4]}/login/access-token",
        data={"username": login_name(email), "password": pw},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {tok}", "X-Tenant-ID": f.m.tid}


def _ev(f: Any, h: Any, ext: str, typ: str, status: int = 200, **kw: Any) -> Any:
    body = {
        "source": kw.pop("source", "simulator"),
        "external_event_id": ext,
        "event_type": typ,
        "equipment_id": kw.pop("equipment_id", f.eq["id"]),
        **kw,
    }
    return f.post(EVENTS, body, status, h)


def test_eap_events_service_only_alarm_flow(client: TestClient, db: Session) -> None:
    f, lot, _ = _setup(client, db)
    svc = _account(client, db, f, "eap_service")
    body = {"payload": {"alid": "1001"}}
    # 只给服务账号：owner / 超级用户 / 普通成员都 403
    _ev(f, f.m.h, "S-0", "alarm_set", 403, **body)
    _ev(f, _account(client, db, f, "member"), "S-0", "alarm_set", 403, **body)
    # 服务账号也不能调手工以外的写接口
    assert (
        client.post(
            f"{EQP}/{f.eq['id']}/alarms", headers=svc, json={"alid": "1"}
        ).status_code
        == 403
    )
    # 信封校验
    _ev(f, svc, "S-0", "alarm_set", 422, source="manual", **body)
    _ev(f, svc, "S-0", "bogus", 422, **body)
    d = _ev(f, svc, "S-0", "alarm_set", 422, payload={"alid": "1", "x": 1})["detail"]
    assert d[0]["loc"] == ["body", "payload", "x"]
    d = _ev(f, svc, "S-0", "alarm_set", 422, alid="1", payload={"alid": "1"})["detail"]
    assert d[0]["type"] == "duplicate_field"
    # D55：超前 > 5 分钟 422 time_in_future，不入账
    fut = (datetime.now(UTC) + timedelta(minutes=10)).isoformat()
    d = _ev(f, svc, "S-1", "alarm_set", 422, payload={"alid": "1001", "set_at": fut})
    assert d["detail"][0]["code"] == "time_in_future"
    # set：模拟器字段名 alid / lot_ids / set_at，平铺也行
    at = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    r = _ev(f, svc, "S-1", "alarm_set", alid="1001", set_at=at, lot_ids=[lot["id"]])
    assert r["duplicate"] is False and r["data"]["event_type"] == "alarm_set"
    a = r["result"]["data"]
    assert a["source"] == "simulator" and a["external_event_id"] == "S-1"
    assert [x["lot_code"] for x in a["lots"]] == [lot["code"]]
    # D58：不 Hold；状态事件 source=simulator、trigger=equipment
    assert a["hold_ids"] is None and f.lot(lot)["on_hold"] is False
    assert r["result"]["state_changed"] is True
    eh = f.m.list("e10_history", equipment=f.eq["id"])["data"]
    assert [(x["source"], x["trigger"]) for x in eh] == [("simulator", "equipment")]
    # 重放：原样返回，不再联动
    again = _ev(f, svc, "S-1", "alarm_set", alid="1001", set_at=at, lot_ids=[lot["id"]])
    assert again["duplicate"] is True and again["result"] == r["result"]
    assert len(f.m.list("e10_history", equipment=f.eq["id"])["data"]) == 1
    # D57：同事件号内容不同 → 422 idempotency_key_reused
    d = _ev(f, svc, "S-1", "alarm_set", 422, alid="9999")["detail"]
    assert d["code"] == "idempotency_key_reused"
    # 未登记 ALID：只记录，仍写 alarm_lot（D55）
    u = _ev(f, svc, "S-2", "alarm_set", alid="7777")["result"]["data"]
    assert u["unregistered"] is True and [x["lot_code"] for x in u["lots"]] == [
        lot["code"]
    ]
    # clear 按 (equipment_id, alid)
    c = _ev(f, svc, "C-1", "alarm_clear", alid="1001", cleared_at=at)
    assert c["result"]["cleared"] is True
    assert c["result"]["data"]["alarm_status"] == "cleared"
    assert c["result"]["data"]["clear_source"] == "simulator"
    assert (
        _ev(f, svc, "C-1", "alarm_clear", alid="1001", cleared_at=at)["duplicate"]
        is True
    )
    # 没有 active 报警 → 200、cleared=false、data=null
    n = _ev(f, svc, "C-2", "alarm_clear", alid="1001")
    assert n["result"] == {"data": None, "duplicate": False, "cleared": False}
    # 同 ALID 清除后再 set → 新记录
    r2 = _ev(f, svc, "S-3", "alarm_set", alid="1001")["result"]
    assert r2["duplicate"] is False and r2["data"]["id"] != a["id"]
    # 手工按 ALID 清除（B9）
    r = f.post(f"{EQP}/alarms/clear", {"equipment_id": f.eq["id"], "alid": "1001"})
    assert r["cleared"] is True and r["data"]["clear_source"] == "manual"
    r = f.post(f"{EQP}/alarms/clear", {"equipment_id": f.eq["id"], "alid": "1001"})
    assert r == {"data": None, "duplicate": False, "cleared": False}
    f.post(
        f"{EQP}/alarms/clear",
        {"equipment_id": f.eq["id"], "alid": "1", "source": "eap"},
        422,
    )


def test_eap_events_state_and_tool_usage(client: TestClient, db: Session) -> None:
    from app.mes.execution.tests.test_tool_life_b10 import _setup as tool_setup

    f = Line(client, db)
    svc = _account(client, db, f, "eap_service")
    r = _ev(
        f,
        svc,
        "E-1",
        "state",
        source="eap",
        payload={"to_state_id": f.st["DOWN"]["id"]},
    )
    assert (r["result"]["from"], r["result"]["to"]) == ("SBY", "DOWN")
    # D53-4 / D58：source = 事件来源，trigger=equipment
    assert (r["result"]["source"], r["result"]["trigger"]) == ("eap", "equipment")
    eh = f.m.list("e10_history", equipment=f.eq["id"])["data"]
    assert [(x["source"], x["trigger"]) for x in eh] == [("eap", "equipment")]
    # 重放不再校验（DOWN->DOWN 不会 422），不写新履历
    again = _ev(
        f,
        svc,
        "E-1",
        "state",
        source="eap",
        payload={"to_state_id": f.st["DOWN"]["id"]},
    )
    assert again["duplicate"] is True and again["result"] == r["result"]
    assert len(f.m.list("e10_history", equipment=f.eq["id"])["data"]) == len(eh)
    # 同事件号不同 source 是另一事件
    fut = (datetime.now(UTC) + timedelta(minutes=10)).isoformat()
    d = _ev(
        f,
        svc,
        "E-1",
        "state",
        422,
        payload={"to_state_id": f.st["SBY"]["id"], "event_at": fut},
    )
    assert d["detail"][0]["code"] == "time_in_future"
    fx = tool_setup(f, max_uses=10, count_basis="reported")
    t = f.m.post("tool", {"code": "PT1", "fixture_id": fx["id"]})
    u = _ev(f, svc, "U-1", "tool_usage", tool_id=t["id"], delta="2.5")
    assert (
        u["result"]["data"]["delta"] == "2.5"
        and u["result"]["data"]["source"] == "simulator"
    )
    assert u["result"]["tool"]["usage_count"] == "2.5"
    assert (
        _ev(f, svc, "U-1", "tool_usage", tool_id=t["id"], delta="2.5")["duplicate"]
        is True
    )
    d = _ev(f, svc, "U-1", "tool_usage", 422, tool_id=t["id"], delta="3")["detail"]
    assert d["code"] == "idempotency_key_reused"
    # D72 R-1（D71-2 / O-2）：7 位小数 422 value_error，带 ctx.max_places=6 与 input
    d = _ev(f, svc, "U-2", "tool_usage", 422, tool_id=t["id"], delta="0.0000001")
    (e,) = [x for x in d["detail"] if x["loc"][-1] == "delta"]
    assert e["type"] == "value_error" and e["ctx"]["max_places"] == 6, d
    assert e["input"] == "0.0000001", d
    # B10 手工接口：同事件号不同内容也 422（D57）
    url = f"{API}/eqp/tools/{t['id']}/usage"
    f.post(url, {"delta": "1", "external_event_id": "M-1"})
    assert f.post(url, {"delta": "1", "external_event_id": "M-1"})["duplicate"] is True
    d = f.post(url, {"delta": "2", "external_event_id": "M-1"}, 422)["detail"]
    assert d["code"] == "idempotency_key_reused"


def test_e10_idempotency_key(client: TestClient, db: Session) -> None:
    """#IK01 / D57：同 key 同内容 → 原响应（不再校验 SBY->SBY / 不写履历）；不同内容 422。"""
    f = Line(client, db)
    url = f"{EQP}/{f.eq['id']}/e10"
    h = {**f.m.h, "Idempotency-Key": "ik-e10-1"}
    first = f.post(url, {"to_state_id": f.st["DOWN"]["id"]}, 200, h)
    n = len(f.m.list("e10_history", equipment=f.eq["id"])["data"])
    r = f.c.post(url, headers=h, json={"to_state_id": f.st["DOWN"]["id"]})
    assert r.status_code == 200 and r.json() == first
    assert r.headers.get("Idempotent-Replayed") == "true"
    assert len(f.m.list("e10_history", equipment=f.eq["id"])["data"]) == n
    d = f.post(url, {"to_state_id": f.st["SBY"]["id"]}, 422, h)["detail"]
    assert d["code"] == "idempotency_key_reused"
    # 没带 key 照常校验
    f.post(url, {"to_state_id": f.st["DOWN"]["id"]}, 422)
    # 失败请求不存档：新 key 第一次 422，修正后同 key 成功
    h2 = {**f.m.h, "Idempotency-Key": "ik-e10-2"}
    f.post(url, {"to_state_id": f.st["DOWN"]["id"]}, 422, h2)
    # 过期（> 24h）的存档不再生效
    f.sql(
        "UPDATE mes_idempotency_key SET created_at = now() - interval '25 hours' WHERE tenant_id = :t AND idem_key = 'ik-e10-1'",
        t=f.m.tid,
    )
    f.post(url, {"to_state_id": f.st["SBY"]["id"]}, 200, h)
    assert EXEC


def test_migration_0028_up_down() -> None:
    """0028 可重复执行；两张表与唯一约束，与表定义一致。"""
    from app.mes.equipment.tests.test_qual import _migration_roundtrip

    names = ("mes_eap_event", "mes_idempotency_key")

    def check(i: Any) -> tuple[frozenset[str], bool]:
        return frozenset(set(names) & set(i.get_table_names())), True

    _migration_roundtrip("0027_transform_undone", "b11", check, names)
