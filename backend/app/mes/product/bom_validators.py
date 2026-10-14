"""BOM 的 CRUD 校验器：只有草稿可改（明细、替代料随主表锁定），版本号自动分配。"""

import uuid
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from fastapi import HTTPException
from sqlmodel import Session

from app.core.spec.base import conn
from app.core.spec.engine import TABLES, Entity
from app.core.spec.errors import MesError, http_422
from app.core.spec.validate import validator
from app.mes.common.query import find
from app.mes.common.validators import Row, _get, reject_unwritable


class StructureError(HTTPException):
    """两级 BOM 结构错误（bom.md §7.1）：422，``type`` / ``code`` 为错误码。"""

    def __init__(self, code: str, msg: str, loc: tuple[Any, ...]) -> None:
        """以错误码、消息和 loc（不含 body 前缀）构造。"""
        super().__init__(
            status_code=422,
            detail=[{"loc": ["body", *loc], "msg": msg, "type": code, "code": code}],
        )


def _product_kids(s: Session, tid: uuid.UUID, product_id: Any) -> list[Any]:
    """产品当前生效 BOM 里的半成品组件 id。"""
    act = find(s, tid, "bom", product_id=product_id, status="active")
    if not act:
        return []
    return [
        ln["component_product_id"]
        for ln in find(s, tid, "bom_line", bom_id=act[0]["id"])
        if ln["component_type"] == "product" and ln["component_product_id"]
    ]


def structure_error(
    s: Session, tid: uuid.UUID, bom: Row | None, comp: Any
) -> tuple[str, str] | None:
    """半成品行的结构校验，返回 ``(code, msg)`` 或 None。

    - ``bom_cycle``：引用 BOM 自己的产品，或沿各产品的生效 BOM 展开能回到本产品。
    - ``bom_depth_exceeded``：被引用半成品的生效 BOM 里还有半成品行（会成三级）。
    """
    if not bom or comp is None:
        return None
    own = bom["product_id"]
    if comp == own:
        return ("bom_cycle", "component_product: a BOM cannot use its own product")
    seen: set[Any] = set()
    todo = [comp]
    while todo and len(seen) < 1000:
        cur = todo.pop()
        if cur in seen:
            continue
        seen.add(cur)
        for k in _product_kids(s, tid, cur):
            if k == own:
                return (
                    "bom_cycle",
                    "component_product: circular reference (its active BOM "
                    "expands back to this product)",
                )
            todo.append(k)
    if _product_kids(s, tid, comp):
        return (
            "bom_depth_exceeded",
            "component_product: its active BOM already contains semi-finished "
            "lines (P1 allows two levels only)",
        )
    return None


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


@validator("bom:payload")
def _bom_payload(
    _s: Session, _t: uuid.UUID, _e: Entity, data: Row, _old: Row | None
) -> None:
    """生效时间 / 确认人只能由 activate 决定，载荷里给了就明确拒绝。"""
    bad = [k for k in ("effective_at", "confirmed_by", "confirmed_at") if k in data]
    if bad:
        raise http_422(
            [(k, f"{k}: set by POST /mes/bom/{{id}}/activate only") for k in bad]
        )
    reject_unwritable(_e, data)


@validator("bom_line:payload", "bom_line_substitute:payload")
def _strict_payload(
    _s: Session, _t: uuid.UUID, e: Entity, data: Row, _old: Row | None
) -> None:
    """明细 / 替代料：未知字段（如旧的 route_step_id）与系统字段返回 422。"""
    reject_unwritable(e, data)


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
        hit = structure_error(s, tid, bom, row.get("component_product_id"))
        if hit:
            raise StructureError(hit[0], hit[1], ("component_product_id",))
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
    # 唯一键冲突：409 并写明冲突字段（否则只有通用的“同键记录已存在”）
    t = TABLES["bom_line_substitute"]
    for f in ("priority", "material_id"):
        q = sa.select(t.c.id).where(
            t.c.tenant_id == tid,
            t.c.bom_line_id == row.get("bom_line_id"),
            t.c[f] == row.get(f),
        )
        if old is not None:
            q = q.where(t.c.id != old["id"])
        hit = conn(s).execute(q).first()
        if hit:
            v = row.get(f)
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "duplicate",
                    "message": f"bom_line_substitute: {f.removesuffix('_id')} {v} "
                    "already used on this BOM line",
                    "field": f.removesuffix("_id"),
                    "bom_line_id": str(row.get("bom_line_id")),
                    f.removesuffix("_id"): str(v) if f == "material_id" else v,
                    "existing_id": str(hit[0]),
                },
            )


@validator("bom_line_substitute:delete")
def _bom_sub_delete(
    s: Session, tid: uuid.UUID, _e: Entity, row: Row, _old: Row | None
) -> None:
    _locked(_line_bom(s, tid, row.get("bom_line_id")))
