"""批次合批：候选、校验，优先级取最高者。"""

import uuid
from typing import Any

import sqlalchemy as sa
from fastapi import HTTPException
from sqlmodel import Session

from app.core.spec.audit import audit
from app.core.spec.base import conn, now
from app.core.spec.engine import TABLES
from app.core.spec.errors import http_422
from app.mes.common.query import one
from app.mes.common.rows import _upd
from app.mes.execution.checks import service as ck
from app.mes.execution.sm_rules import (
    SPLIT_STATES,
    _carrier_cap,
    _evaluate,
    _genealogy,
    _prio,
    _prio_json,
    _rule_result,
    _ser,
    highest_priority,
    rule_for,
)
from app.mes.execution.stage_common import _brief, _ov
from app.mes.execution.stages import LOT
from app.mes.lot.service import check_transition, history, lock_lots, lot_error, units

Row = dict[str, Any]


# ---------------- merge ----------------
def merge_problems(
    target: Row, src: Row, rule: Row | None, src_rule: Row | None = None
) -> list[str]:
    """检查源批次能否合入目标批次。

    校验同产品、同路线及版本、同工步与阶段、同工单（规则允许时除外）、均未 Hold，
    以及目标与源批次各自批次类型的合批规则（需允许合批；仅当规则显式要求时校验优先级相同）。

    Returns:
        不满足的原因列表（为空表示可合批）。
    """
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
    # 源批次自身批次类型的规则也必须允许合批
    if src_rule is None:
        p.append(f"{c}: no split/merge rule for its lot type")
    elif not src_rule["allow_merge"]:
        p.append(f"{c}: rule {src_rule['code']} does not allow merge")
    return p


def merge_candidates(s: Session, tid: uuid.UUID, target: Row) -> list[Row]:
    """目标批次可合入的候选批次，附带每个候选的不满足原因。"""
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
    """把 ``body.source_lot_ids`` 合入目标批次 ``lot_id``（目标存续）。

    合并单元与数量，结果优先级取目标与源批次中最高者（历史记录新旧值）；Q-Time 时钟取
    最早开始（最严格）；源批次置为 Merged 并终止；记录谱系、历史与审计；运行 merge 检查。

    Args:
        s: 数据库会话。
        tid: 租户 id。
        lot_id: 目标批次 id。
        body: ``{source_lot_ids, carrier_id?, comment, override, override_reason}``。
        user: 操作人。

    Returns:
        合批结果（目标批次、源批次、检查结果）。

    Raises:
        HTTPException: 规则不满足或载具容量不足（422）。
        CheckBlocked: 检查阻断。
    """
    ids = [str(x) for x in body.get("source_lot_ids") or []]
    if not ids:
        raise http_422([("source_lot_ids", "source_lot_ids: pick lots to merge")])
    dup = sorted({x for x in ids if ids.count(x) > 1})
    if dup or str(lot_id) in ids:  # P14：不静默去重
        raise HTTPException(
            status_code=422,
            detail={
                "code": "merge_source_invalid",
                "message": "source_lot_ids: duplicate lots or the target lot itself",
                "duplicates": dup,
                "includes_target": str(lot_id) in ids,
            },
        )
    src_ids: list[uuid.UUID] = []
    for x in ids:
        try:
            src_ids.append(uuid.UUID(x))
        except ValueError:
            raise http_422([("source_lot_ids", f"source_lot_ids: {x} not found")])
    # 目标与源批次按 id 升序一次加锁，避免反向合批互相等待造成死锁
    try:
        locked = lock_lots(s, tid, [lot_id, *src_ids])
    except HTTPException:
        if not one(s, tid, "lot", lot_id):
            raise
        missing = [str(x) for x in src_ids if not one(s, tid, "lot", x)]
        raise http_422(
            [("source_lot_ids", f"source_lot_ids: {', '.join(missing)} not found")]
        )
    target = locked[uuid.UUID(str(lot_id))]
    srcs = [locked[x] for x in src_ids]
    # N4：先目标、再按 id 升序逐个源批次走状态机，遇到第一个不合格即 422
    # （状态非法 lot_status 优先于 on_hold）；全部通过后才做合批规则检查（409）
    check_transition(target, "merge_target")
    for src in sorted(srcs, key=lambda x: x["id"]):
        check_transition(src, "merge_source")
        if src["lot_status"] != target["lot_status"]:
            raise lot_error(
                "lot_status",
                f"{src['code']} is {src['lot_status']}, "
                f"target is {target['lot_status']}",
                src,
                action="merge_source",
                lot_status=src["lot_status"],
                target_status=target["lot_status"],
            )
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
