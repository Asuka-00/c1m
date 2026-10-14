"""B7 客户来料：批次的客户批号、物料归属、客户。

- 开批时填写（:func:`customer_start_errors` 校验）；
- 拆批、合批、单位转换（B5）产生的子批用 :func:`inherit_customer` 继承母批的三个字段；
- 合批时两边 ``customer_id`` / ``ownership`` 不同 → :func:`customer_mismatch` 为真，422 ``customer_mismatch``；
- 客户批号与内部批号互查：:func:`lookup_customer_lots`；追溯结果里用 :func:`customer_info` 带出。
"""

import uuid
from typing import Any

import sqlalchemy as sa
from sqlmodel import Session

from app.core.spec.base import conn
from app.core.spec.engine import TABLES
from app.mes.common.query import one

Row = dict[str, Any]
CUSTOMER_KEYS = ("customer_lot_no", "ownership", "customer_id")


def inherit_customer(parent: Row) -> Row:
    """子批继承母批的客户字段（拆批 / 合批 / B5 单位转换共用）。"""
    return {
        "customer_lot_no": parent.get("customer_lot_no"),
        "ownership": parent.get("ownership") or "own",
        "customer_id": parent.get("customer_id"),
    }


def customer_mismatch(a: Row, b: Row) -> bool:
    """两个批次的客户 / 物料归属是否不同（空与非空也算不同）。"""
    return bool(
        a.get("customer_id") != b.get("customer_id")
        or (a.get("ownership") or "own") != (b.get("ownership") or "own")
    )


def customer_info(s: Session, tid: uuid.UUID, lot: Row | None) -> Row:
    """批次的客户来料信息（追溯 / 互查结果用）。"""
    if not lot:
        return {
            "customer_lot_no": None,
            "ownership": None,
            "customer_id": None,
            "customer": None,
        }
    c = lot.get("customer_id") and one(s, tid, "customer", lot["customer_id"])
    return {
        "customer_lot_no": lot.get("customer_lot_no"),
        "ownership": lot.get("ownership") or "own",
        "customer_id": lot.get("customer_id") and str(lot["customer_id"]),
        "customer": c and c["code"],
    }


def customer_start_errors(
    s: Session, tid: uuid.UUID, i: int, x: Row
) -> list[tuple[str, str]]:
    """开批时第 ``i`` 个批次客户字段的校验错误；同时把字段规整进 ``x``。

    规则：ownership 为 customer 时必须指定存在的客户；ownership 为 own 时不能带客户
    或客户批号。
    """
    errs: list[tuple[str, str]] = []
    own = x.get("ownership") or "own"
    x["ownership"] = own
    x["customer_lot_no"] = (x.get("customer_lot_no") or "").strip() or None
    cid = x.get("customer_id")
    if own == "customer":
        if not cid:
            errs.append(
                (
                    f"lots.{i}.customer_id",
                    f"lot {i}: customer required for customer-owned material",
                )
            )
        elif not one(s, tid, "customer", cid):
            errs.append((f"lots.{i}.customer_id", f"lot {i}: customer not found"))
    else:
        if cid:
            errs.append(
                (
                    f"lots.{i}.customer_id",
                    f"lot {i}: customer only for ownership=customer",
                )
            )
        if x["customer_lot_no"]:
            errs.append(
                (
                    f"lots.{i}.customer_lot_no",
                    f"lot {i}: customer lot no. only for ownership=customer",
                )
            )
    return errs


def lookup_customer_lots(
    s: Session,
    tid: uuid.UUID,
    customer_lot_no: str | None = None,
    lot_no: str | None = None,
) -> list[Row]:
    """客户批号 ↔ 内部批号互查（精确匹配，含拆批子批 / 已合批的批次）。"""
    t = TABLES["lot"]
    q = sa.select(t).where(t.c.tenant_id == tid)
    if customer_lot_no:
        q = q.where(t.c.customer_lot_no == customer_lot_no.strip())
    if lot_no:
        q = q.where(t.c.code == lot_no.strip())
    rows = conn(s).execute(q.order_by(t.c.code).limit(500)).mappings().all()
    return [
        {
            "lot_id": str(r["id"]),
            "lot_no": r["code"],
            "lot_status": r["lot_status"],
            **customer_info(s, tid, dict(r)),
        }
        for r in rows
    ]
