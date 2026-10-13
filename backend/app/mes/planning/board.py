"""工单进度看板：完工进度、在制分布与交期预警。"""

import uuid
from collections import defaultdict
from datetime import date
from typing import Any

from sqlmodel import Session

from app.mes.common.query import find, one
from app.mes.lot.service import TERMINAL

Row = dict[str, Any]
ACTIVE = ("released", "in_progress", "on_hold", "completed")


def risk(wo: Row, progress: float, today: date, warn_days: int) -> str:
    """交期状态：done（已完工）/ overdue（逾期）/ at_risk（临近交期未完）/ ok / none（无交期）。"""
    if wo["wo_status"] == "completed" or progress >= 1:
        return "done"
    due = wo["due_date"]
    if not due:
        return "none"
    if due < today:
        return "overdue"
    return "at_risk" if (due - today).days <= warn_days else "ok"


def wo_board(
    s: Session, tid: uuid.UUID, warn_days: int = 3, today: date | None = None
) -> list[Row]:
    """工单进度看板（已下达 / 生产中 / 暂停 / 已完工的工单）。

    Args:
        s: 数据库会话。
        tid: 租户 id。
        warn_days: 距交期不超过该天数且未完工时预警。
        today: 基准日期（默认今天）。

    Returns:
        行：计划 / 投产 / 完工 / 在制 / 报废数量、进度、交期剩余天数、交期状态、在制工序分布。
    """
    today = today or date.today()
    lots: dict[Any, list[Row]] = defaultdict(list)
    for x in find(s, tid, "lot"):
        if x["work_order_id"]:
            lots[x["work_order_id"]].append(x)
    ops: dict[Any, str] = {}

    def op_of(step_id: Any) -> str:
        if step_id not in ops:
            st = one(s, tid, "route_step", step_id)
            op = st and one(s, tid, "operation", st["operation_id"])
            ops[step_id] = op["code"] if op else "—"
        return ops[step_id]

    out = []
    for wo in find(s, tid, "work_order", order="code"):
        if wo["wo_status"] not in ACTIVE:
            continue
        ls = lots.get(wo["id"], [])
        wip = [x for x in ls if x["lot_status"] not in TERMINAL]
        dist: dict[str, int] = defaultdict(int)
        for x in wip:
            dist[op_of(x["current_step_id"])] += x["qty"] or 0
        planned = wo["planned_qty"] or 0
        done = wo["completed_qty"] or 0
        prog = done / planned if planned else 0.0
        prod = one(s, tid, "product", wo["product_id"])
        out.append(
            {
                "id": str(wo["id"]),
                "code": wo["code"],
                "product": prod and prod["code"],
                "status": wo["wo_status"],
                "planned": planned,
                "started": wo["started_qty"] or 0,
                "completed": done,
                "wip": sum(x["qty"] or 0 for x in wip),
                "scrapped": sum(x["scrapped_qty"] or 0 for x in ls),
                "lots": len(wip),
                "progress": round(min(prog, 1.0), 4),
                "due_date": wo["due_date"],
                "days_left": (wo["due_date"] - today).days if wo["due_date"] else None,
                "risk": risk(wo, prog, today, warn_days),
                "wip_by_op": [
                    {"operation": k, "qty": v} for k, v in sorted(dist.items())
                ],
            }
        )
    order = {"overdue": 0, "at_risk": 1, "ok": 2, "none": 3, "done": 4}
    out.sort(key=lambda r: (order[r["risk"]], r["due_date"] or date.max, r["code"]))
    return out
