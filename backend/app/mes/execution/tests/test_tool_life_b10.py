"""P2-B10 tool / consumable life: count_basis counting at Track Out (Decimal),
usage history, hard block at max (overridable=false), warn zone by warn_ratio,
usage report idempotency (D30), adjust/reset, mount/unmount/replace, validators."""

from datetime import timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.spec.base import now
from app.mes.execution.tests.test_exec import Line
from app.testing.mes import API

TOOLS = f"{API}/eqp/tools"


def _setup(f: Line, **fx: Any) -> dict[str, Any]:
    m = f.m
    fixture = m.post(
        "fixture", {"code": "PC", "name": "probe card", "kind": "tool", **fx}
    )
    f.sql(
        "INSERT INTO mes_step_resource (id, tenant_id, route_step_id, resource_kind, fixture_id) VALUES (gen_random_uuid(), :t, :s, 'fixture', :f)",
        t=m.tid,
        s=f.steps[10]["id"],
        f=fixture["id"],
    )
    return fixture


def _get(f: Line, url: str, status: int = 200) -> Any:
    r = f.c.get(url, headers=f.m.h)
    assert r.status_code == status, r.text
    return r.json()


def test_track_out_counts_by_wafer_and_hard_blocks(
    client: TestClient, db: Session
) -> None:
    f = Line(client, db)
    m = f.m
    fx = _setup(f, max_uses=10, count_basis="per_wafer", life_unit="wafer")
    t = m.post("tool", {"code": "PC1", "fixture_id": fx["id"]})
    a, b, c = f.start(4, 7, 1)
    f.stage(a, "move_in", equipment_id=f.eq["id"])
    f.stage(a, "track_in", equipment_id=f.eq["id"], tool_ids=[t["id"]])
    r = f.stage(a, "track_out")
    assert r["tools"] == [{"tool": "PC1", "usage": 4, "max": 10, "status": "available"}]
    h = _get(f, f"{TOOLS}/{t['id']}/usage")
    assert h["count"] == 1
    row = h["data"][0]
    assert (row["kind"], row["delta"], row["count_after"]) == ("track_out", "4", "4")
    assert row["lot_id"] == a["id"] and row["occurred_at"].endswith("Z")
    f.stage(b, "move_in", equipment_id=f.eq["id"])
    f.stage(b, "track_in", equipment_id=f.eq["id"], tool_ids=[t["id"]])
    r = f.stage(b, "track_out")
    assert r["tools"][0]["usage"] == 11
    assert r["tools"][0]["status"] == "pending_maintenance"
    # tool.life_reached: audit event (notification only when someone subscribed)
    n = f.sql(
        "SELECT count(*) FROM mes_audit_log WHERE tenant_id = :t AND entity_type = 'tool' AND action = 'life_reached'",
        t=m.tid,
    )
    assert n[0][0] == 1
    # usage >= max -> 409 check_blocked, tool_life, overridable=false (override ignored)
    f.stage(c, "move_in", equipment_id=f.eq["id"])
    d = f.stage(
        c,
        "track_in",
        409,
        equipment_id=f.eq["id"],
        tool_ids=[t["id"]],
        override=True,
        override_reason="try",
    )["detail"]
    assert d["code"] == "check_blocked"
    items = [x for x in d["results"] if x["check_type"] == "tool_life"]
    assert items and items[0]["overridable"] is False and items[0]["result"] == "block"
    # P2-D3: rule-based tool_life agrees with the built-in block (no "tools available")
    assert all(x["result"] == "block" for x in items), items
    assert not any("tools available" in x["message"] for x in items), items


def test_usage_report_warn_zone_and_idempotency(
    client: TestClient, db: Session
) -> None:
    f = Line(client, db)
    m = f.m
    fx = _setup(f, max_uses=10, count_basis="reported", warn_ratio=0.5)
    t = m.post("tool", {"code": "PC2", "fixture_id": fx["id"]})
    url = f"{TOOLS}/{t['id']}/usage"
    body = {"delta": "5.5", "equipment_id": f.eq["id"], "external_event_id": "E-1"}
    r = f.post(url, body)
    assert r["duplicate"] is False and r["data"]["delta"] == "5.5"
    assert r["tool"]["usage_count"] == "5.5" and r["tool"]["max_usage"] == "10"
    assert r["tool"]["life_state"] == "warning" and r["tool"]["warn_ratio"] == "0.5"
    again = f.post(url, body)
    assert again["duplicate"] is True and again["data"]["id"] == r["data"]["id"]
    assert again["tool"]["usage_count"] == "5.5"
    f.post(url, {"delta": "0.0000001"}, 422)
    f.post(url, {"delta": "1", "source": "eap"}, 422)  # D30: manual rejects source
    fut = (now() + timedelta(minutes=10)).isoformat()
    d = f.post(url, {"delta": "1", "occurred_at": fut}, 422)["detail"]
    assert d[0]["code"] == "time_in_future"
    d = f.post(url, {"delta": "-1"}, 422)["detail"]
    assert d[0]["code"] == "reason_required"
    r = f.post(url, {"delta": "-1.5", "reason_id": f.reasons["hold"]["id"]})
    assert r["data"]["kind"] == "adjust" and r["tool"]["usage_count"] == "4"
    assert r["tool"]["life_state"] == "ok"
    # reported basis: Track Out does not count; warn zone stays overridable
    f.post(url, {"delta": "1"})
    (lot,) = f.start(3)
    f.stage(lot, "move_in", equipment_id=f.eq["id"])
    f.stage(lot, "track_in", equipment_id=f.eq["id"], tool_ids=[t["id"]])
    assert f.stage(lot, "track_out")["tools"][0]["usage"] == 5
    r = f.post(url, {"delta": "5"})
    assert (
        r["life_reached"] is True and r["tool"]["tool_status"] == "pending_maintenance"
    )


def test_mount_replace_reset(client: TestClient, db: Session) -> None:
    f = Line(client, db)
    m = f.m
    fx = _setup(f, max_uses=2)
    t1 = m.post("tool", {"code": "A1", "fixture_id": fx["id"]})
    t2 = m.post("tool", {"code": "A2", "fixture_id": fx["id"]})
    t3 = m.post("tool", {"code": "A3", "fixture_id": fx["id"], "usage_count": 2})
    mb = {"equipment_id": f.eq["id"], "port_code": "P1"}
    r = f.post(f"{TOOLS}/{t1['id']}/mount", mb)
    assert r["data"]["port_code"] == "P1" and r["data"]["usage_at_mount"] == "0"
    assert r["tool"]["equipment_id"] == f.eq["id"]
    d = f.post(f"{TOOLS}/{t1['id']}/mount", mb, 409)["detail"]
    assert d["code"] == "tool_already_mounted"
    d = f.post(f"{TOOLS}/{t2['id']}/mount", mb, 409)["detail"]
    assert d["code"] == "tool_position_occupied"
    f.sql(
        "UPDATE mes_tool SET tool_status = 'pending_maintenance' WHERE id = :i",
        i=t3["id"],
    )
    d = f.post(f"{TOOLS}/{t3['id']}/mount", {"equipment_id": f.eq["id"]}, 409)["detail"]
    assert d["code"] == "tool_not_usable"
    r = f.post(
        f"{TOOLS}/{t1['id']}/replace", {"new_tool_id": t2["id"], "reason": "broken"}
    )
    assert r["unmounted"]["unmount_reason"] == "broken"
    assert r["unmounted"]["replaced_by_tool_id"] == t2["id"]
    assert (
        r["mounted"]["port_code"] == "P1"
        and r["new_tool"]["equipment_id"] == f.eq["id"]
    )
    d = f.post(f"{TOOLS}/{t1['id']}/unmount", {"reason": "pm"}, 409)["detail"]
    assert d["code"] == "tool_not_mounted"
    f.post(f"{TOOLS}/{t2['id']}/unmount", {"reason": "pm"})
    h = _get(f, f"{TOOLS}/{t2['id']}/mounts")
    assert h["count"] == 1 and h["data"][0]["unmounted_at"].endswith("Z")
    r = f.post(f"{TOOLS}/{t3['id']}/reset", {"reason_id": f.reasons["rework"]["id"]})
    assert r["tool"]["usage_count"] == "0" and r["tool"]["tool_status"] == "available"
    assert r["tool"]["life_reset_count"] == 1 and r["data"]["kind"] == "reset"
    assert r["data"]["delta"] == "-2"


def test_tool_validators(client: TestClient, db: Session) -> None:
    f = Line(client, db)
    m = f.m
    h = m.h
    r = client.post(
        f"{API}/fixture",
        headers=h,
        json={"code": "X", "name": "x", "kind": "tool", "warn_ratio": 1.5},
    )
    assert r.status_code == 422, r.text
    # D60: generic CRUD numeric(18,6) columns -> 422 too_many_decimals, no rounding
    for col in ("usage_count", "max_usage"):
        r = client.post(
            f"{API}/tool",
            headers=h,
            json={"code": "X1", "fixture_id": f.fixture["id"], col: "1.1234567"},
        )
        assert r.status_code == 422, r.text
        err = r.json()["detail"][0]
        assert err["code"] == err["type"] == "too_many_decimals", err
        assert err["loc"] == ["body", col]
    t = m.post(
        "tool",
        {"code": "X1", "fixture_id": f.fixture["id"], "usage_count": "1.123456"},
    )
    assert t["usage_count"] == 1.123456
    t = m.post(
        "tool", {"code": "X2", "fixture_id": f.fixture["id"], "usage_count": "1.25"}
    )
    assert float(t["usage_count"]) == 1.25


def test_effective_life_fields(client: TestClient, db: Session) -> None:
    """前端用：有效上限 / 预警比例（工具 → 类型 → warn_pct/100），十进制字符串。"""
    from app.mes.execution.tests.test_exec import EXEC

    f = Line(client, db)
    m = f.m
    fx = _setup(f, max_uses=10, count_basis="reported", warn_ratio=0.8)
    t1 = m.post("tool", {"code": "PE1", "fixture_id": fx["id"]})
    t2 = m.post(
        "tool",
        {"code": "PE2", "fixture_id": fx["id"], "max_usage": 2.5, "warn_ratio": 0.6},
    )
    rows = {r["code"]: r for r in m.list("tool", q="PE")["data"]}
    assert (
        rows["PE1"]["effective_max_usage"],
        rows["PE1"]["effective_warn_ratio"],
    ) == (
        "10",
        "0.8",
    )
    assert (
        rows["PE2"]["effective_max_usage"],
        rows["PE2"]["effective_warn_ratio"],
    ) == (
        "2.5",
        "0.6",
    )
    one = _get(f, f"{API}/tool/{t2['id']}")
    one = one.get("data", one)
    assert one["effective_max_usage"] == "2.5"
    r = f.post(f"{TOOLS}/{t1['id']}/usage", {"delta": "1"})
    assert r["tool"]["effective_max_usage"] == "10"
    assert r["tool"]["effective_warn_ratio"] == "0.8"
    # 类型无上限、工具无覆盖 → null；无 warn_ratio → warn_pct/100
    fx2 = m.post("fixture", {"code": "PN", "name": "no limit", "kind": "tool"})
    t3 = m.post("tool", {"code": "PN1", "fixture_id": fx2["id"], "warn_pct": 75})
    r3 = {r["code"]: r for r in m.list("tool", q="PN")["data"]}["PN1"]
    assert r3["effective_max_usage"] is None and r3["effective_warn_ratio"] == "0.75"
    assert t3["id"]
    # 进站执行上下文的工具选项带有效 warn_ratio，warn_pct 保留
    (lot,) = f.start(3)
    ctx = _get(f, f"{EXEC}/lots/{lot['id']}")
    opts = {o["code"]: o for x in ctx["tools"] for o in x["options"]}
    assert opts["PE1"]["warn_ratio"] == "0.8" and opts["PE2"]["warn_ratio"] == "0.6"
    assert "warn_pct" in opts["PE1"]
