"""来料接收单：确认收料（生成待检物料批）与 IQC 判定。

确认后每个明细生成一个 ``hold`` 状态的物料批（待检，不能被领用 / 扣料）；
IQC 判定 ``pass`` → 物料批变为 ``available``，``fail`` → ``rejected``。
确认的状态流转见 :mod:`app.mes.warehouse.docs`。
"""

import uuid
from datetime import timedelta
from typing import Any

from sqlmodel import Session

from app.core import error_codes as ec
from app.core.spec.audit import audit
from app.core.spec.base import now
from app.core.spec.engine import ENTITIES, Entity
from app.core.spec.errors import MesError, fe, http_422
from app.core.spec.query import get_row
from app.core.spec.validate import validator
from app.mes.common.query import one
from app.mes.common.rows import _ins, _upd
from app.mes.warehouse import docs

Row = dict[str, Any]
RECEIPT, LINE = ENTITIES["material_receipt"], ENTITIES["material_receipt_line"]
#: 物料批编码上限 64，留出 "-NN" 后缀
CODE_ROOM = 56
docs.guard_drafts("material_receipt", "material_receipt_line")


@validator("material_receipt_line")
def _line(_s: Session, _t: uuid.UUID, _e: Entity, row: Row, _o: Row | None) -> None:
    if (row.get("qty") or 0) <= 0:
        raise MesError([fe("qty", ec.FIELD_GT, "qty: must be > 0", min=0)])


def _post(s: Session, tid: uuid.UUID, rc: Row, lines: list[Row], user: Any) -> None:
    """确认收料：每行生成一个待检物料批，回写行上的物料批与默认有效期。"""
    today = now().date()
    for n, x in enumerate(lines, 1):
        mat = one(s, tid, "material", x["material_id"])
        assert mat
        expiry = x["expiry_date"]
        if not expiry and mat["shelf_life_days"]:
            expiry = today + timedelta(days=int(mat["shelf_life_days"]))
        lot_id = _ins(
            s,
            tid,
            "material_lot",
            user,
            code=f"{rc['code'][:CODE_ROOM]}-{n}",
            material_id=x["material_id"],
            qty_remaining=x["qty"],
            initial_qty=x["qty"],
            uom_id=x["uom_id"],
            supplier_lot=x["supplier_lot"],
            expiry_date=expiry,
            location=x["location"],
            ml_status="hold",
        )
        _upd(
            s,
            tid,
            "material_receipt_line",
            x["id"],
            user,
            material_lot_id=lot_id,
            expiry_date=expiry,
        )


def transition(
    s: Session, tid: uuid.UUID, receipt_id: uuid.UUID, action: str, user: Any
) -> Row:
    """执行来料接收单状态迁移（confirm / cancel）。"""
    return docs.transition(
        s,
        tid,
        "material_receipt",
        "material_receipt_line",
        receipt_id,
        action,
        user,
        _post,
    )


def iqc(s: Session, tid: uuid.UUID, line_id: uuid.UUID, result: str, user: Any) -> Row:
    """IQC 判定一行来料：pass → 物料批可用；fail → 物料批拒收。

    Raises:
        HTTPException: 结果非法、单据未确认或该行已判定（422）；行不存在（404）。
    """
    if result not in ("pass", "fail"):
        raise http_422(
            [
                fe(
                    "result",
                    ec.ACTION_INVALID,
                    "result: must be one of pass, fail",
                    actions="pass, fail",
                )
            ]
        )
    line = get_row(s, LINE, tid, line_id)
    rc = one(s, tid, "material_receipt", line["material_receipt_id"])
    if not rc or rc["issue_status"] != "confirmed" or not line["material_lot_id"]:
        raise http_422(
            [
                fe(
                    "iqc_result",
                    ec.IQC_NOT_READY,
                    "iqc_result: confirm the receipt first",
                )
            ]
        )
    if line["iqc_result"] != "pending":
        raise http_422([fe("iqc_result", ec.IQC_DECIDED, "iqc_result: already judged")])
    _upd(s, tid, "material_receipt_line", line_id, user, iqc_result=result)
    _upd(
        s,
        tid,
        "material_lot",
        line["material_lot_id"],
        user,
        ml_status="available" if result == "pass" else "rejected",
    )
    new = get_row(s, LINE, tid, line_id)
    audit(s, tid, LINE, "update", new, user, {"iqc_result": ("pending", result)})
    s.commit()
    return new
