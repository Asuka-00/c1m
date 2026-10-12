"""Equipment status queries: current E10 state, tool life."""

import uuid
from typing import Any

from sqlmodel import Session

from app.mes.common.query import find, one

Row = dict[str, Any]


# ---------------- E10 helpers ----------------
def e10_current(s: Session, tid: uuid.UUID, eq: Row) -> Row | None:
    st = one(s, tid, "e10_state", eq.get("e10_state_id") or eq.get("initial_state_id"))
    if st:
        return st
    init = [r for r in find(s, tid, "e10_state", order="sort_order") if r["is_initial"]]
    return init[0] if init else None


def tool_life(s: Session, tid: uuid.UUID, tool: Row) -> tuple[int | None, int]:
    """(max usage: tool override or the tool type's max uses, current usage)."""
    fx = one(s, tid, "fixture", tool["fixture_id"])
    mx = tool["max_usage"] or (fx["max_uses"] if fx else None)
    return (int(mx) if mx else None), int(tool["usage_count"] or 0)
