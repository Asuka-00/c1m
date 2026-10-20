"""追溯查询：按批次 / 晶圆 / 设备 / 物料批，正向（下游产出）与反向（上游来源、设备、物料）追溯。"""

import uuid
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from sqlmodel import Session

from app.core import error_codes as ec
from app.core.spec.base import conn
from app.core.spec.engine import TABLES
from app.core.spec.errors import coded
from app.mes.common.query import find, jsonable, one

Row = dict[str, Any]
KINDS = ("lot", "wafer", "equipment", "material_lot")


def _code(s: Session, tid: uuid.UUID, ent: str, rid: Any) -> str | None:
    r = one(s, tid, ent, rid) if rid else None
    return r["code"] if r else None


def _walk(s: Session, tid: uuid.UUID, start: Any, up: bool) -> list[Row]:
    """沿谱系递归：``up`` 为真找来源（母批），否则找产出（子批）。"""
    a, b = (
        ("child_lot_id", "parent_lot_id") if up else ("parent_lot_id", "child_lot_id")
    )
    seen: dict[Any, Row] = {}
    todo, depth = [start], 0
    while todo and depth < 50:
        depth += 1
        nxt = []
        for lid in todo:
            for g in find(s, tid, "lot_genealogy", **{a: lid}):
                o = g[b]
                if o in seen or o == start:
                    continue
                lot = one(s, tid, "lot", o)
                seen[o] = {
                    "id": str(o),
                    "code": lot and lot["code"],
                    "relation": g["relation"],
                    "qty": g["qty"],
                    "via": _code(s, tid, "lot", lid),
                    "level": depth,
                    "at": g["at"],
                }
                nxt.append(o)
        todo = nxt
    return list(seen.values())


def _hist(s: Session, tid: uuid.UUID, lot_ids: list[Any], action: str) -> list[Row]:
    h = TABLES["lot_history"]
    rows = (
        conn(s)
        .execute(
            sa.select(h)
            .where(h.c.tenant_id == tid, h.c.lot_id.in_(lot_ids), h.c.action == action)
            .order_by(h.c.at)
        )
        .mappings()
        .all()
    )
    return [dict(r) for r in rows]


def _lot_trace(s: Session, tid: uuid.UUID, lot: Row) -> Row:
    back = _walk(s, tid, lot["id"], True)
    fwd = _walk(s, tid, lot["id"], False)
    ids = [lot["id"], *[uuid.UUID(x["id"]) for x in back]]
    codes = {i: _code(s, tid, "lot", i) for i in ids}
    steps = [
        {
            "lot": codes[r["lot_id"]],
            "step_seq": r["step_seq"],
            "operation": _code(s, tid, "operation", r["operation_id"]),
            "equipment": _code(s, tid, "equipment", r["equipment_id"]),
            "recipe": _code(s, tid, "recipe", r["recipe_id"]),
            "at": r["at"],
            "user": r["username"],
        }
        for r in _hist(s, tid, ids, "track_in")
    ]
    mats = [
        {
            "lot": codes[r["lot_id"]],
            "step_seq": r["step_seq"],
            "material_lot": c.get("material_lot"),
            "qty": c.get("qty"),
            "at": r["at"],
        }
        for r in _hist(s, tid, ids, "track_out")
        for c in ((r["details"] or {}).get("consumed") or [])
    ]
    return {
        "backward": {"lots": back, "steps": steps, "materials": mats},
        "forward": {"lots": fwd},
    }


def _lots_by(s: Session, tid: uuid.UUID, where: Any) -> list[Row]:
    h = TABLES["lot_history"]
    rows = (
        conn(s)
        .execute(sa.select(h).where(h.c.tenant_id == tid, where).order_by(h.c.at))
        .mappings()
        .all()
    )
    out = []
    for r in rows:
        lot = one(s, tid, "lot", r["lot_id"])
        out.append(
            {
                "id": str(r["lot_id"]),
                "code": lot and lot["code"],
                "product": lot and _code(s, tid, "product", lot["product_id"]),
                "step_seq": r["step_seq"],
                "operation": _code(s, tid, "operation", r["operation_id"]),
                "equipment": _code(s, tid, "equipment", r["equipment_id"]),
                "qty": r["qty"],
                "at": r["at"],
                "consumed": [
                    c
                    for c in ((r["details"] or {}).get("consumed") or [])
                    if r["action"] == "track_out"
                ],
            }
        )
    return out


def trace(s: Session, tid: uuid.UUID, kind: str, code: str) -> Row:
    """追溯查询。

    Args:
        s: 数据库会话。
        tid: 租户 id。
        kind: ``lot`` / ``wafer`` / ``equipment`` / ``material_lot``。
        code: 对象编码。

    Returns:
        批次 / 晶圆：``{target, backward: {lots, steps, materials}, forward: {lots}}``；
        设备：``{target, lots}``（在该设备上 Track In 的批次）；
        物料批：``{target, lots}``（消耗了该物料批的批次及其下游产出）。
    """
    if kind not in KINDS:
        raise coded(
            422,
            ec.TRACE_KIND_INVALID,
            f"kind must be one of {KINDS}",
            allowed=", ".join(KINDS),
        )
    t = TABLES[kind]
    hit = (
        conn(s)
        .execute(sa.select(t).where(t.c.tenant_id == tid, t.c.code == code.strip()))
        .mappings()
        .first()
    )
    if not hit:
        raise coded(
            404, ec.TRACE_NOT_FOUND, f"{kind} {code} not found", kind=kind, code=code
        )
    tgt = dict(hit)
    h = TABLES["lot_history"]
    out: Row = {"kind": kind, "target": {"id": str(tgt["id"]), "code": tgt["code"]}}
    if kind in ("lot", "wafer"):
        lot = tgt if kind == "lot" else one(s, tid, "lot", tgt["lot_id"])
        if not lot:
            raise coded(404, ec.LOT_NOT_FOUND, "lot not found")
        out["target"]["lot"] = lot["code"]
        out["target"]["lot_id"] = str(lot["id"])
        out |= _lot_trace(s, tid, lot)
    elif kind == "equipment":
        out["lots"] = _lots_by(
            s, tid, sa.and_(h.c.equipment_id == tgt["id"], h.c.action == "track_in")
        )
    else:
        pat = f'%"material_lot": "{tgt["code"]}"%'
        used = _lots_by(
            s,
            tid,
            sa.and_(
                h.c.action == "track_out",
                sa.cast(h.c.details, sa.Text).like(pat),
            ),
        )
        for u in used:
            u["forward"] = _walk(s, tid, uuid.UUID(u["id"]), False)
        out["lots"] = used
    return jsonable(out)  # type: ignore[no-any-return]


# ---------------- 晶圆级履历与晶圆图 ----------------
def wafer_lots(s: Session, tid: uuid.UUID, wafer: Row) -> list[tuple[Any, Any, Any]]:
    """晶圆经历过的批次及在其中的时间段 ``[(批次 id, 起, 止)]``（起 / 止为 None 表示不限）。

    从当前批次出发，按谱系中记录了该晶圆的拆批 / 合批逆向追溯来源批次：
    晶圆在来源批次中只到移出那一刻为止，不包含来源批次之后的记录，也不包含
    与该晶圆无关的谱系（如合入目标批的其他源批次）。
    """
    out: list[tuple[Any, Any, Any]] = []
    cur, end = wafer["lot_id"], None
    for _ in range(50):
        moves = [
            g
            for g in find(s, tid, "lot_genealogy", child_lot_id=cur)
            if wafer["code"] in (g["units"] or [])
            and (end is None or g["at"] is None or g["at"] <= end)
        ]
        if not moves:
            out.append((cur, None, end))
            break
        g = max(moves, key=lambda x: x["at"] or datetime.min.replace(tzinfo=UTC))
        out.append((cur, g["at"], end))
        cur, end = g["parent_lot_id"], g["at"]
    return out


def wafer_history(s: Session, tid: uuid.UUID, wafer_id: uuid.UUID) -> list[Row]:
    """晶圆履历：该晶圆的单元级记录，加上其所在期间各批次的批次级记录，按时间倒序。

    Raises:
        HTTPException: 晶圆不存在（404）。
    """
    from app.core.spec.engine import ENTITIES
    from app.core.spec.serialize import serialize

    w = one(s, tid, "wafer", wafer_id)
    if not w:
        raise coded(404, ec.RECORD_NOT_FOUND, "Record not found")
    h = TABLES["lot_history"]
    spans = [
        sa.and_(
            h.c.lot_id == lid,
            h.c.at >= start if start is not None else sa.true(),
            h.c.at <= end if end is not None else sa.true(),
        )
        for lid, start, end in wafer_lots(s, tid, w)
    ]
    rows = (
        conn(s)
        .execute(
            sa.select(h)
            .where(
                h.c.tenant_id == tid,
                sa.or_(
                    h.c.unit_id == w["id"],
                    sa.and_(h.c.unit_id.is_(None), sa.or_(*spans)),
                ),
            )
            .order_by(h.c.at.desc())
            .limit(500)
        )
        .mappings()
        .all()
    )
    return serialize(s, tid, ENTITIES["lot_history"], [dict(r) for r in rows])


def wafer_map(s: Session, tid: uuid.UUID, lot_id: uuid.UUID) -> Row:
    """晶圆图：按槽位排列批次的晶圆（容量取载具类型，缺省 25），含状态与返工次数。

    Raises:
        HTTPException: 批次不存在（404）。
    """
    lot = one(s, tid, "lot", lot_id)
    if not lot:
        raise coded(404, ec.RECORD_NOT_FOUND, "Record not found")
    cap = 25
    car = lot["carrier_id"] and one(s, tid, "carrier", lot["carrier_id"])
    ct = car and one(s, tid, "carrier_type", car["carrier_type_id"])
    if ct and ct["capacity"]:
        cap = int(ct["capacity"])
    ws = find(s, tid, "wafer", lot_id=lot_id)
    cap = max([cap, *(w["slot"] or 0 for w in ws)])
    by = {w["slot"]: w for w in ws if w["slot"]}
    slots = []
    for i in range(1, cap + 1):
        w = by.get(i)
        slots.append(
            {
                "slot": i,
                "wafer": w
                and {
                    "id": str(w["id"]),
                    "code": w["code"],
                    "status": w["wafer_status"],
                    "rework_count": w["rework_count"] or 0,
                },
            }
        )
    extra = [
        {"id": str(w["id"]), "code": w["code"], "status": w["wafer_status"]}
        for w in ws
        if not w["slot"]
    ]
    out: Row = jsonable(
        {
            "lot": lot["code"],
            "carrier": car and car["code"],
            "capacity": cap,
            "slots": slots,
            "units": extra,
        }
    )
    return out
