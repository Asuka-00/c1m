"""批次操作台的拆合批上下文。"""

import uuid
from typing import Any

import sqlalchemy as sa
from sqlmodel import Session

from app.core.spec.base import conn
from app.core.spec.engine import TABLES
from app.mes.execution.split_merge.merge import merge_candidates
from app.mes.execution.split_merge.rules import (
    SPLIT_STATES,
    _children,
    _prio,
    _prio_json,
    rule_for,
)

Row = dict[str, Any]


# ---------------- console context ----------------
def sm_context(s: Session, tid: uuid.UUID, lot: Row) -> Row:
    """拆合批上下文：是否可拆 / 可合、规则摘要、可选单元、合批候选。"""
    rule = rule_for(s, tid, lot)
    g = TABLES["lot_genealogy"]
    L = TABLES["lot"]
    P, C = L.alias("p"), L.alias("c")
    rows = (
        conn(s)
        .execute(
            sa.select(g, P.c.code.label("parent_code"), C.c.code.label("child_code"))
            .join(P, P.c.id == g.c.parent_lot_id)
            .join(C, C.c.id == g.c.child_lot_id)
            .where(
                g.c.tenant_id == tid,
                sa.or_(g.c.parent_lot_id == lot["id"], g.c.child_lot_id == lot["id"]),
            )
            .order_by(g.c.at)
        )
        .mappings()
    )
    return {
        "rule": rule
        and {
            "code": rule["code"],
            "allow_split": rule["allow_split"],
            "allow_merge": rule["allow_merge"],
            "max_children": rule["max_children"],
            "min_qty": rule["min_wafers"],
            "child_id_mode": rule.get("child_id_mode") or "suffix",
            "merge_same_wo": rule.get("merge_same_wo", True),
            "children": len(_children(s, tid, lot["id"])),
        },
        "allowed": lot["lot_status"] in SPLIT_STATES,
        "priority": _prio_json(_prio(s, tid, lot["priority_id"])),
        "candidates": merge_candidates(s, tid, lot)
        if lot["lot_status"] in SPLIT_STATES
        else [],
        "genealogy": [
            {
                "relation": r["relation"],
                "parent_id": str(r["parent_lot_id"]),
                "parent": r["parent_code"],
                "child_id": str(r["child_lot_id"]),
                "child": r["child_code"],
                "qty": r["qty"],
                "units": r["units"] or [],
                "at": r["at"].isoformat() if r["at"] else None,
                "user": r["username"],
            }
            for r in rows
        ],
    }
