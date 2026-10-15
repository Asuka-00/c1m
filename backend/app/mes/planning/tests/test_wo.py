"""Work orders + lot start: release checks, default-route snapshot, over-start
limit, carriers / slots, undo, transitions, permissions, audit, RLS."""

import uuid
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlmodel import Session

from app.core.db import engine
from app.core.tenant import set_tenant
from app.platform.users import service as crud
from app.platform.users.schemas import UserCreate
from app.testing.mes import API, Mes
from app.testing.utils import (
    login_name,
    random_email,
    random_lower_string,
    username_for,
)


class Fab:
    """Active product with an active default route (2 steps) + WO code rule."""

    def __init__(self, client: TestClient, db: Session) -> None:
        m = self.m = Mes(client, db)
        m.post(
            "code_rule",
            {"code": "WO", "name": "wo", "target": "work_order", "pattern": "WO{SEQ}"},
        )
        site = m.post("site", {"code": "S1", "name": "site"})
        area = m.post("area", {"code": "A1", "name": "a", "site_id": site["id"]})
        self.site = site
        op1 = m.post("operation", {"code": "OP1", "name": "o1", "area_id": area["id"]})
        op2 = m.post("operation", {"code": "OP2", "name": "o2", "area_id": area["id"]})
        self.product = m.post("product", {"code": "P", "name": "p"})
        self.route = m.post("route", {"code": "R", "name": "r"})
        self.s1 = m.post(
            "route_step",
            {"route_id": self.route["id"], "seq": 10, "operation_id": op1["id"]},
        )
        m.post(
            "route_step",
            {"route_id": self.route["id"], "seq": 20, "operation_id": op2["id"]},
        )
        m.action("route", self.route["id"], "status", {"status": "active"})
        m.post(
            "product_route",
            {"product_id": self.product["id"], "route_id": self.route["id"]},
        )
        m.action("product", self.product["id"], "status", {"status": "active"})
        self.lt = m.fx("lot_type")

    def wo(self, **kw: Any) -> dict[str, Any]:
        return self.m.post(
            "work_order",
            {
                "product_id": self.product["id"],
                "lot_type_id": self.lt,
                "planned_qty": 50,
                **kw,
            },
        )

    def act(self, wo: dict[str, Any], action: str, status: int = 200) -> dict[str, Any]:
        r = self.m.c.post(
            f"{API}/work-order/{wo['id']}/transition",
            headers=self.m.h,
            json={"action": action},
        )
        assert r.status_code == status, r.text
        return r.json()  # type: ignore[no-any-return]

    def call(self, wo: dict[str, Any], what: str, body: Any, status: int = 200) -> Any:
        r = self.m.c.post(
            f"{API}/work-order/{wo['id']}/{what}", headers=self.m.h, json=body
        )
        assert r.status_code == status, r.text
        return r.json()


def _msgs(r: Any) -> str:
    return " ".join(d["msg"] for d in r["detail"])


def test_create_defaults_and_validation(client: TestClient, db: Session) -> None:
    f = Fab(client, db)
    w = f.wo()
    assert w["code"] == "WO0001" and w["wo_status"] == "draft" and w["started_qty"] == 0
    assert w["priority_id"] == f.m.fx("default_priority")  # lot type default
    assert w["route_id"] is None
    # system fields are ignored on input
    w2 = f.wo(code="MY-WO", wo_status="closed", started_qty=99, route_id=f.route["id"])
    assert (w2["code"], w2["wo_status"], w2["started_qty"], w2["route_id"]) == (
        "MY-WO",
        "draft",
        0,
        None,
    )
    r = client.post(
        f.m.url("work_order"),
        headers=f.m.h,
        json={
            "product_id": f.product["id"],
            "lot_type_id": f.lt,
            "planned_qty": 0,
            "over_start_limit_pct": 150,
        },
    )
    assert r.status_code == 422 and {"planned_qty", "over_start_limit_pct"} <= {
        d["loc"][1] for d in r.json()["detail"]
    }


def test_release_checks_and_snapshot(client: TestClient, db: Session) -> None:
    f = Fab(client, db)
    m = f.m
    # draft product version -> release fails; also no default route on it
    p2 = m.action("product", f.product["id"], "new-version")
    w = f.wo(product_id=p2["id"])
    msg = _msgs(f.act(w, "release", 422))
    assert "product: must be active" in msg and "no active default route" in msg
    # good WO: snapshot of route + versions
    w = f.wo()
    rel = f.act(w, "release")
    assert rel["wo_status"] == "released" and rel["route_id"] == f.route["id"]
    assert (rel["product_version"], rel["route_version"]) == (1, 1)
    assert rel["released_at"] and rel["released_by"]
    # a new route version going active does not move the released WO
    r2 = m.action("route", f.route["id"], "new-version")
    m.action("route", r2["id"], "status", {"status": "active"})
    assert m.list("work_order", q=w["code"])["data"][0]["route_id"] == f.route["id"]
    # new WOs would use the new default... only if it is bound as default
    w3 = f.wo()
    assert "no active default route" in _msgs(f.act(w3, "release", 422))
    # after release only remarks/due date/refs may change
    m.patch("work_order", w["id"], {"remarks": "ok", "due_date": "2026-12-31"})
    r = client.patch(
        m.url("work_order", w["id"]), headers=m.h, json={"planned_qty": 99}
    )
    assert r.status_code == 422 and "after release" in r.text
    # released WO cannot be deleted
    assert client.delete(m.url("work_order", w["id"]), headers=m.h).status_code == 422
    f.act(w, "release", 422)  # already released


def test_transitions(client: TestClient, db: Session) -> None:
    f = Fab(client, db)
    w = f.wo()
    f.act(w, "complete", 422)
    f.act(w, "release")
    assert f.act(w, "hold")["wo_status"] == "on_hold"
    f.call(w, "start", {"lots": [{"qty": 5}]}, 422)  # not while on hold
    assert f.act(w, "resume")["wo_status"] == "released"
    f.call(w, "start", {"lots": [{"qty": 5}]})
    f.act(w, "cancel", 422)  # in progress
    assert f.act(w, "hold")["held_from"] == "in_progress"
    assert f.act(w, "resume")["wo_status"] == "in_progress"
    assert f.act(w, "complete")["wo_status"] == "completed"
    f.call(w, "start", {"lots": [{"qty": 1}]}, 422)
    # 手动结案：批次未全部入库 / 报废 / 合批前不可关闭（入库流程见 mes/warehouse）
    assert "awaiting receipt" in _msgs(f.act(w, "close", 422))
    f.act(w, "resume", 422)
    d = f.wo()
    assert f.act(d, "cancel")["wo_status"] == "cancelled"
    f.act(d, "bogus", 422)


def test_plan_start_over_limit_and_undo(client: TestClient, db: Session) -> None:
    f = Fab(client, db)
    m = f.m
    w = f.wo(planned_qty=60, over_start_limit_pct=5)  # cap = 63
    f.act(w, "release")
    p = f.call(w, "start-plan", {})
    assert [x["qty"] for x in p["lots"]] == [25, 25, 10]
    assert (p["max_qty"], p["remaining"], p["first_step_id"]) == (63, 63, f.s1["id"])
    assert p["lots"][0]["wafer_ids"][0].endswith(".01")
    assert [
        x["qty"] for x in f.call(w, "start-plan", {"lot_size": 20, "qty": 63})["lots"]
    ] == [20, 20, 20, 3]
    f.call(w, "start-plan", {"lot_size": 26}, 422)  # > lot type max wafers
    # over-start limit
    over = f.call(w, "start", {"lots": [{"qty": 25}, {"qty": 25}, {"qty": 14}]}, 422)
    assert "exceeds the limit 63" in _msgs(over)
    f.call(w, "start", {"lots": [{"qty": 26}]}, 422)  # lot too big
    lots = f.call(
        w, "start", {"lots": [{"qty": 25, "source_ref": "RAW-1"}, {"qty": 25}]}
    )["data"]
    assert [x["lot_status"] for x in lots] == ["waiting", "waiting"]
    assert (
        lots[0]["current_step_id"] == f.s1["id"] and lots[0]["site_id"] == f.site["id"]
    )
    assert lots[0]["route_id"] == f.route["id"] and lots[0]["started_by"]
    wafers = m.list("wafer", lot_id=lots[0]["id"], page_size=100)
    assert (
        wafers["count"] == 25 and wafers["data"][0]["code"] == f"{lots[0]['code']}.01"
    )
    wo = m.list("work_order", q=w["code"])["data"][0]
    assert (wo["started_qty"], wo["wo_status"]) == (50, "in_progress")
    f.call(w, "start", {"lots": [{"qty": 14}]}, 422)  # 50 + 14 > 63
    f.call(w, "start", {"lots": [{"qty": 13}]})  # exactly the cap
    # undo: blocked once a lot moved on
    with Session(engine) as s:
        set_tenant(s, uuid.UUID(m.tid))
        s.execute(
            text("UPDATE mes_lot SET lot_status = 'processing' WHERE id = :i"),
            {"i": lots[1]["id"]},
        )
        s.commit()
    assert "already processed" in _msgs(f.call(w, "undo-start", {}, 422))
    assert f.call(w, "undo-start", {"lot_ids": [lots[0]["id"]]})["undone"] == 1
    assert m.list("wafer", lot_id=lots[0]["id"])["count"] == 0
    assert m.list("work_order", q=w["code"])["data"][0]["started_qty"] == 38
    with Session(engine) as s:
        set_tenant(s, uuid.UUID(m.tid))
        s.execute(
            text("UPDATE mes_lot SET lot_status = 'waiting' WHERE id = :i"),
            {"i": lots[1]["id"]},
        )
        s.commit()
    assert f.call(w, "undo-start", {})["undone"] == 2
    wo = m.list("work_order", q=w["code"])["data"][0]
    assert (wo["started_qty"], wo["wo_status"]) == (0, "released")
    acts = {r["action"] for r in m.list("audit_log", page_size=100)["data"]}
    assert {"release", "start", "undo_start"} <= acts


def test_carrier_and_slots(client: TestClient, db: Session) -> None:
    f = Fab(client, db)
    m = f.m
    ct = m.post(
        "carrier_type",
        {"code": "F25", "name": "foup", "category": "foup", "capacity": 25},
    )
    ct13 = m.post(
        "carrier_type",
        {"code": "F13", "name": "small", "category": "foup", "capacity": 13},
    )
    c1 = m.post("carrier", {"code": "C1", "name": "c1", "carrier_type_id": ct["id"]})
    c2 = m.post("carrier", {"code": "C2", "name": "c2", "carrier_type_id": ct13["id"]})
    dirty = m.post(
        "carrier",
        {
            "code": "C3",
            "name": "c3",
            "carrier_type_id": ct["id"],
            "status_code": "dirty",
        },
    )
    w = f.wo()
    f.act(w, "release")
    bad = [
        [{"qty": 20, "carrier_id": c2["id"]}],  # capacity 13
        [{"qty": 2, "carrier_id": c1["id"], "slots": [1, 1]}],  # duplicate slot
        [{"qty": 2, "carrier_id": c1["id"], "slots": [1, 30]}],  # out of range
        [{"qty": 2, "carrier_id": dirty["id"]}],  # not available
        [
            {"qty": 2, "carrier_id": c1["id"]},
            {"qty": 2, "carrier_id": c1["id"]},
        ],  # twice
        [{"qty": 2, "wafer_sources": ["only-one"]}],
    ]
    for lots in bad:
        f.call(w, "start", {"lots": lots}, 422)
    lot = f.call(
        w,
        "start",
        {
            "lots": [
                {
                    "qty": 3,
                    "carrier_id": c1["id"],
                    "slots": [5, 10, 15],
                    "wafer_sources": ["a", "b", "c"],
                }
            ]
        },
    )["data"][0]
    assert lot["carrier_id"] == c1["id"]
    ws = m.list("wafer", lot_id=lot["id"], sort_by="slot")["data"]
    assert [(x["slot"], x["source_ref"]) for x in ws] == [
        (5, "a"),
        (10, "b"),
        (15, "c"),
    ]
    assert ws[0]["code"].endswith(".05")
    assert "already in use" in _msgs(
        f.call(w, "start", {"lots": [{"qty": 1, "carrier_id": c1["id"]}]}, 422)
    )


def test_permissions_rls_readonly(client: TestClient, db: Session) -> None:
    f = Fab(client, db)
    m = f.m
    w = f.wo()
    email, pw = random_email(), random_lower_string()
    crud.create_user(
        session=db,
        user_create=UserCreate(email=email, username=username_for(email), password=pw),
    )
    client.post(
        f"{API[:-4]}/tenants/{m.tid}/members",
        headers=m.h,
        json={"username": login_name(email), "roles": ["member"]},
    )
    tok = client.post(
        f"{API[:-4]}/login/access-token",
        data={"username": login_name(email), "password": pw},
    ).json()["access_token"]
    hm = {"Authorization": f"Bearer {tok}", "X-Tenant-ID": m.tid}
    assert client.get(m.url("work_order"), headers=hm).json()["count"] == 1
    for what, body in (
        ("transition", {"action": "release"}),
        ("start", {"lots": [{"qty": 1}]}),
        ("start-plan", {}),
    ):
        assert (
            client.post(
                f"{API}/work-order/{w['id']}/{what}", headers=hm, json=body
            ).status_code
            == 403
        )
    meta = client.get(f"{API}/_meta", headers=hm).json()
    assert meta["perms"] and all(p.endswith(":read") for p in meta["perms"])
    assert {
        "mes.wo:release",
        "mes.lot:start",
        "mes.exec:override",
        "mes.exec:hold",
        "mes.exec:write",
    } <= set(client.get(f"{API}/_meta", headers=m.h).json()["perms"])
    # lots / wafers are read-only through the generic API
    assert client.post(m.url("lot"), headers=m.h, json={"code": "L"}).status_code == 405
    f.act(w, "release")
    f.call(w, "start", {"lots": [{"qty": 2}]})
    other = Mes(client, db)
    assert other.list("lot")["count"] == 0
    with Session(engine) as s:
        assert s.execute(text("SELECT count(*) FROM mes_wafer")).scalar_one() == 0
