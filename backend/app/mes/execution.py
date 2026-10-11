"""Lot execution: Move In -> Track In -> Track Out -> Move Out per route step.

Lot status: waiting -> moved_in -> running -> tracked_out -> (next step) waiting
... -> completed (last step) | scrapped (all units/qty scrapped).
Hold is orthogonal (`on_hold` + active mes_lot_hold rows) and blocks every stage.
Each step may auto-advance stages (route_step.auto_*); auto stages run the same
checks and stop silently at the first block / missing input.
Routing on Move Out: next step | manual branch (branch_to_seq) | rework route
(push frame, return to same/next step) | sub-route call/return (stack in
lot.route_stack); last step -> completed (+ WO completed_qty).
"""

import random
import uuid
from datetime import date, datetime
from typing import Any

import sqlalchemy as sa
from fastapi import HTTPException
from sqlmodel import Session

from app.mes import checks as ck
from app.mes import coderule
from app.mes.checks import Ctx, find, one
from app.mes.core import ENTITIES, TABLES, Entity
from app.mes.service import (
    MesError,
    audit,
    conn,
    http_422,
    now,
    serialize,
    to_json,
    validator,
)
from app.mes.uom import convert

Row = dict[str, Any]
LOT = ENTITIES["lot"]
STAGES = ["move_in", "track_in", "track_out", "move_out"]
FROM_STATUS = {
    "move_in": "waiting",
    "track_in": "moved_in",
    "track_out": "running",
    "move_out": "tracked_out",
}
TO_STATUS = {
    "move_in": "moved_in",
    "track_in": "running",
    "track_out": "tracked_out",
}
NEXT_STAGE = {
    "waiting": "move_in",
    "moved_in": "track_in",
    "running": "track_out",
    "tracked_out": "move_out",
}
TERMINAL = ("completed", "scrapped", "merged")
OOS_RANK = {"warn": 1, "rework": 2, "auto_hold": 3, "block": 4}


def _sys(user: Any, at: datetime) -> Row:
    return {
        "created_at": at,
        "updated_at": at,
        "created_by": getattr(user, "id", None),
        "updated_by": getattr(user, "id", None),
    }


def _upd(
    s: Session, tid: uuid.UUID, code: str, rid: Any, user: Any = None, **vals: Any
) -> None:
    t = TABLES[code]
    vals.setdefault("updated_at", now())
    if user is not None:
        vals.setdefault("updated_by", getattr(user, "id", None))
    conn(s).execute(
        sa.update(t).where(t.c.tenant_id == tid, t.c.id == rid).values(**vals)
    )


def _ins(s: Session, tid: uuid.UUID, ent: str, user: Any, **vals: Any) -> uuid.UUID:
    rid = uuid.uuid4()
    conn(s).execute(
        sa.insert(TABLES[ent]).values(
            id=rid, tenant_id=tid, **_sys(user, now()), **vals
        )
    )
    return rid


def history(
    s: Session,
    tid: uuid.UUID,
    lot: Row,
    action: str,
    user: Any,
    step: Row | None = None,
    **kw: Any,
) -> None:
    step = (
        step if step is not None else one(s, tid, "route_step", lot["current_step_id"])
    )
    if step:
        kw.setdefault("route_step_id", step["id"])
        kw.setdefault("step_seq", step["seq"])
        kw.setdefault("operation_id", step["operation_id"])
    kw.setdefault("qty", lot["qty"])
    kw.setdefault("to_status", lot["lot_status"])
    if "details" in kw:
        kw["details"] = ck.jsonable(kw["details"])
    _ins(
        s,
        tid,
        "lot_history",
        user,
        lot_id=lot["id"],
        action=action,
        user_email=getattr(user, "email", None),
        at=now(),
        **kw,
    )


def lock_lot(s: Session, tid: uuid.UUID, lot_id: uuid.UUID) -> Row:
    t = TABLES["lot"]
    r = (
        conn(s)
        .execute(
            sa.select(t).where(t.c.tenant_id == tid, t.c.id == lot_id).with_for_update()
        )
        .mappings()
        .first()
    )
    if not r:
        raise HTTPException(status_code=404, detail="Record not found")
    return dict(r)


def tracking_level(s: Session, tid: uuid.UUID, product: Row | None) -> str:
    if product and product.get("tracking_level"):
        return str(product["tracking_level"])
    node = product and one(s, tid, "tech_node", product["tech_node_id"])
    return str((node and node["tracking_level"]) or "wafer")


def units(s: Session, tid: uuid.UUID, lot_id: Any, active: bool = True) -> list[Row]:
    rows = find(s, tid, "wafer", order="code", lot_id=lot_id)
    rows.sort(key=lambda u: (u["slot"] or 0, u["code"]))
    return [u for u in rows if not active or u["wafer_status"] not in ("scrapped",)]


# ---------------- route navigation ----------------
def route_steps(s: Session, tid: uuid.UUID, route_id: Any) -> list[Row]:
    return find(s, tid, "route_step", order="seq", route_id=route_id)


def _after(s: Session, tid: uuid.UUID, step: Row) -> Row | None:
    return next(
        (x for x in route_steps(s, tid, step["route_id"]) if x["seq"] > step["seq"]),
        None,
    )


def _enter(
    s: Session, tid: uuid.UUID, step: Row | None, stack: list[Row], ev: list[Row]
) -> Row | None:
    """Descend into sub-routes until an operation step is reached."""
    depth = 0
    while step is not None and step["step_type"] == "sub_route" and depth < 10:
        sub = route_steps(s, tid, step["sub_route_id"])
        rt = one(s, tid, "route", step["sub_route_id"])
        if not sub:
            step = _after(s, tid, step)
            continue
        stack.append(
            {
                "kind": "sub_route",
                "route_id": str(step["route_id"]),
                "step_id": str(step["id"]),
            }
        )
        ev.append({"action": "sub_route", "route": rt and rt["code"], "step": step})
        step, depth = sub[0], depth + 1
    if step is None and stack:
        return _pop(s, tid, stack, ev)
    return step


def _pop(s: Session, tid: uuid.UUID, stack: list[Row], ev: list[Row]) -> Row | None:
    """Leave the current sub/rework route (end reached)."""
    while stack:
        fr = stack.pop()
        caller = one(s, tid, "route_step", uuid.UUID(fr["step_id"]))
        if caller is None:
            continue
        ev.append({"action": "return", "kind": fr["kind"], "step": caller})
        if fr["kind"] == "rework" and fr.get("return", "same_step") == "same_step":
            return caller
        nxt = _after(s, tid, caller)
        if nxt is not None:
            return _enter(s, tid, nxt, stack, ev)
    return None


def next_location(
    s: Session, tid: uuid.UUID, lot: Row, step: Row, *, branch: bool, rework: bool
) -> tuple[Row | None, list[Row], list[Row]]:
    stack: list[Row] = list(lot.get("route_stack") or [])
    ev: list[Row] = []
    if rework:
        if not step["rework_route_id"]:
            raise http_422([("rework", "rework: this step has no rework route")])
        steps = route_steps(s, tid, step["rework_route_id"])
        if not steps:
            raise http_422([("rework", "rework: rework route has no steps")])
        rt = one(s, tid, "route", step["rework_route_id"])
        stack.append(
            {
                "kind": "rework",
                "route_id": str(step["route_id"]),
                "step_id": str(step["id"]),
                "return": step["rework_return"] or "same_step",
            }
        )
        ev.append({"action": "rework", "route": rt and rt["code"], "step": step})
        return _enter(s, tid, steps[0], stack, ev), stack, ev
    if branch:
        if step["branch_to_seq"] is None:
            raise http_422([("branch", "branch: this step has no branch")])
        tgt = next(
            (
                x
                for x in route_steps(s, tid, step["route_id"])
                if x["seq"] == step["branch_to_seq"]
            ),
            None,
        )
        if tgt is None:
            raise http_422(
                [("branch", f"branch: target seq {step['branch_to_seq']} not found")]
            )
        ev.append(
            {
                "action": "branch",
                "condition": step["branch_condition"],
                "to_seq": tgt["seq"],
                "step": step,
            }
        )
        return _enter(s, tid, tgt, stack, ev), stack, ev
    nxt = _after(s, tid, step)
    if nxt is not None:
        return _enter(s, tid, nxt, stack, ev), stack, ev
    return _pop(s, tid, stack, ev), stack, ev


# ---------------- holds ----------------
def default_reason(s: Session, tid: uuid.UUID, rtype: str) -> Row:
    rs = [
        r
        for r in find(s, tid, "reason_code", order="code", reason_type=rtype)
        if r["is_active"]
    ]
    if not rs:
        raise http_422(
            [("reason", f"reason: no active {rtype} reason code configured")]
        )
    return rs[0]


def _reason(
    s: Session, tid: uuid.UUID, rid: Any, rtype: str, field: str = "reason_id"
) -> Row:
    r = one(s, tid, "reason_code", rid)
    if not r or r["reason_type"] != rtype:
        raise http_422([(field, f"{field}: a {rtype} reason code is required")])
    return r


def hold_lot(
    s: Session,
    tid: uuid.UUID,
    lot: Row,
    user: Any,
    reason: Row,
    *,
    hold_type: str = "manual",
    source: str = "manual",
    comment: str | None = None,
    details: Row | None = None,
) -> uuid.UUID:
    hid = _ins(
        s,
        tid,
        "lot_hold",
        user,
        lot_id=lot["id"],
        reason_id=reason["id"],
        hold_type=hold_type,
        source=source,
        comment=(comment or "")[:300] or None,
        is_active=True,
        held_at=now(),
        held_by=getattr(user, "email", None) or "system",
        route_step_id=lot["current_step_id"],
    )
    _upd(s, tid, "lot", lot["id"], user, on_hold=True)
    lot["on_hold"] = True
    history(
        s,
        tid,
        lot,
        "hold",
        user,
        reason_id=reason["id"],
        comment=comment,
        details={"source": source, "hold_type": hold_type, **(details or {})},
    )
    audit(
        s,
        tid,
        LOT,
        "hold",
        lot,
        user,
        {"reason": (None, reason["code"]), "source": (None, source)},
    )
    return hid


def release_hold(
    s: Session,
    tid: uuid.UUID,
    hold_id: uuid.UUID,
    user: Any,
    reason_id: Any,
    comment: str | None,
) -> Row:
    h = one(s, tid, "lot_hold", hold_id)
    if not h:
        raise HTTPException(status_code=404, detail="Record not found")
    if not h["is_active"]:
        raise http_422([("hold", "hold: already released")])
    rr = (
        _reason(s, tid, reason_id, "release", "release_reason_id")
        if reason_id
        else None
    )
    _upd(
        s,
        tid,
        "lot_hold",
        hold_id,
        user,
        is_active=False,
        released_at=now(),
        released_by=getattr(user, "email", None),
        release_reason_id=rr and rr["id"],
        release_comment=(comment or "")[:300] or None,
    )
    lot = lock_lot(s, tid, h["lot_id"])
    left = [
        x
        for x in find(s, tid, "lot_hold", lot_id=lot["id"], is_active=True)
        if x["id"] != hold_id
    ]
    _upd(s, tid, "lot", lot["id"], user, on_hold=bool(left))
    lot["on_hold"] = bool(left)
    history(
        s,
        tid,
        lot,
        "release",
        user,
        reason_id=rr and rr["id"],
        comment=comment,
        details={"hold_id": str(hold_id), "remaining_holds": len(left)},
    )
    audit(s, tid, LOT, "resume", lot, user, {"release": (None, rr and rr["code"])})
    s.commit()
    return lot


# ---------------- E10 ----------------
def e10_apply(
    s: Session, tid: uuid.UUID, eq: Row, trigger: str, user: Any, lot: Row
) -> Row | None:
    if trigger == "track_out":
        t = TABLES["lot"]
        others = (
            conn(s)
            .execute(
                sa.select(sa.func.count()).where(
                    t.c.tenant_id == tid,
                    t.c.equipment_id == eq["id"],
                    t.c.lot_status == "running",
                    t.c.id != lot["id"],
                )
            )
            .scalar()
        )
        if others:
            return {"skipped": f"{others} other lot(s) running"}
    rules = find(s, tid, "e10_auto_rule", trigger=trigger, is_active=True)
    rule = next(
        (r for r in rules if r["equipment_type_id"] == eq.get("equipment_type_id")),
        None,
    ) or next((r for r in rules if r["equipment_type_id"] is None), None)
    if not rule:
        return None
    cur = ck.e10_current(s, tid, eq)
    to = one(s, tid, "e10_state", rule["to_state_id"])
    if not to or (cur and cur["id"] == to["id"]):
        return None
    if cur and not find(
        s, tid, "e10_transition", from_state_id=cur["id"], to_state_id=to["id"]
    ):
        return {"skipped": f"transition {cur['code']} -> {to['code']} not allowed"}
    _upd(s, tid, "equipment", eq["id"], user, e10_state_id=to["id"])
    audit(
        s,
        tid,
        ENTITIES["equipment"],
        "e10",
        eq,
        user,
        {"e10_state": (cur and cur["code"], to["code"])},
    )
    return {"equipment": eq["code"], "from": cur and cur["code"], "to": to["code"]}


# ---------------- sampling / DC ----------------
def dc_plan_for(s: Session, tid: uuid.UUID, op_id: Any) -> Row | None:
    ps = [
        p
        for p in find(s, tid, "dc_plan", operation_id=op_id)
        if p["status"] == "active"
    ]
    return max(ps, key=lambda p: p["version"]) if ps else None


def sampling(s: Session, tid: uuid.UUID, lot: Row, step: Row, us: list[Row]) -> Row:
    op_id = step["operation_id"]
    if not op_id:
        return {
            "sampled": False,
            "items": [],
            "unit_ids": [],
            "message": "no operation",
        }
    rules = [
        r
        for r in find(s, tid, "sampling_rule", operation_id=op_id)
        if r["is_active"] and r["product_id"] in (None, lot["product_id"])
    ]
    rules.sort(key=lambda r: r["product_id"] is None)
    rule = rules[0] if rules else None
    plan = (
        one(s, tid, "dc_plan", rule["dc_plan_id"])
        if rule and rule["dc_plan_id"]
        else None
    ) or dc_plan_for(s, tid, op_id)
    if not plan:
        return {"sampled": False, "items": [], "unit_ids": [], "message": "no DC plan"}
    sampled, unit_ids, msg = True, [], "every lot (no sampling rule)"
    if rule:
        h = TABLES["lot_history"]
        n = (
            conn(s)
            .execute(
                sa.select(sa.func.count(sa.distinct(h.c.lot_id))).where(
                    h.c.tenant_id == tid,
                    h.c.operation_id == op_id,
                    h.c.action == "track_out",
                    h.c.lot_id != lot["id"],
                )
            )
            .scalar()
            or 0
        )
        freq = max(1, rule["lot_frequency"] or 1)
        sampled = n % freq == 0
        msg = f"rule {rule['code']}: lot {n + 1}, every {freq} → {'sampled' if sampled else 'skipped'}"
        if sampled and rule["level"] == "wafer" and us:
            k = min(len(us), rule["wafer_count"] or 1)
            sel = rule["wafer_selection"] or "first"
            if sel == "last":
                pick = us[-k:]
            elif sel == "alternate":
                pick = us[::2][:k]
            elif sel == "fixed":
                slots = {
                    int(x)
                    for x in (rule["fixed_slots"] or "").replace(" ", "").split(",")
                    if x.isdigit()
                }
                pick = [u for u in us if u["slot"] in slots]
            elif sel == "random":
                pick = sorted(
                    random.Random(lot["code"]).sample(us, k),
                    key=lambda u: u["slot"] or 0,
                )
            else:
                pick = us[:k]
            unit_ids = [str(u["id"]) for u in pick]
    items = []
    for it in find(s, tid, "dc_plan_item", order="seq", dc_plan_id=plan["id"]):
        mi = one(s, tid, "measurement_item", it["measurement_item_id"])
        if mi:
            items.append(
                {
                    "measurement_item_id": str(mi["id"]),
                    "code": mi["code"],
                    "name": mi["name"],
                    "meas_type": mi["meas_type"],
                    "lsl": it["lsl"],
                    "usl": it["usl"],
                    "target": it["target"],
                    "sites": it["sites"],
                    "oos_action": mi["oos_action"],
                }
            )
    return {
        "sampled": sampled,
        "rule": rule and rule["code"],
        "dc_plan_id": str(plan["id"]),
        "dc_plan": plan["code"],
        "unit_ids": unit_ids,
        "items": items,
        "message": msg,
    }


def _oos(it: Row, v: float) -> bool:
    return (it["lsl"] is not None and v < it["lsl"]) or (
        it["usl"] is not None and v > it["usl"]
    )


# ---------------- materials ----------------
def material_needs(
    s: Session, tid: uuid.UUID, step: Row, lot: Row, chosen: list[Row], at: datetime
) -> list[Row]:
    out = []
    for r in find(s, tid, "step_resource", route_step_id=step["id"]):
        if r["resource_kind"] != "material" or not r["material_id"] or not r["qty"]:
            continue
        need = float(r["qty"]) * (lot["qty"] if r["qty_basis"] == "per_unit" else 1)
        mat = one(s, tid, "material", r["material_id"])
        cands = [
            m for m in chosen if m["material_id"] == r["material_id"]
        ] or candidate_lots(s, tid, r["material_id"], at)
        alloc, have, total = [], 0.0, 0.0
        for m in cands:
            if m["ml_status"] != "available" or (
                m["expiry_date"] and m["expiry_date"] < at.date()
            ):
                continue
            q = float(m["qty_remaining"] or 0)
            if r["uom_id"] and m["uom_id"] != r["uom_id"]:
                try:
                    q = convert(s, tid, m["uom_id"], r["uom_id"], q)["value"]
                except HTTPException:
                    continue
            total += q
            take = min(q, need - have)
            if take > 1e-12:
                alloc.append(
                    {
                        "material_lot_id": m["id"],
                        "code": m["code"],
                        "qty": take,
                        "uom_id": m["uom_id"],
                        "req_uom_id": r["uom_id"],
                    }
                )
                have += take
        out.append(
            {
                "resource_id": r["id"],
                "material_id": r["material_id"],
                "material_code": mat and mat["code"],
                "need": need,
                "uom_id": r["uom_id"],
                "basis": r["qty_basis"],
                "available": total,
                "allocation": alloc,
            }
        )
    return out


def candidate_lots(
    s: Session, tid: uuid.UUID, material_id: Any, at: datetime
) -> list[Row]:
    """Usable lots of a material, first-expiry-first-out."""
    ls = [
        m
        for m in find(s, tid, "material_lot", material_id=material_id)
        if m["ml_status"] == "available"
        and (m["qty_remaining"] or 0) > 0
        and not (m["expiry_date"] and m["expiry_date"] < at.date())
    ]
    return sorted(ls, key=lambda m: (m["expiry_date"] or date.max, m["code"]))


def _consume(s: Session, tid: uuid.UUID, needs: list[Row], user: Any) -> list[Row]:
    out = []
    for n in needs:
        for a in n["allocation"]:
            m = one(s, tid, "material_lot", a["material_lot_id"])
            assert m
            q = a["qty"]
            if a["req_uom_id"] and m["uom_id"] != a["req_uom_id"]:
                q = convert(s, tid, a["req_uom_id"], m["uom_id"], q)["value"]
            left = max(0.0, round(float(m["qty_remaining"]) - q, 9))
            _upd(
                s,
                tid,
                "material_lot",
                m["id"],
                user,
                qty_remaining=left,
                ml_status="empty" if left <= 0 else m["ml_status"],
            )
            out.append({"material_lot": m["code"], "qty": round(q, 6), "left": left})
    return out


# ---------------- context ----------------
def _rows(s: Session, tid: uuid.UUID, code: str, ids: list[Any] | None) -> list[Row]:
    return [r for r in (one(s, tid, code, uuid.UUID(str(i))) for i in (ids or [])) if r]


def build_ctx(s: Session, tid: uuid.UUID, lot: Row, trigger: str, body: Row) -> Ctx:
    step = one(s, tid, "route_step", lot["current_step_id"])
    if not step:
        raise http_422([("lot", "lot: no current step")])
    xc = lot.get("exec_ctx") or {}
    eq_id = body.get("equipment_id") or lot.get("equipment_id")
    eq = one(s, tid, "equipment", eq_id)
    if eq_id and not eq:
        raise http_422([("equipment_id", "equipment_id: not found")])
    rc = one(s, tid, "recipe", body.get("recipe_id") or lot.get("recipe_id"))
    rt = one(s, tid, "reticle", body.get("reticle_id") or xc.get("reticle_id"))
    car = one(s, tid, "carrier", body.get("carrier_id") or lot.get("carrier_id"))
    tools = _rows(s, tid, "tool", body.get("tool_ids") or xc.get("tool_ids"))
    mls = _rows(
        s,
        tid,
        "material_lot",
        body.get("material_lot_ids") or xc.get("material_lot_ids"),
    )
    ctx = Ctx(
        s=s,
        tid=tid,
        trigger=trigger,
        lot=lot,
        step=step,
        op=one(s, tid, "operation", step["operation_id"]),
        product=one(s, tid, "product", lot["product_id"]),
        wo=one(s, tid, "work_order", lot["work_order_id"]),
        equipment=eq,
        recipe=rc,
        reticle=rt,
        carrier=car,
        tools=tools,
        material_lots=mls,
    )
    ctx.material_needs = material_needs(s, tid, step, lot, mls, ctx.at)
    ctx.sampling = sampling(s, tid, lot, step, units(s, tid, lot["id"]))
    return ctx


def context(s: Session, tid: uuid.UUID, lot_id: uuid.UUID) -> Row:
    """Everything the operation console needs for the lot's current stage."""
    lot = one(s, tid, "lot", lot_id)
    if not lot:
        raise HTTPException(status_code=404, detail="Record not found")
    step = one(s, tid, "route_step", lot["current_step_id"])
    out: Row = {
        "lot": serialize(s, tid, LOT, [lot])[0],
        "next_stage": None
        if lot["lot_status"] in TERMINAL
        else NEXT_STAGE.get(lot["lot_status"]),
    }
    us = units(s, tid, lot["id"], active=False)
    out["units"] = [
        {
            "id": str(u["id"]),
            "code": u["code"],
            "slot": u["slot"],
            "status": u["wafer_status"],
            "unit_kind": u["unit_kind"],
            "rework_count": u["rework_count"],
        }
        for u in us
    ]
    out["holds"] = serialize(
        s,
        tid,
        ENTITIES["lot_hold"],
        find(s, tid, "lot_hold", lot_id=lot["id"], is_active=True),
    )
    out["reasons"] = {
        k: [
            {"id": str(r["id"]), "code": r["code"], "name": r["name"]}
            for r in find(s, tid, "reason_code", order="code", reason_type=k)
            if r["is_active"]
        ]
        for k in ("hold", "release", "scrap", "rework")
    }
    out["stack"] = lot.get("route_stack") or []
    if not step:
        return out
    rt = one(s, tid, "route", step["route_id"])
    op = one(s, tid, "operation", step["operation_id"])
    rw = one(s, tid, "route", step["rework_route_id"])
    out["step"] = {
        "id": str(step["id"]),
        "seq": step["seq"],
        "route_id": str(step["route_id"]),
        "route": rt and f"{rt['code']} v{rt['version']}",
        "operation": op
        and {"id": str(op["id"]), "code": op["code"], "name": op["name"]},
        "branch_to_seq": step["branch_to_seq"],
        "branch_condition": step["branch_condition"],
        "rework_route": rw and f"{rw['code']} v{rw['version']}",
        "rework_return": step["rework_return"],
        "auto": {k: bool(step[f"auto_{k}"]) for k in STAGES},
        "is_last": _after(s, tid, step) is None and not (lot.get("route_stack") or []),
    }
    res = find(s, tid, "step_resource", route_step_id=step["id"])
    ctx = Ctx(s=s, tid=tid, trigger="move_in", lot=lot, step=step, op=op)
    eq_ids = ck.allowed_equipment_ids(ctx)
    if not eq_ids and op:
        eq_ids = {
            c["equipment_id"]
            for c in find(s, tid, "equipment_capability", operation_id=op["id"])
        }
    eqs = (
        [e for e in (one(s, tid, "equipment", i) for i in eq_ids) if e]
        if eq_ids
        else [
            e
            for e in find(s, tid, "equipment", order="code", unit_kind="main")
            if e["is_active"]
        ]
    )

    def _eq(e: Row) -> Row:
        st = ck.e10_current(s, tid, e)
        return {
            "id": str(e["id"]),
            "code": e["code"],
            "name": e["name"],
            "state": st and st["code"],
            "category": st and st["e10_category"],
            "color": st and st["color"],
        }

    out["equipment"] = sorted((_eq(e) for e in eqs), key=lambda x: x["code"])
    rids = {r["recipe_id"] for r in res if r["recipe_id"]}
    out["recipes"] = [
        {
            "id": str(r["id"]),
            "code": r["code"],
            "name": r["name"],
            "version": r["version"],
            "status": r["status"],
            "equipment_type_id": str(r["equipment_type_id"]),
        }
        for r in (one(s, tid, "recipe", i) for i in rids)
        if r
    ]
    out["reticles"] = [
        {"id": str(r["id"]), "code": r["code"], "status": r["status_code"]}
        for r in (
            one(s, tid, "reticle", x["reticle_id"])
            for x in res
            if x["resource_kind"] == "reticle" and x["reticle_id"]
        )
        if r
    ]
    out["tools"] = []
    for x in res:
        if x["resource_kind"] == "fixture" and x["fixture_id"]:
            fx = one(s, tid, "fixture", x["fixture_id"])
            opts = []
            for t in find(s, tid, "tool", order="code", fixture_id=x["fixture_id"]):
                mx, used = ck.tool_life(s, tid, t)
                opts.append(
                    {
                        "id": str(t["id"]),
                        "code": t["code"],
                        "status": t["tool_status"],
                        "usage": used,
                        "max": mx,
                        "expiry": to_json(t["expiry_date"]),
                        "warn_pct": t["warn_pct"],
                    }
                )
            out["tools"].append(
                {
                    "fixture": fx
                    and {"id": str(fx["id"]), "code": fx["code"], "name": fx["name"]},
                    "options": opts,
                }
            )
    at = now()
    out["materials"] = []
    for n in material_needs(s, tid, step, lot, [], at):
        uom = one(s, tid, "uom", n["uom_id"])
        out["materials"].append(
            {
                "material_id": str(n["material_id"]),
                "material": n["material_code"],
                "need": n["need"],
                "basis": n["basis"],
                "uom": uom and uom["code"],
                "options": [
                    {
                        "id": str(m["id"]),
                        "code": m["code"],
                        "qty": m["qty_remaining"],
                        "expiry": to_json(m["expiry_date"]),
                        "location": m["location"],
                    }
                    for m in candidate_lots(s, tid, n["material_id"], at)
                ],
            }
        )
    out["dc"] = sampling(s, tid, lot, step, units(s, tid, lot["id"]))
    out["qtime"] = [
        {
            "rule": x["rule"]["code"],
            "minutes": x["minutes"],
            "min": x["rule"]["min_minutes"],
            "max": x["rule"]["max_minutes"],
            "exceeded": x["exceeded"],
            "too_early": x["too_early"],
        }
        for x in ck.qtime_status(s, tid, lot, step, at)
    ]
    out["tracking_level"] = lot["tracking_level"] or "wafer"
    out["exec_ctx"] = lot.get("exec_ctx") or {}
    return out


# ---------------- stages ----------------
def _guard(lot: Row, stage: str) -> None:
    if lot["lot_status"] in TERMINAL:
        raise http_422([("lot_status", f"lot_status: lot is {lot['lot_status']}")])
    if lot["on_hold"]:
        raise http_422([("on_hold", "on_hold: lot is on hold; release it first")])
    if lot["lot_status"] != FROM_STATUS[stage]:
        raise http_422(
            [("lot_status", f"lot_status: cannot {stage} a {lot['lot_status']} lot")]
        )


def _qtime_actions(
    s: Session, tid: uuid.UUID, lot: Row, step: Row, user: Any
) -> str | None:
    """Apply max-Q-Time violation actions once per violation; returns outcome."""
    h = TABLES["lot_history"]
    for x in ck.qtime_status(s, tid, lot, step, now()):
        if not x["exceeded"]:
            continue
        r = x["rule"]
        done = (
            conn(s)
            .execute(
                sa.select(h.c.details).where(
                    h.c.tenant_id == tid,
                    h.c.lot_id == lot["id"],
                    h.c.action == "qtime",
                    h.c.at >= x["since"],
                )
            )
            .scalars()
            .all()
        )
        if any((d or {}).get("rule_id") == str(r["id"]) for d in done):
            continue
        action = r["action"] or "hold"
        det = {
            "rule_id": str(r["id"]),
            "rule": r["code"],
            "minutes": x["minutes"],
            "max": r["max_minutes"],
            "action": action,
        }
        history(s, tid, lot, "qtime", user, reason_id=r["reason_id"], details=det)
        if action == "warn":
            continue
        if action == "rework" and step["rework_route_id"]:
            _relocate(
                s,
                tid,
                lot,
                step,
                user,
                rework=True,
                branch=False,
                record_move_out=False,
            )
            return "rework"
        if action == "scrap":
            reason = one(s, tid, "reason_code", r["reason_id"]) or default_reason(
                s, tid, "scrap"
            )
            for u in units(s, tid, lot["id"]):
                _upd(
                    s,
                    tid,
                    "wafer",
                    u["id"],
                    user,
                    wafer_status="scrapped",
                    scrap_reason_id=reason["id"],
                )
            _upd(
                s,
                tid,
                "lot",
                lot["id"],
                user,
                lot_status="scrapped",
                scrapped_qty=(lot["scrapped_qty"] or 0) + lot["qty"],
                qty=0,
            )
            lot.update(lot_status="scrapped", qty=0)
            history(
                s,
                tid,
                lot,
                "scrap",
                user,
                reason_id=reason["id"],
                details={"source": "qtime", "rule": r["code"]},
            )
            return "scrap"
        reason = one(s, tid, "reason_code", r["reason_id"]) or default_reason(
            s, tid, "hold"
        )
        hold_lot(
            s,
            tid,
            lot,
            user,
            reason,
            hold_type="auto",
            source="qtime",
            comment=f"Q-Time {r['code']}: {x['minutes']:g} > {r['max_minutes']} min",
            details=det,
        )
        return "hold"
    return None


def _result(
    s: Session, tid: uuid.UUID, lot_id: Any, results: list[Row], **extra: Any
) -> Row:
    lot = one(s, tid, "lot", lot_id)
    return {
        "lot": serialize(s, tid, LOT, [lot])[0] if lot else None,
        "results": results,
        **extra,
    }


def move_in(s: Session, tid: uuid.UUID, lot_id: uuid.UUID, body: Row, user: Any) -> Row:
    lot = lock_lot(s, tid, lot_id)
    _guard(lot, "move_in")
    step = one(s, tid, "route_step", lot["current_step_id"])
    assert step
    q = _qtime_actions(s, tid, lot, step, user)
    if q:
        s.commit()
        return _result(s, tid, lot_id, [], qtime=q)
    ctx = build_ctx(s, tid, lot, "move_in", body)
    if ctx.equipment and ctx.equipment["unit_kind"] != "main":
        raise http_422([("equipment_id", "equipment_id: select a main equipment unit")])
    results = ck.evaluate(
        ctx,
        user,
        override=body.get("override", False),
        reason=body.get("override_reason"),
    )
    eq = ctx.equipment
    _upd(
        s,
        tid,
        "lot",
        lot["id"],
        user,
        lot_status="moved_in",
        equipment_id=eq and eq["id"],
        stage_at=now(),
    )
    lot.update(lot_status="moved_in", equipment_id=eq and eq["id"])
    history(
        s,
        tid,
        lot,
        "move_in",
        user,
        step=step,
        from_status="waiting",
        equipment_id=eq and eq["id"],
        details={"checks": _brief(results), **_ov(body, results)},
    )
    audit(s, tid, LOT, "move_in", lot, user, {"lot_status": ("waiting", "moved_in")})
    s.commit()
    return _result(s, tid, lot_id, results)


def track_in(
    s: Session, tid: uuid.UUID, lot_id: uuid.UUID, body: Row, user: Any
) -> Row:
    lot = lock_lot(s, tid, lot_id)
    _guard(lot, "track_in")
    ctx = build_ctx(s, tid, lot, "track_in", body)
    eq = ctx.equipment
    errs: list[tuple[str, str]] = []
    if not eq and ck.allowed_equipment_ids(ctx):
        errs.append(("equipment_id", "equipment_id: required for track in"))
    elif eq and (eq["unit_kind"] != "main" or not eq["is_active"]):
        errs.append(
            ("equipment_id", "equipment_id: select an active main equipment unit")
        )
    if not ctx.recipe and any(r["recipe_id"] for r in ctx.resources()):
        errs.append(("recipe_id", "recipe_id: required at this step"))
    for fid in {r["fixture_id"] for r in ctx.resources("fixture") if r["fixture_id"]}:
        if not any(t["fixture_id"] == fid for t in ctx.tools):
            fx = one(s, tid, "fixture", fid)
            errs.append(
                ("tool_ids", f"tool_ids: a {fx and fx['code']} tool is required")
            )
    if errs:
        raise http_422(errs)
    eid = eq and eq["id"]
    results = ck.evaluate(
        ctx,
        user,
        override=body.get("override", False),
        reason=body.get("override_reason"),
    )
    xc = {
        "reticle_id": ctx.reticle and str(ctx.reticle["id"]),
        "tool_ids": [str(t["id"]) for t in ctx.tools],
        "material_lot_ids": [str(m["id"]) for m in ctx.material_lots],
    }
    for t in ctx.tools:
        _upd(s, tid, "tool", t["id"], user, tool_status="in_use", equipment_id=eid)
    if ctx.carrier and ctx.carrier["id"] != lot["carrier_id"]:
        _upd(s, tid, "lot", lot["id"], user, carrier_id=ctx.carrier["id"])
    for u in units(s, tid, lot["id"]):
        _upd(s, tid, "wafer", u["id"], user, wafer_status="processing")
    _upd(
        s,
        tid,
        "lot",
        lot["id"],
        user,
        lot_status="running",
        equipment_id=eid,
        recipe_id=ctx.recipe and ctx.recipe["id"],
        exec_ctx=xc,
        stage_at=now(),
    )
    lot.update(lot_status="running", equipment_id=eid)
    e10 = e10_apply(s, tid, eq, "track_in", user, lot) if eq else None
    history(
        s,
        tid,
        lot,
        "track_in",
        user,
        step=ctx.step,
        from_status="moved_in",
        equipment_id=eid,
        recipe_id=ctx.recipe and ctx.recipe["id"],
        details={
            "checks": _brief(results),
            "tools": [t["code"] for t in ctx.tools],
            "reticle": ctx.reticle and ctx.reticle["code"],
            "carrier": ctx.carrier and ctx.carrier["code"],
            "e10": e10,
            **_ov(body, results),
        },
    )
    audit(
        s,
        tid,
        LOT,
        "track_in",
        lot,
        user,
        {"lot_status": ("moved_in", "running"), "equipment": (None, eq and eq["code"])},
    )
    s.commit()
    return _result(s, tid, lot_id, results, e10=e10)


def track_out(
    s: Session, tid: uuid.UUID, lot_id: uuid.UUID, body: Row, user: Any
) -> Row:
    lot = lock_lot(s, tid, lot_id)
    _guard(lot, "track_out")
    ctx = build_ctx(s, tid, lot, "track_out", body)
    level = lot["tracking_level"] or "wafer"
    us = {str(u["id"]): u for u in units(s, tid, lot["id"])}
    errs: list[tuple[str, str]] = []
    # scrap / rework
    scrap_units: list[tuple[Row, Row]] = []
    scrap_qty: list[tuple[int, Row]] = []
    for i, x in enumerate(body.get("scrap") or [], 1):
        r = one(s, tid, "reason_code", x.get("reason_id"))
        if not r or r["reason_type"] != "scrap":
            errs.append(
                (f"scrap.{i}.reason_id", f"scrap {i}: a scrap reason code is required")
            )
            continue
        if level == "quantity":
            n = int(x.get("qty") or 0)
            if n < 1:
                errs.append((f"scrap.{i}.qty", f"scrap {i}: qty must be >= 1"))
            scrap_qty.append((n, r))
        else:
            u = us.get(str(x.get("unit_id")))
            if not u:
                errs.append((f"scrap.{i}.unit_id", f"scrap {i}: unit not in this lot"))
            else:
                scrap_units.append((u, r))
    if level == "quantity" and sum(n for n, _ in scrap_qty) > lot["qty"]:
        errs.append(("scrap", f"scrap: total exceeds lot qty {lot['qty']}"))
    if len({u["id"] for u, _ in scrap_units}) != len(scrap_units):
        errs.append(("scrap", "scrap: a unit is listed twice"))
    rework_units: list[tuple[Row, Row]] = []
    for i, x in enumerate(body.get("rework_units") or [], 1):
        r = one(s, tid, "reason_code", x.get("reason_id"))
        u = us.get(str(x.get("unit_id")))
        if not r or r["reason_type"] != "rework" or not u:
            errs.append(
                (
                    f"rework_units.{i}",
                    f"rework {i}: unit of this lot + rework reason required",
                )
            )
        else:
            rework_units.append((u, r))
    # DC values
    smp = ctx.sampling or {}
    items = {it["measurement_item_id"]: it for it in smp.get("items") or []}
    dc: list[Row] = []
    for i, d in enumerate(body.get("dc") or [], 1):
        it = items.get(str(d.get("measurement_item_id")))
        if not it:
            errs.append((f"dc.{i}", f"dc {i}: measurement item not in the DC plan"))
            continue
        if d.get("value") is None or d.get("value") == "":
            continue
        try:
            v = float(d["value"])
        except TypeError, ValueError:
            errs.append((f"dc.{i}.value", f"dc {i}: value must be a number"))
            continue
        uid = d.get("unit_id")
        if uid and str(uid) not in {str(k) for k in us}:
            errs.append((f"dc.{i}.unit_id", f"dc {i}: unit not in this lot"))
            continue
        dc.append(
            {
                "measurement_item_id": uuid.UUID(it["measurement_item_id"]),
                "unit_id": uuid.UUID(str(uid)) if uid else None,
                "site_no": int(d.get("site_no") or 1),
                "value": v,
                "is_oos": _oos(it, v),
                "oos_action": it["oos_action"],
                "code": it["code"],
            }
        )
    if errs:
        raise http_422(errs)
    ctx.dc = dc
    # material: hard requirement (cannot be overridden)
    short = [
        n
        for n in ctx.material_needs
        if sum(a["qty"] for a in n["allocation"]) + 1e-9 < n["need"]
    ]
    if short:
        raise http_422(
            [
                (
                    "material_lot_ids",
                    "material_lot_ids: insufficient "
                    + "; ".join(
                        f"{n['material_code']} need {n['need']:g}" for n in short
                    ),
                )
            ]
        )
    oos = [d for d in dc if d["is_oos"]]
    worst = max(
        (d["oos_action"] for d in oos), key=lambda a: OOS_RANK.get(a, 0), default=None
    )
    extra = []
    if oos:
        msg = "; ".join(f"{d['code']}={d['value']:g}" for d in oos[:6])
        extra.append(
            ck.result(
                "oos",
                "fail" if worst == "block" else "warn",
                f"OOS ({worst}): {msg}",
                severity="block" if worst == "block" else "warn",
                data={"action": worst, "values": len(oos)},
            )
        )
    results = ck.evaluate(
        ctx,
        user,
        extra=extra,
        override=body.get("override", False),
        reason=body.get("override_reason"),
    )
    at, email = now(), getattr(user, "email", None)
    for d in dc:
        _ins(
            s,
            tid,
            "dc_result",
            user,
            lot_id=lot["id"],
            unit_id=d["unit_id"],
            route_step_id=ctx.step["id"],
            dc_plan_id=uuid.UUID(smp["dc_plan_id"]),
            measurement_item_id=d["measurement_item_id"],
            site_no=d["site_no"],
            value=d["value"],
            is_oos=d["is_oos"],
            oos_action=d["oos_action"] if d["is_oos"] else None,
            user_email=email,
        )
    consumed = _consume(s, tid, ctx.material_needs, user)
    tools = []
    for t in ctx.tools:
        mx, used = ck.tool_life(s, tid, t)
        used += 1
        st = "available"
        if mx and used >= mx:
            st = "pending_maintenance"
        if t["expiry_date"] and t["expiry_date"] < at.date():
            st = "expired"
        _upd(s, tid, "tool", t["id"], user, usage_count=used, tool_status=st)
        tools.append({"tool": t["code"], "usage": used, "max": mx, "status": st})
    n_scrap = len(scrap_units) + sum(n for n, _ in scrap_qty)
    for u, r in scrap_units:
        _upd(
            s,
            tid,
            "wafer",
            u["id"],
            user,
            wafer_status="scrapped",
            scrap_reason_id=r["id"],
        )
        history(
            s,
            tid,
            lot,
            "scrap",
            user,
            step=ctx.step,
            unit_id=u["id"],
            qty=1,
            reason_id=r["id"],
            equipment_id=lot["equipment_id"],
        )
    for n, r in scrap_qty:
        history(
            s,
            tid,
            lot,
            "scrap",
            user,
            step=ctx.step,
            qty=n,
            reason_id=r["id"],
            equipment_id=lot["equipment_id"],
        )
    for u, r in rework_units:
        _upd(
            s,
            tid,
            "wafer",
            u["id"],
            user,
            wafer_status="rework",
            rework_count=(u["rework_count"] or 0) + 1,
        )
        history(
            s,
            tid,
            lot,
            "rework",
            user,
            step=ctx.step,
            unit_id=u["id"],
            qty=1,
            reason_id=r["id"],
        )
    scrapped = {u["id"] for u, _ in scrap_units} | {u["id"] for u, _ in rework_units}
    for u in us.values():
        if u["id"] not in scrapped and u["wafer_status"] == "processing":
            _upd(s, tid, "wafer", u["id"], user, wafer_status="waiting")
    qty = lot["qty"] - n_scrap
    status = "tracked_out" if qty > 0 else "scrapped"
    pending = bool(rework_units) or worst == "rework"
    _upd(
        s,
        tid,
        "lot",
        lot["id"],
        user,
        lot_status=status,
        qty=qty,
        scrapped_qty=(lot["scrapped_qty"] or 0) + n_scrap,
        stage_at=at,
        pending_rework=pending and bool(ctx.step["rework_route_id"]),
    )
    lot.update(lot_status=status, qty=qty)
    eq = one(s, tid, "equipment", lot["equipment_id"])
    e10 = e10_apply(s, tid, eq, "track_out", user, lot) if eq else None
    history(
        s,
        tid,
        lot,
        "track_out",
        user,
        step=ctx.step,
        from_status="running",
        equipment_id=lot["equipment_id"],
        recipe_id=lot["recipe_id"],
        details={
            "checks": _brief(results),
            "dc": len(dc),
            "oos": len(oos),
            "oos_action": worst,
            "scrap": n_scrap,
            "consumed": consumed,
            "tools": tools,
            "e10": e10,
            "sampling": smp.get("message"),
            **_ov(body, results),
        },
    )
    if oos:
        history(
            s,
            tid,
            lot,
            "oos",
            user,
            step=ctx.step,
            details={
                "action": worst,
                "values": [{"item": d["code"], "value": d["value"]} for d in oos],
            },
        )
    if worst == "auto_hold" and status != "scrapped":
        mi = one(
            s,
            tid,
            "measurement_item",
            next(
                d["measurement_item_id"] for d in oos if d["oos_action"] == "auto_hold"
            ),
        )
        reason = one(
            s, tid, "reason_code", mi and mi["oos_reason_id"]
        ) or default_reason(s, tid, "hold")
        hold_lot(
            s,
            tid,
            lot,
            user,
            reason,
            hold_type="auto",
            source="oos",
            comment="OOS: " + ", ".join(f"{d['code']}={d['value']:g}" for d in oos[:5]),
        )
    if status == "scrapped":
        history(
            s,
            tid,
            lot,
            "scrap",
            user,
            step=ctx.step,
            qty=0,
            details={"lot": "all units scrapped"},
        )
    audit(
        s,
        tid,
        LOT,
        "track_out",
        lot,
        user,
        {"lot_status": ("running", status), "qty": (lot["qty"] + n_scrap, qty)},
    )
    s.commit()
    return _result(
        s,
        tid,
        lot_id,
        results,
        e10=e10,
        oos_action=worst,
        consumed=consumed,
        tools=tools,
    )


def _relocate(
    s: Session,
    tid: uuid.UUID,
    lot: Row,
    step: Row,
    user: Any,
    *,
    branch: bool,
    rework: bool,
    record_move_out: bool = True,
) -> Row | None:
    nxt, stack, ev = next_location(s, tid, lot, step, branch=branch, rework=rework)
    at = now()
    if record_move_out:
        history(
            s,
            tid,
            lot,
            "move_out",
            user,
            step=step,
            from_status="tracked_out",
            to_status="waiting" if nxt else "completed",
            equipment_id=lot["equipment_id"],
        )
    for e in ev:
        st = e.pop("step")
        history(s, tid, lot, e.pop("action"), user, step=st, details=e)
    vals: Row = {
        "equipment_id": None,
        "recipe_id": None,
        "exec_ctx": None,
        "pending_rework": False,
        "stage_at": at,
        "route_stack": stack,
    }
    if nxt is None:
        vals.update(lot_status="completed", completed_at=at)
        for u in units(s, tid, lot["id"]):
            _upd(s, tid, "wafer", u["id"], user, wafer_status="completed")
        wo = one(s, tid, "work_order", lot["work_order_id"])
        if wo:
            _upd(
                s,
                tid,
                "work_order",
                wo["id"],
                user,
                completed_qty=(wo["completed_qty"] or 0) + lot["qty"],
            )
    else:
        vals.update(lot_status="waiting", current_step_id=nxt["id"], step_in_at=at)
        for u in units(s, tid, lot["id"]):
            if u["wafer_status"] == "rework" and rework:
                continue
            if u["wafer_status"] in ("rework",):
                _upd(s, tid, "wafer", u["id"], user, wafer_status="waiting")
    _upd(s, tid, "lot", lot["id"], user, **vals)
    lot.update(vals)
    if nxt is None:
        history(
            s,
            tid,
            lot,
            "complete",
            user,
            step=step,
            details={"completed_qty": lot["qty"]},
        )
        audit(
            s,
            tid,
            LOT,
            "complete",
            lot,
            user,
            {"lot_status": ("tracked_out", "completed")},
        )
    return nxt


def move_out(
    s: Session, tid: uuid.UUID, lot_id: uuid.UUID, body: Row, user: Any
) -> Row:
    lot = lock_lot(s, tid, lot_id)
    _guard(lot, "move_out")
    ctx = build_ctx(s, tid, lot, "move_out", body)
    rework = bool(body.get("rework")) or bool(lot["pending_rework"])
    results = ck.evaluate(
        ctx,
        user,
        override=body.get("override", False),
        reason=body.get("override_reason"),
    )
    nxt = _relocate(
        s,
        tid,
        lot,
        ctx.step,
        user,
        branch=bool(body.get("branch")) and not rework,
        rework=rework,
    )
    audit(
        s,
        tid,
        LOT,
        "move_out",
        lot,
        user,
        {"lot_status": ("tracked_out", lot["lot_status"])},
    )
    s.commit()
    return _result(
        s,
        tid,
        lot_id,
        results,
        next_step=nxt and {"id": str(nxt["id"]), "seq": nxt["seq"]},
    )


def _brief(results: list[Row]) -> list[Row]:
    return [
        {
            "type": r["check_type"],
            "rule": r["rule_code"],
            "result": r["result"],
            "message": r["message"],
        }
        for r in results
        if r["applicable"] or r["result"] != "pass"
    ]


def _ov(body: Row, results: list[Row]) -> Row:
    if any(r["result"] == "overridden" for r in results):
        return {"override_reason": body.get("override_reason")}
    return {}


STAGE_FN = {
    "move_in": move_in,
    "track_in": track_in,
    "track_out": track_out,
    "move_out": move_out,
}


def run_stage(
    s: Session, tid: uuid.UUID, lot_id: uuid.UUID, stage: str, body: Row, user: Any
) -> Row:
    """Run a stage, then any auto stages configured on the (new) current step."""
    out = STAGE_FN[stage](s, tid, lot_id, body, user)
    if body.get("override") and any(
        r["result"] == "overridden" for r in out["results"]
    ):
        lot = one(s, tid, "lot", lot_id)
        if lot:
            history(
                s,
                tid,
                lot,
                "override",
                user,
                details={
                    "stage": stage,
                    "reason": body.get("override_reason"),
                    "rules": [
                        r["rule_code"] or r["check_type"]
                        for r in out["results"]
                        if r["result"] == "overridden"
                    ],
                },
            )
            s.commit()
    auto: list[Row] = []
    for _ in range(40):
        lot = one(s, tid, "lot", lot_id)
        if not lot or lot["on_hold"] or lot["lot_status"] not in NEXT_STAGE:
            break
        nxt = NEXT_STAGE[lot["lot_status"]]
        step = one(s, tid, "route_step", lot["current_step_id"])
        if not step or not step[f"auto_{nxt}"]:
            break
        try:
            r = STAGE_FN[nxt](s, tid, lot_id, {}, user)
            auto.append({"stage": nxt, "ok": True, "results": r["results"]})
        except HTTPException as ex:
            s.rollback()
            auto.append({"stage": nxt, "ok": False, "error": ex.detail})
            break
    out["auto"] = auto
    lot = one(s, tid, "lot", lot_id)
    out["lot"] = serialize(s, tid, LOT, [lot])[0] if lot else None
    return out


def preview(
    s: Session, tid: uuid.UUID, lot_id: uuid.UUID, stage: str, body: Row, user: Any
) -> list[Row]:
    lot = one(s, tid, "lot", lot_id)
    if not lot:
        raise HTTPException(status_code=404, detail="Record not found")
    ctx = build_ctx(s, tid, lot, stage, body)
    res = ck.evaluate(ctx, user, preview=True)
    s.commit()
    return res


def manual_hold(
    s: Session,
    tid: uuid.UUID,
    lot_id: uuid.UUID,
    reason_id: Any,
    comment: str | None,
    user: Any,
) -> Row:
    lot = lock_lot(s, tid, lot_id)
    if lot["lot_status"] in TERMINAL:
        raise http_422([("lot_status", f"lot_status: lot is {lot['lot_status']}")])
    r = _reason(s, tid, reason_id, "hold")
    if r["comment_required"] and not (comment or "").strip():
        raise http_422([("comment", "comment: required for this reason code")])
    hold_lot(s, tid, lot, user, r, comment=comment)
    s.commit()
    return lot


# ---------------- lot start hook ----------------
def create_units(
    s: Session,
    tid: uuid.UUID,
    lot: Row,
    product: Row,
    slots: list[int],
    srcs: list[Any],
    wr: Row,
    user: Any,
    attrs: Row,
) -> str:
    """Units at lot start by tracking level; returns the level."""
    level = tracking_level(s, tid, product)
    at = now()
    if level == "quantity":
        return level
    if level == "unit":
        rule = one(s, tid, "code_rule", product["unit_code_rule_id"]) or wr
        codes = (
            coderule.generate(
                s, tid, rule, len(slots), {"LOT": lot["code"]}, commit=False
            )
            if "{SEQ" in rule["pattern"]
            else [
                coderule.render(rule, i, at, {"LOT": lot["code"], "SLOT": i})
                for i in range(1, len(slots) + 1)
            ]
        )
        for code, src in zip(codes, srcs, strict=True):
            _ins(
                s,
                tid,
                "wafer",
                user,
                code=code,
                lot_id=lot["id"],
                unit_kind=product["serial_kind"] or "unit",
                slot=None,
                wafer_status="waiting",
                source_ref=src or None,
                rework_count=0,
                attrs=dict(attrs),
            )
        return level
    seq_wafer = "{SEQ" in wr["pattern"]
    for k, src in zip(slots, srcs, strict=True):
        ctx = {"LOT": lot["code"], "SLOT": int(k)}
        wid = (
            coderule.generate(s, tid, wr, 1, ctx, commit=False)[0]
            if seq_wafer
            else coderule.render(wr, int(k), at, ctx)
        )
        _ins(
            s,
            tid,
            "wafer",
            user,
            code=wid,
            lot_id=lot["id"],
            unit_kind="wafer",
            slot=int(k),
            wafer_status="waiting",
            source_ref=src or None,
            rework_count=0,
            attrs=dict(attrs),
        )
    return level


# ---------------- CRUD validators ----------------
@validator("tool")
def _tool(_s: Session, _t: uuid.UUID, _e: Entity, row: Row, _o: Row | None) -> None:
    errs = []
    if (row.get("usage_count") or 0) < 0:
        errs.append(("usage_count", "usage_count: must be >= 0"))
    if row.get("max_usage") is not None and row["max_usage"] < 1:
        errs.append(("max_usage", "max_usage: must be >= 1"))
    if row.get("warn_pct") is not None and not 1 <= row["warn_pct"] <= 100:
        errs.append(("warn_pct", "warn_pct: must be 1..100"))
    if errs:
        raise MesError(errs)


@validator("material_lot")
def _material_lot(
    _s: Session, _t: uuid.UUID, _e: Entity, row: Row, _o: Row | None
) -> None:
    if (row.get("qty_remaining") or 0) < 0:
        raise MesError([("qty_remaining", "qty_remaining: must be >= 0")])
    if row.get("initial_qty") is None:
        row["initial_qty"] = row.get("qty_remaining")


@validator("check_rule")
def _check_rule(
    _s: Session, _t: uuid.UUID, _e: Entity, row: Row, _o: Row | None
) -> None:
    if row.get("check_type") not in ck.CHECKS:
        raise MesError([("check_type", "check_type: not implemented")])
    p = row.get("params")
    if p is not None and not isinstance(p, dict):
        raise MesError([("params", "params: must be a JSON object")])


@validator("check_binding")
def _check_binding(
    _s: Session, _t: uuid.UUID, _e: Entity, row: Row, _o: Row | None
) -> None:
    for sc in ck.SPECIFICITY:  # only the scope's reference is kept
        if sc != row.get("scope"):
            row[f"{sc}_id"] = None
