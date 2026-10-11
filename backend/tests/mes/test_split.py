"""Lot split / merge: rules (states, max children, min qty, same product /
route / step / stage / WO, hold, carrier capacity), child IDs, inheritance
(step, stage, holds, Q-Time clocks, attrs), genealogy, history, audit, bound
checks (triggers split / merge) with override, permissions."""

from typing import Any

from fastapi.testclient import TestClient
from sqlmodel import Session

from app import crud
from app.models import UserCreate
from tests.mes.test_exec import EXEC, Line, _msgs
from tests.utils.utils import random_email, random_lower_string

API = EXEC[: -len("/exec")]


def _line(client: TestClient, db: Session, opt: Any = None, **rule: Any) -> Line:
    f = Line(client, db, opt)
    f.rule = f.m.post(  # type: ignore[attr-defined]
        "split_merge_rule",
        {
            "code": "SM",
            "name": "sm",
            "lot_type_id": f.lt["id"],
            "max_children": 3,
            "min_wafers": 2,
            **rule,
        },
    )
    return f


def split(f: Line, lot: Any, children: list[Any], status: int = 200, **kw: Any) -> Any:
    return f.post(
        f"{EXEC}/lots/{lot['id']}/split", {"children": children, **kw}, status
    )


def merge(f: Line, lot: Any, srcs: list[Any], status: int = 200, **kw: Any) -> Any:
    return f.post(
        f"{EXEC}/lots/{lot['id']}/merge",
        {"source_lot_ids": [x["id"] for x in srcs], **kw},
        status,
    )


def uid(f: Line, lot: Any, *idx: int) -> list[str]:
    us = f.ctx(lot)["units"]
    return [us[i]["id"] for i in idx]


def test_split_wafers_children_genealogy_history(
    client: TestClient, db: Session
) -> None:
    f = _line(client, db)
    (lot,) = f.start(6)
    f.stage(lot, "move_in", equipment_id=f.eq["id"])
    ids = uid(f, lot, 0, 1)
    r = split(f, lot, [{"unit_ids": ids}], comment="eng split")
    (ch,) = r["children"]
    assert ch["code"] == f"{lot['code']}.01" and ch["qty"] == 2
    assert r["lot"]["qty"] == 4
    c = f.lot(ch)
    for k in (
        "work_order_id",
        "product_id",
        "route_id",
        "current_step_id",
        "priority_id",
        "equipment_id",
    ):
        assert c[k] == r["lot"][k], k
    assert c["lot_status"] == "moved_in"
    assert [u["id"] for u in f.ctx(ch)["units"]] == ids
    assert len(f.ctx(lot)["units"]) == 4
    g = f.m.list("lot_genealogy", parent_lot=lot["id"])["data"]
    assert len(g) == 1 and g[0]["relation"] == "split" and g[0]["qty"] == 2
    assert f.m.list("lot_history", lot=ch["id"], action="split")["count"] == 1
    assert f.m.list("lot_history", lot=lot["id"], action="split")["count"] == 1
    sm = f.ctx(lot)["sm"]
    assert sm["rule"]["children"] == 1 and sm["genealogy"][0]["child"] == ch["code"]
    # audit
    rows = f.sql("SELECT count(*) FROM mes_audit_log WHERE action = 'split'")
    assert rows[0][0] == 2
    # the child continues through the route on its own
    f.stage(ch, "track_in", equipment_id=f.eq["id"])
    assert (
        f.lot(ch)["lot_status"] == "running" and f.lot(lot)["lot_status"] == "moved_in"
    )


def test_split_rules(client: TestClient, db: Session) -> None:
    f = _line(client, db)
    (lot,) = f.start(8)
    # min qty per lot (child and remainder)
    assert "at least 2" in _msgs(split(f, lot, [{"unit_ids": uid(f, lot, 0)}], 409))
    split(f, lot, [{"unit_ids": uid(f, lot, 0, 1)}, {"unit_ids": uid(f, lot, 2, 3)}])
    # max lots (parent + children) = 3
    assert "exceed max 3" in _msgs(
        split(f, lot, [{"unit_ids": uid(f, lot, 0, 1)}], 409)
    )
    # input validation
    other = f.start(4)[0]
    assert "not in the lot" in _msgs(
        split(f, lot, [{"unit_ids": uid(f, other, 0, 1)}], 422)
    )
    assert "pick" in _msgs(split(f, lot, [{"unit_ids": []}], 422))
    # state: not while running
    f.stage(other, "move_in", equipment_id=f.eq["id"])
    f.stage(other, "track_in", equipment_id=f.eq["id"])
    assert "cannot split a running lot" in _msgs(
        split(f, other, [{"unit_ids": uid(f, other, 0, 1)}], 409)
    )
    # rule switches
    f.m.patch(
        "split_merge_rule", f.rule["id"], {"allow_split": False, "max_children": 3}
    )  # type: ignore[attr-defined]
    (x,) = f.start(4)
    assert "split not allowed" in _msgs(
        split(f, x, [{"unit_ids": uid(f, x, 0, 1)}], 409)
    )
    f.m.delete("split_merge_rule", f.rule["id"])  # type: ignore[attr-defined]
    assert "no split/merge rule" in _msgs(
        split(f, x, [{"unit_ids": uid(f, x, 0, 1)}], 409)
    )
    # rule violations cannot be overridden
    assert "no split/merge rule" in _msgs(
        split(
            f,
            x,
            [{"unit_ids": uid(f, x, 0, 1)}],
            409,
            override=True,
            override_reason="x",
        )
    )


def test_split_quantity_and_code_rule_ids(client: TestClient, db: Session) -> None:
    f = _line(
        client,
        db,
        {"product": {"tracking_level": "quantity"}},
        child_id_mode="code_rule",
    )
    (lot,) = f.start(500)
    assert "qty must be > 0" in _msgs(split(f, lot, [{"qty": 0}], 422))
    assert "keep at least" in _msgs(split(f, lot, [{"qty": 500}], 409))
    r = split(f, lot, [{"qty": 120}, {"qty": 80}])
    assert [c["qty"] for c in r["children"]] == [120, 80] and r["lot"]["qty"] == 300
    codes = [c["code"] for c in r["children"]]
    assert (
        all("." not in c and c != lot["code"] for c in codes) and len(set(codes)) == 2
    )
    assert f.lot(r["children"][0])["tracking_level"] == "quantity"


def test_split_inherits_hold_and_qtime(client: TestClient, db: Session) -> None:
    f = _line(client, db)
    f.m.post(
        "qtime_rule",
        {
            "code": "QT",
            "name": "q",
            "route_id": f.route["id"],
            "from_step_id": f.steps[10]["id"],
            "to_step_id": f.steps[20]["id"],
            "max_minutes": 30,
            "reason_id": f.reasons["hold"]["id"],
        },
    )
    (lot,) = f.start(4)
    f.run_step(lot)
    f.sql(
        "UPDATE mes_lot_history SET at = at - interval '2 hours' WHERE lot_id = :l AND action = 'move_out'",
        l=lot["id"],
    )
    f.post(f"{EXEC}/lots/{lot['id']}/hold", {"reason_id": f.reasons["hold"]["id"]})
    (ch,) = split(f, lot, [{"unit_ids": uid(f, lot, 0, 1)}])["children"]
    c = f.ctx(ch)
    assert c["lot"]["on_hold"] and c["qtime"][0]["exceeded"]
    h = f.m.list("lot_hold", lot=ch["id"])["data"]
    assert len(h) == 1 and h[0]["is_active"] and h[0]["source"] == "split"
    assert "inherited" in h[0]["comment"]


def test_merge_back_and_terminate(client: TestClient, db: Session) -> None:
    f = _line(client, db)
    (lot,) = f.start(6)
    (ch,) = split(f, lot, [{"unit_ids": uid(f, lot, 0, 1)}])["children"]
    cands = f.ctx(lot)["sm"]["candidates"]
    assert [c["code"] for c in cands] == [ch["code"]] and cands[0]["problems"] == []
    assert "itself" in _msgs(merge(f, lot, [lot], 409))
    r = merge(f, lot, [ch], comment="rejoin")
    assert r["lot"]["qty"] == 6 and r["merged"][0]["code"] == ch["code"]
    c = f.lot(ch)
    assert c["lot_status"] == "merged" and c["qty"] == 0
    assert len(f.ctx(lot)["units"]) == 6
    g = f.m.list("lot_genealogy", child_lot=lot["id"], relation="merge")["data"]
    assert len(g) == 1 and g[0]["parent_lot_id"] == ch["id"]
    assert "merged" in _msgs(f.stage(ch, "move_in", 422, equipment_id=f.eq["id"]))
    assert f.ctx(ch)["next_stage"] is None
    assert (
        f.m.list("lot_history", lot=ch["id"], action="merge")["data"][0]["to_status"]
        == "merged"
    )


def test_merge_rules(client: TestClient, db: Session) -> None:
    f = _line(client, db)
    a, b, c = f.start(3, 3, 3)
    # different step / stage
    f.run_step(c)
    assert "different route step" in _msgs(merge(f, a, [c], 409))
    f.stage(b, "move_in", equipment_id=f.eq["id"])
    assert "different stage" in _msgs(merge(f, a, [b], 409))
    # hold blocks (not overridable)
    (d,) = f.start(3)
    f.post(f"{EXEC}/lots/{d['id']}/hold", {"reason_id": f.reasons["hold"]["id"]})
    r = merge(f, a, [d], 409, override=True, override_reason="x")
    assert "on hold" in _msgs(r)
    # different WO: blocked unless the rule allows it
    wo2 = f.m.post(
        "work_order",
        {"product_id": f.product["id"], "lot_type_id": f.lt["id"], "planned_qty": 100},
    )
    f.post(f"{API}/work-order/{wo2['id']}/transition", {"action": "release"})
    (e,) = f.post(f"{API}/work-order/{wo2['id']}/start", {"lots": [{"qty": 3}]})["data"]
    assert "different work order" in _msgs(merge(f, a, [e], 409))
    f.m.patch("split_merge_rule", f.rule["id"], {"merge_same_wo": False})  # type: ignore[attr-defined]
    assert merge(f, a, [e])["lot"]["qty"] == 6
    f.m.patch("split_merge_rule", f.rule["id"], {"allow_merge": False})  # type: ignore[attr-defined]
    (g,) = f.start(3)
    assert "merge not allowed" in _msgs(merge(f, a, [g], 409))


def test_merge_qtime_earliest_and_carrier_capacity(
    client: TestClient, db: Session
) -> None:
    f = _line(client, db, max_children=5)
    f.m.post(
        "qtime_rule",
        {
            "code": "QT",
            "name": "q",
            "route_id": f.route["id"],
            "from_step_id": f.steps[10]["id"],
            "to_step_id": f.steps[20]["id"],
            "max_minutes": 30,
            "reason_id": f.reasons["hold"]["id"],
        },
    )
    a, b = f.start(3, 3)
    f.run_step(a)
    f.run_step(b)
    f.sql(
        "UPDATE mes_lot_history SET at = at - interval '2 hours' WHERE lot_id = :l AND action = 'move_out'",
        l=a["id"],
    )
    assert not f.ctx(b)["qtime"][0]["exceeded"]
    merge(f, b, [a])
    assert f.ctx(b)["qtime"][0]["exceeded"]  # strictest (earliest) clock wins
    # carrier capacity
    ct = f.m.post(
        "carrier_type", {"code": "CT", "name": "ct", "category": "foup", "capacity": 4}
    )
    car = f.m.post(
        "carrier", {"code": "FP1", "name": "fp", "carrier_type_id": ct["id"]}
    )
    x, y = f.start(3, 3)
    f.sql("UPDATE mes_lot SET carrier_id = :c WHERE id = :l", c=car["id"], l=x["id"])
    assert "capacity 4" in _msgs(merge(f, x, [y], 409))
    # split child onto a carrier that is too small / busy
    (z,) = f.start(6)
    assert "capacity 4" in _msgs(
        split(
            f, z, [{"unit_ids": uid(f, z, 0, 1, 2, 3, 4), "carrier_id": car["id"]}], 409
        )
    )


def test_bound_checks_override_preview_and_perms(
    client: TestClient, db: Session
) -> None:
    f = _line(client, db)
    f.bind("split", ("wo_status", "block", {}))
    f.bind("merge", ("wo_status", "warn", {}))
    (lot,) = f.start(4)
    f.post(f"{API}/work-order/{f.wo['id']}/transition", {"action": "hold"})
    body = [{"unit_ids": uid(f, lot, 0, 1)}]
    r = split(f, lot, body, 409)
    assert any(
        x["check_type"] == "wo_status" and x["result"] == "block"
        for x in r["detail"]["results"]
    )
    pv = split(f, lot, body, preview=True)
    assert any(x["result"] == "block" for x in pv["results"]) and f.lot(lot)["qty"] == 4
    r = split(f, lot, body, override=True, override_reason="engineering approval")
    assert any(x["result"] == "overridden" for x in r["results"])
    logs = f.m.list("check_log", trigger="split", result="overridden")["data"]
    assert logs and logs[0]["override_reason"] == "engineering approval"
    # merge with a warn check passes
    (ch,) = r["children"]
    r = merge(f, lot, [ch])
    assert any(x["result"] == "warn" for x in r["results"])
    # member: no split / merge permission
    email, pw = random_email(), random_lower_string()
    crud.create_user(session=db, user_create=UserCreate(email=email, password=pw))
    client.post(
        f"{API[:-4]}/tenants/{f.m.tid}/members",
        headers=f.m.h,
        json={"email": email, "roles": ["member"]},
    )
    tok = client.post(
        f"{API[:-4]}/login/access-token", data={"username": email, "password": pw}
    ).json()["access_token"]
    hm = {"Authorization": f"Bearer {tok}", "X-Tenant-ID": f.m.tid}
    url = f"{EXEC}/lots/{lot['id']}"
    assert (
        client.post(f"{url}/split", headers=hm, json={"children": body}).status_code
        == 403
    )
    assert (
        client.post(
            f"{url}/merge", headers=hm, json={"source_lot_ids": [ch["id"]]}
        ).status_code
        == 403
    )
