"""NCR / MRB：不合格品登记 → 处置提案 → 多级审批 → 自动执行处置并关闭。

审批级数按严重度（minor 1 / major 2 / critical 3）；每级须不同的人，提案人不能审批自己的提案。
驳回回到 open 重新提案，已有审批作废。最后一级批准后在同一事务内执行处置：
放行 / 特采 / 降级 / 退供应商只释放 NCR 的 Hold；报废先报废受影响单元（或数量）；
返工标记批次待返工（下次 Move Out 进入当前工步的返工路线）。
"""

import uuid
from typing import Any

import sqlalchemy as sa
from sqlmodel import Session

from app.core import error_codes as ec
from app.core.models import actor_name
from app.core.spec.audit import audit
from app.core.spec.base import conn, now
from app.core.spec.engine import ENTITIES, TABLES
from app.core.spec.errors import coded, fe, http_422
from app.core.spec.serialize import serialize
from app.mes.common.query import find, one
from app.mes.common.rows import _ins, _upd
from app.mes.execution.events import NCR_REVIEW
from app.mes.execution.hold.manage import _reason, default_reason, hold_lot, release
from app.mes.execution.stage.common import LOT
from app.mes.lot.service import check_transition, history, lock_lot, units
from app.platform.notification import service as notification
from app.platform.tenants.service import members_with

Row = dict[str, Any]
NCR = ENTITIES["ncr"]
LEVELS = {"minor": 1, "major": 2, "critical": 3}


def _notify_approvers(
    s: Session, tid: uuid.UUID, n: Row, lot: Row, done: set[Any], level: int
) -> None:
    """通知当前这一级可审批的人：有审批权限，且不是提案人、本轮未审批过。"""
    skip = done | {n["proposed_by"]}
    users = {
        uid
        for uid, name in members_with(s, tid, "mes.ncr:approve").items()
        if name not in skip
    }
    disp = n["disposition"]
    notification.notify(
        s,
        tid,
        NCR_REVIEW,
        title=f"NCR {n['code']} on {lot.get('code')}: {disp} awaiting approval",
        params={"ncr": n["code"], "lot": lot.get("code"), "disposition": disp},
        object_id=n["id"],
        object_code=n["code"],
        link=f"/mes/ncr?id={n['id']}",
        dedupe_key=f"ncr:{n['id']}:{n['proposed_at']:%Y%m%d%H%M%S%f}:L{level}",
        users=users,
    )


def _err(ncr: Row) -> Exception:
    return coded(
        422,
        ec.NCR_STATUS,
        f"NCR {ncr['code']} is {ncr['ncr_status']}",
        ncr=ncr["code"],
        status=ncr["ncr_status"],
    )


def _lock(s: Session, tid: uuid.UUID, ncr_id: Any) -> Row:
    t = TABLES["ncr"]
    r = (
        conn(s)
        .execute(
            sa.select(t).where(t.c.tenant_id == tid, t.c.id == ncr_id).with_for_update()
        )
        .mappings()
        .first()
    )
    if not r:
        raise coded(404, ec.RECORD_NOT_FOUND, "Record not found")
    return dict(r)


def _next_code(s: Session, tid: uuid.UUID) -> str:
    t, prefix = TABLES["ncr"], f"NCR{now():%y%m%d}-"
    n = (
        conn(s)
        .execute(
            sa.select(sa.func.count()).where(
                t.c.tenant_id == tid, t.c.code.like(f"{prefix}%")
            )
        )
        .scalar()
        or 0
    )
    return f"{prefix}{n + 1:03d}"


def detail(s: Session, tid: uuid.UUID, ncr_id: Any) -> Row:
    """NCR 详情：NCR、审批记录、批次与 Hold 是否仍生效。

    Raises:
        HTTPException: 不存在（404）。
    """
    n = one(s, tid, "ncr", ncr_id)
    if not n:
        raise coded(404, ec.RECORD_NOT_FOUND, "Record not found")
    h = one(s, tid, "lot_hold", n["hold_id"])
    return {
        "ncr": serialize(s, tid, NCR, [n])[0],
        "approvals": serialize(
            s,
            tid,
            ENTITIES["ncr_approval"],
            find(s, tid, "ncr_approval", order="at", ncr_id=n["id"]),
        ),
        "hold_active": bool(h and h["is_active"]),
    }


def create(s: Session, tid: uuid.UUID, body: Row, user: Any) -> Row:
    """登记 NCR（默认同时 Hold 批次，来源 ncr）。

    Args:
        s: 数据库会话。
        tid: 租户 id。
        body: ``{lot_id, title, severity, defect_code_id?, description?, unit_ids?,
            qty?, hold, reason_id?}``。
        user: 操作人。

    Raises:
        HTTPException: 批次状态不可 Hold、受影响单元不属于批次（422）。
    """
    lot = lock_lot(s, tid, body["lot_id"])
    check_transition(lot, "hold")
    active = {str(u["id"]): u for u in units(s, tid, lot["id"])}
    ids = [str(i) for i in body.get("unit_ids") or []]
    if any(i not in active for i in ids):
        raise http_422([fe("unit_ids", ec.NCR_UNITS, "units not in lot")])
    codes = [active[i]["code"] for i in dict.fromkeys(ids)]
    code, at, who = _next_code(s, tid), now(), actor_name(user)
    hid = None
    if body.get("hold", True):
        reason = (
            _reason(s, tid, body["reason_id"], "hold")
            if body.get("reason_id")
            else default_reason(s, tid, "hold")
        )
        hid = hold_lot(
            s,
            tid,
            lot,
            user,
            reason,
            source="ncr",
            comment=body["title"],
            note={"key": "ncr", "params": {"ncr": code}},
        )
    nid = _ins(
        s,
        tid,
        "ncr",
        user,
        code=code,
        lot_id=lot["id"],
        title=body["title"][:200],
        severity=body.get("severity") or "major",
        defect_code_id=body.get("defect_code_id"),
        description=body.get("description"),
        qty=len(codes) or int(body.get("qty") or lot["qty"]),
        units=codes or None,
        hold_id=hid,
        ncr_status="open",
        required_levels=LEVELS[body.get("severity") or "major"],
        approved_levels=0,
        raised_by=who,
        raised_at=at,
    )
    history(
        s,
        tid,
        lot,
        "ncr",
        user,
        comment=body["title"],
        details={"ncr": code, "event": "raised"},
    )
    s.commit()
    return detail(s, tid, nid)


def propose(s: Session, tid: uuid.UUID, ncr_id: Any, body: Row, user: Any) -> Row:
    """提出处置方案（open → reviewing），清空本轮审批。

    Raises:
        HTTPException: 状态不是 open、报废缺原因、返工无返工路线（422）。
    """
    n = _lock(s, tid, ncr_id)
    if n["ncr_status"] != "open":
        raise _err(n)
    disp = body["disposition"]
    reason = None
    if disp == "scrap":
        reason = one(s, tid, "reason_code", body.get("scrap_reason_id"))
        if not reason or reason["reason_type"] != "scrap":
            raise http_422([fe("scrap_reason_id", ec.NCR_SCRAP_REASON, "scrap reason")])
    lot = one(s, tid, "lot", n["lot_id"]) or {}
    if disp == "rework":
        step = one(s, tid, "route_step", lot.get("current_step_id"))
        if not step or not step["rework_route_id"]:
            raise http_422(
                [fe("disposition", ec.NCR_NO_REWORK_ROUTE, "no rework route")]
            )
    _upd(
        s,
        tid,
        "ncr",
        n["id"],
        user,
        ncr_status="reviewing",
        disposition=disp,
        disposition_comment=(body.get("comment") or "")[:300] or None,
        scrap_reason_id=reason and reason["id"],
        approved_levels=0,
        proposed_by=actor_name(user),
        proposed_at=now(),
    )
    _notify_approvers(s, tid, _lock(s, tid, n["id"]), lot, set(), 1)
    s.commit()
    return detail(s, tid, n["id"])


def approve(s: Session, tid: uuid.UUID, ncr_id: Any, body: Row, user: Any) -> Row:
    """审批一级（approve / reject）；最后一级批准后执行处置并关闭。

    Raises:
        HTTPException: 状态不是 reviewing、提案人自审、本轮已审批、驳回无备注（422）。
    """
    n = _lock(s, tid, ncr_id)
    if n["ncr_status"] != "reviewing":
        raise _err(n)
    who, at = actor_name(user), now()
    if who == n["proposed_by"]:
        raise http_422([fe("decision", ec.NCR_SELF_APPROVE, "self approval")])
    done = [
        a
        for a in find(s, tid, "ncr_approval", ncr_id=n["id"], decision="approve")
        if a["at"] and n["proposed_at"] and a["at"] >= n["proposed_at"]
    ]
    if who in {a["username"] for a in done}:
        raise http_422([fe("decision", ec.NCR_ALREADY_APPROVED, "already approved")])
    decision, comment = body["decision"], (body.get("comment") or "").strip()
    if decision == "reject" and not comment:
        raise http_422([fe("comment", ec.NCR_REJECT_COMMENT, "comment required")])
    level = (n["approved_levels"] or 0) + 1
    _ins(
        s,
        tid,
        "ncr_approval",
        user,
        ncr_id=n["id"],
        level=level,
        decision=decision,
        comment=comment[:300] or None,
        username=who,
        at=at,
    )
    notification.close(s, tid, NCR_REVIEW, n["id"])
    if decision == "reject":
        _upd(s, tid, "ncr", n["id"], user, ncr_status="open", approved_levels=0)
    elif level < (n["required_levels"] or 1):
        _upd(s, tid, "ncr", n["id"], user, approved_levels=level)
        lot = one(s, tid, "lot", n["lot_id"]) or {}
        names = {a["username"] for a in done} | {who}
        _notify_approvers(s, tid, n, lot, names, level + 1)
    else:
        result = _execute(s, tid, n, user)
        _upd(
            s,
            tid,
            "ncr",
            n["id"],
            user,
            approved_levels=level,
            ncr_status="closed",
            closed_by=who,
            closed_at=at,
            result=result,
        )
    s.commit()
    return detail(s, tid, n["id"])


def cancel(s: Session, tid: uuid.UUID, ncr_id: Any, body: Row, user: Any) -> Row:
    """取消 NCR（open / reviewing → cancelled），释放其 Hold。"""
    n = _lock(s, tid, ncr_id)
    if n["ncr_status"] not in ("open", "reviewing"):
        raise _err(n)
    comment = (body.get("comment") or "").strip() or None
    lot = lock_lot(s, tid, n["lot_id"])
    _release(s, tid, n, user, f"NCR {n['code']} cancelled: {comment or ''}".strip())
    _upd(
        s,
        tid,
        "ncr",
        n["id"],
        user,
        ncr_status="cancelled",
        closed_by=actor_name(user),
        closed_at=now(),
        result={"cancelled": comment},
    )
    notification.close(s, tid, NCR_REVIEW, n["id"])
    history(
        s,
        tid,
        lot,
        "ncr",
        user,
        comment=comment,
        details={"ncr": n["code"], "event": "cancelled"},
    )
    s.commit()
    return detail(s, tid, n["id"])


def _release(s: Session, tid: uuid.UUID, n: Row, user: Any, comment: str) -> bool:
    h = one(s, tid, "lot_hold", n["hold_id"])
    if not h or not h["is_active"]:
        return False
    release(s, tid, h["id"], user, None, comment[:300])
    return True


def _scrap(s: Session, tid: uuid.UUID, lot: Row, n: Row, user: Any) -> int:
    """报废 NCR 受影响的单元（未指定则全部）或数量，返回报废数。"""
    if lot["lot_status"] == "running":
        check_transition(lot, "scrap")  # 加工中不能报废（decisions.md #3）
    reason_id = n["scrap_reason_id"]
    picked: list[Row] = []
    if (lot["tracking_level"] or "wafer") == "quantity":
        cnt = min(int(n["qty"] or lot["qty"]), int(lot["qty"]))
    else:
        active = units(s, tid, lot["id"])
        want = set(n["units"] or [])
        picked = [u for u in active if not want or u["code"] in want]
        cnt = len(picked)
        for u in picked:
            _upd(
                s,
                tid,
                "wafer",
                u["id"],
                user,
                wafer_status="scrapped",
                scrap_reason_id=reason_id,
            )
    qty = lot["qty"] - cnt
    vals: Row = {"qty": qty, "scrapped_qty": (lot["scrapped_qty"] or 0) + cnt}
    if qty <= 0:
        vals["lot_status"] = "scrapped"
    old = lot["lot_status"]
    _upd(s, tid, "lot", lot["id"], user, **vals)
    lot.update(vals)
    history(
        s,
        tid,
        lot,
        "scrap",
        user,
        qty=cnt,
        from_status=old,
        reason_id=reason_id,
        details={
            "source": "ncr",
            "ncr": n["code"],
            "units": [u["code"] for u in picked],
        },
    )
    return cnt


def _execute(s: Session, tid: uuid.UUID, n: Row, user: Any) -> Row:
    """执行已批准的处置，返回执行摘要。"""
    lot = lock_lot(s, tid, n["lot_id"])
    disp = n["disposition"]
    out: Row = {"disposition": disp}
    if disp == "scrap":
        out["scrapped"] = _scrap(s, tid, lot, n, user)
    elif disp == "rework":
        _upd(s, tid, "lot", lot["id"], user, pending_rework=True)
        out["pending_rework"] = True
    elif disp == "downgrade":
        attrs = {**(lot.get("attrs") or {}), "grade": "downgraded", "ncr": n["code"]}
        _upd(s, tid, "lot", lot["id"], user, attrs=attrs)
        out["grade"] = "downgraded"
    out["released"] = _release(s, tid, n, user, f"NCR {n['code']}: {disp}")
    history(
        s,
        tid,
        lot,
        "ncr",
        user,
        comment=n["disposition_comment"],
        details={"ncr": n["code"], "event": "closed", **out},
    )
    audit(
        s,
        tid,
        LOT,
        "disposition",
        lot,
        user,
        {"ncr": (None, n["code"]), "disposition": (None, disp)},
    )
    return out
