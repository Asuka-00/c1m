"""打标模板领域事件（P3-B1）：``marking_template.approved``。

TODO(domain-events.md)：按约定须先由架构师登记到 domain-events.md；此处与其它模块一致，
以 audit_log（entity_type=marking_template，action=事件名，changes.payload）留痕并按订阅通知。
"""

import uuid
from typing import Any

from sqlmodel import Session

from app.core.spec.audit import audit
from app.core.spec.engine import ENTITIES
from app.platform.notification.service import notify, register_event

Row = dict[str, Any]
APPROVED = "marking_template.approved"
register_event(
    APPROVED,
    "Marking template approved|打标模板已批准|マーキングテンプレート承認",
    "info",
    "marking_template",
)


def emit_approved(
    s: Session, tid: uuid.UUID, tpl: Row, ver: Row, user: Any, payload: Row
) -> None:
    """写 audit 留痕并按订阅通知。"""
    audit(
        s,
        tid,
        ENTITIES["marking_template"],
        APPROVED,
        tpl,
        user,
        {"payload": (None, payload)},
    )
    notify(
        s,
        tid,
        APPROVED,
        title=f"Marking template approved: {tpl['code']} v{ver['version']}",
        params=payload,
        object_type="marking_template",
        object_id=tpl["id"],
        object_code=tpl["code"],
        link="/mes/marking-template",
    )
