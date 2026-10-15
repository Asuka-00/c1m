"""批次拆批。"""

import uuid
from typing import Any

import sqlalchemy as sa
from sqlmodel import Session

from app.core.spec.audit import audit
from app.core.spec.base import conn, now
from app.core.spec.engine import TABLES
from app.core.spec.errors import http_422
from app.mes.common.query import find, one
from app.mes.common.rows import _ins, _upd
from app.mes.execution.sm_rules import (
    COPY,
    SPLIT_STATES,
    _carrier_busy,
    _carrier_cap,
    _child_codes,
    _children,
    _evaluate,
    _genealogy,
    _rule_result,
    _ser,
    rule_for,
)
from app.mes.execution.stage_common import _brief, _ov
from app.mes.execution.stages import LOT
from app.mes.lot.service import (
    check_transition,
    history,
    inherit_customer,
    lock_lot,
    lot_error,
    units,
)

Row = dict[str, Any]


# ---------------- split ----------------
def split(s: Session, tid: uuid.UUID, lot_id: uuid.UUID, body: Row, user: Any) -> Row:
    """拆批：从母批拆出若干子批。

    仅允许在 Waiting / MovedIn 状态；受批次类型拆合批规则约束（允许、最大子批数、最小数量）。
    晶圆 / 单元模式按单元拆分，数量模式按数量拆分。子批继承产品、路线、当前工步与阶段、工单、
    优先级、Q-Time 时钟、Hold 状态与属性；子批编码按批次类型规则生成；记录谱系、历史与审计。

    Args:
        s: 数据库会话。
        tid: 租户 id。
        lot_id: 母批 id。
        body: ``{children: [{unit_ids? | qty?, carrier_id?}], comment, override, override_reason}``。
        user: 操作人。

    Returns:
        拆批结果（母批、子批、检查结果）。

    Raises:
        HTTPException: 状态或规则不允许（422）。
        CheckBlocked: 检查阻断。
    """
    lot = lock_lot(s, tid, lot_id)
    check_transition(lot, "split")
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
    if remain < 1:  # 不能拆完，母批至少保留 1（P13）
        raise lot_error(
            "lot_status", "parent lot must keep at least 1", lot, action="split"
        )
    # 规则校验（不可强制放行）
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
        vals = {k: lot[k] for k in COPY} | inherit_customer(lot)
        vals["attrs"] = dict(lot.get("attrs") or {})
        cid = _ins(
            s,
            tid,
            "lot",
            user,
            code=code,
            qty=qtys[i],
            scrapped_qty=0,
            received_qty=0,
            rework_count=0,
            bonus_qty=0,
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
