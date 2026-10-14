"""载具管理：换载具、清洗、使用计数与载具状态总览。"""

import uuid
from datetime import timedelta
from typing import Any

from fastapi import HTTPException
from sqlmodel import Session

from app.core.models import actor_name
from app.core.spec.audit import audit
from app.core.spec.base import now
from app.core.spec.errors import http_422
from app.mes.common.query import find, one
from app.mes.common.rows import _ins, _upd
from app.mes.execution.checks import service as ck
from app.mes.execution.context import build_ctx
from app.mes.execution.sm_rules import _carrier_busy, _carrier_cap
from app.mes.execution.stages import LOT
from app.mes.execution.usage import clean_due
from app.mes.lot.service import TERMINAL, history, lock_lot, units

Row = dict[str, Any]


def event(
    s: Session,
    tid: uuid.UUID,
    car: Row,
    ev: str,
    user: Any,
    *,
    lot: Row | None = None,
    other: Row | None = None,
    qty: int | None = None,
    comment: str | None = None,
) -> None:
    """写一条载具履历。"""
    _ins(
        s,
        tid,
        "carrier_event",
        user,
        carrier_id=car["id"],
        event=ev,
        lot_id=lot and lot["id"],
        other_carrier_id=other and other["id"],
        qty=qty,
        comment=comment,
        username=actor_name(user),
        at=now(),
    )


def change_carrier(
    s: Session, tid: uuid.UUID, lot_id: uuid.UUID, body: Row, user: Any
) -> Row:
    """换载具：整批晶圆移入目标载具（槽位尽量保持，超出容量时顺排）。

    Args:
        s: 数据库会话。
        tid: 租户 id。
        lot_id: 批次 id。
        body: ``{carrier_id, comment?}``。
        user: 操作人。

    Raises:
        HTTPException: 批次已结束 / 运行中，或目标载具不可用 / 容量不足（422）。
    """
    lot = lock_lot(s, tid, lot_id)
    if lot["lot_status"] in TERMINAL or lot["lot_status"] == "running":
        raise http_422(
            [("lot", f"lot: cannot change carrier while {lot['lot_status']}")]
        )
    car, cap = _carrier_cap(s, tid, body["carrier_id"])
    if car["id"] == lot["carrier_id"]:
        raise http_422([("carrier_id", "carrier_id: already in this carrier")])
    if car["status_code"] != "available" or _carrier_busy(s, tid, car["id"], lot["id"]):
        raise http_422([("carrier_id", f"carrier_id: {car['code']} is not available")])
    us = units(s, tid, lot["id"])
    if cap and len(us) > cap:
        raise http_422(
            [("carrier_id", f"carrier_id: {len(us)} wafers exceed capacity {cap}")]
        )
    slots = [u["slot"] for u in us]
    keep = all(x and (not cap or x <= cap) for x in slots) and len(set(slots)) == len(
        slots
    )
    for i, u in enumerate(us):
        if not keep:
            _upd(s, tid, "wafer", u["id"], user, slot=i + 1)
    old = one(s, tid, "carrier", lot["carrier_id"])
    _upd(s, tid, "lot", lot["id"], user, carrier_id=car["id"])
    if old:
        _upd(s, tid, "carrier", old["id"], user, status_code="available")
        event(s, tid, old, "unload", user, lot=lot, other=car, qty=lot["qty"])
    _upd(s, tid, "carrier", car["id"], user, status_code="in_use")
    event(
        s,
        tid,
        car,
        "load",
        user,
        lot=lot,
        other=old,
        qty=lot["qty"],
        comment=body.get("comment"),
    )
    history(
        s,
        tid,
        lot,
        "carrier_change",
        user,
        comment=body.get("comment"),
        details={"from": old and old["code"], "to": car["code"], "resorted": not keep},
    )
    audit(
        s,
        tid,
        LOT,
        "carrier_change",
        lot,
        user,
        {"carrier": (old and old["code"], car["code"])},
    )
    s.commit()
    return {"lot_id": str(lot["id"]), "carrier": car["code"], "resorted": not keep}


def clean_carrier(
    s: Session,
    tid: uuid.UUID,
    carrier_id: uuid.UUID,
    user: Any,
    comment: str | None = None,
) -> Row:
    """清洗载具：使用次数清零、记录清洗时间并恢复可用（载具须为空）。"""
    car = one(s, tid, "carrier", carrier_id)
    if not car:
        raise HTTPException(status_code=404, detail="Record not found")
    if _carrier_busy(s, tid, car["id"]):
        raise http_422([("carrier", f"carrier: {car['code']} still holds a lot")])
    if car["status_code"] == "retired":
        raise http_422([("carrier", f"carrier: {car['code']} is retired")])
    _upd(
        s,
        tid,
        "carrier",
        car["id"],
        user,
        use_count=0,
        last_cleaned_at=now(),
        status_code="available",
    )
    event(s, tid, car, "clean", user, comment=comment)
    s.commit()
    return {"id": str(car["id"]), "code": car["code"]}


def carrier_board(s: Session, tid: uuid.UUID) -> list[Row]:
    """载具总览：状态、所装批次、晶圆数 / 容量、使用次数与清洗到期。"""
    lots = {
        x["carrier_id"]: x
        for x in find(s, tid, "lot")
        if x["carrier_id"] and x["lot_status"] not in TERMINAL
    }
    types = {t["id"]: t for t in find(s, tid, "carrier_type")}
    at = now()
    out = []
    for c in find(s, tid, "carrier", order="code"):
        ct = types.get(c["carrier_type_id"]) or {}
        lot = lots.get(c["id"])
        due = clean_due(s, tid, c)
        mx = c["max_uses"]
        used = c["use_count"] or 0
        state = "ok"
        if (due and at > due) or (mx and used >= mx):
            state = "overdue"
        elif (due and at > due - timedelta(days=1)) or (mx and used >= mx * 0.9):
            state = "warn"
        out.append(
            {
                "id": str(c["id"]),
                "code": c["code"],
                "carrier_type": ct.get("code"),
                "status": c["status_code"],
                "lot_id": lot and str(lot["id"]),
                "lot": lot and lot["code"],
                "lot_status": lot and lot["lot_status"],
                "wafers": len(units(s, tid, lot["id"])) if lot else 0,
                "capacity": ct.get("capacity"),
                "use_count": used,
                "max_uses": mx,
                "last_cleaned_at": c["last_cleaned_at"],
                "clean_due_at": due,
                "due_state": state,
            }
        )
    return out


def sort_wafers(
    s: Session, tid: uuid.UUID, lot_id: uuid.UUID, body: Row, user: Any
) -> Row:
    """晶圆整理（Sorter）：在本批次内重排槽位，可同时移入另一个空载具。

    Args:
        s: 数据库会话。
        tid: 租户 id。
        lot_id: 批次 id。
        body: ``{slots: [{wafer_id, slot}], carrier_id?, comment?, override?, override_reason?}``；
            须覆盖批次全部在制晶圆。
        user: 操作人。

    Raises:
        HTTPException: 批次运行中 / 已结束、晶圆或槽位不合法、目标载具不可用（422）；检查阻断（409）。
    """
    lot = lock_lot(s, tid, lot_id)
    if lot["lot_status"] in TERMINAL or lot["lot_status"] == "running":
        raise http_422([("lot", f"lot: cannot sort while {lot['lot_status']}")])
    cid = body.get("carrier_id") or lot["carrier_id"]
    if not cid:
        raise http_422([("carrier_id", "carrier_id: required")])
    car, cap = _carrier_cap(s, tid, cid)
    moving = car["id"] != lot["carrier_id"]
    if moving and (
        car["status_code"] != "available" or _carrier_busy(s, tid, car["id"], lot["id"])
    ):
        raise http_422([("carrier_id", f"carrier_id: {car['code']} is not available")])
    us = {str(u["id"]): u for u in units(s, tid, lot["id"])}
    smap: list[Row] = [
        {"wafer": us.get(str(x["wafer_id"])), "slot": int(x["slot"])}
        for x in body.get("slots") or []
    ]
    errs: list[tuple[str, str]] = []
    if any(x["wafer"] is None for x in smap) or len(smap) != len(us):
        errs.append(("slots", "slots: list every wafer of the lot once"))
    sl = [x["slot"] for x in smap]
    if len(set(sl)) != len(sl) or any(x < 1 or (cap and x > cap) for x in sl):
        errs.append(("slots", f"slots: use unique slots 1–{cap or '…'}"))
    if errs:
        raise http_422(errs)
    ctx = build_ctx(s, tid, lot, "sort", {})
    ctx.sort_map = smap
    results = ck.evaluate(
        ctx,
        user,
        override=bool(body.get("override")),
        reason=body.get("override_reason"),
    )
    for x in smap:
        if x["wafer"]["slot"] != x["slot"]:
            _upd(s, tid, "wafer", x["wafer"]["id"], user, slot=x["slot"])
    old = one(s, tid, "carrier", lot["carrier_id"])
    if moving:
        _upd(s, tid, "lot", lot["id"], user, carrier_id=car["id"])
        _upd(s, tid, "carrier", car["id"], user, status_code="in_use")
        if old:
            _upd(s, tid, "carrier", old["id"], user, status_code="available")
            event(s, tid, old, "unload", user, lot=lot, other=car, qty=lot["qty"])
    event(
        s,
        tid,
        car,
        "sort",
        user,
        lot=lot,
        other=old if moving else None,
        qty=len(smap),
        comment=body.get("comment"),
    )
    history(
        s,
        tid,
        lot,
        "sort",
        user,
        comment=body.get("comment"),
        details={
            "carrier": car["code"],
            "from": old and old["code"],
            "slots": {x["wafer"]["code"]: x["slot"] for x in smap},
            "checks": [r["check_type"] for r in results],
        },
    )
    s.commit()
    return {"lot_id": str(lot["id"]), "carrier": car["code"], "results": results}
