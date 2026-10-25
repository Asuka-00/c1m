"""Bank：前道完工批次入库（Wafer / Die Bank），封测工单从 Bank 领用开出新批次。"""

import uuid
from typing import Any

import sqlalchemy as sa
from sqlmodel import Session

from app.core import error_codes as ec
from app.core.spec.audit import audit
from app.core.spec.base import conn, now
from app.core.spec.engine import TABLES
from app.core.spec.errors import FieldError, fe, http_422
from app.mes.common.query import one
from app.mes.common.rows import _upd
from app.mes.execution.split_merge.rules import _genealogy, _ser
from app.mes.execution.stage.stages import LOT
from app.mes.lot.service import check_transition, history, lock_lot, lock_lots, units
from app.mes.planning import service as planning

Row = dict[str, Any]


def bank_in(s: Session, tid: uuid.UUID, lot_id: uuid.UUID, body: Row, user: Any) -> Row:
    """完工批次入 Bank（completed → banked）。

    Raises:
        HTTPException: 状态不允许或 Bank 无效（422）。
    """
    lot = lock_lot(s, tid, lot_id)
    check_transition(lot, "bank_in")
    bank = one(s, tid, "bank", body.get("bank_id"))
    if not bank or not bank["is_active"]:
        raise http_422([fe("bank_id", ec.BANK_NOT_FOUND, "bank not found")])
    at = now()
    _upd(
        s,
        tid,
        "lot",
        lot["id"],
        user,
        lot_status="banked",
        bank_id=bank["id"],
        banked_at=at,
    )
    lot.update(lot_status="banked")
    history(
        s,
        tid,
        lot,
        "bank_in",
        user,
        from_status="completed",
        comment=body.get("comment"),
        details={"bank": bank["code"]},
    )
    audit(s, tid, LOT, "bank_in", lot, user, {"bank": (None, bank["code"])})
    s.commit()
    return {"lot": _ser(s, tid, lot_id)}


def _pick(
    src: Row, x: Row, active: list[Row], errs: list[FieldError]
) -> tuple[int, list[Row]]:
    """来源批次的领用数量与单元（数量级批次只有数量）。"""
    if (src["tracking_level"] or "wafer") == "quantity":
        q = int(x.get("qty") or src["qty"])
        if not 1 <= q <= src["qty"]:
            errs.append(
                fe("lots", ec.BANK_QTY, "bad qty", lot=src["code"], max=src["qty"])
            )
        return q, []
    by = {str(u["id"]): u for u in active}
    ids = [str(i) for i in x.get("unit_ids") or []] or list(by)
    if len(set(ids)) != len(ids) or any(i not in by for i in ids):
        errs.append(fe("lots", ec.BANK_UNITS, "bad units", lot=src["code"]))
        return 0, []
    return len(ids), [by[i] for i in ids]


def bank_issue(s: Session, tid: uuid.UUID, body: Row, user: Any) -> Row:
    """从 Bank 领用：把若干在库批次（全部或部分单元）移入工单下新开的批次。

    新批次从工单路线首工步开始，单元保留原编号与履历；来源批次领完即终止（issued），
    否则留在 Bank。记录批次谱系（bank_issue）、历史与审计。

    Args:
        s: 数据库会话。
        tid: 租户 id。
        body: ``{work_order_id, lots: [{lot_id, unit_ids? | qty?}], comment}``。
        user: 操作人。

    Returns:
        ``{lot, sources: [{lot, qty, left}]}``。

    Raises:
        HTTPException: 来源不在库 / 持 Hold、追踪级别不一致、数量或单元不合法、工单不可开批（422）。
    """
    picks = body.get("lots") or []
    if not picks:
        raise http_422([fe("lots", ec.BANK_SOURCES, "no source lots")])
    srcs = lock_lots(s, tid, [x["lot_id"] for x in picks])
    if len(srcs) != len(picks):  # 同一批次只能列一次
        raise http_422([fe("lots", ec.BANK_SOURCES, "duplicate source lots")])
    for src in srcs.values():
        check_transition(src, "bank_out")
    levels = {src["tracking_level"] or "wafer" for src in srcs.values()}
    if len(levels) > 1:
        raise http_422([fe("lots", ec.BANK_MIXED_TRACKING, "mixed tracking")])
    errs: list[FieldError] = []
    taken: list[tuple[Row, int, list[Row]]] = []
    for x in picks:
        src = srcs[uuid.UUID(str(x["lot_id"]))]
        q, us = _pick(src, x, units(s, tid, src["id"]), errs)
        taken.append((src, q, us))
    if errs:
        raise http_422(errs)
    total = sum(q for _, q, _ in taken)
    new = planning.open_lot(
        s,
        tid,
        body.get("work_order_id"),
        total,
        user,
        tracking_level=levels.pop(),
        source_ref=",".join(src["code"] for src, _, _ in taken),
        details={"bank_issue": [{"lot": src["code"], "qty": q} for src, q, _ in taken]},
    )
    at, w = now(), TABLES["wafer"]
    out = []
    for src, q, us in taken:
        if us:
            conn(s).execute(
                sa.update(w)
                .where(w.c.tenant_id == tid, w.c.id.in_([u["id"] for u in us]))
                .values(lot_id=new["id"], wafer_status="waiting", updated_at=at)
            )
        left = src["qty"] - q
        status = "banked" if left > 0 else "issued"
        _upd(s, tid, "lot", src["id"], user, qty=left, lot_status=status)
        codes = [u["code"] for u in us]
        _genealogy(s, tid, src, new, "bank_issue", q, codes, user, at)
        src.update(qty=left, lot_status=status)
        history(
            s,
            tid,
            src,
            "bank_out",
            user,
            qty=q,
            from_status="banked",
            comment=body.get("comment"),
            details={"to": new["code"], "units": codes, "left": left},
        )
        audit(
            s,
            tid,
            LOT,
            "bank_out",
            src,
            user,
            {"qty": (left + q, left), "to": (None, new["code"])},
        )
        out.append({"lot": src["code"], "qty": q, "left": left})
    s.commit()
    return {"lot": _ser(s, tid, new["id"]), "sources": out}
