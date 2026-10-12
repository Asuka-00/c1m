"""设备模块的通知事件：PM 即将到期 / 超期、设备宕机（E10 改为停机类状态）、停机记录。"""

import uuid
from typing import Any

from sqlmodel import Session

from app.platform.notification.service import notify, register_event

Row = dict[str, Any]

PM_DUE = register_event(
    "mes.pm_due", "PM due soon|PM 即将到期|PM 期限間近", "warning", "equipment"
).code
PM_OVERDUE = register_event(
    "mes.pm_overdue", "PM overdue|PM 已超期|PM 期限切れ", "critical", "equipment"
).code
EQP_DOWN = register_event(
    "mes.eqp_down", "Equipment down|设备宕机|設備ダウン", "critical", "equipment"
).code
DOWNTIME = register_event(
    "mes.downtime", "Downtime recorded|停机记录|停止記録", "warning", "equipment"
).code


def notify_eqp(
    s: Session,
    tid: uuid.UUID,
    event: str,
    eq: Row,
    title: str,
    params: Row,
    dedupe_key: str | None = None,
) -> uuid.UUID | None:
    """发送设备相关通知（关联对象为设备，链接到设备状态看板）。"""
    return notify(
        s,
        tid,
        event,
        title=title,
        params={"equipment": eq["code"], **params},
        object_type="equipment",
        object_id=eq["id"],
        object_code=eq["code"],
        link="/mes/eqp-board",
        dedupe_key=dedupe_key,
    )
