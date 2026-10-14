"""光罩领域事件（D66/D67/D68 及补充，domain-events.md §9 已登记）。

be/p2 尚无 outbox 表：事件以 ``audit_log``（entity_type=reticle，action=事件名，changes.payload）
落库留痕，并按订阅发站内通知（无订阅不生成通知）。都在调用方事务内写入，回滚不留事件。
"""

import uuid
from typing import Any

from sqlmodel import Session

from app.core.spec.audit import audit
from app.core.spec.engine import ENTITIES
from app.platform.notification.service import notify, register_event

Row = dict[str, Any]

_EVENTS = {
    "reticle.held": ("Reticle held|光罩 Hold|レチクルホールド", "warning"),
    "reticle.released": ("Reticle released|光罩释放|レチクル解除", "info"),
    "reticle.restored": ("Reticle restored|光罩恢复|レチクル復帰", "info"),
    "reticle.life_reset": (
        "Reticle life reset|光罩寿命复位|レチクル寿命リセット",
        "info",
    ),
    "reticle.incident_recorded": ("Reticle incident|光罩事故|レチクル事故", "critical"),
    "reticle.mounted": ("Reticle mounted|光罩挂载|レチクル装着", "info"),
    "reticle.unmounted": ("Reticle unmounted|光罩卸载|レチクル取外し", "info"),
    "reticle.life_reached": (
        "Reticle life reached|光罩寿命到期|レチクル寿命到達",
        "warning",
    ),
    "reticle.inspected": ("Reticle inspected|光罩检查合格|レチクル検査合格", "info"),
    "reticle.inspection_failed": (
        "Reticle inspection failed|光罩检查不合格|レチクル検査不合格",
        "critical",
    ),
    "reticle.scrapped": ("Reticle scrapped|光罩报废|レチクル廃棄", "warning"),
    "reticle.status_changed": (
        "Reticle status changed|光罩状态变更|レチクル状態変更",
        "info",
    ),
}
for _code, (_label, _sev) in _EVENTS.items():
    register_event(_code, _label, _sev, "reticle")

EVENTS = tuple(_EVENTS)


def emit(
    s: Session, tid: uuid.UUID, event: str, rt: Row, user: Any, payload: Row
) -> None:
    """写一条光罩领域事件（审计留痕 + 订阅通知），调用方负责提交。"""
    assert event in _EVENTS, event
    body = {"reticle_id": str(rt["id"]), "reticle_code": rt["code"], **payload}
    audit(s, tid, ENTITIES["reticle"], event, rt, user, {"payload": (None, body)})
    notify(
        s,
        tid,
        event,
        title=f"{_EVENTS[event][0].split('|')[0]}: {rt['code']}",
        params=body,
        object_type="reticle",
        object_id=rt["id"],
        object_code=rt["code"],
        link=f"/mes/reticle?id={rt['id']}",
    )
