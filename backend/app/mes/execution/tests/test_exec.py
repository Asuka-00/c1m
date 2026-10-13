"""Lot execution: stages + statuses, auto stages, routing (branch / rework /
sub-route), check bindings (most specific wins), every built-in check type,
override, E10 auto transitions, material consumption, tool life, DC + OOS
actions, Q-Time actions, holds, tracking levels, permissions."""

import uuid
from datetime import timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlmodel import Session

from app.core.spec.base import now
from app.platform.users import service as crud
from app.platform.users.schemas import UserCreate
from app.testing.mes import API, Mes
from app.testing.utils import (
    login_name,
    random_email,
    random_lower_string,
    username_for,
)

EXEC = f"{API}/exec"


class Line:
    """Tenant with E10 states, one tool EQ1, route R: 10 -> 20 -> 30 (+ options)."""

    def __init__(
        self, client: TestClient, db: Session, opt: dict[Any, Any] | None = None
    ) -> None:
        opt = opt or {}
        m = self.m = Mes(client, db)
        self.c = client
        m.post(
            "code_rule",
            {"code": "WO", "name": "wo", "target": "work_order", "pattern": "WO{SEQ}"},
        )
        st = {}
        for i, (c, cat) in enumerate((("SBY", "SBY"), ("PRD", "PRD"), ("DOWN", "UDT"))):
            st[c] = m.post(
                "e10_state",
                {
                    "code": c,
                    "name": c,
                    "e10_category": cat,
                    "is_initial": c == "SBY",
                    "sort_order": i,
                },
            )
        for a, b in (("SBY", "PRD"), ("PRD", "SBY"), ("SBY", "DOWN"), ("DOWN", "SBY")):
            m.post(
                "e10_transition",
                {"from_state_id": st[a]["id"], "to_state_id": st[b]["id"]},
            )
        self.st = st
        m.post("e10_auto_rule", {"trigger": "track_in", "to_state_id": st["PRD"]["id"]})
        m.post(
            "e10_auto_rule", {"trigger": "track_out", "to_state_id": st["SBY"]["id"]}
        )
        self.eq = m.post("equipment", {"code": "EQ1", "name": "eq"})
        self.eq2 = m.post("equipment", {"code": "EQ2", "name": "eq2"})
        area = m.fx("area")
        self.ops = [
            m.post("operation", {"code": f"OP{i}", "name": f"o{i}", "area_id": area})
            for i in range(1, 6)
        ]
        self.recipe = m.post("recipe", {"code": "RC", "name": "rc"})
        m.action("recipe", self.recipe["id"], "status", {"status": "active"})
        for o in self.ops:
            for e in (self.eq, self.eq2):
                m.post(
                    "equipment_capability",
                    {"equipment_id": e["id"], "operation_id": o["id"]},
                )
        mt = m.post(
            "material_type", {"code": "MT", "name": "mt", "category": "chemical"}
        )
        self.mat = m.post(
            "material",
            {
                "code": "MAT",
                "name": "mat",
                "material_type_id": mt["id"],
                "uom_id": m.fx("uom"),
            },
        )
        self.fixture = m.post(
            "fixture", {"code": "PAD", "name": "pad", "kind": "tool", "max_uses": 3}
        )
        # rework route + sub route
        self.rw = m.post("route", {"code": "RW", "name": "rw", "route_type": "rework"})
        m.post(
            "route_step",
            {"route_id": self.rw["id"], "seq": 10, "operation_id": self.ops[4]["id"]},
        )
        m.action("route", self.rw["id"], "status", {"status": "active"})
        self.sub = m.post("route", {"code": "SUB", "name": "sub", "route_type": "sub"})
        m.post(
            "route_step",
            {"route_id": self.sub["id"], "seq": 10, "operation_id": self.ops[3]["id"]},
        )
        m.action("route", self.sub["id"], "status", {"status": "active"})
        self.route = m.post("route", {"code": "R", "name": "r"})
        self.steps = {}
        self.steps[10] = m.post(
            "route_step",
            {
                "route_id": self.route["id"],
                "seq": 10,
                "operation_id": self.ops[0]["id"],
                **opt.get(10, {}),
            },
        )
        self.steps[20] = m.post(
            "route_step",
            {
                "route_id": self.route["id"],
                "seq": 20,
                "operation_id": self.ops[1]["id"],
                "rework_route_id": self.rw["id"],
                "branch_condition": "lot_type == 'ENG'",
                "branch_to_seq": 40,
                **opt.get(20, {}),
            },
        )
        self.steps[30] = m.post(
            "route_step",
            {
                "route_id": self.route["id"],
                "seq": 30,
                "step_type": "sub_route",
                "sub_route_id": self.sub["id"],
            },
        )
        self.steps[40] = m.post(
            "route_step",
            {
                "route_id": self.route["id"],
                "seq": 40,
                "operation_id": self.ops[2]["id"],
                **opt.get(40, {}),
            },
        )
        for seq, res in opt.get("res", {}).items():
            for r in res:
                m.post("step_resource", {"route_step_id": self.steps[seq]["id"], **r})
        m.action("route", self.route["id"], "status", {"status": "active"})
        prod_body = {"code": "P", "name": "p", **opt.get("product", {})}
        if prod_body.get("tracking_level") == "unit":
            rule = m.post(
                "code_rule",
                {
                    "code": "UNIT",
                    "name": "u",
                    "target": "unit",
                    "pattern": "{LOT}-{SEQ}",
                    "seq_width": 3,
                },
            )
            prod_body |= {"serial_kind": "strip", "unit_code_rule_id": rule["id"]}
        self.product = m.post("product", prod_body)
        m.post(
            "product_route",
            {"product_id": self.product["id"], "route_id": self.route["id"]},
        )
        m.action("product", self.product["id"], "status", {"status": "active"})
        self.lt = lt = m.post(
            "lot_type",
            {
                "code": "LT",
                "name": "lt",
                "max_wafers": 1000,
                "default_priority_id": m.fx("default_priority"),
                "lot_id_rule_id": m.fx("lot_id_rule"),
                "wafer_id_rule_id": m.fx("wafer_id_rule"),
            },
        )
        self.wo = m.post(
            "work_order",
            {
                "product_id": self.product["id"],
                "lot_type_id": lt["id"],
                "planned_qty": 1000,
            },
        )
        self.post(f"{API}/work-order/{self.wo['id']}/transition", {"action": "release"})
        self.reasons = {
            t: m.post("reason_code", {"code": f"R-{t}", "name": t, "reason_type": t})
            for t in ("hold", "release", "scrap", "rework")
        }

    def post(self, url: str, body: Any, status: int = 200, h: Any = None) -> Any:
        r = self.c.post(url, headers=h or self.m.h, json=body)
        assert r.status_code == status, r.text
        return r.json()

    def start(self, *qty: int) -> list[dict[str, Any]]:
        out = self.post(
            f"{API}/work-order/{self.wo['id']}/start",
            {"lots": [{"qty": q} for q in qty]},
        )
        return out["data"]  # type: ignore[no-any-return]

    def stage(
        self, lot: dict[str, Any], stage: str, status: int = 200, **body: Any
    ) -> Any:
        return self.post(f"{EXEC}/lots/{lot['id']}/{stage}", body, status)

    def ctx(self, lot: dict[str, Any]) -> Any:
        r = self.c.get(f"{EXEC}/lots/{lot['id']}", headers=self.m.h)
        assert r.status_code == 200, r.text
        return r.json()

    def run_step(self, lot: dict[str, Any], **ti: Any) -> Any:
        self.stage(lot, "move_in", equipment_id=self.eq["id"])
        self.stage(lot, "track_in", equipment_id=self.eq["id"], **ti)
        self.stage(lot, "track_out")
        return self.stage(lot, "move_out")

    def lot(self, lot: dict[str, Any]) -> Any:
        return self.ctx(lot)["lot"]

    def bind(
        self,
        trigger: str,
        *rules: tuple[str, str, dict[str, Any]],
        scope: str = "product",
        **ref: Any,
    ) -> dict[str, Any]:
        m = self.m
        plan = m.post("check_plan", {"code": f"P{uuid.uuid4().hex[:6]}", "name": "p"})
        for i, (tp, sev, params) in enumerate(rules):
            r = m.post(
                "check_rule",
                {
                    "code": f"C{uuid.uuid4().hex[:6]}",
                    "name": tp,
                    "check_type": tp,
                    "severity": sev,
                    "params": params,
                },
            )
            m.post(
                "check_plan_item",
                {"check_plan_id": plan["id"], "check_rule_id": r["id"], "seq": i},
            )
        if scope == "product":
            ref = {"product_id": self.product["id"]}
        m.post(
            "check_binding",
            {"check_plan_id": plan["id"], "trigger": trigger, "scope": scope, **ref},
        )
        return plan

    def sql(self, q: str, **p: Any) -> Any:
        from app.core.db import engine

        with engine.connect() as c:
            c.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"),
                {"t": self.m.tid},
            )
            r = c.execute(text(q), p)
            rows = r.fetchall() if r.returns_rows else None
            c.commit()
            return rows


def _msgs(r: Any) -> str:
    d = r["detail"]
    if isinstance(d, dict):
        if "results" not in d:  # N5：{code, message, ...}
            return f"{d.get('code')}: {d.get('message', '')}"
        return " ".join(x["message"] for x in d["results"])
    return " ".join(x["msg"] for x in d)


# ---------------- stages, statuses, completion ----------------
def test_stage_sequence_history_and_completion(client: TestClient, db: Session) -> None:
    f = Line(client, db)
    (lot,) = f.start(2)
    assert lot["lot_status"] == "waiting" and lot["tracking_level"] == "wafer"
    assert "lot_status" in _msgs(f.stage(lot, "track_in", 422, equipment_id=f.eq["id"]))
    r = f.stage(lot, "move_in", equipment_id=f.eq["id"])
    assert r["lot"]["lot_status"] == "moved_in"
    assert (
        f.stage(lot, "track_in", equipment_id=f.eq["id"], recipe_id=f.recipe["id"])[
            "lot"
        ]["lot_status"]
        == "running"
    )
    assert f.stage(lot, "track_out")["lot"]["lot_status"] == "tracked_out"
    r = f.stage(lot, "move_out")
    assert r["lot"]["lot_status"] == "waiting" and r["next_step"]["seq"] == 20
    f.run_step(lot)  # 20 -> sub-route SUB#10
    cx = f.ctx(lot)
    assert (
        cx["step"]["route"].startswith("SUB") and cx["stack"][0]["kind"] == "sub_route"
    )
    f.run_step(lot)  # SUB#10 -> return -> 40
    assert f.ctx(lot)["step"]["seq"] == 40 and f.ctx(lot)["stack"] == []
    assert f.ctx(lot)["step"]["is_last"]
    r = f.run_step(lot)
    assert r["lot"]["lot_status"] == "completed" and r["next_step"] is None
    # 完工 = 待入库；工单完工数在入库确认时才累加
    assert f.m.list("work_order")["data"][0]["completed_qty"] == 0
    acts = [
        h["action"]
        for h in f.m.list(
            "lot_history", lot=lot["id"], sort_by="at", sort_order="asc", page_size=100
        )["data"]
    ]
    assert (
        acts[0] == "start"
        and "sub_route" in acts
        and "return" in acts
        and acts[-1] == "complete"
    )
    ws = f.m.list("wafer", lot=lot["id"])["data"]
    assert {w["wafer_status"] for w in ws} == {"completed"}
    assert "completed" in _msgs(f.stage(lot, "move_in", 422))
    # undo start is not possible once a lot has been processed
    r = f.post(f"{API}/work-order/{f.wo['id']}/undo-start", {}, 422)
    assert "already processed" in _msgs(r)


def test_auto_stages(client: TestClient, db: Session) -> None:
    f = Line(
        client,
        db,
        {
            20: {"auto_move_in": True, "auto_track_in": True},
            10: {"auto_move_out": True, "auto_track_out": True},
        },
    )
    (lot,) = f.start(1)
    f.stage(lot, "move_in", equipment_id=f.eq["id"])
    r = f.stage(lot, "track_in", equipment_id=f.eq["id"])
    # track out + move out of 10 run automatically, then 20 moves in automatically;
    # auto track-in at 20 needs equipment (EQ1 kept? no: cleared at move-out) -> runs without
    stages = [a["stage"] for a in r["auto"]]
    assert stages[:3] == ["track_out", "move_out", "move_in"]
    lot2 = f.lot(lot)
    assert f.ctx(lot)["step"]["seq"] == 20 and lot2["lot_status"] in (
        "moved_in",
        "running",
    )


def test_branch_and_rework_routing(client: TestClient, db: Session) -> None:
    f = Line(client, db, {20: {"rework_return": "same_step"}})
    a, b = f.start(1, 1)
    for x in (a, b):
        f.run_step(x)  # -> 20
    # manual branch: 20 -> 40, condition text recorded
    f.stage(a, "move_in", equipment_id=f.eq["id"])
    f.stage(a, "track_in", equipment_id=f.eq["id"])
    f.stage(a, "track_out")
    f.stage(a, "move_out", branch=True)
    assert f.ctx(a)["step"]["seq"] == 40
    br = f.m.list("lot_history", lot=a["id"], action="branch")["data"][0]
    assert br["details"]["condition"] == "lot_type == 'ENG'"
    # rework: 20 -> RW#10 -> back to 20 (same step)
    f.stage(b, "move_in", equipment_id=f.eq["id"])
    f.stage(b, "track_in", equipment_id=f.eq["id"])
    f.stage(b, "track_out")
    f.stage(b, "move_out", rework=True)
    assert f.ctx(b)["step"]["route"].startswith("RW")
    f.run_step(b)
    assert f.ctx(b)["step"]["seq"] == 20 and f.ctx(b)["step"]["route"].startswith("R ")
    # step without branch / rework route
    f.run_step(b)  # -> SUB
    f.stage(b, "move_in", equipment_id=f.eq["id"])
    f.stage(b, "track_in", equipment_id=f.eq["id"])
    f.stage(b, "track_out")
    assert "branch" in _msgs(f.stage(b, "move_out", 422, branch=True))
    d = f.stage(b, "move_out", 422, rework=True)["detail"]  # M3 / N5
    assert d["code"] == "rework_route_missing" and d["message"] and d["route_step_id"]
    assert f.lot(b)["lot_status"] == "tracked_out"


# ---------------- check resolution / override ----------------
def test_most_specific_binding_wins_and_logging(
    client: TestClient, db: Session
) -> None:
    f = Line(client, db)
    f.bind("move_in", ("lot_hold", "block", {}), ("wo_status", "block", {}))
    f.bind(
        "move_in",
        ("carrier_available", "warn", {}),
        scope="route_step",
        route_step_id=f.steps[10]["id"],
    )
    (lot,) = f.start(1)
    r = f.stage(lot, "move_in", equipment_id=f.eq["id"])
    assert [x["check_type"] for x in r["results"]] == [
        "carrier_available"
    ]  # step beats product
    f.stage(lot, "track_in", equipment_id=f.eq["id"])
    f.stage(lot, "track_out")
    f.stage(lot, "move_out")
    r = f.stage(lot, "move_in", equipment_id=f.eq["id"])  # step 20: product plan
    assert {x["check_type"] for x in r["results"]} == {"lot_hold", "wo_status"}
    logs = f.m.list("check_log", lot=lot["id"])["data"]
    assert len(logs) == 3 and {x["result"] for x in logs} == {"pass"}


def test_block_override_permission_and_audit(client: TestClient, db: Session) -> None:
    f = Line(client, db)
    f.bind(
        "track_in", ("e10_available", "block", {"allowed": ["PRD"]})
    )  # SBY not allowed
    (lot,) = f.start(1)
    f.stage(lot, "move_in", equipment_id=f.eq["id"])
    r = f.stage(lot, "track_in", 409, equipment_id=f.eq["id"])
    assert (
        r["detail"]["code"] == "check_blocked"
        and r["detail"]["results"][0]["result"] == "block"
    )
    assert f.lot(lot)["lot_status"] == "moved_in"
    assert (
        f.m.list("check_log", lot=lot["id"], result="block")["count"] == 1
    )  # kept despite rollback
    assert "override_reason" in _msgs(
        f.stage(lot, "track_in", 422, equipment_id=f.eq["id"], override=True)
    )
    # a member may read but not run / override
    email, pw = random_email(), random_lower_string()
    crud.create_user(
        session=db,
        user_create=UserCreate(email=email, username=username_for(email), password=pw),
    )
    client.post(
        f"{API[:-4]}/tenants/{f.m.tid}/members",
        headers=f.m.h,
        json={"username": login_name(email), "roles": ["member"]},
    )
    tok = client.post(
        f"{API[:-4]}/login/access-token",
        data={"username": login_name(email), "password": pw},
    ).json()["access_token"]
    hm = {"Authorization": f"Bearer {tok}", "X-Tenant-ID": f.m.tid}
    assert client.get(f"{EXEC}/lots/{lot['id']}", headers=hm).status_code == 200
    assert (
        client.post(
            f"{EXEC}/lots/{lot['id']}/track_in",
            headers=hm,
            json={"equipment_id": f.eq["id"]},
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"{EXEC}/lots/{lot['id']}/hold",
            headers=hm,
            json={"reason_id": f.reasons["hold"]["id"]},
        ).status_code
        == 403
    )
    r = f.stage(
        lot,
        "track_in",
        equipment_id=f.eq["id"],
        override=True,
        override_reason="engineer approved",
    )
    assert (
        r["results"][0]["result"] == "overridden"
        and r["lot"]["lot_status"] == "running"
    )
    log = f.m.list("check_log", lot=lot["id"], result="overridden")["data"][0]
    assert log["override_reason"] == "engineer approved"
    assert f.m.list("lot_history", lot=lot["id"], action="override")["count"] == 1
    assert f.m.list("audit_log", action="override")["count"] == 1
    # preview evaluates without executing
    pv = f.post(f"{EXEC}/lots/{lot['id']}/preview/track_out", {})
    assert pv["results"] == [] and f.lot(lot)["lot_status"] == "running"


# ---------------- built-in check types ----------------
def _ti_block(f: Line, lot: dict[str, Any], **body: Any) -> str:
    f.stage(lot, "move_in", equipment_id=f.eq["id"])
    return _msgs(f.stage(lot, "track_in", 409, equipment_id=f.eq["id"], **body))


def test_e10_capability_recipe_checks(client: TestClient, db: Session) -> None:
    f = Line(client, db)
    f.bind(
        "track_in",
        ("e10_available", "block", {}),
        ("eqp_capability", "block", {}),
        ("recipe_active", "block", {}),
    )
    a, b, c = f.start(1, 1, 1)
    f.sql(
        "UPDATE mes_equipment SET e10_state_id = :s WHERE id = :e",
        s=f.st["DOWN"]["id"],
        e=f.eq["id"],
    )
    assert "DOWN" in _ti_block(f, a)
    f.sql(
        "UPDATE mes_equipment SET e10_state_id = :s WHERE id = :e",
        s=f.st["SBY"]["id"],
        e=f.eq["id"],
    )
    f.sql("DELETE FROM mes_equipment_capability WHERE equipment_id = :e", e=f.eq["id"])
    assert "no capability" in _ti_block(f, b)
    f.stage(c, "move_in", equipment_id=f.eq2["id"])
    draft = f.m.post("recipe", {"code": "RC2", "name": "rc2"})
    assert "draft" in _msgs(
        f.stage(c, "track_in", 409, equipment_id=f.eq2["id"], recipe_id=draft["id"])
    )
    r = f.stage(c, "track_in", equipment_id=f.eq2["id"], recipe_id=f.recipe["id"])
    assert {x["result"] for x in r["results"]} == {"pass"}


def test_e10_auto_transitions(client: TestClient, db: Session) -> None:
    f = Line(client, db)
    a, b = f.start(1, 1)
    for x in (a, b):
        f.stage(x, "move_in", equipment_id=f.eq["id"])
        r = f.stage(x, "track_in", equipment_id=f.eq["id"])

    def state() -> str:
        return f.sql(
            "SELECT s.code FROM mes_equipment e JOIN mes_e10_state s ON s.id = e.e10_state_id WHERE e.id = :e",
            e=f.eq["id"],
        )[0][0]

    assert state() == "PRD"
    r = f.stage(a, "track_out")
    assert r["e10"]["skipped"].startswith("1 other") and state() == "PRD"
    f.stage(b, "track_out")
    assert state() == "SBY"
    # a transition that is not configured is skipped
    f.sql(
        "UPDATE mes_equipment SET e10_state_id = :s WHERE id = :e",
        s=f.st["DOWN"]["id"],
        e=f.eq["id"],
    )
    (c,) = f.start(1)
    f.stage(c, "move_in", equipment_id=f.eq["id"])
    r = f.stage(c, "track_in", equipment_id=f.eq["id"])
    assert "not allowed" in r["e10"]["skipped"] and state() == "DOWN"


def test_reticle_carrier_hold_wo_checks(client: TestClient, db: Session) -> None:
    f = Line(client, db)
    rt = f.m.post(
        "reticle",
        {
            "code": "RT",
            "name": "rt",
            "product_id": f.product["id"],
            "layer": "L1",
            "status_code": "hold",
        },
    )
    f.sql(
        "INSERT INTO mes_step_resource (id, tenant_id, route_step_id, resource_kind, reticle_id) VALUES (gen_random_uuid(), :t, :s, 'reticle', :r)",
        t=f.m.tid,
        s=f.steps[10]["id"],
        r=rt["id"],
    )
    f.bind(
        "track_in",
        ("reticle_available", "block", {}),
        ("carrier_available", "block", {}),
    )
    f.bind("move_in", ("lot_hold", "block", {}), ("wo_status", "block", {}))
    ct = f.m.post(
        "carrier_type",
        {"code": "FOUP", "name": "f", "category": "foup", "capacity": 25},
    )
    car = f.m.post(
        "carrier",
        {
            "code": "C1",
            "name": "c",
            "carrier_type_id": ct["id"],
            "status_code": "dirty",
        },
    )
    a, b = f.start(1, 1)
    assert "reticle required" in _ti_block(f, a)
    assert "is hold" in _msgs(
        f.stage(a, "track_in", 409, equipment_id=f.eq["id"], reticle_id=rt["id"])
    )
    f.m.patch("reticle", rt["id"], {"status_code": "available"})
    assert "carrier C1 is dirty" in _msgs(
        f.stage(
            a,
            "track_in",
            409,
            equipment_id=f.eq["id"],
            reticle_id=rt["id"],
            carrier_id=car["id"],
        )
    )
    f.stage(a, "track_in", equipment_id=f.eq["id"], reticle_id=rt["id"])
    # WO on hold blocks move-in (configured), lot hold always blocks (intrinsic)
    f.post(f"{API}/work-order/{f.wo['id']}/transition", {"action": "hold"})
    assert "work order is on_hold" in _msgs(f.stage(b, "move_in", 409))
    f.post(f"{API}/work-order/{f.wo['id']}/transition", {"action": "resume"})
    f.post(
        f"{EXEC}/lots/{b['id']}/hold",
        {"reason_id": f.reasons["hold"]["id"], "comment": "check"},
    )
    assert "on hold" in _msgs(f.stage(b, "move_in", 422))


def test_material_sufficiency_and_consumption(client: TestClient, db: Session) -> None:
    f = Line(client, db)
    m = f.m
    f.sql(
        "INSERT INTO mes_step_resource (id, tenant_id, route_step_id, resource_kind, material_id, qty, uom_id, qty_basis) "
        "VALUES (gen_random_uuid(), :t, :s, 'material', :m, 2, :u, 'per_unit')",
        t=m.tid,
        s=f.steps[10]["id"],
        m=f.mat["id"],
        u=m.fx("uom"),
    )
    ml1 = m.post(
        "material_lot",
        {
            "code": "ML1",
            "material_id": f.mat["id"],
            "qty_remaining": 3,
            "uom_id": m.fx("uom"),
            "expiry_date": "2030-01-01",
        },
    )
    ml2 = m.post(
        "material_lot",
        {
            "code": "ML2",
            "material_id": f.mat["id"],
            "qty_remaining": 10,
            "uom_id": m.fx("uom"),
            "expiry_date": str(
                now().date() - timedelta(days=1)
            ),  # 与应用时钟（UTC）一致,
        },
    )
    assert ml1["initial_qty"] == 3
    f.bind("track_in", ("material_sufficient", "block", {}))
    (lot,) = f.start(2)  # needs 2 x 2 = 4, only 3 usable (ML2 expired)
    cx = f.ctx(lot)
    assert cx["materials"][0]["need"] == 4 and [
        o["code"] for o in cx["materials"][0]["options"]
    ] == ["ML1"]
    assert "need 4, available 3" in _ti_block(f, lot)
    f.stage(
        lot,
        "track_in",
        equipment_id=f.eq["id"],
        override=True,
        override_reason="top up coming",
    )
    assert "insufficient" in _msgs(
        f.stage(lot, "track_out", 422)
    )  # hard rule at track out
    m.patch("material_lot", ml1["id"], {"qty_remaining": 5})
    r = f.stage(lot, "track_out")
    assert r["consumed"] == [{"material_lot": "ML1", "qty": 4.0, "left": 1.0}]
    assert m.list("material_lot", q="ML2")["data"][0]["qty_remaining"] == 10
    assert ml2["ml_status"] == "available"


def test_tool_life(client: TestClient, db: Session) -> None:
    f = Line(client, db)
    m = f.m
    f.sql(
        "INSERT INTO mes_step_resource (id, tenant_id, route_step_id, resource_kind, fixture_id) VALUES (gen_random_uuid(), :t, :s, 'fixture', :f)",
        t=m.tid,
        s=f.steps[10]["id"],
        f=f.fixture["id"],
    )
    t1 = m.post(
        "tool",
        {"code": "T1", "fixture_id": f.fixture["id"], "usage_count": 1, "warn_pct": 30},
    )
    t2 = m.post(
        "tool",
        {
            "code": "T2",
            "fixture_id": f.fixture["id"],
            "expiry_date": str(
                now().date() - timedelta(days=1)
            ),  # 与应用时钟（UTC）一致,
        },
    )
    f.bind("track_in", ("tool_life", "block", {}))
    a, b, c = f.start(1, 1, 1)
    f.stage(a, "move_in", equipment_id=f.eq["id"])
    assert "tool_ids" in _msgs(
        f.stage(a, "track_in", 422, equipment_id=f.eq["id"])
    )  # tool required
    assert "expired" in _msgs(
        f.stage(a, "track_in", 409, equipment_id=f.eq["id"], tool_ids=[t2["id"]])
    )
    r = f.stage(a, "track_in", equipment_id=f.eq["id"], tool_ids=[t1["id"]])
    assert r["results"][0]["result"] == "warn"  # 1/3 >= 30 %
    assert m.list("tool", q="T1")["data"][0]["tool_status"] == "in_use"
    r = f.stage(a, "track_out")
    assert r["tools"] == [{"tool": "T1", "usage": 2, "max": 3, "status": "available"}]
    f.stage(b, "move_in", equipment_id=f.eq["id"])
    f.stage(b, "track_in", equipment_id=f.eq["id"], tool_ids=[t1["id"]])
    assert f.stage(b, "track_out")["tools"][0]["status"] == "pending_maintenance"  # 3/3
    f.stage(c, "move_in", equipment_id=f.eq["id"])
    assert "pending_maintenance" in _msgs(
        f.stage(c, "track_in", 409, equipment_id=f.eq["id"], tool_ids=[t1["id"]])
    )


def _dc_line(
    client: TestClient, db: Session, actions: dict[str, str], kw: Any = None
) -> tuple[Line, list[dict[str, Any]]]:
    f = Line(client, db, kw)
    m = f.m
    mis = {
        c: m.post("measurement_item", {"code": c, "name": c, "oos_action": a})
        for c, a in actions.items()
    }
    plan = m.post(
        "dc_plan", {"code": "DCP", "name": "dc", "operation_id": f.ops[0]["id"]}
    )
    for i, mi in enumerate(mis.values()):
        m.post(
            "dc_plan_item",
            {
                "dc_plan_id": plan["id"],
                "measurement_item_id": mi["id"],
                "seq": i,
                "lsl": 1,
                "usl": 2,
                "target": 1.5,
            },
        )
    m.action("dc_plan", plan["id"], "status", {"status": "active"})
    f.bind("track_out", ("dc_complete", "block", {}), ("oos", "warn", {}))
    return f, list(mis.values())


def _dc(items: list[dict[str, Any]], *vals: float) -> list[dict[str, Any]]:
    return [
        {"measurement_item_id": it["id"], "value": v}
        for it, v in zip(items, vals, strict=True)
    ]


def test_dc_completeness_and_oos_actions(client: TestClient, db: Session) -> None:
    f, items = _dc_line(client, db, {"A": "warn", "B": "auto_hold", "C": "block"})
    a, b, c, d = f.start(1, 1, 1, 1)
    for x in (a, b, c, d):
        f.stage(x, "move_in", equipment_id=f.eq["id"])
        f.stage(x, "track_in", equipment_id=f.eq["id"])
    assert "missing DC values" in _msgs(
        f.stage(a, "track_out", 409, dc=_dc(items[:1], 1.5))
    )
    # warn only
    r = f.stage(a, "track_out", dc=_dc(items, 5, 1.5, 1.5))
    assert r["oos_action"] == "warn" and not r["lot"]["on_hold"]
    # warn + auto_hold -> hold wins
    r = f.stage(b, "track_out", dc=_dc(items, 5, 5, 1.5))
    assert r["oos_action"] == "auto_hold" and r["lot"]["on_hold"]
    hold = f.m.list("lot_hold", lot=b["id"])["data"][0]
    assert (
        hold["hold_type"] == "auto"
        and hold["source"] == "oos"
        and "B=5" in hold["comment"]
    )
    # block wins over hold; can be overridden
    assert "OOS (block)" in _msgs(f.stage(c, "track_out", 409, dc=_dc(items, 5, 5, 5)))
    r = f.stage(
        c, "track_out", dc=_dc(items, 5, 5, 5), override=True, override_reason="MRB"
    )
    assert r["lot"]["lot_status"] == "tracked_out"
    assert f.m.list("dc_result", lot=c["id"], is_oos=True)["count"] == 3
    # in spec
    r = f.stage(d, "track_out", dc=_dc(items, 1.2, 1.8, 1.5))
    assert r["oos_action"] is None


def test_oos_rework_routes_to_rework(client: TestClient, db: Session) -> None:
    f = Line(client, db)
    m = f.m
    mi = m.post(
        "measurement_item", {"code": "CD", "name": "cd", "oos_action": "rework"}
    )
    plan = m.post(
        "dc_plan", {"code": "DC2", "name": "dc", "operation_id": f.ops[1]["id"]}
    )
    m.post(
        "dc_plan_item",
        {"dc_plan_id": plan["id"], "measurement_item_id": mi["id"], "usl": 1},
    )
    m.action("dc_plan", plan["id"], "status", {"status": "active"})
    (lot,) = f.start(1)
    f.run_step(lot)
    f.stage(lot, "move_in", equipment_id=f.eq["id"])
    f.stage(lot, "track_in", equipment_id=f.eq["id"])
    r = f.stage(lot, "track_out", dc=[{"measurement_item_id": mi["id"], "value": 3}])
    assert r["oos_action"] == "rework" and r["lot"]["pending_rework"]
    f.stage(lot, "move_out")
    assert f.ctx(lot)["step"]["route"].startswith("RW")


def test_sampling_frequency(client: TestClient, db: Session) -> None:
    f, items = _dc_line(client, db, {"A": "warn"})
    f.m.post(
        "sampling_rule",
        {
            "code": "SR",
            "name": "sr",
            "operation_id": f.ops[0]["id"],
            "lot_frequency": 2,
        },
    )
    f.bind("track_in", ("sampling", "warn", {}))
    a, b = f.start(2, 2)
    for x in (a, b):
        f.stage(x, "move_in", equipment_id=f.eq["id"])
    r = f.stage(a, "track_in", equipment_id=f.eq["id"])
    assert "sampled" in r["results"][0]["message"]
    f.stage(a, "track_out", dc=_dc(items, 1.5))
    f.stage(b, "track_in", equipment_id=f.eq["id"])
    assert f.ctx(b)["dc"]["sampled"] is False  # 2nd lot skipped -> no DC needed
    f.stage(b, "track_out")
    # wafer-level sampling picks units
    f.m.post(
        "sampling_rule",
        {
            "code": "SRW",
            "name": "w",
            "operation_id": f.ops[0]["id"],
            "level": "wafer",
            "wafer_count": 1,
            "wafer_selection": "last",
            "product_id": f.product["id"],
        },
    )
    (c,) = f.start(3)
    cx = f.ctx(c)
    assert (
        len(cx["dc"]["unit_ids"]) == 1
        and cx["dc"]["unit_ids"][0] == cx["units"][-1]["id"]
    )


def test_qtime_min_and_violation_actions(client: TestClient, db: Session) -> None:
    f = Line(client, db)
    m = f.m
    rule = m.post(
        "qtime_rule",
        {
            "code": "QT",
            "name": "q",
            "route_id": f.route["id"],
            "from_step_id": f.steps[10]["id"],
            "to_step_id": f.steps[20]["id"],
            "min_minutes": 1,
            "max_minutes": 30,
            "reason_id": f.reasons["hold"]["id"],
        },
    )
    f.bind("move_in", ("qtime", "block", {}))
    a, b, c = f.start(1, 1, 1)
    for x in (a, b, c):
        f.run_step(x)
    assert "min 1 min" in _msgs(f.stage(a, "move_in", 409, equipment_id=f.eq["id"]))
    f.sql(
        "UPDATE mes_lot_history SET at = at - interval '10 minutes' WHERE lot_id = :l AND action = 'move_out'",
        l=a["id"],
    )
    f.stage(a, "move_in", equipment_id=f.eq["id"])  # inside the window
    # exceeded -> default action hold (once per violation)
    f.sql(
        "UPDATE mes_lot_history SET at = at - interval '2 hours' WHERE lot_id IN (:b, :c) AND action = 'move_out'",
        b=b["id"],
        c=c["id"],
    )
    r = f.stage(b, "move_in", equipment_id=f.eq["id"])
    assert (
        r["qtime"] == "hold"
        and r["lot"]["on_hold"]
        and r["lot"]["lot_status"] == "waiting"
    )
    hold = m.list("lot_hold", lot=b["id"])["data"][0]
    assert hold["source"] == "qtime"
    f.post(
        f"{EXEC}/holds/{hold['id']}/release", {"reason_id": f.reasons["release"]["id"]}
    )
    f.bind(
        "move_in",
        ("lot_hold", "block", {}),
        scope="route_step",
        route_step_id=f.steps[20]["id"],
    )  # replaces qtime check
    assert (
        f.stage(b, "move_in", equipment_id=f.eq["id"])["lot"]["lot_status"]
        == "moved_in"
    )  # not re-held
    # scrap / rework actions
    m.patch(
        "qtime_rule",
        rule["id"],
        {"action": "scrap", "reason_id": f.reasons["scrap"]["id"]},
    )
    # QT-01（M1）：配置为 scrap 的超时也改为自动 Hold（原因码 qtime_expired），不报废
    qe = next(  # 系统原因码，租户初始化时已建（D18）
        x
        for x in m.list("reason_code", code="qtime_expired")["data"]
        if x["code"] == "qtime_expired"
    )
    r = f.stage(c, "move_in", equipment_id=f.eq["id"])
    assert r["qtime"] == "hold" and r["lot"]["on_hold"]
    assert r["lot"]["lot_status"] == "waiting" and r["lot"]["qty"] > 0
    ch = [h for h in m.list("lot_hold", lot=c["id"])["data"] if h["is_active"]]
    assert len(ch) == 1 and ch[0]["source"] == "qtime"
    assert ch[0]["reason_id"] == qe["id"]
    assert m.list("lot_history", lot=c["id"], action="scrap")["count"] == 0
    (d,) = f.start(1)
    f.run_step(d)
    f.sql(
        "UPDATE mes_lot_history SET at = at - interval '2 hours' WHERE lot_id = :l AND action = 'move_out'",
        l=d["id"],
    )
    m.patch("qtime_rule", rule["id"], {"action": "rework", "reason_id": None})
    r = f.stage(d, "move_in", equipment_id=f.eq["id"])
    assert r["qtime"] == "rework" and f.ctx(d)["step"]["route"].startswith("RW")


def test_hold_release(client: TestClient, db: Session) -> None:
    f = Line(client, db)
    (lot,) = f.start(1)
    url = f"{EXEC}/lots/{lot['id']}/hold"
    assert "hold reason" in _msgs(
        f.post(url, {"reason_id": f.reasons["scrap"]["id"]}, 422)
    )
    f.post(url, {"reason_id": f.reasons["hold"]["id"], "comment": "1"})
    f.post(url, {"reason_id": f.reasons["hold"]["id"], "comment": "2"})
    holds = f.ctx(lot)["holds"]
    assert len(holds) == 2 and f.lot(lot)["on_hold"]
    assert "release reason" in _msgs(
        f.post(
            f"{EXEC}/holds/{holds[0]['id']}/release",
            {"reason_id": f.reasons["hold"]["id"]},
            422,
        )
    )
    assert f.post(
        f"{EXEC}/holds/{holds[0]['id']}/release",
        {"reason_id": f.reasons["release"]["id"]},
    )["on_hold"]
    assert "already released" in _msgs(
        f.post(f"{EXEC}/holds/{holds[0]['id']}/release", {}, 422)
    )
    assert not f.post(f"{EXEC}/holds/{holds[1]['id']}/release", {"comment": "ok"})[
        "on_hold"
    ]
    acts = [h["action"] for h in f.m.list("lot_history", lot=lot["id"])["data"]]
    assert acts.count("hold") == 2 and acts.count("release") == 2
    assert (
        f.c.post(f.m.url("lot_hold"), headers=f.m.h, json={}).status_code == 405
    )  # read-only


# ---------------- tracking levels ----------------
def test_wafer_scrap_and_rework_units(client: TestClient, db: Session) -> None:
    f = Line(client, db)
    (lot,) = f.start(3)
    f.stage(lot, "move_in", equipment_id=f.eq["id"])
    f.stage(lot, "track_in", equipment_id=f.eq["id"])
    us = f.ctx(lot)["units"]
    assert [u["slot"] for u in us] == [1, 2, 3] and us[0]["unit_kind"] == "wafer"
    sr, rr = f.reasons["scrap"]["id"], f.reasons["rework"]["id"]
    assert "scrap reason" in _msgs(
        f.stage(
            lot, "track_out", 422, scrap=[{"unit_id": us[0]["id"], "reason_id": rr}]
        )
    )
    r = f.stage(
        lot,
        "track_out",
        scrap=[{"unit_id": us[0]["id"], "reason_id": sr}],
        rework_units=[{"unit_id": us[1]["id"], "reason_id": rr}],
    )
    assert r["lot"]["qty"] == 2 and r["lot"]["scrapped_qty"] == 1
    st = {u["code"]: u["status"] for u in f.ctx(lot)["units"]}
    assert sorted(st.values()) == ["rework", "scrapped", "waiting"]
    f.stage(lot, "move_out")
    (l2,) = f.start(1)
    f.stage(l2, "move_in", equipment_id=f.eq["id"])
    f.stage(l2, "track_in", equipment_id=f.eq["id"])
    u = f.ctx(l2)["units"][0]
    assert (
        f.stage(l2, "track_out", scrap=[{"unit_id": u["id"], "reason_id": sr}])["lot"][
            "lot_status"
        ]
        == "scrapped"
    )


def test_quantity_tracking(client: TestClient, db: Session) -> None:
    f = Line(client, db, {"product": {"tracking_level": "quantity"}})
    (lot,) = f.start(500)
    assert lot["tracking_level"] == "quantity" and f.ctx(lot)["units"] == []
    f.stage(lot, "move_in")
    f.stage(lot, "track_in", equipment_id=f.eq["id"])
    sr = f.reasons["scrap"]["id"]
    assert "exceeds" in _msgs(
        f.stage(lot, "track_out", 422, scrap=[{"qty": 501, "reason_id": sr}])
    )
    r = f.stage(
        lot,
        "track_out",
        scrap=[{"qty": 7, "reason_id": sr}, {"qty": 3, "reason_id": sr}],
    )
    assert r["lot"]["qty"] == 490 and r["lot"]["scrapped_qty"] == 10
    assert f.m.list("lot_history", lot=lot["id"], action="scrap")["count"] == 2


def test_unit_tracking_inherits_and_serializes(client: TestClient, db: Session) -> None:
    f = Line(client, db, {"product": {"tracking_level": "unit"}})
    (lot,) = f.start(3)
    us = f.ctx(lot)["units"]
    assert (
        lot["tracking_level"] == "unit"
        and [u["unit_kind"] for u in us] == ["strip"] * 3
    )
    assert us[0]["code"] == f"{lot['code']}-001" and us[0]["slot"] is None
    # tech-node level is inherited when the product leaves it blank
    m = f.m
    node = m.post(
        "tech_node", {"code": "BE", "name": "be", "tracking_level": "quantity"}
    )
    p = m.post("product", {"code": "P2", "name": "p2", "tech_node_id": node["id"]})
    from app.core.spec.engine import ENTITIES
    from app.core.spec.query import get_row
    from app.core.tenant import set_tenant
    from app.mes.lot.lots import tracking_level

    set_tenant(db, uuid.UUID(m.tid))
    row = get_row(db, ENTITIES["product"], uuid.UUID(m.tid), uuid.UUID(p["id"]))
    assert tracking_level(db, uuid.UUID(m.tid), row) == "quantity"
    m.post(
        "product", {"code": "P3", "name": "p3", "tracking_level": "unit"}, status=422
    )  # needs rule + kind


def test_rls_isolation(client: TestClient, db: Session) -> None:
    f = Line(client, db)
    (lot,) = f.start(1)
    other = Mes(client, db)
    assert client.get(f"{EXEC}/lots/{lot['id']}", headers=other.h).status_code == 404
    assert (
        client.post(
            f"{EXEC}/lots/{lot['id']}/move_in", headers=other.h, json={}
        ).status_code
        == 404
    )
