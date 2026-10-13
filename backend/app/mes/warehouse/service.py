"""完工入库：入库单校验、状态流转与确认过账（仅 MES 内部，不做 ERP 库存过账）。

状态机（动作：从 → 到）::

    submit    draft -> submitted        （提交：校验批次与可入库数量）
    reject    submitted -> draft        （退回修改）
    confirm   submitted -> confirmed    （确认：累加批次已入库数、工单完工数）
    cancel    draft|submitted -> cancelled

部分入库：一个批次可分多张入库单入库；批次「已入库数（良品 + 报废）」达到批次数量时
状态变为 ``stored``（已入库）并关闭。可入库数 = 批次数量 − 已入库数 − 其他已提交未确认的数量。
"""

import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.core.models import actor_name
from app.core.spec.audit import audit
from app.core.spec.base import conn, now
from app.core.spec.engine import ENTITIES, TABLES, Entity
from app.core.spec.errors import MesError, http_422
from app.core.spec.query import get_row
from app.core.spec.validate import validator
from app.mes.common import coderule
from app.mes.common.query import find, one
from app.mes.common.rows import _upd
from app.mes.lot import service as lot_svc

Row = dict[str, Any]
RECEIPT, LINE, LOT = (ENTITIES[c] for c in ("receipt", "receipt_line", "lot"))

TRANSITIONS: dict[str, tuple[set[str], str]] = {
    "submit": ({"draft"}, "submitted"),
    "reject": ({"submitted"}, "draft"),
    "confirm": ({"submitted"}, "confirmed"),
    "cancel": ({"draft", "submitted"}, "cancelled"),
}
#: 可接收入库的批次状态（完工 = 待入库）
RECEIVABLE = "completed"
#: 允许入库的工单状态（暂停 / 结案 / 取消的工单不可入库）
WO_OPEN = {"released", "in_progress", "completed"}


def _err(field: str, msg: str) -> MesError:
    return MesError([(field, f"{field}: {msg}")])


def pending_qty(
    s: Session, tid: uuid.UUID, lot_id: Any, exclude_receipt: Any = None
) -> int:
    """批次在「已提交未确认」入库单中占用的数量（良品 + 报废）。

    Args:
        s: 数据库会话。
        tid: 租户 id。
        lot_id: 批次 id。
        exclude_receipt: 排除的入库单 id（校验本单时）。

    Returns:
        占用数量。
    """
    rl, rc = TABLES["receipt_line"], TABLES["receipt"]
    stmt = (
        sa.select(sa.func.coalesce(sa.func.sum(rl.c.good_qty + rl.c.scrap_qty), 0))
        .join(rc, rc.c.id == rl.c.receipt_id)
        .where(
            rl.c.tenant_id == tid,
            rl.c.lot_id == lot_id,
            rc.c.receipt_status == "submitted",
        )
    )
    if exclude_receipt is not None:
        stmt = stmt.where(rc.c.id != exclude_receipt)
    return int(conn(s).execute(stmt).scalar() or 0)


def remaining(lot: Row) -> int:
    """批次尚未入库的数量（批次数量 − 已入库数）。"""
    return max(0, int(lot["qty"] or 0) - int(lot.get("received_qty") or 0))


def _check_line(
    s: Session, tid: uuid.UUID, lot: Row | None, good: int, scrap: int, receipt_id: Any
) -> list[tuple[str, str]]:
    """校验一行入库明细（批次状态、工单状态、数量），返回字段错误列表。"""
    if not lot:
        return [("lot", "lot: not found")]
    errs: list[tuple[str, str]] = []
    if lot["lot_status"] != RECEIVABLE:
        errs.append(("lot", f"lot: {lot['code']} is not finished (awaiting receipt)"))
    if lot["on_hold"]:
        errs.append(("lot", f"lot: {lot['code']} is on hold"))
    wo = one(s, tid, "work_order", lot["work_order_id"])
    if wo and wo["wo_status"] not in WO_OPEN:
        errs.append(
            (
                "lot",
                f"lot: work order {wo['code']} is {wo['wo_status']}; cannot receive",
            )
        )
    if good < 0 or scrap < 0:
        errs.append(("good_qty", "good_qty: quantities must be >= 0"))
    elif good + scrap < 1:
        errs.append(("good_qty", "good_qty: good + scrap must be >= 1"))
    else:
        room = remaining(lot) - pending_qty(s, tid, lot["id"], receipt_id)
        if good + scrap > room:
            errs.append(
                (
                    "good_qty",
                    f"good_qty: {lot['code']} has only {max(room, 0)} left to receive",
                )
            )
    return errs


def _retotal(
    s: Session, tid: uuid.UUID, receipt_id: Any, override: Row | None = None
) -> None:
    """重算入库单表头合计（批次数 / 良品数 / 报废数）。

    Args:
        s: 数据库会话。
        tid: 租户 id。
        receipt_id: 入库单 id。
        override: 尚未写库的明细变更 ``{"id", "good_qty", "scrap_qty", "_delete"}``。
    """
    lines = {x["id"]: x for x in find(s, tid, "receipt_line", receipt_id=receipt_id)}
    if override is not None:
        if override.get("_delete"):
            lines.pop(override.get("id"), None)
        else:
            lines[override.get("id") or "new"] = override
    _upd(
        s,
        tid,
        "receipt",
        receipt_id,
        lot_count=len(lines),
        total_good=sum(int(x.get("good_qty") or 0) for x in lines.values()),
        total_scrap=sum(int(x.get("scrap_qty") or 0) for x in lines.values()),
    )


# ---------------- generic CRUD hooks ----------------
@validator("receipt:prefill")
def _prefill(s: Session, tid: uuid.UUID, _e: Entity, row: Row, old: Row | None) -> None:
    if old is None and not row.get("code"):
        t = TABLES["code_rule"]
        rule = (
            conn(s)
            .execute(
                sa.select(t)
                .where(t.c.tenant_id == tid, t.c.target == "receipt")
                .order_by(t.c.code)
            )
            .mappings()
            .first()
        )
        if not rule:
            raise _err("code", "no code rule for receipts; enter a receipt number")
        row["code"] = coderule.generate(s, tid, dict(rule), 1, commit=False)[0]


@validator("receipt")
def _receipt(s: Session, tid: uuid.UUID, _e: Entity, row: Row, old: Row | None) -> None:
    if old and old["receipt_status"] != "draft":
        raise _err("receipt_status", "only draft receipts can be edited")
    wh = one(s, tid, "warehouse", row.get("warehouse_id"))
    if wh and wh["is_active"] is False:
        raise _err("warehouse", "warehouse is inactive")
    loc = one(s, tid, "storage_location", row.get("location_id"))
    if loc:
        if loc["warehouse_id"] != row.get("warehouse_id"):
            raise _err("location", "location does not belong to the warehouse")
        if loc["is_active"] is False:
            raise _err("location", "location is inactive")


@validator("receipt:delete")
def _receipt_delete(
    _s: Session, _t: uuid.UUID, _e: Entity, row: Row, _o: Row | None
) -> None:
    if row["receipt_status"] != "draft":
        raise _err(
            "receipt_status", "only draft receipts can be deleted (cancel instead)"
        )


@validator("receipt_line")
def _line(s: Session, tid: uuid.UUID, _e: Entity, row: Row, old: Row | None) -> None:
    rc = one(s, tid, "receipt", row.get("receipt_id"))
    if not rc or rc["receipt_status"] != "draft":
        raise _err("receipt", "lines can only change while the receipt is a draft")
    if old and old["receipt_id"] != row["receipt_id"]:
        raise _err("receipt", "cannot move a line to another receipt")
    lot = one(s, tid, "lot", row.get("lot_id"))
    errs = _check_line(
        s,
        tid,
        lot,
        int(row.get("good_qty") or 0),
        int(row.get("scrap_qty") or 0),
        rc["id"],
    )
    if errs:
        raise MesError(errs)
    assert lot
    row["work_order_id"], row["product_id"] = lot["work_order_id"], lot["product_id"]
    _retotal(s, tid, rc["id"], row)


@validator("receipt_line:delete")
def _line_delete(
    s: Session, tid: uuid.UUID, _e: Entity, row: Row, _o: Row | None
) -> None:
    rc = one(s, tid, "receipt", row["receipt_id"])
    if rc and rc["receipt_status"] != "draft":
        raise _err("receipt", "lines can only change while the receipt is a draft")
    _retotal(s, tid, row["receipt_id"], {"id": row["id"], "_delete": True})


# ---------------- transitions ----------------
def _validate_all(s: Session, tid: uuid.UUID, rc: Row, lock: bool) -> list[Row]:
    lines = find(s, tid, "receipt_line", order="created_at", receipt_id=rc["id"])
    if not lines:
        raise http_422([("lines", "lines: add at least one lot")])
    errs: list[tuple[str, str]] = []
    for i, x in enumerate(lines, 1):
        lot = (
            lot_svc.lock_lot(s, tid, x["lot_id"])
            if lock
            else one(s, tid, "lot", x["lot_id"])
        )
        for f, m in _check_line(
            s, tid, lot, x["good_qty"] or 0, x["scrap_qty"] or 0, rc["id"]
        ):
            errs.append((f"lines.{i}.{f}", f"line {i}: {m}"))
    if errs:
        raise http_422(errs)
    return lines


def _post(s: Session, tid: uuid.UUID, rc: Row, lines: list[Row], user: Any) -> None:
    """确认过账：累加批次已入库数（满额则关闭批次）与工单完工数，写批次履历。"""
    at = now()
    wo_good: dict[Any, int] = {}
    for x in lines:
        lot = lot_svc.lock_lot(s, tid, x["lot_id"])
        good, scrap = int(x["good_qty"] or 0), int(x["scrap_qty"] or 0)
        received = int(lot["received_qty"] or 0) + good + scrap
        vals: Row = {
            "received_qty": received,
            "scrapped_qty": int(lot["scrapped_qty"] or 0) + scrap,
        }
        closed = received >= int(lot["qty"] or 0)
        if closed:
            vals.update(lot_status="stored", stored_at=at, carrier_id=None)
        _upd(s, tid, "lot", lot["id"], user, **vals)
        before = lot["lot_status"]
        lot.update(vals)
        lot_svc.history(
            s,
            tid,
            lot,
            "receive",
            user,
            from_status=before,
            details={
                "receipt": rc["code"],
                "good_qty": good,
                "scrap_qty": scrap,
                "remaining": remaining(lot),
            },
        )
        audit(
            s,
            tid,
            LOT,
            "receive",
            lot,
            user,
            {"received_qty": (received - good - scrap, received)}
            | ({"lot_status": (before, "stored")} if closed else {}),
        )
        wo_good[lot["work_order_id"]] = wo_good.get(lot["work_order_id"], 0) + good
    for wid, good in wo_good.items():
        wo = one(s, tid, "work_order", wid)
        if wo and good:
            new = int(wo["completed_qty"] or 0) + good
            _upd(s, tid, "work_order", wid, user, completed_qty=new)
            audit(
                s,
                tid,
                ENTITIES["work_order"],
                "receive",
                wo,
                user,
                {"completed_qty": (wo["completed_qty"], new)},
            )


def transition(
    s: Session, tid: uuid.UUID, receipt_id: uuid.UUID, action: str, user: Any
) -> Row:
    """执行入库单状态迁移。

    Args:
        s: 数据库会话。
        tid: 租户 id。
        receipt_id: 入库单 id。
        action: 动作（submit / reject / confirm / cancel）。
        user: 操作人。

    Returns:
        更新后的入库单。

    Raises:
        HTTPException: 非法迁移或数量校验失败（422）。
    """
    if action not in TRANSITIONS:
        raise http_422([("action", f"action: must be one of {', '.join(TRANSITIONS)}")])
    t = TABLES["receipt"]
    r = (
        conn(s)
        .execute(
            sa.select(t)
            .where(t.c.tenant_id == tid, t.c.id == receipt_id)
            .with_for_update()
        )
        .mappings()
        .first()
    )
    rc = dict(r) if r else get_row(s, RECEIPT, tid, receipt_id)  # 404
    allowed, to = TRANSITIONS[action]
    if rc["receipt_status"] not in allowed:
        raise http_422(
            [
                (
                    "receipt_status",
                    f"receipt_status: cannot {action} a {rc['receipt_status']} receipt",
                )
            ]
        )
    at, who = now(), actor_name(user)
    vals: Row = {"receipt_status": to}
    if action == "submit":
        _validate_all(s, tid, rc, lock=False)
        vals.update(submitted_at=at, submitted_by=who)
    elif action == "confirm":
        lines = _validate_all(s, tid, rc, lock=True)
        _post(s, tid, rc, lines, user)
        vals.update(confirmed_at=at, confirmed_by=who)
    elif action == "reject":
        vals.update(submitted_at=None, submitted_by=None)
    _upd(s, tid, "receipt", rc["id"], user, **vals)
    new = get_row(s, RECEIPT, tid, rc["id"])
    audit(
        s,
        tid,
        RECEIPT,
        action,
        new,
        user,
        {"receipt_status": (rc["receipt_status"], to)},
    )
    try:
        s.commit()
    except IntegrityError as ex:  # pragma: no cover - 并发保护
        s.rollback()
        raise http_422([("receipt", "receipt: concurrent update, retry")]) from ex
    return new


def receivable(s: Session, tid: uuid.UUID, lot_id: uuid.UUID) -> Row:
    """批次的可入库信息（供前端新增明细时提示）。"""
    lot = get_row(s, LOT, tid, lot_id)
    room = remaining(lot) - pending_qty(s, tid, lot["id"])
    return {
        "lot_id": str(lot["id"]),
        "qty": lot["qty"],
        "received_qty": lot["received_qty"] or 0,
        "pending_qty": pending_qty(s, tid, lot["id"]),
        "receivable_qty": max(0, room),
        "lot_status": lot["lot_status"],
    }
