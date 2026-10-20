"""交接班日志：交班人登记交接事项与未结事项，接班人确认。"""

import uuid
from datetime import date
from typing import Any

from sqlmodel import Session

from app.core import error_codes as ec
from app.core.models import actor_name
from app.core.spec.audit import audit
from app.core.spec.base import now
from app.core.spec.engine import ENTITIES
from app.core.spec.errors import coded, fe, http_422
from app.mes.common.query import find, jsonable, one
from app.mes.common.rows import _ins, _upd
from app.mes.common.switch import switch

Row = dict[str, Any]
E = ENTITIES["shift_log"]


def _view(s: Session, tid: uuid.UUID, r: Row) -> Row:
    sh = one(s, tid, "shift", r["shift_id"])
    ar = one(s, tid, "area", r["area_id"])
    out: Row = jsonable(
        {
            **r,
            "shift": sh and sh["code"],
            "shift_name": sh and sh["name"],
            "area": ar and ar["code"],
        }
    )
    return out


def list_logs(
    s: Session, tid: uuid.UUID, date_from: date | None, date_to: date | None
) -> list[Row]:
    """日期范围内的交接班日志（新到旧）。"""
    out = [
        r
        for r in find(s, tid, "shift_log")
        if (not date_from or r["shift_date"] >= date_from)
        and (not date_to or r["shift_date"] <= date_to)
    ]
    out.sort(key=lambda r: (r["shift_date"], r["handed_at"] or now()), reverse=True)
    return [_view(s, tid, r) for r in out]


def create(s: Session, tid: uuid.UUID, body: Row, user: Any) -> Row:
    """登记交班：日期、班次、区域（可选）、交接事项、未结事项。"""
    errs = []
    if not one(s, tid, "shift", body.get("shift_id")):
        errs.append(fe("shift_id", ec.SHIFT_NOT_FOUND, "shift_id: not found"))
    if body.get("area_id") and not one(s, tid, "area", body["area_id"]):
        errs.append(fe("area_id", ec.AREA_NOT_FOUND, "area_id: not found"))
    if not (body.get("summary") or "").strip():
        errs.append(fe("summary", ec.SUMMARY_REQUIRED, "summary: required"))
    if errs:
        raise http_422(errs)
    rid = _ins(
        s,
        tid,
        "shift_log",
        user,
        shift_date=body["shift_date"],
        shift_id=body["shift_id"],
        area_id=body.get("area_id"),
        summary=body["summary"].strip(),
        open_items=(body.get("open_items") or "").strip() or None,
        handed_by=actor_name(user),
        handed_at=now(),
        log_status="open",
    )
    row = one(s, tid, "shift_log", rid) or {}
    audit(s, tid, E, "create", row, user)
    s.commit()
    return _view(s, tid, row)


def acknowledge(
    s: Session, tid: uuid.UUID, rid: uuid.UUID, body: Row, user: Any
) -> Row:
    """接班确认（「接班须由他人确认」管控开启时，交班人不能自己确认）。"""
    row = one(s, tid, "shift_log", rid)
    if not row:
        raise coded(404, ec.SHIFT_LOG_NOT_FOUND, "shift log not found")
    if row["log_status"] != "open":
        raise coded(409, ec.ALREADY_ACKNOWLEDGED, "already acknowledged")
    if switch(s, tid, "handover_ack_other") is not None and row[
        "created_by"
    ] == getattr(user, "id", None):
        raise http_422(
            [fe("received_by", ec.ACK_OTHER_USER, "received_by: must be another user")]
        )
    vals = {
        "log_status": "acknowledged",
        "received_by": actor_name(user),
        "received_at": now(),
        "receive_comment": (body.get("comment") or "").strip()[:300] or None,
    }
    _upd(s, tid, "shift_log", rid, user, **vals)
    audit(s, tid, E, "acknowledge", row, user, {"log_status": ("open", "acknowledged")})
    s.commit()
    return _view(s, tid, one(s, tid, "shift_log", rid) or {})
