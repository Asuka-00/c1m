"""出货单：校验与确认出货（仅 MES 内部，不做 ERP 库存过账）。

只有已入库（``stored``）且未 Hold 的批次可以出货（批次状态机的 ``ship`` 规则）；
可出货数 = 已确认入库单中该批次的良品数 − 已出货数。批次状态保持 ``stored``，
出货量记在批次的 ``shipped_qty``，写批次履历 ``ship`` 供追溯。
确认的状态流转见 :mod:`app.mes.warehouse.docs`。
"""

import uuid
from typing import Any

import sqlalchemy as sa
from sqlmodel import Session

from app.core import error_codes as ec
from app.core.spec.audit import audit
from app.core.spec.base import conn
from app.core.spec.engine import ENTITIES, TABLES, Entity
from app.core.spec.errors import MesError, fe, http_422
from app.core.spec.validate import validator
from app.mes.common.query import one
from app.mes.common.rows import _upd
from app.mes.lot import service as lot_svc
from app.mes.warehouse import docs

Row = dict[str, Any]
SHIPMENT, LOT = ENTITIES["shipment"], ENTITIES["lot"]
docs.guard_drafts("shipment", "shipment_line")


def good_received(s: Session, tid: uuid.UUID, lot_id: Any) -> int:
    """批次在已确认入库单中的良品数合计。"""
    rl, rc = TABLES["receipt_line"], TABLES["receipt"]
    stmt = (
        sa.select(sa.func.coalesce(sa.func.sum(rl.c.good_qty), 0))
        .join(rc, rc.c.id == rl.c.receipt_id)
        .where(
            rl.c.tenant_id == tid,
            rl.c.lot_id == lot_id,
            rc.c.receipt_status == "confirmed",
        )
    )
    return int(conn(s).execute(stmt).scalar() or 0)


def shippable(s: Session, tid: uuid.UUID, lot: Row) -> int:
    """批次还能出货的数量。"""
    return max(0, good_received(s, tid, lot["id"]) - int(lot["shipped_qty"] or 0))


def _qty_error(s: Session, tid: uuid.UUID, lot: Row, qty: int) -> MesError | None:
    if qty < 1:
        return MesError([fe("qty", ec.FIELD_MIN, "qty: must be >= 1", min=1)])
    room = shippable(s, tid, lot)
    if qty > room:
        return MesError(
            [
                fe(
                    "qty",
                    ec.SHIP_QTY_EXCEEDS,
                    f"qty: {lot['code']} has only {room} left to ship",
                    lot=lot["code"],
                    room=room,
                )
            ]
        )
    return None


@validator("shipment_line")
def _line(s: Session, tid: uuid.UUID, _e: Entity, row: Row, _old: Row | None) -> None:
    lot = one(s, tid, "lot", row.get("lot_id"))
    if not lot:
        raise MesError([fe("lot", ec.LOT_NOT_FOUND_2, "lot: not found")])
    lot_svc.check_transition(lot, "ship")  # 非已入库 / Hold 中 → 422
    if err := _qty_error(s, tid, lot, int(row.get("qty") or 0)):
        raise err
    row["product_id"] = lot["product_id"]


def _post(s: Session, tid: uuid.UUID, ship: Row, lines: list[Row], user: Any) -> None:
    """确认出货：锁定批次并复核，累加已出货数，写批次履历。"""
    locked = lot_svc.lock_lots(s, tid, [x["lot_id"] for x in lines])
    for x in lines:
        lot = locked[x["lot_id"]]
        lot_svc.check_transition(lot, "ship")
        qty = int(x["qty"])
        if err := _qty_error(s, tid, lot, qty):
            raise http_422(err.errors)
        shipped = int(lot["shipped_qty"] or 0) + qty
        _upd(s, tid, "lot", lot["id"], user, shipped_qty=shipped)
        lot_svc.history(
            s,
            tid,
            lot,
            "ship",
            user,
            details={
                "shipment": ship["code"],
                "customer": ship["customer"],
                "qty": qty,
                "shipped_qty": shipped,
            },
        )
        audit(
            s,
            tid,
            LOT,
            "ship",
            lot,
            user,
            {"shipped_qty": (lot["shipped_qty"], shipped)},
        )


def transition(
    s: Session, tid: uuid.UUID, shipment_id: uuid.UUID, action: str, user: Any
) -> Row:
    """执行出货单状态迁移（confirm / cancel）。"""
    return docs.transition(
        s, tid, "shipment", "shipment_line", shipment_id, action, user, _post
    )


def shipments_of(s: Session, tid: uuid.UUID, lot_ids: list[Any]) -> list[Row]:
    """给定批次（及其来源 / 下游）的已确认出货记录，供追溯展示。"""
    sl, sh = TABLES["shipment_line"], TABLES["shipment"]
    rows = conn(s).execute(
        sa.select(
            sl.c.lot_id,
            sl.c.qty,
            sh.c.code,
            sh.c.customer,
            sh.c.waybill,
            sh.c.confirmed_at,
        )
        .join(sh, sh.c.id == sl.c.shipment_id)
        .where(
            sl.c.tenant_id == tid,
            sl.c.lot_id.in_(lot_ids),
            sh.c.issue_status == "confirmed",
        )
        .order_by(sh.c.confirmed_at)
    )
    return [dict(r) for r in rows.mappings()]
