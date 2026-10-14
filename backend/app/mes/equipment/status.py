"""设备状态查询：当前 E10 状态、工具寿命。"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlmodel import Session

from app.core.spec.serialize import dec_str
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


def _dec(v: Any) -> Decimal | None:
    return None if v is None else Decimal(str(v))


def tool_life(s: Session, tid: uuid.UUID, tool: Row) -> tuple[Decimal | None, Decimal]:
    """工具寿命（P2-B10：按 life_unit 计，Decimal，禁止整数运算）。

    Returns:
        ``(寿命上限, 已用)``；上限取工具自身覆盖值，否则取工具类型的上限，均无则 None。
    """
    fx = one(s, tid, "fixture", tool["fixture_id"])
    mx = _dec(tool["max_usage"]) or (_dec(fx["max_uses"]) if fx else None)
    return (mx or None), (_dec(tool["usage_count"]) or Decimal(0))


def warn_ratio(s: Session, tid: uuid.UUID, tool: Row) -> Decimal:
    """预警比例（D54）：工具 warn_ratio → 类型 warn_ratio → warn_pct / 100（默认 0.9）。"""
    if tool.get("warn_ratio") is not None:
        return Decimal(str(tool["warn_ratio"]))
    fx = one(s, tid, "fixture", tool["fixture_id"])
    if fx and fx.get("warn_ratio") is not None:
        return Decimal(str(fx["warn_ratio"]))
    return Decimal(tool.get("warn_pct") or 90) / 100


def tool_block(s: Session, tid: uuid.UUID, tool: Row, today: date) -> str | None:
    """开工硬拦截原因（D53-5 / D54，overridable=false）：已用 >= 上限、过期、状态不可用。"""
    if tool["tool_status"] not in ("available", "in_use"):
        return f"tool {tool['code']} is {tool['tool_status']}"
    mx, used = tool_life(s, tid, tool)
    if mx and used >= mx:
        return f"tool {tool['code']} reached its life ({dec_str(used)}/{dec_str(mx)})"
    if tool["expiry_date"] and tool["expiry_date"] < today:
        return f"tool {tool['code']} expired on {tool['expiry_date']}"
    return None
