"""Q-Time 超时处置：在 Move In 时执行（警告 / Hold / 返工 / 报废）。"""

import uuid
from typing import Any

import sqlalchemy as sa
from sqlmodel import Session

from app.core.spec.base import conn, now
from app.core.spec.engine import TABLES
from app.mes.common.query import one
from app.mes.common.rows import _upd
from app.mes.execution.checks import service as ck
from app.mes.execution.hold import default_reason, hold_lot
from app.mes.execution.stage_common import _relocate
from app.mes.lot.service import history, units

Row = dict[str, Any]


def _qtime_actions(
    s: Session, tid: uuid.UUID, lot: Row, step: Row, user: Any
) -> str | None:
    """执行最大 Q-Time 超时处置（每次超时只执行一次），返回处置结果。"""
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
