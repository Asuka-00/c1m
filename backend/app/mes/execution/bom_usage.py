"""BOM 出站用量比对（D28 / B2，bom.md §3、§10、§11）。

- 只比 consume_mode=issue 的物料明细（半成品明细不比）。
- 明细挂工序（operation_id）：该工序的任一工步出站都比，实际用量为该批次在该工序下
  各工步累计的正常用量；未挂工序：在流程最后一步出站时统一比，实际用量为该批次
  所有未被同物料挂工序明细认领的正常用量。返工 / 报废用量（usage_type≠normal）不计入。
- 主料与替代料合并计入；各记录换算到明细单位后累加（6 位小数）。
- 计划用量 = 基准 × qty ×（1 + scrap_rate），基准取当前工步进站时的良品数（per_basis=lot
  时为 1）。实际 > 计划：只提示，不拦截。
"""

import uuid
from typing import Any

from fastapi import HTTPException
from sqlmodel import Session

from app.mes.common.query import find, one
from app.mes.common.uom import convert, round_qty

Row = dict[str, Any]
EPS = 1e-9


def _issue_lines(s: Session, tid: uuid.UUID, bom_id: Any) -> list[Row]:
    lines = [
        ln
        for ln in find(s, tid, "bom_line", bom_id=bom_id)
        if ln["consume_mode"] == "issue"
        and ln["component_type"] == "material"
        and ln["material_id"]
    ]
    for ln in lines:
        ln["_mats"] = {ln["material_id"]} | {
            x["material_id"]
            for x in find(s, tid, "bom_line_substitute", bom_line_id=ln["id"])
        }
    return sorted(lines, key=lambda x: x["line_no"])


def _code(s: Session, tid: uuid.UUID, ent: str, rid: Any) -> str | None:
    r = one(s, tid, ent, rid) if rid else None
    return str(r["code"]) if r else None


def compare(
    s: Session,
    tid: uuid.UUID,
    lot: Row,
    basis_qty: float,
    *,
    operation_id: Any = None,
    is_last: bool = False,
    all_lines: bool = False,
) -> list[Row]:
    """按明细比对累计实际用量与计划用量。

    Args:
        s: 数据库会话。
        tid: 租户 id。
        lot: 批次（取锁定的 ``bom_id``）。
        basis_qty: 基准数量（当前工步进站时的良品数）。
        operation_id: 当前工步的工序；只比挂在该工序上的明细。
        is_last: 是否流程最后一步（同时比未挂工序的明细）。
        all_lines: 为真时比全部 issue 明细（查询用，忽略工序 / 最后一步条件）。

    Returns:
        每条明细 ``{bom_line_id, line_no, material, operation, uom, basis, planned,
        actual, over, unconverted}``；``unconverted`` 为无法换算到明细单位而未计入的记录数。
    """
    if not lot.get("bom_id"):
        return []
    lines = _issue_lines(s, tid, lot["bom_id"])
    claimed = {
        (ln["operation_id"], m)
        for ln in lines
        if ln["operation_id"]
        for m in ln["_mats"]
    }
    recs = find(s, tid, "material_consumption", lot_id=lot["id"], usage_type="normal")
    out = []
    for ln in lines:
        op = ln["operation_id"]
        if not all_lines and not ((op and op == operation_id) or (not op and is_last)):
            continue
        mine = [
            r
            for r in recs
            if r["material_id"] in ln["_mats"]
            and (
                r["operation_id"] == op
                if op
                else (r["operation_id"], r["material_id"]) not in claimed
            )
        ]
        actual, bad = 0.0, 0
        for r in mine:
            q = float(r["qty"] or 0)
            if r["uom_id"] != ln["uom_id"]:
                try:
                    q = convert(s, tid, r["uom_id"], ln["uom_id"], q)["value"]
                except HTTPException:
                    bad += 1
                    continue
            actual += q
        basis = 1.0 if ln["per_basis"] == "lot" else float(basis_qty)
        planned = round_qty(
            basis * float(ln["qty"]) * (1 + float(ln["scrap_rate"] or 0))
        )
        actual = round_qty(actual)
        out.append(
            {
                "bom_line_id": str(ln["id"]),
                "line_no": ln["line_no"],
                "material": _code(s, tid, "material", ln["material_id"]),
                "operation": _code(s, tid, "operation", op),
                "uom": _code(s, tid, "uom", ln["uom_id"]),
                "per_basis": ln["per_basis"],
                "basis": basis,
                "planned": planned,
                "actual": actual,
                "over": actual > planned + EPS,
                "unconverted": bad,
            }
        )
    return out


def over_warning(rows: list[Row]) -> Row | None:
    """超量明细汇总成一条出站提示（无超量时为 None）。"""
    over = [r for r in rows if r["over"]]
    if not over:
        return None
    return {
        "code": "bom_over_consumption",
        "message": "BOM over-consumption: "
        + "; ".join(
            f"{r['material']} {r['actual']:g}/{r['planned']:g} {r['uom'] or ''}".strip()
            for r in over
        ),
        "lines": over,
    }


def lot_bom_usage(s: Session, tid: uuid.UUID, lot_id: uuid.UUID) -> Row:
    """批次 BOM 用量总览：全部 issue 明细的累计正常用量对比计划（基准为当前良品数）。

    Raises:
        HTTPException: 批次不存在（404）。
    """
    lot = one(s, tid, "lot", lot_id)
    if not lot:
        raise HTTPException(status_code=404, detail="Record not found")
    bom = one(s, tid, "bom", lot.get("bom_id")) if lot.get("bom_id") else None
    return {
        "lot": lot["code"],
        "bom_id": bom and str(bom["id"]),
        "bom_version": bom and bom["version"],
        "basis": lot["qty"],
        "lines": compare(s, tid, lot, lot["qty"] or 0, all_lines=True),
    }
