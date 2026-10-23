"""领料单：校验、确认发料与工单物料需求（仅 MES 内部，不做 ERP 库存过账）。

确认（状态流转见 :mod:`app.mes.warehouse.docs`）：扣减源物料批，拆出归属该工单的线边批。

确认后新批的 ``work_order`` 为领料工单，出站扣料只会用到本工单的批或无归属的批。
"""

import uuid
from typing import Any

import sqlalchemy as sa
from sqlmodel import Session

from app.core import error_codes as ec
from app.core.spec.base import conn
from app.core.spec.engine import ENTITIES, TABLES, Entity
from app.core.spec.errors import MesError, fe, http_422
from app.core.spec.query import get_row
from app.core.spec.validate import validator
from app.mes.common.query import find, one
from app.mes.common.rows import _ins, _upd
from app.mes.common.uom import convert
from app.mes.warehouse import docs

Row = dict[str, Any]
ISSUE = ENTITIES["material_issue"]
#: 可领料的工单状态
WO_OPEN = {"released", "in_progress"}
#: 物料批编码上限 64，留出 "-NN" 后缀
CODE_ROOM = 56


def _err(field: str, code: int, msg: str, **params: Any) -> MesError:
    return MesError([fe(field, code, f"{field}: {msg}", **params)])


def _lot_errors(lot: Row | None, qty: float) -> MesError | None:
    """校验一行领料：源批可用、未归属工单、数量不超过剩余。"""
    if not lot:
        return _err("material_lot", ec.RECORD_NOT_FOUND, "not found")
    if lot["ml_status"] != "available" or lot["work_order_id"]:
        return _err(
            "material_lot",
            ec.MATERIAL_LOT_UNAVAILABLE,
            f"{lot['code']} is not available",
            lot=lot["code"],
        )
    if qty <= 0:
        return _err("qty", ec.FIELD_GT, "must be > 0", min=0)
    room = float(lot["qty_remaining"] or 0)
    if qty > room:
        return _err(
            "qty",
            ec.ISSUE_QTY_EXCEEDS,
            f"{lot['code']} has only {room:g} left",
            lot=lot["code"],
            room=room,
        )
    return None


def _issue_wo_error(wo: Row) -> MesError:
    return _err(
        "work_order",
        ec.ISSUE_WO_STATUS,
        f"{wo['code']} is {wo['wo_status']}",
        wo=wo["code"],
        status=wo["wo_status"],
    )


# ---------------- generic CRUD hooks ----------------
docs.guard_drafts("material_issue", "material_issue_line")


@validator("material_issue")
def _issue(s: Session, tid: uuid.UUID, _e: Entity, row: Row, _old: Row | None) -> None:
    wo = one(s, tid, "work_order", row.get("work_order_id"))
    if wo and wo["wo_status"] not in WO_OPEN:
        raise _issue_wo_error(wo)


@validator("material_issue_line")
def _line(s: Session, tid: uuid.UUID, _e: Entity, row: Row, _old: Row | None) -> None:
    lot = one(s, tid, "material_lot", row.get("material_lot_id"))
    if err := _lot_errors(lot, float(row.get("qty") or 0)):
        raise err


def _post(s: Session, tid: uuid.UUID, iss: Row, lines: list[Row], user: Any) -> None:
    """确认过账：逐行锁定源批并复核，扣减后拆出归属工单的新批。"""
    t = TABLES["material_lot"]
    for n, x in enumerate(sorted(lines, key=lambda x: x["material_lot_id"]), 1):
        r = (
            conn(s)
            .execute(
                sa.select(t)
                .where(t.c.tenant_id == tid, t.c.id == x["material_lot_id"])
                .with_for_update()
            )
            .mappings()
            .first()
        )
        src = dict(r) if r else None
        qty = float(x["qty"])
        if err := _lot_errors(src, qty):
            raise http_422(err.errors)
        assert src
        left = round(float(src["qty_remaining"]) - qty, 9)
        _upd(
            s,
            tid,
            "material_lot",
            src["id"],
            user,
            qty_remaining=left,
            ml_status="empty" if left <= 0 else src["ml_status"],
        )
        _ins(
            s,
            tid,
            "material_lot",
            user,
            code=f"{iss['code'][:CODE_ROOM]}-{n}",
            material_id=src["material_id"],
            qty_remaining=qty,
            initial_qty=qty,
            uom_id=src["uom_id"],
            work_order_id=iss["work_order_id"],
            expiry_date=src["expiry_date"],
            location=src["location"],
            ml_status="available",
        )


def _confirm(s: Session, tid: uuid.UUID, iss: Row, lines: list[Row], user: Any) -> None:
    wo = one(s, tid, "work_order", iss["work_order_id"])
    if wo and wo["wo_status"] not in WO_OPEN:
        raise http_422(_issue_wo_error(wo).errors)
    _post(s, tid, iss, lines, user)


def transition(
    s: Session, tid: uuid.UUID, issue_id: uuid.UUID, action: str, user: Any
) -> Row:
    """执行领料单状态迁移（confirm / cancel）。"""
    return docs.transition(
        s,
        tid,
        "material_issue",
        "material_issue_line",
        issue_id,
        action,
        user,
        _confirm,
    )


# ---------------- requirements ----------------
def requirements(s: Session, tid: uuid.UUID, wo_id: uuid.UUID) -> Row:
    """工单的物料需求与已领数量（按物料汇总；需求来自工单锁定的 BOM）。

    需求 = 用量 ×（按单元计时乘以工单计划片数）×（1 + 损耗率），统一换算为该物料首条
    明细的单位；已领 = 归属该工单的线边批的领入数量。

    Raises:
        HTTPException: 工单不存在（404）；单位之间没有换算关系（422）。
    """
    wo = get_row(s, ENTITIES["work_order"], tid, wo_id)
    bom = one(s, tid, "bom", wo["bom_id"])
    need: dict[Any, Row] = {}
    lines = find(s, tid, "bom_line", order="created_at", bom_id=wo["bom_id"])
    for ln in lines if wo["bom_id"] else []:
        q = float(ln["qty"]) * (
            wo["planned_qty"] if ln["qty_basis"] == "per_unit" else 1
        )
        q *= 1 + float(ln["scrap_rate"] or 0) / 100
        cur = need.setdefault(
            ln["material_id"],
            {"material_id": ln["material_id"], "uom_id": ln["uom_id"], "required": 0.0},
        )
        cur["required"] += convert(s, tid, ln["uom_id"], cur["uom_id"], q)["value"]
    out = []
    for m in need.values():
        issued = sum(
            convert(s, tid, x["uom_id"], m["uom_id"], float(x["initial_qty"] or 0))[
                "value"
            ]
            for x in find(
                s,
                tid,
                "material_lot",
                work_order_id=wo["id"],
                material_id=m["material_id"],
            )
        )
        mat = one(s, tid, "material", m["material_id"])
        uom = one(s, tid, "uom", m["uom_id"])
        out.append(
            {
                "material_id": str(m["material_id"]),
                "material": mat and mat["code"],
                "uom": uom and uom["code"],
                "required": round(m["required"], 6),
                "issued": round(issued, 6),
                "short": round(max(0.0, m["required"] - issued), 6),
            }
        )
    return {
        "work_order": wo["code"],
        "bom": bom and bom["code"],
        "lines": sorted(out, key=lambda x: str(x["material"] or "")),
    }
