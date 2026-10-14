"""BOM 的 CRUD 校验器：只有草稿可改（明细、替代料随主表锁定），版本号自动分配。"""

import uuid
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from fastapi import HTTPException
from sqlmodel import Session

from app.core.spec.base import conn
from app.core.spec.engine import TABLES, Entity
from app.core.spec.errors import MesError
from app.core.spec.validate import validator
from app.mes.common.validators import Row, _get


def _locked(bom: Row | None) -> None:
    """BOM 非草稿时拒绝修改（409，与版本化主数据一致）。"""
    if bom and bom.get("status") != "draft":
        raise HTTPException(
            status_code=409,
            detail=f"BOM v{bom.get('version')} is {bom.get('status')}; "
            "only draft BOMs can be changed (copy it to a new version)",
        )


def next_version(s: Session, tid: uuid.UUID, product_id: Any) -> int:
    """该产品的下一个 BOM 版本号。"""
    t = TABLES["bom"]
    cur = (
        conn(s)
        .execute(
            sa.select(sa.func.max(t.c.version)).where(
                t.c.tenant_id == tid, t.c.product_id == product_id
            )
        )
        .scalar()
    )
    return int(cur or 0) + 1


@validator("bom")
def _bom(s: Session, tid: uuid.UUID, _e: Entity, row: Row, old: Row | None) -> None:
    if old is None:
        row["version"] = next_version(s, tid, row.get("product_id"))
        row["status"] = "draft"
        return
    _locked(old)
    if row.get("product_id") != old.get("product_id"):
        raise MesError([("product", "product: cannot change the product of a BOM")])


@validator("bom:delete")
def _bom_delete(
    _s: Session, _t: uuid.UUID, _e: Entity, row: Row, _old: Row | None
) -> None:
    _locked(row)


def _count_uom(s: Session, tid: uuid.UUID, uom_id: Any) -> bool:
    u = _get(s, tid, "uom", uom_id)
    return bool(u and u.get("dimension") == "count")


@validator("bom_line")
def _bom_line(
    s: Session, tid: uuid.UUID, _e: Entity, row: Row, old: Row | None
) -> None:
    if old is not None:
        _locked(_get(s, tid, "bom", old.get("bom_id")))
        if row.get("bom_id") != old.get("bom_id"):
            raise MesError([("bom", "bom: cannot move a line to another BOM")])
    bom = _get(s, tid, "bom", row.get("bom_id"))
    _locked(bom)
    errs: list[tuple[str, str]] = []
    if row.get("component_type") == "material":
        row["component_product_id"] = None
    else:
        row["material_id"] = None
        if bom and row.get("component_product_id") == bom["product_id"]:
            errs.append(
                (
                    "component_product",
                    "component_product: a BOM cannot use its own product",
                )
            )
    qty = row.get("qty")
    if qty is not None and qty <= 0:
        errs.append(("qty", "qty: must be > 0"))
    elif qty is not None and _count_uom(s, tid, row.get("uom_id")):
        if Decimal(qty) != Decimal(qty).to_integral_value():
            errs.append(("qty", "qty: must be a whole number for a count unit"))
    sr = row.get("scrap_rate")
    if sr is not None and not 0 <= sr < 1:
        errs.append(("scrap_rate", "scrap_rate: must be within 0..1 (e.g. 0.02 = 2%)"))
    if (row.get("line_no") or 0) <= 0:
        errs.append(("line_no", "line_no: must be > 0"))
    if errs:
        raise MesError(errs)


@validator("bom_line:delete")
def _bom_line_delete(
    s: Session, tid: uuid.UUID, _e: Entity, row: Row, _old: Row | None
) -> None:
    _locked(_get(s, tid, "bom", row.get("bom_id")))


def _line_bom(s: Session, tid: uuid.UUID, line_id: Any) -> Row | None:
    line = _get(s, tid, "bom_line", line_id)
    return line and _get(s, tid, "bom", line["bom_id"])


@validator("bom_line_substitute")
def _bom_sub(s: Session, tid: uuid.UUID, _e: Entity, row: Row, old: Row | None) -> None:
    if old is not None:
        _locked(_line_bom(s, tid, old.get("bom_line_id")))
        if row.get("bom_line_id") != old.get("bom_line_id"):
            raise MesError([("bom_line", "bom_line: cannot move a substitute")])
    _locked(_line_bom(s, tid, row.get("bom_line_id")))
    line = _get(s, tid, "bom_line", row.get("bom_line_id"))
    errs: list[tuple[str, str]] = []
    if line and line.get("component_type") != "material":
        errs.append(("bom_line", "bom_line: substitutes apply to material lines only"))
    if line and row.get("material_id") == line.get("material_id"):
        errs.append(("material", "material: same as the primary material"))
    if (row.get("priority") or 0) <= 0:
        errs.append(("priority", "priority: must be > 0"))
    if errs:
        raise MesError(errs)


@validator("bom_line_substitute:delete")
def _bom_sub_delete(
    s: Session, tid: uuid.UUID, _e: Entity, row: Row, _old: Row | None
) -> None:
    _locked(_line_bom(s, tid, row.get("bom_line_id")))
