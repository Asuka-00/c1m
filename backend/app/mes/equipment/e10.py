"""E10 自动状态迁移：由执行事件（Track In / Track Out 等）触发。"""

import uuid
from typing import Any

import sqlalchemy as sa
from sqlmodel import Session

from app.core.spec.audit import audit
from app.core.spec.base import conn
from app.core.spec.engine import ENTITIES, TABLES
from app.mes.common.query import find, one
from app.mes.common.rows import _upd
from app.mes.equipment.maint import e10_log
from app.mes.equipment.status import e10_current

Row = dict[str, Any]


# ---------------- E10 ----------------
def e10_apply(
    s: Session, tid: uuid.UUID, eq: Row, trigger: str, user: Any, lot: Row
) -> Row | None:
    """按自动规则迁移设备 E10 状态。

    规则匹配：设备类型专用规则优先于通用规则（equipment_type 为空）。
    Track Out 时若同机台仍有其他运行中的批次则跳过；目标状态与当前相同则不变；
    当前→目标不在允许迁移表中则跳过。迁移成功会写审计。

    Args:
        s: 数据库会话。
        tid: 租户 id。
        eq: 设备行。
        trigger: 触发事件（track_in / track_out ...）。
        user: 操作人。
        lot: 触发的批次。

    Returns:
        迁移结果 ``{equipment, from, to}``、跳过原因 ``{skipped}``，无匹配规则时为 None。
    """
    # 同机台仍有其他批次在运行时，Track Out 不触发状态迁移（设备仍在生产）
    if trigger == "track_out":
        t = TABLES["lot"]
        others = (
            conn(s)
            .execute(
                sa.select(sa.func.count()).where(
                    t.c.tenant_id == tid,
                    t.c.equipment_id == eq["id"],
                    t.c.lot_status == "running",
                    t.c.id != lot["id"],
                )
            )
            .scalar()
        )
        if others:
            return {"skipped": f"{others} other lot(s) running"}
    # 设备类型专用规则优先，其次是通用规则（equipment_type 为空）
    rules = find(s, tid, "e10_auto_rule", trigger=trigger, is_active=True)
    rule = next(
        (r for r in rules if r["equipment_type_id"] == eq.get("equipment_type_id")),
        None,
    ) or next((r for r in rules if r["equipment_type_id"] is None), None)
    if not rule:
        return None
    cur = e10_current(s, tid, eq)
    to = one(s, tid, "e10_state", rule["to_state_id"])
    if not to or (cur and cur["id"] == to["id"]):
        return None
    # 必须满足 E10 迁移表：当前状态 -> 目标状态 需被允许
    if cur and not find(
        s, tid, "e10_transition", from_state_id=cur["id"], to_state_id=to["id"]
    ):
        return {"skipped": f"transition {cur['code']} -> {to['code']} not allowed"}
    _upd(s, tid, "equipment", eq["id"], user, e10_state_id=to["id"])
    e10_log(
        s,
        tid,
        eq,
        cur,
        to,
        "auto",
        user,
        note={"key": "e10_auto", "params": {"trigger": trigger, "lot": lot["code"]}},
    )
    audit(
        s,
        tid,
        ENTITIES["equipment"],
        "e10",
        eq,
        user,
        {"e10_state": (cur and cur["code"], to["code"])},
    )
    return {"equipment": eq["code"], "from": cur and cur["code"], "to": to["code"]}
