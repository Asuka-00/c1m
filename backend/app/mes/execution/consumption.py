"""物料需求、线边批次候选与 Track Out 扣料。"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlmodel import Session

from app.core.models import actor_name
from app.core.spec.base import now
from app.mes.common.query import find, one
from app.mes.common.rows import _ins, _upd
from app.mes.common.uom import convert, to_qty

Row = dict[str, Any]


# ---------------- materials ----------------
def material_needs(
    s: Session, tid: uuid.UUID, step: Row, lot: Row, chosen: list[Row], at: datetime
) -> list[Row]:
    """计算当前工步的物料需求及分配方案。

    需求量 = 工步资源数量 ×（按单元计时乘以批次数量）。优先使用操作员选择的线边批次，
    否则按先到期先出（FEFO）自动分配；跳过不可用 / 已过期批次，单位不同时换算。

    Args:
        s: 数据库会话。
        tid: 租户 id。
        step: 当前工步。
        lot: 批次。
        chosen: 操作员选择的线边批次。
        at: 参考时间（判断过期）。

    Returns:
        每种物料的 ``{需求、可用、分配明细、是否足够}``。
    """
    out = []
    for r in find(s, tid, "step_resource", route_step_id=step["id"]):
        if r["resource_kind"] != "material" or not r["material_id"] or not r["qty"]:
            continue
        # per_unit：用量 × 批次数量；否则为每批固定用量
        need = float(r["qty"]) * (lot["qty"] if r["qty_basis"] == "per_unit" else 1)
        mat = one(s, tid, "material", r["material_id"])
        cands = [
            m
            for m in chosen
            if m["material_id"] == r["material_id"]
            # 操作员指定的线边批次优先，否则按先到期先出（FEFO）自动分配
        ] or candidate_lots(s, tid, r["material_id"], at)
        alloc, have, total = [], 0.0, 0.0
        for m in cands:
            if m["ml_status"] != "available" or (
                m["expiry_date"] and m["expiry_date"] < at.date()
            ):
                continue
            q = float(m["qty_remaining"] or 0)
            if r["uom_id"] and m["uom_id"] != r["uom_id"]:
                try:
                    q = convert(s, tid, m["uom_id"], r["uom_id"], q)["value"]
                except HTTPException:
                    continue
            total += q
            take = min(q, need - have)
            if take > 1e-12:
                alloc.append(
                    {
                        "material_lot_id": m["id"],
                        "code": m["code"],
                        "qty": take,
                        "uom_id": m["uom_id"],
                        "req_uom_id": r["uom_id"],
                    }
                )
                have += take
        out.append(
            {
                "resource_id": r["id"],
                "material_id": r["material_id"],
                "material_code": mat and mat["code"],
                "need": need,
                "uom_id": r["uom_id"],
                "basis": r["qty_basis"],
                "available": total,
                "allocation": alloc,
            }
        )
    return out


def candidate_lots(
    s: Session, tid: uuid.UUID, material_id: Any, at: datetime
) -> list[Row]:
    """物料的可用线边批次，按先到期先出（FEFO）排序。"""
    ls = [
        m
        for m in find(s, tid, "material_lot", material_id=material_id)
        if m["ml_status"] == "available"
        and (m["qty_remaining"] or 0) > 0
        and not (m["expiry_date"] and m["expiry_date"] < at.date())
    ]
    return sorted(ls, key=lambda m: (m["expiry_date"] or date.max, m["code"]))


def usage_type(s: Session, tid: uuid.UUID, lot: Row, step: Row) -> str:
    """本次扣料的用途：在返工路线中、或返工后回到已扣过料的同一工步重做时为 rework。"""
    if any(x.get("kind") == "rework" for x in lot.get("route_stack") or []):
        return "rework"
    done = find(
        s,
        tid,
        "material_consumption",
        lot_id=lot["id"],
        route_step_id=step["id"],
        usage_type="normal",
    )
    return "rework" if done else "normal"


def _consume(
    s: Session,
    tid: uuid.UUID,
    needs: list[Row],
    user: Any,
    *,
    lot: Row | None = None,
    step: Row | None = None,
    usage: str = "normal",
) -> list[Row]:
    """按分配方案扣减线边批次；给定 ``lot`` 时逐条写用料记录（material_consumption）。"""
    out = []
    at, who = now(), actor_name(user)
    for n in needs:
        for a in n["allocation"]:
            m = one(s, tid, "material_lot", a["material_lot_id"])
            assert m
            q = a["qty"]
            if a["req_uom_id"] and m["uom_id"] != a["req_uom_id"]:
                q = convert(s, tid, a["req_uom_id"], m["uom_id"], q)["value"]
            q = to_qty(q)  # Decimal(18,6)，入库前定点化（D31）
            left = max(Decimal(0), to_qty(m["qty_remaining"] or 0) - q)
            _upd(
                s,
                tid,
                "material_lot",
                m["id"],
                user,
                qty_remaining=left,
                ml_status="empty" if left <= 0 else m["ml_status"],
            )
            if lot is not None:
                _ins(
                    s,
                    tid,
                    "material_consumption",
                    user,
                    lot_id=lot["id"],
                    route_step_id=step and step["id"],
                    operation_id=step and step.get("operation_id"),
                    material_id=m["material_id"],
                    material_lot_id=m["id"],
                    qty=q,
                    uom_id=m["uom_id"],
                    source="step_resource",
                    usage_type=usage,
                    username=who,
                    at=at,
                )
            out.append(
                {"material_lot": m["code"], "qty": float(q), "left": float(left)}
            )
    return out
