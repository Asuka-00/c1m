"""Material needs, line-side lot candidates and consumption at Track Out."""

import uuid
from datetime import date, datetime
from typing import Any

from fastapi import HTTPException
from sqlmodel import Session

from app.mes.common.query import find, one
from app.mes.common.rows import _upd
from app.mes.common.uom import convert

Row = dict[str, Any]


# ---------------- materials ----------------
def material_needs(
    s: Session, tid: uuid.UUID, step: Row, lot: Row, chosen: list[Row], at: datetime
) -> list[Row]:
    out = []
    for r in find(s, tid, "step_resource", route_step_id=step["id"]):
        if r["resource_kind"] != "material" or not r["material_id"] or not r["qty"]:
            continue
        need = float(r["qty"]) * (lot["qty"] if r["qty_basis"] == "per_unit" else 1)
        mat = one(s, tid, "material", r["material_id"])
        cands = [
            m for m in chosen if m["material_id"] == r["material_id"]
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
    """Usable lots of a material, first-expiry-first-out."""
    ls = [
        m
        for m in find(s, tid, "material_lot", material_id=material_id)
        if m["ml_status"] == "available"
        and (m["qty_remaining"] or 0) > 0
        and not (m["expiry_date"] and m["expiry_date"] < at.date())
    ]
    return sorted(ls, key=lambda m: (m["expiry_date"] or date.max, m["code"]))


def _consume(s: Session, tid: uuid.UUID, needs: list[Row], user: Any) -> list[Row]:
    out = []
    for n in needs:
        for a in n["allocation"]:
            m = one(s, tid, "material_lot", a["material_lot_id"])
            assert m
            q = a["qty"]
            if a["req_uom_id"] and m["uom_id"] != a["req_uom_id"]:
                q = convert(s, tid, a["req_uom_id"], m["uom_id"], q)["value"]
            left = max(0.0, round(float(m["qty_remaining"]) - q, 9))
            _upd(
                s,
                tid,
                "material_lot",
                m["id"],
                user,
                qty_remaining=left,
                ml_status="empty" if left <= 0 else m["ml_status"],
            )
            out.append({"material_lot": m["code"], "qty": round(q, 6), "left": left})
    return out
