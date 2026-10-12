"""设备状态查询：当前 E10 状态、工具寿命。"""

import uuid
from typing import Any

from sqlmodel import Session

from app.mes.common.query import find, one

Row = dict[str, Any]


# ---------------- E10 helpers ----------------
def e10_current(s: Session, tid: uuid.UUID, eq: Row) -> Row | None:
    """设备当前 E10 状态行，未设置时为 None。"""
    st = one(s, tid, "e10_state", eq.get("e10_state_id") or eq.get("initial_state_id"))
    if st:
        return st
    init = [r for r in find(s, tid, "e10_state", order="sort_order") if r["is_initial"]]
    return init[0] if init else None


def tool_life(s: Session, tid: uuid.UUID, tool: Row) -> tuple[int | None, int]:
    """工具寿命。

    Returns:
        ``(最大使用次数, 当前使用次数)``；最大值取工具自身覆盖值，否则取工具类型的上限，均无则 None。
    """
    fx = one(s, tid, "fixture", tool["fixture_id"])
    mx = tool["max_usage"] or (fx["max_uses"] if fx else None)
    return (int(mx) if mx else None), int(tool["usage_count"] or 0)
