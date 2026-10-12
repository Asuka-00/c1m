"""Lot split / merge.

Split: parent keeps the remainder; children inherit product, route, current
step + stage, WO, priority, carrier-less placement, route stack, execution
context, attrs, Q-Time clocks (via genealogy) and active holds. Child lot
numbers: parent no. + ".NN" (rule child_id_mode=suffix) or the lot type's lot
ID code rule. Merge: sources join the target (same product, route version,
step, stage, route stack, tracking level; same WO unless the rule allows; none
on hold) and end as `merged`. Both are governed by the lot type's
split_merge_rule, run the bound checks (triggers split / merge), and write
genealogy, history and audit.
"""

import uuid
from typing import Any

import sqlalchemy as sa
from fastapi import HTTPException
from sqlmodel import Session

from app.core.spec.audit import audit
from app.core.spec.base import conn, now
from app.core.spec.engine import TABLES
from app.core.spec.errors import http_422
from app.core.spec.serialize import serialize
from app.mes.common import coderule
from app.mes.common.query import find, one
from app.mes.common.rows import _ins, _upd
from app.mes.execution.checks import service as ck
from app.mes.execution.context import build_ctx
from app.mes.execution.stages import LOT, _brief, _ov
from app.mes.lot.lots import history, lock_lot, units

Row = dict[str, Any]
SPLIT_STATES = ("waiting", "moved_in")
COPY = (
    "work_order_id",
    "product_id",
    "route_id",
    "lot_type_id",
    "priority_id",
    "tracking_level",
    "site_id",
    "current_step_id",
    "lot_status",
    "equipment_id",
    "recipe_id",
    "step_in_at",
    "stage_at",
    "pending_rework",
    "route_stack",
    "exec_ctx",
    "source_ref",
    "started_at",
    "started_by",
    "attrs",
)


def rule_for(s: Session, tid: uuid.UUID, lot: Row) -> Row | None:
    rows = [
        r
        for r in find(s, tid, "split_merge_rule", lot_type_id=lot["lot_type_id"])
        if r.get("is_active", True) is not False
    ]
    return rows[0] if rows else None


def _rule_result(errs: list[str], ok: str) -> Row:
    return ck.result(
        "split_merge_rule",
        "fail" if errs else "pass",
        "; ".join(errs) if errs else ok,
        overridable=False,
    )


def _children(s: Session, tid: uuid.UUID, lot_id: Any) -> list[Row]:
    return find(s, tid, "lot_genealogy", parent_lot_id=lot_id, relation="split")


def _carrier_cap(s: Session, tid: uuid.UUID, carrier_id: Any) -> tuple[Row, int | None]:
    car = one(s, tid, "carrier", carrier_id)
    if not car:
        raise http_422([("carrier_id", "carrier_id: not found")])
    ct = one(s, tid, "carrier_type", car["carrier_type_id"])
    cap = ct.get("capacity") if ct else None
    return car, int(cap) if cap else None


def _carrier_busy(s: Session, tid: uuid.UUID, carrier_id: Any, but: Any = None) -> bool:
    t = TABLES["lot"]
    q = sa.select(t.c.id).where(
        t.c.tenant_id == tid,
        t.c.carrier_id == carrier_id,
        t.c.lot_status.notin_(["completed", "scrapped", "merged"]),
    )
    if but is not None:
        q = q.where(t.c.id != but)
    return conn(s).execute(q).first() is not None


def _child_codes(s: Session, tid: uuid.UUID, lot: Row, rule: Row, n: int) -> list[str]:
    if rule.get("child_id_mode") == "code_rule":
        lt = one(s, tid, "lot_type", lot["lot_type_id"])
        cr = lt and one(s, tid, "code_rule", lt["lot_id_rule_id"])
        if not cr:
            raise http_422([("lot_type", "lot_type: no lot ID rule")])
        return coderule.generate(s, tid, cr, n, commit=False)
    t = TABLES["lot"]
    taken = {
        c
        for (c,) in conn(s).execute(
            sa.select(t.c.code).where(
                t.c.tenant_id == tid, t.c.code.like(f"{lot['code']}.%")
            )
        )
    }
    out: list[str] = []
    k = 1
    while len(out) < n:
        c = f"{lot['code']}.{k:02d}"
        if c not in taken:
            out.append(c)
        k += 1
    return out


def _genealogy(
    s: Session,
    tid: uuid.UUID,
    parent: Row,
    child: Row,
    relation: str,
    qty: int,
    unit_codes: list[str],
    user: Any,
    at: Any,
) -> None:
    _ins(
        s,
        tid,
        "lot_genealogy",
        user,
        parent_lot_id=parent["id"],
        child_lot_id=child["id"],
        relation=relation,
        qty=qty,
        units=unit_codes,
        route_step_id=parent["current_step_id"],
        user_email=getattr(user, "email", None),
        at=at,
    )


def _evaluate(
    s: Session,
    tid: uuid.UUID,
    lot: Row,
    trigger: str,
    extra: list[Row],
    body: Row,
    user: Any,
) -> list[Row]:
    ctx = build_ctx(s, tid, lot, trigger, {})
    return ck.evaluate(
        ctx,
        user,
        extra=extra,
        override=bool(body.get("override")),
        reason=body.get("override_reason"),
        preview=bool(body.get("preview")),
    )


# ---------------- split ----------------
def split(s: Session, tid: uuid.UUID, lot_id: uuid.UUID, body: Row, user: Any) -> Row:
    """body: children=[{unit_ids?|qty?, carrier_id?}], comment, override(_reason)."""
    lot = lock_lot(s, tid, lot_id)
    rule = rule_for(s, tid, lot)
    qty_mode = (lot["tracking_level"] or "wafer") == "quantity"
    kids = body.get("children") or []
    if not kids:
        raise http_422([("children", "children: at least one child lot")])
    active = {str(u["id"]): u for u in units(s, tid, lot["id"])}
    take: list[list[Row]] = []
    qtys: list[int] = []
    seen: set[str] = set()
    for i, c in enumerate(kids):
        if qty_mode:
            q = int(c.get("qty") or 0)
            if q <= 0:
                raise http_422(
                    [(f"children.{i}.qty", f"child {i + 1}: qty must be > 0")]
                )
            qtys.append(q)
            take.append([])
            continue
        ids = [str(x) for x in c.get("unit_ids") or []]
        if not ids:
            raise http_422(
                [(f"children.{i}.unit_ids", f"child {i + 1}: pick wafers / units")]
            )
        bad = [x for x in ids if x not in active or x in seen]
        if bad:
            raise http_422(
                [
                    (
                        f"children.{i}.unit_ids",
                        f"child {i + 1}: units not in the lot or picked twice",
                    )
                ]
            )
        seen.update(ids)
        take.append([active[x] for x in ids])
        qtys.append(len(ids))
    remain = lot["qty"] - sum(qtys)
    # rule checks (not overridable)
    errs: list[str] = []
    if lot["lot_status"] not in SPLIT_STATES:
        errs.append(f"cannot split a {lot['lot_status']} lot (only waiting / moved in)")
    if not rule:
        errs.append("no split/merge rule for the lot type")
    elif not rule["allow_split"]:
        errs.append(f"rule {rule['code']}: split not allowed")
    else:
        total = 1 + len(_children(s, tid, lot["id"])) + len(kids)
        mx = rule["max_children"] or 0
        if mx and total > mx:
            errs.append(f"rule {rule['code']}: {total} lots exceed max {mx}")
        mn = rule["min_wafers"] or 1
        if remain < mn or any(q < mn for q in qtys):
            errs.append(f"rule {rule['code']}: every lot needs at least {mn}")
    if remain < 1:
        errs.append("parent lot must keep at least 1")
    carriers: list[Any] = []
    for i, c in enumerate(kids):
        cid = c.get("carrier_id")
        if not cid:
            carriers.append(None)
            continue
        car, cap = _carrier_cap(s, tid, cid)
        if (
            car.get("status_code") not in (None, "available")
            or _carrier_busy(s, tid, car["id"])
            or car["id"] in carriers
        ):
            errs.append(f"child {i + 1}: carrier {car['code']} is not available")
        if cap and not qty_mode and qtys[i] > cap:
            errs.append(f"child {i + 1}: {qtys[i]} exceeds carrier capacity {cap}")
        carriers.append(car["id"])
    results = _evaluate(
        s, tid, lot, "split", [_rule_result(errs, "split allowed")], body, user
    )
    if body.get("preview"):
        s.commit()
        return {"results": results}
    at = now()
    codes = _child_codes(s, tid, lot, rule or {}, len(kids))
    holds = find(s, tid, "lot_hold", lot_id=lot["id"], is_active=True)
    out: list[Row] = []
    for i, code in enumerate(codes):
        vals = {k: lot[k] for k in COPY}
        vals["attrs"] = dict(lot.get("attrs") or {})
        cid = _ins(
            s,
            tid,
            "lot",
            user,
            code=code,
            qty=qtys[i],
            scrapped_qty=0,
            on_hold=bool(holds),
            carrier_id=carriers[i],
            **vals,
        )
        child = one(s, tid, "lot", cid)
        assert child
        ws = TABLES["wafer"]
        if take[i]:
            conn(s).execute(
                sa.update(ws)
                .where(ws.c.tenant_id == tid, ws.c.id.in_([u["id"] for u in take[i]]))
                .values(lot_id=cid, updated_at=at)
            )
        for h in holds:
            _ins(
                s,
                tid,
                "lot_hold",
                user,
                lot_id=cid,
                reason_id=h["reason_id"],
                hold_type=h["hold_type"],
                source="split",
                comment=f"inherited from {lot['code']}"
                + (f": {h['comment']}" if h["comment"] else ""),
                is_active=True,
                held_at=h["held_at"],
                held_by=h["held_by"],
                route_step_id=h["route_step_id"],
            )
        ucodes = [u["code"] for u in take[i]]
        _genealogy(s, tid, lot, child, "split", qtys[i], ucodes, user, at)
        history(
            s,
            tid,
            child,
            "split",
            user,
            from_status=lot["lot_status"],
            comment=body.get("comment"),
            details={
                "parent": lot["code"],
                "units": ucodes,
                "holds": len(holds),
                "checks": _brief(results),
                **_ov(body, results),
            },
        )
        audit(s, tid, LOT, "split", child, user, {"parent": (None, lot["code"])})
        out.append({"id": str(cid), "code": code, "qty": qtys[i], "units": ucodes})
    _upd(s, tid, "lot", lot["id"], user, qty=remain)
    old = lot["qty"]
    lot["qty"] = remain
    history(
        s,
        tid,
        lot,
        "split",
        user,
        from_status=lot["lot_status"],
        comment=body.get("comment"),
        details={
            "children": [{"code": c["code"], "qty": c["qty"]} for c in out],
            "checks": _brief(results),
            **_ov(body, results),
        },
    )
    audit(
        s,
        tid,
        LOT,
        "split",
        lot,
        user,
        {"qty": (old, remain), "children": (None, ", ".join(codes))},
    )
    s.commit()
    return {"results": results, "children": out, "lot": _ser(s, tid, lot_id)}


def _ser(s: Session, tid: uuid.UUID, lot_id: Any) -> Row | None:
    lot = one(s, tid, "lot", lot_id)
    return serialize(s, tid, LOT, [lot])[0] if lot else None


# ---------------- merge ----------------
def merge_problems(
    target: Row, src: Row, rule: Row | None, src_rule: Row | None = None
) -> list[str]:
    c = src["code"]
    p: list[str] = []
    if src["id"] == target["id"]:
        return [f"{c}: cannot merge a lot into itself"]
    if src["lot_status"] not in SPLIT_STATES:
        p.append(f"{c}: cannot merge a {src['lot_status']} lot")
    for f, label in (
        ("product_id", "product"),
        ("route_id", "route / route version"),
        ("current_step_id", "route step"),
        ("lot_status", "stage"),
        ("tracking_level", "tracking level"),
    ):
        if src[f] != target[f]:
            p.append(f"{c}: different {label}")
    if (src.get("route_stack") or []) != (target.get("route_stack") or []):
        p.append(f"{c}: different sub-route / rework frame")
    if (
        rule
        and rule.get("merge_same_wo", True)
        and src["work_order_id"] != target["work_order_id"]
    ):
        p.append(f"{c}: different work order")
    if (
        rule
        and rule.get("merge_same_priority")
        and src["priority_id"] != target["priority_id"]
    ):
        p.append(f"{c}: different priority")
    # the source's own lot-type rule must allow merging too
    if src_rule is None:
        p.append(f"{c}: no split/merge rule for its lot type")
    elif not src_rule["allow_merge"]:
        p.append(f"{c}: rule {src_rule['code']} does not allow merge")
    return p


def _prio(s: Session, tid: uuid.UUID, pid: Any) -> Row | None:
    return one(s, tid, "lot_priority", pid)


def _prio_json(p: Row | None) -> Row | None:
    return p and {
        "id": str(p["id"]),
        "code": p["code"],
        "name": p["name"],
        "level": p["level"],
        "color": p.get("color"),
    }


def highest_priority(s: Session, tid: uuid.UUID, lots: list[Row]) -> Row | None:
    """Level 1 = highest; ties keep the first (the target)."""
    ps = [p for p in (_prio(s, tid, x["priority_id"]) for x in lots) if p]
    return min(ps, key=lambda p: p["level"]) if ps else None


def merge_candidates(s: Session, tid: uuid.UUID, target: Row) -> list[Row]:
    t = TABLES["lot"]
    rows = (
        conn(s)
        .execute(
            sa.select(t)
            .where(
                t.c.tenant_id == tid,
                t.c.product_id == target["product_id"],
                t.c.current_step_id == target["current_step_id"],
                t.c.id != target["id"],
                t.c.lot_status.in_(SPLIT_STATES),
            )
            .order_by(t.c.code)
        )
        .mappings()
    )
    rule = rule_for(s, tid, target)
    return [
        {
            "id": str(r["id"]),
            "code": r["code"],
            "qty": r["qty"],
            "on_hold": r["on_hold"],
            "priority": _prio_json(_prio(s, tid, r["priority_id"])),
            "problems": merge_problems(
                target, dict(r), rule, rule_for(s, tid, dict(r))
            ),
        }
        for r in rows
    ]


def merge(s: Session, tid: uuid.UUID, lot_id: uuid.UUID, body: Row, user: Any) -> Row:
    """Merge body.source_lot_ids into lot `lot_id` (the surviving target)."""
    ids = list(dict.fromkeys(str(x) for x in body.get("source_lot_ids") or []))
    if not ids:
        raise http_422([("source_lot_ids", "source_lot_ids: pick lots to merge")])
    target = lock_lot(s, tid, lot_id)
    srcs: list[Row] = []
    for x in ids:
        try:
            srcs.append(lock_lot(s, tid, uuid.UUID(x)))
        except HTTPException, ValueError:
            raise http_422([("source_lot_ids", f"source_lot_ids: {x} not found")])
    rule = rule_for(s, tid, target)
    errs: list[str] = []
    if target["lot_status"] not in SPLIT_STATES:
        errs.append(f"cannot merge into a {target['lot_status']} lot")
    if not rule:
        errs.append("no split/merge rule for the lot type")
    elif not rule["allow_merge"]:
        errs.append(f"rule {rule['code']}: merge not allowed")
    for src in srcs:
        errs += merge_problems(target, src, rule, rule_for(s, tid, src))
    qty_mode = (target["tracking_level"] or "wafer") == "quantity"
    total = target["qty"] + sum(x["qty"] for x in srcs)
    if target["carrier_id"] and not qty_mode:
        car, cap = _carrier_cap(s, tid, target["carrier_id"])
        if cap and total > cap:
            errs.append(f"{total} exceeds carrier {car['code']} capacity {cap}")
    held = [x["code"] for x in [target, *srcs] if x["on_hold"]]
    extra = [
        _rule_result(errs, "merge allowed"),
        ck.result(
            "lot_hold",
            "fail" if held else "pass",
            f"on hold: {', '.join(held)}" if held else "no lot on hold",
            overridable=False,
        ),
    ]
    results = _evaluate(s, tid, target, "merge", extra, body, user)
    if body.get("preview"):
        s.commit()
        return {"results": results}
    at = now()
    ws = TABLES["wafer"]
    used = {u["slot"] for u in units(s, tid, target["id"]) if u["slot"]}
    merged: list[Row] = []
    for src in srcs:
        moved = units(s, tid, src["id"], active=False)
        for u in moved:
            vals: Row = {"lot_id": target["id"], "updated_at": at}
            if u["slot"] and u["slot"] in used:
                k = 1
                while k in used:
                    k += 1
                vals["slot"] = k
            if u["slot"]:
                used.add(vals.get("slot", u["slot"]))
            conn(s).execute(
                sa.update(ws)
                .where(ws.c.tenant_id == tid, ws.c.id == u["id"])
                .values(**vals)
            )
        ucodes = [u["code"] for u in moved if u["wafer_status"] != "scrapped"]
        _genealogy(s, tid, src, target, "merge", src["qty"], ucodes, user, at)
        _upd(
            s,
            tid,
            "lot",
            src["id"],
            user,
            lot_status="merged",
            qty=0,
            carrier_id=None,
            completed_at=at,
        )
        old_status, old_qty = src["lot_status"], src["qty"]
        src.update(lot_status="merged", qty=0)
        history(
            s,
            tid,
            src,
            "merge",
            user,
            from_status=old_status,
            comment=body.get("comment"),
            details={"target": target["code"], "qty": old_qty, "units": ucodes},
        )
        audit(
            s,
            tid,
            LOT,
            "merge",
            src,
            user,
            {"lot_status": (old_status, "merged"), "target": (None, target["code"])},
        )
        merged.append({"code": src["code"], "qty": old_qty})
    step_in = min(
        [x["step_in_at"] for x in [target, *srcs] if x["step_in_at"]], default=None
    )
    old = target["qty"]
    best = highest_priority(s, tid, [target, *srcs])
    old_p = _prio(s, tid, target["priority_id"])
    new_pid = best["id"] if best else target["priority_id"]
    _upd(
        s,
        tid,
        "lot",
        target["id"],
        user,
        qty=total,
        step_in_at=step_in,
        priority_id=new_pid,
    )
    target.update(qty=total, priority_id=new_pid)
    prio_change = (
        {"from": old_p and old_p["code"], "to": best["code"]}
        if best and (not old_p or best["id"] != old_p["id"])
        else None
    )
    history(
        s,
        tid,
        target,
        "merge",
        user,
        from_status=target["lot_status"],
        comment=body.get("comment"),
        details={
            "sources": merged,
            "priority": prio_change,
            "checks": _brief(results),
            **_ov(body, results),
        },
    )
    audit(
        s,
        tid,
        LOT,
        "merge",
        target,
        user,
        {
            "qty": (old, total),
            "sources": (None, ", ".join(m["code"] for m in merged)),
            **(
                {"priority": (prio_change["from"], prio_change["to"])}
                if prio_change
                else {}
            ),
        },
    )
    s.commit()
    return {"results": results, "merged": merged, "lot": _ser(s, tid, lot_id)}


# ---------------- console context ----------------
def sm_context(s: Session, tid: uuid.UUID, lot: Row) -> Row:
    rule = rule_for(s, tid, lot)
    g = TABLES["lot_genealogy"]
    L = TABLES["lot"]
    P, C = L.alias("p"), L.alias("c")
    rows = (
        conn(s)
        .execute(
            sa.select(g, P.c.code.label("parent_code"), C.c.code.label("child_code"))
            .join(P, P.c.id == g.c.parent_lot_id)
            .join(C, C.c.id == g.c.child_lot_id)
            .where(
                g.c.tenant_id == tid,
                sa.or_(g.c.parent_lot_id == lot["id"], g.c.child_lot_id == lot["id"]),
            )
            .order_by(g.c.at)
        )
        .mappings()
    )
    return {
        "rule": rule
        and {
            "code": rule["code"],
            "allow_split": rule["allow_split"],
            "allow_merge": rule["allow_merge"],
            "max_children": rule["max_children"],
            "min_qty": rule["min_wafers"],
            "child_id_mode": rule.get("child_id_mode") or "suffix",
            "merge_same_wo": rule.get("merge_same_wo", True),
            "children": len(_children(s, tid, lot["id"])),
        },
        "allowed": lot["lot_status"] in SPLIT_STATES,
        "priority": _prio_json(_prio(s, tid, lot["priority_id"])),
        "candidates": merge_candidates(s, tid, lot)
        if lot["lot_status"] in SPLIT_STATES
        else [],
        "genealogy": [
            {
                "relation": r["relation"],
                "parent_id": str(r["parent_lot_id"]),
                "parent": r["parent_code"],
                "child_id": str(r["child_lot_id"]),
                "child": r["child_code"],
                "qty": r["qty"],
                "units": r["units"] or [],
                "at": r["at"].isoformat() if r["at"] else None,
                "user": r["user_email"],
            }
            for r in rows
        ],
    }
