"""D65：422 ``unknown_field``、查询参数 422 的 loc 以 ``query`` 开头、eap_service 只读三实体。"""

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings
from app.mes.alarm.tests.test_alarm import _line, _setup
from app.mes.alarm.tests.test_eap_events import _account

MES = f"{settings.API_V1_STR}/mes"
AC = f"{MES}/alarm-code"


def test_unknown_field_code(client: TestClient, db: Session) -> None:
    f = _line(client, db)
    base = {"equipment_type_id": f.eq["equipment_type_id"], "alid": "U1"}
    r = client.post(AC, headers=f.m.h, json={**base, "foo": 1, "bar": 2})
    assert r.status_code == 422, r.text
    assert r.json()["detail"] == [
        {
            "loc": ["body", k],
            "msg": f"{k}: unknown field",
            "type": "unknown_field",
            "code": "unknown_field",
        }
        for k in ("bar", "foo")
    ]
    rid = client.post(AC, headers=f.m.h, json=base).json()["id"]
    r = client.patch(f"{AC}/{rid}", headers=f.m.h, json={"foo": "x"})
    d = r.json()["detail"][0]
    assert r.status_code == 422 and d["code"] == "unknown_field"
    assert d["loc"] == ["body", "foo"]


def test_query_param_loc(client: TestClient, db: Session) -> None:
    f = _line(client, db)
    h = f.m.h
    for params, name in (
        ({"has_migration_note": "maybe"}, "has_migration_note"),
        ({"id": "nope"}, "id"),
        ({"created_at_from": "xx"}, "created_at_from"),
        ({"severity": "nope"}, "severity"),
        ({"sort_by": "nope"}, "sort_by"),
    ):
        r = client.get(AC, headers=h, params=params)
        assert r.status_code == 422, (params, r.text)
        d = r.json()["detail"]
        assert d[0]["loc"] == ["query", name], (params, d)
    for url, params, name in (
        ("e10-history", {"trigger": "bogus"}, "trigger"),
        ("equipment", {"is_active": "maybe"}, "is_active"),
        ("lot", {"lot_status": "bogus"}, "lot_status"),
    ):
        r = client.get(f"{MES}/{url}", headers=h, params=params)
        assert r.status_code == 422, (url, r.text)
        assert r.json()["detail"][0]["loc"] == ["query", name]
    r = client.get(AC, headers=h, params={"page": "x"})
    assert r.status_code == 422 and r.json()["detail"][0]["loc"][0] == "query"
    r = client.get(f"{MES}/exec/customer-lots", headers=h)
    assert r.status_code == 422
    assert r.json()["detail"][0]["loc"] == ["query", "customer_lot_no"]


def test_eap_service_read_only(client: TestClient, db: Session) -> None:
    f, _, _ = _setup(client, db)
    svc = _account(client, db, f, "eap_service")
    eq = f.eq["id"]
    r = client.get(f"{MES}/equipment", headers=svc)
    assert r.status_code == 200 and r.json()["count"] >= 1, r.text
    assert client.get(f"{MES}/equipment/{eq}", headers=svc).status_code == 200
    r = client.get(AC, headers=svc, params={"alid": "1001"})
    assert r.status_code == 200 and r.json()["count"] == 1, r.text
    ac = r.json()["data"][0]["id"]
    assert client.get(f"{AC}/{ac}", headers=svc).status_code == 200
    r = client.get(f"{MES}/e10-state", headers=svc)
    assert r.status_code == 200 and r.json()["count"] >= 1
    st = r.json()["data"][0]["id"]
    assert client.get(f"{MES}/e10-state/{st}", headers=svc).status_code == 200
    # 不放开写权限
    assert (
        client.patch(f"{MES}/equipment/{eq}", headers=svc, json={}).status_code == 403
    )
    assert client.post(AC, headers=svc, json={"alid": "X"}).status_code == 403
    assert client.delete(f"{AC}/{ac}", headers=svc).status_code == 403
    assert client.post(f"{MES}/e10-state", headers=svc, json={}).status_code == 403
    # 同模块 / 其他主数据、导出都不放开
    for u in ("equipment-type", "e10-history", "product", "equipment/export"):
        assert client.get(f"{MES}/{u}", headers=svc).status_code == 403, u


def test_alarm_log_list_flattens_state(client: TestClient, db: Session) -> None:
    from app.mes.alarm.tests.test_alarm import _set

    f, _, _ = _setup(client, db)
    a = _set(f, alid="1001")["data"]
    _set(f, alid="9999", alarm_text="no code")
    r = client.get(f"{MES}/alarm-log", headers=f.m.h, params={"page_size": 100})
    assert r.status_code == 200, r.text
    rows = {x["id"]: x for x in r.json()["data"]}
    assert rows[a["id"]]["state_changed"] is True
    assert rows[a["id"]]["state_skip_reason"] is None
    for x in rows.values():
        assert isinstance(x["state_changed"], bool) and "state_skip_reason" in x
    d = client.get(f"{MES}/alarm-log/{a['id']}", headers=f.m.h).json()
    assert d["state_changed"] is True
    # alarm_code 列表也返回 migration_note（spec list=False 只影响显示）
    r = client.get(AC, headers=f.m.h)
    assert all("migration_note" in x for x in r.json()["data"])


def test_duplicate_alarm_returns_original_state(
    client: TestClient, db: Session
) -> None:
    """P2-D8 / D57：重复上报返回原记录的 state_changed / state_skip_reason。"""
    from app.mes.alarm.tests.test_alarm import _set

    f, _, _ = _setup(client, db)
    first = _set(f, alid="1001")
    assert first["state_changed"] is True and first["state_skip_reason"] is None
    dup = _set(f, alid="1001")
    assert dup["duplicate"] is True
    assert dup["state_changed"] is True
    assert dup["state_skip_reason"] == first["state_skip_reason"]


def test_exec_bodies_forbid_extra(client: TestClient, db: Session) -> None:
    """D65：E10 / 过站等自定义请求体多余字段 → 422 unknown_field，不写入。"""
    f, lot, _ = _setup(client, db)
    before = client.get(f"{MES}/equipment/{f.eq['id']}", headers=f.m.h).json()
    d = f.post(
        f"{MES}/eqp/{f.eq['id']}/e10",
        {"to_state_id": f.st["DOWN"]["id"], "bogus": 1},
        422,
    )["detail"][0]
    assert d["loc"] == ["body", "bogus"] and d["code"] == "unknown_field"
    assert d["type"] == "extra_forbidden"
    after = client.get(f"{MES}/equipment/{f.eq['id']}", headers=f.m.h).json()
    assert after.get("e10_state_id") == before.get("e10_state_id")
    d = f.stage(lot, "track_in", 422, equipment_id=f.eq["id"], bogus=1)["detail"][0]
    assert d["loc"] == ["body", "bogus"] and d["code"] == "unknown_field"
    d = f.post(
        f"{MES}/exec/lots/{lot['id']}/hold", {"reason_id": f.eq["id"], "x": 1}, 422
    )["detail"]
    assert any(x["loc"] == ["body", "x"] and x["code"] == "unknown_field" for x in d)


def test_action_endpoints_empty_body(client: TestClient, db: Session) -> None:
    """D65 补充 4：无字段的动作接口接受空 / {}，多余字段 422 unknown_field。"""
    import uuid

    f = _line(client, db)
    h = f.m.h
    sweep = f"{MES}/exec/qtime/sweep"
    assert client.post(sweep, headers=h).status_code == 200
    assert client.post(sweep, headers=h, json={}).status_code == 200
    r = client.post(sweep, headers=h, json={"x": 1})
    assert r.status_code == 422 and r.json()["detail"][0]["code"] == "unknown_field"
    for act in ("release", "cancel"):
        u = f"{MES}/change-order/{uuid.uuid4()}/{act}"
        assert client.post(u, headers=h).status_code == 404
        assert client.post(u, headers=h, json={}).status_code == 404
        r = client.post(u, headers=h, json={"x": 1})
        assert r.status_code == 422
        assert r.json()["detail"][0]["loc"] == ["body", "x"]
        assert r.json()["detail"][0]["code"] == "unknown_field"
