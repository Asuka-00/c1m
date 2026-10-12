"""设备维护：E10 手动改状态与状态履历、PM 计划到期判定与执行、设备状态看板。"""

import uuid
from datetime import datetime, timedelta
from typing import Any

import sqlalchemy as sa
from fastapi import HTTPException
from sqlmodel import Session

from app.core.spec.audit import audit
from app.core.spec.base import conn, now
from app.core.spec.engine import ENTITIES, TABLES
from app.core.spec.errors import http_422
from app.mes.common.query import find, one
from app.mes.common.rows import _ins, _upd
from app.mes.equipment.events import (
    DOWNTIME,
    EQP_DOWN,
    PM_DUE,
    PM_OVERDUE,
    notify_eqp,
)
from app.mes.equipment.status import e10_current

Row = dict[str, Any]
#: 视为宕机（触发设备宕机通知）的 E10 类别：计划 / 非计划停机
DOWN_CATEGORIES = ("UDT", "SDT")


def e10_log(
    s: Session,
    tid: uuid.UUID,
    eq: Row,
    frm: Row | None,
    to: Row,
    source: str,
    user: Any,
    reason_id: Any = None,
    comment: str | None = None,
) -> None:
    """写一条 E10 状态履历（手动 / 自动迁移共用）。"""
    _ins(
        s,
        tid,
        "e10_history",
        user,
        equipment_id=eq["id"],
        from_state_id=frm and frm["id"],
        to_state_id=to["id"],
        source=source,
        reason_id=reason_id,
        comment=comment,
        user_email=getattr(user, "email", None),
        at=now(),
    )


def e10_change(
    s: Session, tid: uuid.UUID, eq_id: uuid.UUID, body: Row, user: Any
) -> Row:
    """手动变更设备 E10 状态。

    校验：目标状态存在且与当前不同；当前→目标须在 E10 迁移表中；迁移要求原因时必须给出
    ``e10`` 类型的原因代码。写状态履历与审计。

    Args:
        s: 数据库会话。
        tid: 租户 id。
        eq_id: 设备 id。
        body: ``{to_state_id, reason_id?, comment?}``。
        user: 操作人。

    Returns:
        ``{equipment, from, to}``。
    """
    eq = one(s, tid, "equipment", eq_id)
    if not eq:
        raise HTTPException(status_code=404, detail="equipment not found")
    to = one(s, tid, "e10_state", body.get("to_state_id"))
    if not to:
        raise http_422([("to_state_id", "to_state_id: unknown E10 state")])
    cur = e10_current(s, tid, eq)
    if cur and cur["id"] == to["id"]:
        raise http_422([("to_state_id", f"to_state_id: already {to['code']}")])
    tr = (
        find(s, tid, "e10_transition", from_state_id=cur["id"], to_state_id=to["id"])
        if cur
        else []
    )
    if cur and not tr:
        raise http_422(
            [("to_state_id", f"to_state_id: {cur['code']} -> {to['code']} not allowed")]
        )
    reason = one(s, tid, "reason_code", body.get("reason_id"))
    if body.get("reason_id") and (not reason or reason["reason_type"] != "e10"):
        raise http_422([("reason_id", "reason_id: must be an e10 reason code")])
    if tr and tr[0]["reason_required"] and not reason:
        raise http_422([("reason_id", "reason_id: required for this transition")])
    _upd(s, tid, "equipment", eq["id"], user, e10_state_id=to["id"])
    e10_log(
        s,
        tid,
        eq,
        cur,
        to,
        "manual",
        user,
        reason and reason["id"],
        body.get("comment"),
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
    if to["e10_category"] in DOWN_CATEGORIES:
        notify_eqp(
            s,
            tid,
            EQP_DOWN,
            eq,
            f"Equipment {eq['code']} down: {to['code']} {to['name']}",
            {
                "state": to["code"],
                "state_name": to["name"],
                "reason": reason["code"] if reason else "",
                "comment": body.get("comment") or "",
            },
        )
    s.commit()
    return {"equipment": eq["code"], "from": cur and cur["code"], "to": to["code"]}


def _plans(s: Session, tid: uuid.UUID, eq: Row) -> list[Row]:
    """适用于设备的有效 PM 计划（指定设备，或同设备类型且未指定设备）。"""
    return [
        p
        for p in find(s, tid, "pm_plan", is_active=True)
        if p["equipment_id"] == eq["id"]
        or (
            p["equipment_id"] is None
            and p["equipment_type_id"]
            and p["equipment_type_id"] == eq.get("equipment_type_id")
        )
    ]


def _lots_since(s: Session, tid: uuid.UUID, eq_id: Any, since: datetime | None) -> int:
    """自 ``since`` 起在该设备上 Track In 的批次数。"""
    h = TABLES["lot_history"]
    q = sa.select(sa.func.count()).where(
        h.c.tenant_id == tid, h.c.equipment_id == eq_id, h.c.action == "track_in"
    )
    if since:
        q = q.where(h.c.at > since)
    return int(conn(s).execute(q).scalar() or 0)


def pm_status(
    s: Session, tid: uuid.UUID, eq: Row, at: datetime | None = None
) -> list[Row]:
    """设备各 PM 计划的到期状态。

    起算点为该设备该计划的最近一次 PM 记录，无记录时为设备创建时间。
    到期：天数周期已满，或自起算点 Track In 的批次数达到批次周期；
    预警：距天数到期不超过 ``warn_days`` 天。

    Returns:
        每计划 ``{plan_id, plan, last_done, next_due, days_left, lots_since,
        interval_lots, due, warn}``。
    """
    at = at or now()
    out = []
    for p in _plans(s, tid, eq):
        recs = find(s, tid, "pm_record", pm_plan_id=p["id"], equipment_id=eq["id"])
        last = max((r["done_at"] for r in recs if r["done_at"]), default=None)
        base = last or eq.get("created_at") or at
        nxt = base + timedelta(days=p["interval_days"]) if p["interval_days"] else None
        days_left = (
            round((nxt - at).total_seconds() / 86400, 1) if nxt is not None else None
        )
        lots = _lots_since(s, tid, eq["id"], base)
        due = bool(
            (days_left is not None and days_left <= 0)
            or (p["interval_lots"] and lots >= p["interval_lots"])
        )
        warn = bool(
            not due and days_left is not None and days_left <= (p["warn_days"] or 0)
        )
        out.append(
            {
                "plan_id": str(p["id"]),
                "plan": p["code"],
                "last_done": last and last.isoformat(),
                "next_due": nxt and nxt.isoformat(),
                "days_left": days_left,
                "lots_since": lots,
                "interval_lots": p["interval_lots"],
                "due": due,
                "warn": warn,
            }
        )
    return out


def pm_complete(
    s: Session, tid: uuid.UUID, plan_id: uuid.UUID, body: Row, user: Any
) -> Row:
    """登记 PM 完成（重置该设备该计划的天数 / 批次周期）。

    Args:
        s: 数据库会话。
        tid: 租户 id。
        plan_id: PM 计划 id。
        body: ``{equipment_id, result?, comment?}``。
        user: 操作人。

    Returns:
        新的 PM 状态列表。
    """
    p = one(s, tid, "pm_plan", plan_id)
    eq = one(s, tid, "equipment", body.get("equipment_id"))
    if not p or not eq:
        raise HTTPException(status_code=404, detail="PM plan / equipment not found")
    if not any(x["id"] == p["id"] for x in _plans(s, tid, eq)):
        raise http_422([("equipment_id", "equipment_id: plan does not apply")])
    _ins(
        s,
        tid,
        "pm_record",
        user,
        pm_plan_id=p["id"],
        equipment_id=eq["id"],
        result=body.get("result") or "ok",
        comment=body.get("comment"),
        user_email=getattr(user, "email", None),
        done_at=now(),
    )
    audit(s, tid, ENTITIES["equipment"], "pm", eq, user, {"pm": (None, p["code"])})
    s.commit()
    return {"pm": pm_status(s, tid, eq)}


def equipment_board(s: Session, tid: uuid.UUID) -> list[Row]:
    """设备状态看板：主设备的当前 E10 状态、可迁移状态、PM 状态、进行中的停机。"""
    states = {r["id"]: r for r in find(s, tid, "e10_state")}
    trans = find(s, tid, "e10_transition")
    open_dt = {
        d["equipment_id"] for d in find(s, tid, "downtime") if d["end_at"] is None
    }
    wcs = {w["id"]: w for w in find(s, tid, "workcenter")}
    out = []
    for eq in find(s, tid, "equipment", order="code", unit_kind="main"):
        wc = wcs.get(eq.get("workcenter_id"))
        cur = e10_current(s, tid, eq)
        nxt = [t for t in trans if cur is None or t["from_state_id"] == cur["id"]]
        pm = pm_status(s, tid, eq)
        out.append(
            {
                "id": str(eq["id"]),
                "code": eq["code"],
                "name": eq["name"],
                "is_active": eq["is_active"],
                "workcenter": wc and wc["code"],
                "workcenter_name": wc and wc["name"],
                "state": cur
                and {
                    "id": str(cur["id"]),
                    "code": cur["code"],
                    "name": cur["name"],
                    "category": cur["e10_category"],
                    "color": cur["color"],
                },
                "next": [
                    {
                        "id": str(t["to_state_id"]),
                        "code": states[t["to_state_id"]]["code"],
                        "name": states[t["to_state_id"]]["name"],
                        "reason_required": t["reason_required"],
                    }
                    for t in trans
                    if t in nxt and t["to_state_id"] in states
                ],
                "pm": pm,
                "pm_due": any(x["due"] for x in pm),
                "pm_warn": any(x["warn"] for x in pm),
                "down": eq["id"] in open_dt,
            }
        )
    return out


def pm_notify(s: Session, tid: uuid.UUID) -> int:
    """PM 到期通知：即将到期 / 已超期各在每个周期内通知一次（按上次 PM 时间去重），返回发送数。"""
    n = 0
    for eq in find(s, tid, "equipment", unit_kind="main", is_active=True):
        for x in pm_status(s, tid, eq):
            if not (x["due"] or x["warn"]):
                continue
            ev = PM_OVERDUE if x["due"] else PM_DUE
            base = x["last_done"] or "initial"
            title = (
                f"PM {x['plan']} overdue on {eq['code']}"
                if x["due"]
                else f"PM {x['plan']} on {eq['code']} due soon"
            )
            n += bool(
                notify_eqp(
                    s,
                    tid,
                    ev,
                    eq,
                    title,
                    {
                        "plan": x["plan"],
                        "days_left": x["days_left"] or 0,
                        "lots": x["lots_since"],
                    },
                    f"{ev}:{eq['id']}:{x['plan_id']}:{base}",
                )
            )
    return n


def downtime_notify(s: Session, tid: uuid.UUID, row: Row) -> None:
    """新建停机记录通知（按设备 + 开始时间去重）。"""
    eq = one(s, tid, "equipment", row.get("equipment_id"))
    if not eq:
        return
    rc = one(s, tid, "reason_code", row.get("reason_id"))
    start = row.get("start_at")
    notify_eqp(
        s,
        tid,
        DOWNTIME,
        eq,
        f"Downtime on {eq['code']}: {rc['code'] if rc else ''}",
        {"reason": rc["code"] if rc else "", "start": str(start or "")},
        f"downtime:{eq['id']}:{start}",
    )
