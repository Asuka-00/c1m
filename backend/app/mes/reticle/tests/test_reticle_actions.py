"""P3-B4 光罩状态机与动作接口（v0.8.2 §3 / §3.1 / §3.2 / §4 / §5 / §6，D66–D69）。"""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, text

from app.core.db import admin_engine
from app.mes.product.tests.test_bom import _member
from app.testing.mes import API, Mes

ROOT = API[:-4]


def _k() -> dict[str, str]:
    return {"Idempotency-Key": uuid.uuid4().hex}


class R:
    def __init__(self, client: TestClient, db: Session, **rt: Any) -> None:
        self.m = Mes(client, db)
        self.c = client
        self.rt = self.m.post("reticle", {"code": "RT1", "name": "rt", **rt})
        self.id = self.rt["id"]
        self.eq = self.m.post("equipment", {"code": "SCN1", "name": "scanner"})
        self.eq2 = self.m.post("equipment", {"code": "SCN2", "name": "scanner2"})

    def act(
        self, a: str, body: Any = None, status: int = 200, h: Any = None, **hdr: str
    ) -> Any:
        # D80：写接口必填 Idempotency-Key；未显式给出时每次用新 key
        hdr = {"Idempotency-Key": uuid.uuid4().hex, **hdr}
        r = self.c.post(
            f"{API}/reticle/{self.id}/{a}",
            headers={**(h or self.m.h), **hdr},
            json=body,
        )
        assert r.status_code == status, r.text
        return r.json()

    def get(self) -> dict[str, Any]:
        r = self.c.get(f"{API}/reticle/{self.id}", headers=self.m.h)
        assert r.status_code == 200, r.text
        return r.json()  # type: ignore[no-any-return]

    def st(self) -> tuple[str, str | None]:
        g = self.get()
        return g["status_code"], g["hold_reason"]

    def mount(self, eq: dict[str, Any] | None = None, status: int = 200) -> Any:
        return self.act("mount", {"equipment_id": (eq or self.eq)["id"]}, status)

    def sql(self, q: str, **p: Any) -> list[Any]:
        with admin_engine.begin() as c:
            return list(c.execute(text(q), {"r": self.id, **p}))

    def events(self) -> list[str]:
        return [
            r[0]
            for r in self.sql(
                "SELECT action FROM mes_audit_log WHERE record_id = CAST(:r AS text) AND action LIKE 'reticle.%' ORDER BY created_at, id"
            )
        ]

    def logs(self) -> list[tuple[Any, ...]]:
        return [
            tuple(r)
            for r in self.sql(
                "SELECT from_status, to_status, action, hold_reason_to, reason FROM mes_reticle_status_log WHERE reticle_id = :r ORDER BY at, created_at"
            )
        ]

    def at_limit(self) -> None:
        self.m.patch("reticle", self.id, {"max_shots": "100"})
        self.act("usage", {"delta": "100"})


def test_mount_unmount_and_duplicate(client: TestClient, db: Session) -> None:
    r = R(client, db)
    out = r.mount()["data"]
    assert out["mounted_at"].endswith("Z") and out["shots_at_mount"] == "0"
    g = r.get()
    assert g["status_code"] == "in_use" and g["equipment_id"] == r.eq["id"]
    assert g["mount_count"] == 1 and g["first_used_at"]
    d = r.mount(r.eq2, 409)["detail"]
    assert d["code"] == "already_mounted" and d["equipment_id"] == r.eq["id"]
    r.act("unmount")
    assert r.st() == ("available", None) and r.get()["equipment_id"] is None
    assert r.act("unmount", status=409)["detail"]["code"] == "invalid_transition"
    assert r.events() == ["reticle.mounted", "reticle.unmounted"]
    r.act("hold", {"reason": "x"})
    assert r.mount(status=409)["detail"]["code"] == "reticle_unavailable"


def test_manual_hold_release_and_no_stacking(client: TestClient, db: Session) -> None:
    r = R(client, db)
    r.mount()
    r.act("hold", {"reason": "suspect"})
    g = r.get()
    assert (g["status_code"], g["hold_reason"], g["status_before_hold"]) == (
        "on_hold",
        "manual",
        "available",
    )
    assert g["equipment_id"] is None  # D68 Q18：在用 Hold 同事务卸载
    d = r.act("hold", {"reason": "again"}, 409)["detail"]
    assert d["code"] == "invalid_transition" and d["hold_reason"] == "manual"
    r.act("release")
    assert r.st() == ("available", None) and r.get()["status_before_hold"] is None
    assert r.events() == [
        "reticle.mounted",
        "reticle.unmounted",
        "reticle.held",
        "reticle.released",
    ]
    assert ("in_use", "on_hold", "hold", "manual", "suspect") in r.logs()
    r.act("release", status=409)


def test_hold_mounted_pending_maintenance_records_current(
    client: TestClient, db: Session
) -> None:
    r = R(client, db)
    r.mount()
    r.at_limit()
    assert r.st()[0] == "pending_maintenance" and r.get()["equipment_id"] == r.eq["id"]
    r.act("hold", {"reason": "x"})
    g = r.get()
    assert (
        g["status_before_hold"] == "pending_maintenance" and g["equipment_id"] is None
    )
    r.act("release", {"comment": "ok"})
    assert r.st() == ("pending_maintenance", None)


def test_incident_escalation_and_release_targets(
    client: TestClient, db: Session
) -> None:
    r = R(client, db)
    r.mount()
    r.act("hold", {"reason": "m"})
    inc = r.act("incident", {"kind": "collision"}, 201)
    assert inc["reticle"]["hold_reason"] == "incident"
    assert inc["reticle"]["inspection_required"] is True
    assert inc["reticle"]["status_before_hold"] == "available"
    r.act("release")
    assert r.st() == ("inspecting", None)
    r.act("inspection", {"kind": "particle", "result": "fail"})
    assert r.st() == ("on_hold", "inspection_failed")
    # 不更严：碰撞不降级
    r.act("incident", {"kind": "drop"}, 201)
    assert r.st() == ("on_hold", "inspection_failed")
    r.act("release")
    assert r.st() == ("pending_maintenance", None)
    r.act("repair-complete")
    assert r.st() == ("inspecting", None)
    r.act("inspection", {"kind": "particle", "result": "pass"})
    g = r.get()
    assert g["status_code"] == "available" and g["inspection_required"] is False
    assert g["last_inspected_at"].endswith("Z")
    ev = r.events()
    assert ev.count("reticle.incident_recorded") == 2
    assert "reticle.inspection_failed" in ev and "reticle.inspected" in ev


def test_incident_from_inspecting_returns_there_and_scrapped_409(
    client: TestClient, db: Session
) -> None:
    r = R(client, db)
    r.act("inspect-start")
    r.act("incident", {"kind": "collision"}, 201)
    assert r.get()["status_before_hold"] == "inspecting"
    r.act("release")
    assert r.st() == ("inspecting", None)
    r.act("scrap", {"reason": "broken"})
    d = r.act("incident", {"kind": "collision"}, 409)["detail"]
    assert d["code"] == "invalid_transition" and d["status_code"] == "scrapped"
    assert ("inspecting", "scrapped", "scrap", None, "broken") in r.logs()


def test_flow_actions_and_still_mounted(client: TestClient, db: Session) -> None:
    r = R(client, db)
    r.act("clean-start", {})
    assert r.st()[0] == "dirty"
    assert r.act("inspect-start", status=409)["detail"]["code"] == "invalid_transition"
    r.act("clean-complete", {"comment": "c"})
    g = r.get()
    assert g["status_code"] == "inspecting" and g["inspection_required"] is True
    r.act("inspection", {"kind": "haze", "result": "pass"})
    r.mount()
    for a, body in (
        ("clean-start", None),
        ("inspect-start", None),
        ("repair-complete", None),
        ("restore", {"reason": "r"}),
        ("life-reset", {"reason": "r"}),
    ):
        # D71-3：当前状态（in_use）本身不允许 → 先报 invalid_transition
        assert r.act(a, body, 409)["detail"]["code"] == "invalid_transition", a
    changed = list(
        r.sql(
            "SELECT changes FROM mes_audit_log WHERE record_id = CAST(:r AS text) AND action = 'reticle.status_changed' ORDER BY created_at"
        )
    )
    p = changed[0][0]["payload"][1]
    assert (p["from"], p["to"], p["action"]) == ("available", "dirty", "clean-start")


def test_restore_life_reset_at_limit(client: TestClient, db: Session) -> None:
    r = R(client, db)
    r.mount()
    r.at_limit()
    assert "reticle.life_reached" in r.events()
    assert r.act("restore", {"reason": "r"}, 409)["detail"]["code"] == "still_mounted"
    # D71-3：状态允许（pending_maintenance）但仍挂载 → still_mounted
    for a, body in (("life-reset", {"reason": "r"}), ("repair-complete", None)):
        assert r.act(a, body, 409)["detail"]["code"] == "still_mounted", a
    assert r.act("clean-start", None, 409)["detail"]["code"] == "invalid_transition"
    r.act("unmount")
    assert r.st()[0] == "pending_maintenance"  # 非 in_use 卸载不改状态
    assert r.events()[-1] == "reticle.unmounted"
    d = r.act("restore", {"reason": "r"}, 409)["detail"]
    assert d["code"] == "life_limit_reached" and d["shot_count"] == "100"
    out = r.act("life-reset", {"reason": "refurbished"})
    assert out["usage"]["kind"] == "reset" and out["usage"]["comment"] == "refurbished"
    assert out["usage"]["reason_id"] is None and out["usage"]["count_after"] == "0"
    g = out["data"]
    assert (g["status_code"], g["shot_count"], g["life_reset_count"]) == (
        "available",
        "0",
        1,
    )
    assert g["inspection_required"] is True
    # adjust 回到上限以下不自动恢复；restore 置待检
    r.act("usage", {"delta": "100"})
    r.act("usage", {"delta": "-10", "reason_id": r.m.fx("reason")})
    assert r.st()[0] == "pending_maintenance"
    r.act("restore", {"reason": "checked"})
    assert r.st()[0] == "available"
    assert ("pending_maintenance", "available", "restore", None, "checked") in r.logs()


def test_scrap_mounted_only_scrapped_event(client: TestClient, db: Session) -> None:
    r = R(client, db)
    r.mount()
    r.act("usage", {"delta": "7.5"})
    r.act("scrap", {"reason": "crack"})
    g = r.get()
    assert g["status_code"] == "scrapped" and g["equipment_id"] is None
    ev = r.events()
    assert ev[-1] == "reticle.scrapped" and "reticle.unmounted" not in ev
    p = r.sql(
        "SELECT changes FROM mes_audit_log WHERE record_id = CAST(:r AS text) AND action = 'reticle.scrapped'"
    )[0][0]["payload"][1]
    assert p["equipment_id"] == r.eq["id"] and p["shots_at_unmount"] == "7.5"
    assert (
        r.act("scrap", {"reason": "x"}, 409)["detail"]["code"] == "invalid_transition"
    )
    assert r.act("hold", {"reason": "x"}, 409)["detail"]["code"] == "invalid_transition"


def test_usage_validation_and_idempotency(client: TestClient, db: Session) -> None:
    r = R(client, db)

    def err(body: Any) -> tuple[Any, str]:
        d = r.act("usage", body, 422)["detail"][0]
        return d["loc"], d["code"]

    assert err({"delta": "0"}) == (["body", "delta"], "value_error")
    assert err({"delta": "-1"}) == (["body", "reason_id"], "missing")
    assert err({"delta": "-1", "reason_id": r.m.fx("reason")}) == (
        ["body", "delta"],
        "value_error",
    )
    d = r.act("usage", {"delta": "1.1234567"}, 422)["detail"][0]
    assert d["loc"] == ["body", "delta"] and d["code"] == d["type"] == "value_error"
    assert d["ctx"] == {"max_places": 6}  # D71-5
    assert err({"delta": "1", "reason_id": r.id}) == (
        ["body", "reason_id"],
        "ref_not_found",
    )
    assert err({"delta": "1", "kind": "report"}) == (["body", "kind"], "unknown_field")
    assert err({"delta": "1", "source": "eap"}) == (["body", "source"], "unknown_field")
    assert err({"delta": "1", "note": "x" * 301}) == (
        ["body", "note"],
        "string_too_long",
    )
    a = r.act("usage", {"delta": "5", "note": "n"}, **{"Idempotency-Key": "k1"})
    assert a["data"]["kind"] == "report" and a["data"]["source"] == "manual"
    assert "duplicate" not in a
    b = r.act("usage", {"delta": "5", "note": "n"}, **{"Idempotency-Key": "k1"})
    assert b == a and float(r.get()["shot_count"]) == 5
    d = r.act("usage", {"delta": "6"}, 422, **{"Idempotency-Key": "k1"})["detail"]
    assert d["code"] == "idempotency_key_reused"


def test_incident_idempotent_replay_and_strict(client: TestClient, db: Session) -> None:
    r = R(client, db)
    body = {"kind": "collision", "description": "hit"}
    a = r.act("incident", body, 201, **{"Idempotency-Key": "i1"})
    b = r.act("incident", body, 201, **{"Idempotency-Key": "i1"})
    assert a == b and "duplicate" not in a
    assert (
        r.sql("SELECT count(*) FROM mes_reticle_incident WHERE reticle_id = :r")[0][0]
        == 1
    )
    assert r.events().count("reticle.incident_recorded") == 1
    d = r.act("incident", {**body, "source": "eap"}, 422)["detail"][0]
    assert d["code"] == "unknown_field" and d["loc"] == ["body", "source"]


def test_strict_bodies_and_reason_limits(client: TestClient, db: Session) -> None:
    r = R(client, db)
    d = r.act("hold", {}, 422)["detail"][0]
    assert d["loc"] == ["body", "reason"] and d["code"] == "missing"
    d = r.act("hold", {"reason": "x" * 301}, 422)["detail"][0]
    assert d["code"] == "string_too_long"
    d = r.act("hold", {"reason": "x", "hold_reason": "incident"}, 422)["detail"][0]
    assert d["code"] == "unknown_field"
    d = r.act("life-reset", {"reason": "x", "reason_id": r.m.fx("reason")}, 422)[
        "detail"
    ][0]
    assert d["code"] == "unknown_field"
    d = r.act("clean-start", {"comment": "x", "to": "dirty"}, 422)["detail"][0]
    assert d["code"] == "unknown_field"


def test_permissions_write_vs_override(client: TestClient, db: Session) -> None:
    r = R(client, db)
    m = r.m
    for name, perms in (
        ("rt_writer", ["mes.reticle:read", "mes.reticle:write"]),
        ("rt_override", ["mes.reticle:override"]),
    ):
        res = client.post(
            f"{ROOT}/tenants/{m.tid}/roles",
            headers=m.h,
            json={"name": name, "title": name, "permission_codes": perms},
        )
        assert res.status_code == 200, res.text

    def member(role: str) -> dict[str, str]:
        h = _member(client, db, m)
        members = client.get(f"{ROOT}/tenants/{m.tid}/members", headers=m.h).json()
        (uid,) = [x["user_id"] for x in members["data"] if x["roles"] == ["member"]]
        res = client.put(
            f"{ROOT}/tenants/{m.tid}/members/{uid}/roles",
            headers=m.h,
            json={"roles": [role]},
        )
        assert res.status_code == 200, res.text
        return h

    hw, ho = member("rt_writer"), member("rt_override")
    # 403 先于请求体校验（D34）
    for a in ("scrap", "life-reset", "restore"):
        r.act(a, {"bad": 1}, 403, h=hw)
    r.act("clean-start", None, 200, h=hw)
    r.act("hold", {"reason": "x"}, 403, h=ho)
    r.act("scrap", {"reason": "done"}, 200, h=ho)


def test_history_merged_newest_first_and_cross_tenant(
    client: TestClient, db: Session
) -> None:
    r = R(client, db)
    r.mount()
    r.act("usage", {"delta": "3"})
    r.act("incident", {"kind": "collision"}, 201)
    h = client.get(f"{API}/reticle/{r.id}/history", headers=r.m.h).json()
    types = {x["type"] for x in h["data"]}
    assert {"mount", "usage", "incident", "status"} <= types
    ats = [x["at"] for x in h["data"]]
    assert ats == sorted(ats, reverse=True) and all(a.endswith("Z") for a in ats)
    other = Mes(client, db)
    assert (
        client.get(f"{API}/reticle/{r.id}/history", headers=other.h).status_code == 404
    )
    res = client.post(
        f"{API}/reticle/{r.id}/hold", headers={**other.h, **_k()}, json={"reason": "x"}
    )
    assert res.status_code == 404


def test_track_in_mounted_at_life_limit_blocked(
    client: TestClient, db: Session
) -> None:
    """D69 补充：到上限仍挂着（pending_maintenance）进站按 life_reached 拦，不可放行。"""
    from app.mes.execution.tests.test_exec import Line, _msgs

    f = Line(client, db)
    rt = f.m.post("reticle", {"code": "RTL", "name": "r", "max_shots": "10"})
    url = f"{API}/reticle/{rt['id']}"
    res = client.post(
        f"{url}/mount", headers={**f.m.h, **_k()}, json={"equipment_id": f.eq["id"]}
    )
    assert res.status_code == 200, res.text
    res = client.post(f"{url}/usage", headers={**f.m.h, **_k()}, json={"delta": "10"})
    assert res.json()["reticle"]["status_code"] == "pending_maintenance"
    f.sql(
        "INSERT INTO mes_step_resource (id, tenant_id, route_step_id, resource_kind, reticle_id) VALUES (gen_random_uuid(), :t, :s, 'reticle', :r)",
        t=f.m.tid,
        s=f.steps[10]["id"],
        r=rt["id"],
    )
    f.bind("track_in", ("reticle_available", "block", {}))
    (a,) = f.start(1)
    f.stage(a, "move_in", equipment_id=f.eq["id"])
    r = f.stage(
        a,
        "track_in",
        409,
        equipment_id=f.eq["id"],
        reticle_id=rt["id"],
        override=True,
        override_reason="try",
    )
    assert "reached its life limit" in _msgs(r)
    assert r["detail"]["overridable"] is False


def test_inspection_idempotent_and_schema_d71(client: TestClient, db: Session) -> None:
    """D71 补充：检查记录 D57 幂等；无 source/external_event_id；disposition 非空默认 none。"""
    r = R(client, db)
    r.act("inspect-start")
    body = {"kind": "haze", "result": "pass"}
    a = r.act("inspection", body, **{"Idempotency-Key": "q1"})
    b = r.act("inspection", body, **{"Idempotency-Key": "q1"})
    assert a == b and "duplicate" not in a
    assert r.st()[0] == "available"
    rows = r.sql("SELECT disposition FROM mes_reticle_inspection WHERE reticle_id = :r")
    assert [x[0] for x in rows] == ["none"]
    d = r.act("inspection", {**body, "source": "eap"}, 422)["detail"][0]
    assert d["code"] == "unknown_field"
    cols = {
        x[0]: (x[1], x[2])
        for x in r.sql(
            "SELECT column_name, is_nullable, column_default FROM information_schema.columns"
            " WHERE table_name = 'mes_reticle_inspection'"
        )
    }
    assert "source" not in cols and "external_event_id" not in cols
    assert cols["disposition"][0] == "NO" and "none" in (cols["disposition"][1] or "")
    assert not r.sql(
        "SELECT 1 FROM pg_indexes WHERE indexname = 'uq_mes_reticle_inspection_event'"
    )


def test_scrapped_usage_and_inspection_409_no_life_reached(
    client: TestClient, db: Session
) -> None:
    """D72：scrapped 后 usage / 检查录入一律 409 invalid_transition，不发 life_reached。"""
    r = R(client, db, max_shots="10")
    r.act("scrap", {"reason": "crack"})
    before = r.events()
    d = r.act("usage", {"delta": "100"}, 409)["detail"]
    assert d["code"] == "invalid_transition" and d["status_code"] == "scrapped"
    for res in ("pass", "fail"):
        d = r.act("inspection", {"kind": "haze", "result": res}, 409)["detail"]
        assert d["code"] == "invalid_transition" and d["status_code"] == "scrapped"
    assert r.events() == before and "reticle.life_reached" not in before
    assert r.get()["shot_count"] == "0"
    assert not r.sql("SELECT 1 FROM mes_reticle_usage WHERE reticle_id = :r")
    assert not r.sql("SELECT 1 FROM mes_reticle_inspection WHERE reticle_id = :r")


def test_generic_crud_numeric_strings_and_value_error(
    client: TestClient, db: Session
) -> None:
    """D72 / D50：通用 CRUD 定点数输出字符串；超 6 位小数 422 value_error + ctx。"""
    r = R(client, db, max_shots="1000.5")
    g = r.get()
    assert g["max_shots"] == "1000.5" and g["shot_count"] == "0"
    r.act("usage", {"delta": "1.25"})
    assert r.get()["shot_count"] == "1.25"
    lst = client.get(f"{API}/reticle", headers=r.m.h).json()["data"]
    assert [x["shot_count"] for x in lst] == ["1.25"]
    resp = client.patch(
        f"{API}/reticle/{r.id}", headers=r.m.h, json={"max_shots": "1.1234567"}
    )
    assert resp.status_code == 422, resp.text
    d = resp.json()["detail"][0]
    assert d["type"] == d["code"] == "value_error" and d["loc"] == ["body", "max_shots"]
    assert d["ctx"] == {"max_places": 6}


def test_delete_reticle_with_history_409_referenced(
    client: TestClient, db: Session
) -> None:
    """D72：5 张履历表 ON DELETE RESTRICT；有履历删光罩 409 referenced + tables[]。"""
    r = R(client, db)
    r.act("usage", {"delta": "5"})
    r.act("hold", {"reason": "x"})
    resp = client.delete(f"{API}/reticle/{r.id}", headers=r.m.h)
    assert resp.status_code == 409, resp.text
    d = resp.json()["detail"]
    assert d["code"] == "referenced"
    assert set(d["tables"]) == {"mes_reticle_usage", "mes_reticle_status_log"}
    assert r.get()["id"] == r.id
    rules = {
        x[0]: x[1]
        for x in r.sql(
            "SELECT tc.table_name, rc.delete_rule FROM information_schema.referential_constraints rc"
            " JOIN information_schema.table_constraints tc ON tc.constraint_name = rc.constraint_name"
            " JOIN information_schema.constraint_column_usage cu ON cu.constraint_name = rc.constraint_name"
            " WHERE cu.table_name = 'mes_reticle' AND tc.table_name LIKE 'mes_reticle_%'"
        )
    }
    for t in ("incident", "mount_log", "usage", "inspection", "status_log"):
        assert rules[f"mes_reticle_{t}"] == "RESTRICT", rules
    assert rules["mes_reticle_applicability"] == "CASCADE"
    # 外键兜底：绕过接口直接删也被数据库拦下
    with pytest.raises(IntegrityError):
        r.sql("DELETE FROM mes_reticle WHERE id = :r")
    # 没有履历的光罩可以删
    fresh = r.m.post("reticle", {"code": "RT2", "name": "rt2"})
    assert client.delete(f"{API}/reticle/{fresh['id']}", headers=r.m.h).status_code in (
        200,
        204,
    )
