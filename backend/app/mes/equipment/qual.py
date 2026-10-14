"""PM 后 Qual 放行（B6，bom-p1-tasks.md）。

- PM 判 OK：机台 ``qual_state`` 转为 ``wait_qual``（WAIT_QUAL），生成一条 Qual 任务（已有
  未登记任务时沿用，不重复生成）。PM 判 NG：周期不重置、机台状态不变。
- 待 Qual 期间进站（Move In / Track In）硬拦截，结果写入卡控记录（见 :func:`qual_block`）。
- 登记 Qual 通过：任务关闭，机台恢复 ``ready``；不通过：任务关闭为 failed 并生成复测任务，
  机台保持待 Qual。
"""

import uuid
from typing import Any

from fastapi import HTTPException
from sqlmodel import Session

from app.core.models import actor_name
from app.core.spec.audit import audit
from app.core.spec.base import now
from app.core.spec.engine import ENTITIES
from app.core.spec.serialize import serialize
from app.mes.common.query import find, one
from app.mes.common.rows import _ins, _upd

Row = dict[str, Any]
ENT = "equipment_qual"
WAIT = "wait_qual"


def _ser(s: Session, tid: uuid.UUID, row: Row | None) -> Row | None:
    return serialize(s, tid, ENTITIES[ENT], [row])[0] if row else None


def open_task(s: Session, tid: uuid.UUID, eq_id: Any) -> Row | None:
    """机台当前未登记的 Qual 任务（最多一条）。"""
    rows = find(s, tid, ENT, equipment_id=eq_id, qual_status="open")
    return min(rows, key=lambda r: r["requested_at"]) if rows else None


def _new_task(
    s: Session,
    tid: uuid.UUID,
    eq: Row,
    user: Any,
    *,
    plan_id: Any = None,
    record_id: Any = None,
    retry_of: Any = None,
) -> Row:
    rid = _ins(
        s,
        tid,
        ENT,
        user,
        equipment_id=eq["id"],
        pm_plan_id=plan_id,
        pm_record_id=record_id,
        retry_of_id=retry_of,
        qual_status="open",
        requested_at=now(),
    )
    row = one(s, tid, ENT, rid)
    assert row
    return row


def start_qual(
    s: Session, tid: uuid.UUID, eq: Row, plan_id: Any, record_id: Any, user: Any
) -> Row:
    """PM 判 OK 后：机台转待 Qual 并生成 Qual 任务（已有未登记任务时沿用）。调用方提交。"""
    task = open_task(s, tid, eq["id"]) or _new_task(
        s, tid, eq, user, plan_id=plan_id, record_id=record_id
    )
    if eq.get("qual_state") != WAIT:
        _upd(s, tid, "equipment", eq["id"], user, qual_state=WAIT)
        audit(
            s,
            tid,
            ENTITIES["equipment"],
            "qual",
            eq,
            user,
            {"qual_state": (eq.get("qual_state") or "ready", WAIT)},
        )
    return task


def record_result(
    s: Session, tid: uuid.UUID, task_id: uuid.UUID, body: Row, user: Any
) -> Row:
    """登记 Qual 结果。

    Args:
        s: 数据库会话。
        tid: 租户 id。
        task_id: Qual 任务 id。
        body: ``{result: pass | fail, comment?}``。
        user: 操作人。

    Returns:
        ``{data: 任务, next_task: 复测任务或 None, equipment: {id, code, qual_state}}``。

    Raises:
        HTTPException: 任务不存在（404）；任务已登记（409 qual_task_closed）。
    """
    task = one(s, tid, ENT, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Record not found")
    if task["qual_status"] != "open":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "qual_task_closed",
                "message": f"Qual task already {task['qual_status']}",
                "qual_status": task["qual_status"],
            },
        )
    eq = one(s, tid, "equipment", task["equipment_id"])
    assert eq
    ok = body["result"] == "pass"
    _upd(
        s,
        tid,
        ENT,
        task["id"],
        user,
        qual_status="passed" if ok else "failed",
        done_by=actor_name(user),
        done_at=now(),
        comment=(str(body.get("comment") or "").strip() or None),
    )
    nxt = None
    if ok:
        if not open_task(s, tid, eq["id"]):
            _upd(s, tid, "equipment", eq["id"], user, qual_state="ready")
    else:  # 不通过：保持待 Qual，生成复测任务
        nxt = _new_task(
            s,
            tid,
            eq,
            user,
            plan_id=task["pm_plan_id"],
            record_id=task["pm_record_id"],
            retry_of=task["id"],
        )
        if eq.get("qual_state") != WAIT:
            _upd(s, tid, "equipment", eq["id"], user, qual_state=WAIT)
    cur = one(s, tid, "equipment", eq["id"])
    assert cur
    audit(
        s,
        tid,
        ENTITIES["equipment"],
        "qual",
        cur,
        user,
        {
            "qual": (None, "passed" if ok else "failed"),
            "qual_state": (eq.get("qual_state") or "ready", cur["qual_state"]),
        },
    )
    s.commit()
    return {
        "data": _ser(s, tid, one(s, tid, ENT, task["id"])),
        "next_task": _ser(s, tid, nxt),
        "equipment": {
            "id": str(cur["id"]),
            "code": cur["code"],
            "qual_state": cur["qual_state"],
        },
    }


def qual_block(s: Session, tid: uuid.UUID, eq: Row | None) -> Row | None:
    """机台待 Qual 时返回 ``{equipment, task_id}``（供进站卡控），否则 None。"""
    if not eq or (eq.get("qual_state") or "ready") != WAIT:
        return None
    t = open_task(s, tid, eq["id"])
    return {"equipment": eq["code"], "task_id": t and str(t["id"])}
