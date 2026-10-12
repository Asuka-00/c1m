"""The four execution stages (Move In, Track In, Track Out, Move Out) and Q-time actions."""

import uuid
from typing import Any

import sqlalchemy as sa
from fastapi import HTTPException
from sqlmodel import Session

from app.core.spec.audit import audit
from app.core.spec.base import conn, now
from app.core.spec.engine import ENTITIES, TABLES
from app.core.spec.errors import http_422
from app.core.spec.serialize import serialize
from app.mes.common.query import one
from app.mes.common.rows import _ins, _upd
from app.mes.equipment.service import e10_apply
from app.mes.execution.checks import service as ck
from app.mes.execution.constants import FROM_STATUS, NEXT_STAGE, OOS_RANK
from app.mes.execution.consumption import _consume
from app.mes.execution.context import build_ctx
from app.mes.execution.hold import default_reason, hold_lot
from app.mes.lot.service import TERMINAL, history, lock_lot, units
from app.mes.process.service import next_location
from app.mes.quality.service import out_of_spec

Row = dict[str, Any]
LOT = ENTITIES["lot"]


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
                "is_oos": out_of_spec(it, v),
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
