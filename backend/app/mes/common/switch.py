"""租户级管控开关（检查规则方案）。"""

import uuid
from typing import Any

from sqlmodel import Session

from app.mes.common.query import find

Row = dict[str, Any]


def switch(s: Session, tid: uuid.UUID, check: str) -> Row | None:
    """租户级管控开关（定时提醒等无工步上下文的管控）。

    取该检查类型的第一条有效规则：严重度 ``off`` 为关闭（返回 None），
    否则返回规则参数；无规则时默认开启（返回空参数）。
    """
    for r in find(s, tid, "check_rule", order="code", check_type=check, is_active=True):
        return None if r["severity"] == "off" else dict(r["params"] or {})
    return {}
