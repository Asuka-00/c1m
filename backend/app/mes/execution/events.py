"""执行模块的通知事件：Q-Time 预警 / 超时、自动 Hold、超规（OOS）。"""

import uuid
from typing import Any

from sqlmodel import Session

from app.platform.notification.service import notify, register_event

Row = dict[str, Any]

QTIME_WARN = register_event("mes.qtime_warn", "Q-Time warning", "warning", "lot").code
QTIME_EXCEEDED = register_event(
    "mes.qtime_exceeded",
    "Q-Time exceeded",
    "critical",
    "lot",
).code
LOT_HOLD = register_event("mes.lot_hold", "Lot auto hold", "warning", "lot").code
OOS = register_event("mes.oos", "Out of spec", "critical", "lot").code


def lot_link(lot: Row) -> str:
    """批次作业页链接。"""
    return f"/mes/lot-console?lot={lot['id']}"


def notify_lot(
    s: Session,
    tid: uuid.UUID,
    event: str,
    lot: Row,
    title: str,
    params: Row,
    dedupe_key: str | None = None,
) -> uuid.UUID | None:
    """发送批次相关通知（关联对象为批次，链接到批次作业页）。"""
    return notify(
        s,
        tid,
        event,
        title=title,
        params={"lot": lot["code"], **params},
        object_type="lot",
        object_id=lot["id"],
        object_code=lot["code"],
        link=lot_link(lot),
        dedupe_key=dedupe_key,
    )


QUAL_EXPIRING = register_event(
    "mes.qual_expiring",
    "Qualification expiring",
    "warning",
    "operator_qual",
).code
QUAL_EXPIRED = register_event(
    "mes.qual_expired",
    "Qualification expired",
    "critical",
    "operator_qual",
).code
