"""追溯查询：按批次 / 晶圆 / 设备 / 物料批，正向（下游产出）与反向（上游来源、设备、物料）追溯。"""

import uuid
from typing import Any

import sqlalchemy as sa
from fastapi import HTTPException
from sqlmodel import Session

from app.core.spec.base import conn
from app.core.spec.engine import TABLES
from app.core.spec.errors import err_422
from app.mes.common.query import find, jsonable, one
from app.mes.lot import service as lot_svc

Row = dict[str, Any]
KINDS = ("lot", "wafer", "equipment", "material_lot", "customer_lot")


def _code(s: Session, tid: uuid.UUID, ent: str, rid: Any) -> str | None:
    r = one(s, tid, ent, rid) if rid else None
    return r["code"] if r else None


def _transform_id(s: Session, tid: uuid.UUID, child_id: Any) -> str | None:
    rows = find(s, tid, "unit_transform_output", lot_id=child_id)
    return str(rows[0]["unit_transform_id"]) if rows else None


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
                    **lot_svc.customer_info(s, tid, lot),
                    "relation": g["relation"],
                    "qty": g["qty"],
                    "via": _code(s, tid, "lot", lid),
                    "level": depth,
                    "at": g["at"],
                    # 转换产生的谱系带转换 id，前端可在追溯页直接撤销（B6 / D54）
                    "transform_id": _transform_id(s, tid, lid if up else o)
                    if g["relation"] == "transform"
                    else None,
                    "undone": False,
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


def _origins(s: Session, tid: uuid.UUID, where: Any, limit: int = 5000) -> list[Row]:
    """单位转换的位置映射（B5）：子批位置 ← 母批 / 母晶圆 / die 坐标。"""
    o = TABLES["unit_origin"]
    rows = (
        conn(s)
        .execute(
            sa.select(o)
            .where(o.c.tenant_id == tid, where)
            .order_by(o.c.child_lot_id, o.c.child_seq)
            .limit(limit)
        )
        .mappings()
        .all()
    )
    return [
        {
            "child_lot": _code(s, tid, "lot", r["child_lot_id"]),
            "child_seq": r["child_seq"],
            "child_unit": _code(s, tid, "wafer", r["child_unit_id"]),
            "parent_lot": _code(s, tid, "lot", r["parent_lot_id"]),
            "parent_wafer": _code(s, tid, "wafer", r["parent_wafer_id"]),
            "die_row": r["die_row"],
            "die_col": r["die_col"],
            "qty": r["qty"],
        }
        for r in rows
    ]


def _undone(s: Session, tid: uuid.UUID, parents: dict[Any, int]) -> list[Row]:
    """D60：已撤销转换的子批节点（``undone=true``），仅供展示，不参与谱系计算。

    子批与谱系行在撤销时已删除，节点取自母批 ``transform_undo`` 履历快照与转换记录。
    ``parents``：母批 id → 其层级（目标批为 0）。
    """
    if not parents:
        return []
    out: list[Row] = []
    seen: set[tuple[str, str]] = set()
    for r in _hist(s, tid, list(parents), "transform_undo"):
        d = r["details"] or {}
        tr = one(s, tid, "unit_transform", d.get("transform_id"))
        if not tr or tr.get("undone_at") is None:
            continue
        for code in d.get("children") or []:
            if (str(tr["id"]), code) in seen:
                continue
            seen.add((str(tr["id"]), code))
            out.append(
                {
                    "id": None,
                    "code": code,
                    "relation": "transform",
                    "qty": None,
                    "via": _code(s, tid, "lot", r["lot_id"]),
                    "level": parents[r["lot_id"]] + 1,
                    "at": tr["at"],
                    "transform_id": str(tr["id"]),
                    "transform_type": tr["transform_type"],
                    "undone": True,
                    "undone_at": tr["undone_at"],
                    "undone_by": tr["undone_by"],
                    "undo_reason": tr["undo_reason"],
                }
            )
    return out


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
    o = TABLES["unit_origin"]
    fids = [lot["id"], *[uuid.UUID(x["id"]) for x in fwd]]
    return {
        "backward": {
            "lots": back,
            "steps": steps,
            "materials": mats,
            "origins": _origins(s, tid, o.c.child_lot_id.in_(ids)),
        },
        "forward": {
            # 已撤销转换节点追加在后（undone=true，仅展示；谱系计算请过滤）
            "lots": [
                *fwd,
                *_undone(
                    s,
                    tid,
                    {lot["id"]: 0, **{uuid.UUID(x["id"]): x["level"] for x in fwd}},
                ),
            ],
            "origins": _origins(s, tid, o.c.parent_lot_id.in_(fids)),
        },
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
        raise err_422(
            ["query", "kind"],
            f"kind must be one of {KINDS}",
            "enum",
            {"expected": list(KINDS)},
        )
    if kind == "customer_lot":  # B7：按客户批号找到批次，各批次再做正反向追溯
        hits = lot_svc.lookup_customer_lots(s, tid, customer_lot_no=code)
        if not hits:
            raise HTTPException(
                status_code=404, detail=f"customer lot {code} not found"
            )
        res = []
        for x in hits:
            lot = one(s, tid, "lot", uuid.UUID(x["lot_id"]))
            res.append({**x, **(_lot_trace(s, tid, lot) if lot else {})})
        return jsonable(  # type: ignore[no-any-return]
            {"kind": kind, "target": {"customer_lot_no": code.strip()}, "lots": res}
        )
    t = TABLES[kind]
    hit = (
        conn(s)
        .execute(sa.select(t).where(t.c.tenant_id == tid, t.c.code == code.strip()))
        .mappings()
        .first()
    )
    if not hit:
        raise HTTPException(status_code=404, detail=f"{kind} {code} not found")
    tgt = dict(hit)
    h = TABLES["lot_history"]
    out: Row = {"kind": kind, "target": {"id": str(tgt["id"]), "code": tgt["code"]}}
    if kind in ("lot", "wafer"):
        lot = tgt if kind == "lot" else one(s, tid, "lot", tgt["lot_id"])
        if not lot:
            raise HTTPException(status_code=404, detail="lot not found")
        out["target"]["lot"] = lot["code"]
        out["target"]["lot_id"] = str(lot["id"])
        out["target"] |= lot_svc.customer_info(s, tid, lot)
        out |= _lot_trace(s, tid, lot)
        if kind == "wafer":  # 该晶圆的 die 去了哪些子批（含坐标）
            o = TABLES["unit_origin"]
            out["forward"]["dies"] = _origins(s, tid, o.c.parent_wafer_id == tgt["id"])
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
def wafer_lots(s: Session, tid: uuid.UUID, wafer: Row) -> list[Any]:
    """晶圆经历过的批次：当前批次及其谱系上的全部来源批次（拆批 / 合批前的母批）。"""
    up = _walk(s, tid, wafer["lot_id"], True)
    return [wafer["lot_id"], *(uuid.UUID(x["id"]) for x in up)]


def wafer_history(s: Session, tid: uuid.UUID, wafer_id: uuid.UUID) -> list[Row]:
    """晶圆履历：该晶圆的单元级记录，加上其所在批次（含来源批次）的批次级记录，按时间倒序。

    Raises:
        HTTPException: 晶圆不存在（404）。
    """
    from app.core.spec.engine import ENTITIES
    from app.core.spec.serialize import serialize

    w = one(s, tid, "wafer", wafer_id)
    if not w:
        raise HTTPException(status_code=404, detail="Record not found")
    h = TABLES["lot_history"]
    rows = (
        conn(s)
        .execute(
            sa.select(h)
            .where(
                h.c.tenant_id == tid,
                h.c.lot_id.in_(wafer_lots(s, tid, w)),
                sa.or_(h.c.unit_id.is_(None), h.c.unit_id == w["id"]),
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
        raise HTTPException(status_code=404, detail="Record not found")
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
