"""D80（含补充一、二）/ D81 / D82-4：光罩 14 个写接口必填 Idempotency-Key、校验顺序、
下机单独记事件行、事件 payload 带 source / external_event_id、补录时间校验。"""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, text

from app.core.db import admin_engine
from app.mes.execution.tests.test_site_date import _session
from app.mes.product.tests.test_bom import _member
from app.mes.reticle import router as rt_router
from app.mes.reticle import service as rt_svc
from app.mes.reticle.tests.test_reticle_actions import R
from app.testing.mes import API

KEY = "Idempotency-Key"


def _state(st: str, **extra: Any) -> Callable[[R], None]:
    def prep(r: R) -> None:
        sets = ", ".join(["status_code = :s", *(f"{k} = :{k}" for k in extra)])
        with admin_engine.begin() as c:
            c.execute(
                text(f"UPDATE mes_reticle SET {sets} WHERE id = :r"),
                {"r": r.id, "s": st, **extra},
            )

    return prep


def _mounted(r: R) -> None:
    r.mount()


def _held(r: R) -> None:
    r.act("hold", {"reason": "h"})


# 路径 → (准备, 请求体 A, 请求体 B（同 key 换体）, 成功状态码)
CASES: dict[str, tuple[Callable[[R], None] | None, Any, Any, int]] = {
    "hold": (None, {"reason": "a"}, {"reason": "b"}, 200),
    "release": (_held, None, {"comment": "b"}, 200),
    "restore": (_state("pending_maintenance"), {"reason": "a"}, {"reason": "b"}, 200),
    "life-reset": (
        _state("pending_maintenance"),
        {"reason": "a"},
        {"reason": "b"},
        200,
    ),
    "scrap": (None, {"reason": "a"}, {"reason": "b"}, 200),
    "mount": (None, "EQ", "EQ+c", 200),
    "unmount": (_mounted, None, {"comment": "b"}, 200),
    "usage": (None, {"delta": "1"}, {"delta": "2"}, 200),
    "incident": (None, {"kind": "other"}, {"kind": "drop"}, 201),
    "inspection": (
        _state("inspecting"),
        {"kind": "cd", "result": "pass"},
        {"kind": "cd", "result": "fail"},
        200,
    ),
    "clean-start": (None, None, {"comment": "b"}, 200),
    "clean-complete": (_state("dirty"), None, {"comment": "b"}, 200),
    "repair-complete": (
        _state("pending_maintenance"),
        None,
        {"comment": "b"},
        200,
    ),
    "inspect-start": (None, None, {"comment": "b"}, 200),
}
PATHS = list(CASES)


def _body(r: R, b: Any) -> Any:
    if b == "EQ":
        return {"equipment_id": r.eq["id"]}
    if b == "EQ+c":
        return {"equipment_id": r.eq["id"], "comment": "b"}
    return b


def _post(r: R, path: str, body: Any, hdr: dict[str, str], rid: Any = None) -> Any:
    return r.c.post(
        f"{API}/reticle/{rid or r.id}/{path}", headers={**r.m.h, **hdr}, json=body
    )


def test_fourteen_paths_listed() -> None:
    routes = {
        p.path
        for p in rt_router.router.routes
        if "POST" in getattr(p, "methods", set())
    }
    assert routes == {f"/mes/reticle/{{rid}}/{p}" for p in PATHS}
    assert len(PATHS) == 14


@pytest.mark.parametrize("path", PATHS)
def test_missing_key_order(client: TestClient, db: Session, path: str) -> None:
    """D81：403 → 缺 key 422 → body 422 → 404 → 409；不存在 / 状态不合法也先报缺 key。"""
    r = R(client, db)
    for hdr in ({}, {KEY: "   "}):
        res = _post(r, path, _body(r, CASES[path][1]), hdr)
        assert res.status_code == 422, res.text
        (d,) = res.json()["detail"]
        assert (d["type"], d["loc"]) == ("missing", ["header", KEY])
    # 不存在的光罩、坏请求体，缺 key 仍先 422 missing
    res = _post(r, path, {"bogus": 1}, {}, rid=uuid.uuid4())
    assert res.status_code == 422 and res.json()["detail"][0]["loc"] == [
        "header",
        KEY,
    ]
    # 有 key：body 422 先于 404
    res = _post(r, path, {"bogus": 1}, {KEY: "x1"}, rid=uuid.uuid4())
    assert res.status_code == 422 and res.json()["detail"][0]["loc"][0] == "body"
    # body 合法 → 404
    res = _post(r, path, _body(r, CASES[path][1]), {KEY: "x2"}, rid=uuid.uuid4())
    assert res.status_code == 404, res.text
    # 无权限：403 先于缺 key
    hm = _member(client, db, r.m)
    res = r.c.post(f"{API}/reticle/{r.id}/{path}", headers=hm, json={"bogus": 1})
    assert res.status_code == 403 and "loc" not in res.text


def test_missing_key_beats_409(client: TestClient, db: Session) -> None:
    """available 上调 clean-complete：缺 key → 422 missing，不是 409。"""
    r = R(client, db)
    res = _post(r, "clean-complete", None, {})
    assert res.status_code == 422 and res.json()["detail"][0]["type"] == "missing"
    res = _post(r, "clean-complete", None, {KEY: "c1"})
    assert (
        res.status_code == 409 and res.json()["detail"]["code"] == "invalid_transition"
    )


@pytest.mark.parametrize("path", PATHS)
def test_replay_and_reused(client: TestClient, db: Session, path: str) -> None:
    prep, a, b, ok = CASES[path]
    r = R(client, db)
    if prep:
        prep(r)
    k = {KEY: f"k-{path}"}
    first = _post(r, path, _body(r, a), k)
    assert first.status_code == ok, first.text
    # 重放：原状态码、原响应（状态已变，也不报 409）
    again = _post(r, path, _body(r, a), k)
    assert again.status_code == ok and again.json() == first.json()
    assert again.headers.get("Idempotent-Replayed") == "true"
    # 同 key 换体：422 idempotency_key_reused（D57 对象格式）
    d = _post(r, path, _body(r, b), k)
    assert d.status_code == 422, d.text
    assert d.json()["detail"]["code"] == "idempotency_key_reused"
    assert d.json()["detail"]["message"]


def _mount_rows(r: R) -> list[tuple[Any, ...]]:
    return [
        tuple(x)
        for x in r.sql(
            "SELECT event_type, source, external_event_id, mount_log_id, "
            "unmounted_at IS NOT NULL FROM mes_reticle_mount_log "
            "WHERE reticle_id = :r ORDER BY event_type"
        )
    ]


def _payload(r: R, ev: str) -> dict[str, Any]:
    (row,) = r.sql(
        "SELECT changes FROM mes_audit_log WHERE record_id = CAST(:r AS text) "
        "AND action = :a ORDER BY created_at DESC LIMIT 1",
        a=ev,
    )
    ch = row[0]
    return dict(ch["payload"][1])


def test_unmount_event_row_and_payloads(client: TestClient, db: Session) -> None:
    r = R(client, db)
    m = r.mount()["data"]
    k = {KEY: "u1"}
    u = _post(r, "unmount", None, k)
    assert u.status_code == 200, u.text
    assert "duplicate" not in u.json()
    assert _post(r, "unmount", None, k).json() == u.json()  # 重放不产生第二行
    rows = _mount_rows(r)
    assert rows == [
        ("mount", "manual", None, None, True),
        ("unmount", "manual", None, uuid.UUID(m["id"]), True),
    ]
    ev = u.json()["unmount_event"]
    assert ev["event_type"] == "unmount" and ev["mount_log_id"] == m["id"]
    for e in ("reticle.mounted", "reticle.unmounted"):
        p = _payload(r, e)
        assert p["source"] == "manual" and p["external_event_id"] is None, (e, p)
    r.at_limit()
    p = _payload(r, "reticle.life_reached")
    assert p["source"] == "manual" and p["external_event_id"] is None
    h = client.get(f"{API}/reticle/{r.id}/history", headers=r.m.h).json()["data"]
    assert {"mount", "unmount"} <= {x["type"] for x in h}


def test_eap_unmount_dedupe(client: TestClient, db: Session) -> None:
    """EAP 同事件号重复下机：返回首次记录 duplicate=true，不写第二行、不再发事件。"""
    r = R(client, db)
    r.mount()
    tid = uuid.UUID(str(r.m.tid))
    rid = uuid.UUID(r.id)
    with _session(str(tid)) as s:
        a = rt_svc.unmount(s, tid, rid, {}, None, source="eap", external_event_id="E1")
        s.commit()
    with _session(str(tid)) as s:
        b = rt_svc.unmount(s, tid, rid, {}, None, source="eap", external_event_id="E1")
        s.commit()
    assert a["duplicate"] is False and b["duplicate"] is True
    assert b["unmount_event"]["id"] == a["unmount_event"]["id"]
    assert [x[:3] for x in _mount_rows(r)] == [
        ("mount", "manual", None),
        ("unmount", "eap", "E1"),
    ]
    assert r.events().count("reticle.unmounted") == 1
    p = _payload(r, "reticle.unmounted")
    assert (p["source"], p["external_event_id"]) == ("eap", "E1")


def test_source_check_constraint(client: TestClient, db: Session) -> None:
    r = R(client, db)
    r.mount()
    with pytest.raises(Exception, match="ck_mes_reticle_mount_log_source"):
        with admin_engine.begin() as c:
            c.execute(
                text(
                    "UPDATE mes_reticle_mount_log SET source = 'bogus' "
                    "WHERE reticle_id = :r"
                ),
                {"r": r.id},
            )


T0 = datetime.now(UTC).replace(microsecond=0)


def _clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rt_router, "now", lambda: T0)
    monkeypatch.setattr(rt_svc, "now", lambda: T0)


def _z(d: datetime) -> str:
    return d.isoformat().replace("+00:00", "Z")


@pytest.mark.parametrize(
    ("delta", "ok"),
    [
        (timedelta(minutes=4, seconds=59), True),
        (timedelta(minutes=5), True),
        (timedelta(minutes=5, seconds=1), False),
    ],
    ids=["4m59", "5m00", "5m01"],
)
def test_future_time_strict(
    client: TestClient,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
    delta: timedelta,
    ok: bool,
) -> None:
    _clock(monkeypatch)
    r = R(client, db)
    at = _z(T0 + delta)
    res = _post(r, "incident", {"kind": "other", "occurred_at": at}, {KEY: "f1"})
    res2 = _post(
        r, "mount", {"equipment_id": r.eq["id"], "mounted_at": at}, {KEY: "f2"}
    )
    if ok:
        assert res.status_code == 201, res.text
        assert res2.status_code in (200, 409), res2.text  # incident 后已 on_hold
        assert res2.status_code == 409 and res2.json()["detail"]["code"] in (
            "reticle_unavailable",
            "time_out_of_order",
        )
        return
    for x, f in ((res, "occurred_at"), (res2, "mounted_at")):
        assert x.status_code == 422, x.text
        (d,) = x.json()["detail"]
        assert d["type"] == "value_error" and d["ctx"] == {"reason": "future_time"}
        assert d["loc"] == ["body", f]


def test_future_time_mount_ok_at_5m(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clock(monkeypatch)
    r = R(client, db)
    at = _z(T0 + timedelta(minutes=5))
    res = _post(r, "mount", {"equipment_id": r.eq["id"], "mounted_at": at}, {KEY: "m"})
    assert res.status_code == 200, res.text


def test_time_out_of_order(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clock(monkeypatch)
    r = R(client, db)
    m_at = T0 - timedelta(hours=1)
    res = _post(
        r, "mount", {"equipment_id": r.eq["id"], "mounted_at": _z(m_at)}, {KEY: "m"}
    )
    assert res.status_code == 200, res.text
    # 下机早于对应上机 → 409（不是 422）
    res = _post(
        r, "unmount", {"unmounted_at": _z(m_at - timedelta(seconds=1))}, {KEY: "u0"}
    )
    assert res.status_code == 409, res.text
    d = res.json()["detail"]
    assert d["code"] == "time_out_of_order" and d["field"] == "unmounted_at"
    # 相等合法
    res = _post(r, "unmount", {"unmounted_at": _z(m_at)}, {KEY: "u1"})
    assert res.status_code == 200, res.text
    # 上机 / 事故早于最近一次下机 → 409；相等合法
    res = _post(
        r,
        "mount",
        {"equipment_id": r.eq["id"], "mounted_at": _z(m_at - timedelta(minutes=1))},
        {KEY: "m2"},
    )
    assert (
        res.status_code == 409 and res.json()["detail"]["code"] == "time_out_of_order"
    )
    res = _post(
        r,
        "incident",
        {"kind": "other", "occurred_at": _z(m_at - timedelta(minutes=1))},
        {KEY: "i1"},
    )
    assert (
        res.status_code == 409 and res.json()["detail"]["code"] == "time_out_of_order"
    )
    res = _post(r, "incident", {"kind": "other", "occurred_at": _z(m_at)}, {KEY: "i2"})
    assert res.status_code == 201, res.text
    # 不存在的光罩：404 先于 409
    res = _post(
        r,
        "incident",
        {"kind": "other", "occurred_at": _z(m_at - timedelta(days=1))},
        {KEY: "i3"},
        rid=uuid.uuid4(),
    )
    assert res.status_code == 404


@pytest.mark.parametrize(
    ("path", "field"),
    [("mount", "mounted_at"), ("unmount", "unmounted_at"), ("incident", "occurred_at")],
)
def test_time_checks_before_404(
    client: TestClient,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    field: str,
) -> None:
    """D81：补录时间的 422（timezone_required / future_time）先于光罩 404。"""
    _clock(monkeypatch)
    r = R(client, db)
    base: dict[str, Any] = {
        "mount": {"equipment_id": r.eq["id"]},
        "unmount": {},
        "incident": {"kind": "other"},
    }[path]
    ghost = uuid.uuid4()
    for v, typ, ctx in (
        ("2026-03-10T08:00:00", "timezone_required", None),
        (_z(T0 + timedelta(minutes=5, seconds=1)), "value_error", "future_time"),
    ):
        res = _post(r, path, {**base, field: v}, {KEY: uuid.uuid4().hex}, rid=ghost)
        assert res.status_code == 422, res.text
        (d,) = res.json()["detail"]
        assert d["type"] == typ and d["loc"] == ["body", field]
        if ctx:
            assert d["ctx"] == {"reason": ctx}


def test_write_permission_403(client: TestClient, db: Session) -> None:
    """缺 mes.reticle:write：403（先于缺 key / body / 404）。"""
    r = R(client, db)
    hm = _member(client, db, r.m)
    for path in ("mount", "unmount", "incident"):
        res = r.c.post(
            f"{API}/reticle/{r.id}/{path}",
            headers={**hm, KEY: "p"},
            json=_body(r, CASES[path][1]),
        )
        assert res.status_code == 403, res.text


def _count(r: R, table: str) -> int:
    return int(r.sql(f"SELECT count(*) FROM {table} WHERE reticle_id = :r")[0][0])


def test_latest_event_sources(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """最近事件 = 状态履历 / 历次下机；检查记录不算；usage 只对 incident 算（D82 补充）。"""
    _clock(monkeypatch)
    r = R(client, db)
    r.act("usage", {"delta": "1"})  # usage occurred_at = T0
    before = _z(T0 - timedelta(minutes=10))
    # mount 不看 usage：早于 usage 也放行
    res = _post(
        r, "mount", {"equipment_id": r.eq["id"], "mounted_at": before}, {KEY: "a"}
    )
    assert res.status_code == 200, res.text
    res = _post(r, "unmount", {"unmounted_at": before}, {KEY: "b"})
    assert res.status_code == 200, res.text
    # incident 看 usage：早于最近一次 usage → 409；与 usage 相同时刻合法
    res = _post(r, "incident", {"kind": "other", "occurred_at": before}, {KEY: "c"})
    assert (
        res.status_code == 409 and res.json()["detail"]["code"] == "time_out_of_order"
    )
    res = _post(r, "incident", {"kind": "other", "occurred_at": _z(T0)}, {KEY: "d"})
    assert res.status_code == 201, res.text
    # 检查记录不算：补一条更晚的检查，不影响事故时间判断（状态履历仍是 T0）
    r2 = R(client, db)
    with admin_engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO mes_reticle_inspection (id, tenant_id, reticle_id, kind, "
                "result, inspected_at) VALUES (gen_random_uuid(), :t, :r, 'cd', 'pass', :at)"
            ),
            {"t": r2.m.tid, "r": r2.id, "at": T0 + timedelta(minutes=1)},
        )
    res = _post(r2, "incident", {"kind": "other", "occurred_at": _z(T0)}, {KEY: "e"})
    assert res.status_code == 201, res.text


def test_incident_unmount_uses_occurred_at(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clock(monkeypatch)
    for occurred in (T0 - timedelta(minutes=30), None):
        r = R(client, db)
        m_at = T0 - timedelta(hours=1)
        _post(
            r,
            "mount",
            {"equipment_id": r.eq["id"], "mounted_at": _z(m_at)},
            {KEY: "m"},
        )
        body: dict[str, Any] = {"kind": "drop"}
        if occurred:
            body["occurred_at"] = _z(occurred)
        res = _post(r, "incident", body, {KEY: "i"})
        assert res.status_code == 201, res.text
        want = occurred or T0
        rows = r.sql(
            "SELECT event_type, unmounted_at FROM mes_reticle_mount_log "
            "WHERE reticle_id = :r ORDER BY event_type"
        )
        assert [(x[0], x[1]) for x in rows] == [("mount", want), ("unmount", want)]
        (st,) = r.sql(
            "SELECT at FROM mes_reticle_status_log WHERE reticle_id = :r "
            "AND action = 'incident'"
        )
        assert st[0] == want


def test_incident_before_mounted_at_rolls_back(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """occurred_at 早于本次上机：整体 409，不写事故、不 Hold、不下机。"""
    _clock(monkeypatch)
    r = R(client, db)
    m_at = T0 - timedelta(hours=1)
    _post(r, "mount", {"equipment_id": r.eq["id"], "mounted_at": _z(m_at)}, {KEY: "m"})
    n_log = _count(r, "mes_reticle_status_log")
    res = _post(
        r,
        "incident",
        {"kind": "drop", "occurred_at": _z(m_at - timedelta(seconds=1))},
        {KEY: "i"},
    )
    assert (
        res.status_code == 409 and res.json()["detail"]["code"] == "time_out_of_order"
    )
    assert r.st() == ("in_use", None)
    assert _count(r, "mes_reticle_incident") == 0
    assert _count(r, "mes_reticle_status_log") == n_log
    assert [
        x[0]
        for x in r.sql(
            "SELECT event_type FROM mes_reticle_mount_log WHERE reticle_id = :r"
        )
    ] == ["mount"]
    assert "reticle.unmounted" not in r.events()
