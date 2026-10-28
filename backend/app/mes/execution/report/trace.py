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
from app.mes.execution.units.die_map import current_maps
from app.mes.warehouse.service import shipments_of

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


def _mounted_at(s: Session, tid: uuid.UUID, equipment_id: Any, at: Any) -> list[Row]:
    """某时刻机台上装着的物料批（上料记录）。"""
    m = TABLES["equipment_material_mount"]
    stmt = sa.select(m).where(
        m.c.tenant_id == tid,
        m.c.equipment_id == equipment_id,
        m.c.mounted_at <= at,
        sa.or_(m.c.unmounted_at.is_(None), m.c.unmounted_at >= at),
    )
    return [dict(r) for r in conn(s).execute(stmt).mappings()]


def _shipments(s: Session, tid: uuid.UUID, lot: Row, fwd: list[Row]) -> list[Row]:
    """本批及其下游批次的已确认出货记录（客户级出货追溯）。"""
    ids = [lot["id"], *[uuid.UUID(x["id"]) for x in fwd]]
    codes = {i: _code(s, tid, "lot", i) for i in ids}
    return [
        {
            "lot": codes[r["lot_id"]],
            "shipment": r["code"],
            "customer": r["customer"],
            "waybill": r["waybill"],
            "qty": r["qty"],
            "at": r["confirmed_at"],
        }
        for r in shipments_of(s, tid, ids)
    ]


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
    # 过站时机台上装着的物料批（上料记录），与出站扣料并列
    mats += [
        {
            "lot": codes[r["lot_id"]],
            "step_seq": r["step_seq"],
            "material_lot": _code(s, tid, "material_lot", m["material_lot_id"]),
            "qty": None,
            "at": r["at"],
            "position": m["position"],
        }
        for r in _hist(s, tid, ids, "track_in")
        if r["equipment_id"]
        for m in _mounted_at(s, tid, r["equipment_id"], r["at"])
    ]
    return {
        "backward": {"lots": back, "steps": steps, "materials": mats},
        "forward": {"lots": fwd, "shipments": _shipments(s, tid, lot, fwd)},
    }


UNIT_TRACE_MAX = 500


def _unit_walk(s: Session, tid: uuid.UUID, start: Any, up: bool) -> Row:
    """沿单元谱系（晶圆 → 芯片 → 封装）逐层追溯，最多返回 ``UNIT_TRACE_MAX`` 个单元。"""
    g, w = TABLES["unit_genealogy"], TABLES["wafer"]
    a, b = (
        (g.c.child_unit_id, g.c.parent_unit_id)
        if up
        else (
            g.c.parent_unit_id,
            g.c.child_unit_id,
        )
    )
    out: list[Row] = []
    seen, todo, total = {start}, [start], 0
    for depth in range(1, 11):
        if not todo:
            break
        rows = (
            conn(s)
            .execute(
                sa.select(b.label("o"), g.c.relation, g.c.at, w.c.code, w.c.unit_kind)
                .join(w, w.c.id == b)
                .where(g.c.tenant_id == tid, a.in_(todo))
                .order_by(w.c.code)
            )
            .mappings()
            .all()
        )
        todo = []
        for r in rows:
            if r["o"] in seen:
                continue
            seen.add(r["o"])
            todo.append(r["o"])
            total += 1
            if len(out) < UNIT_TRACE_MAX:
                out.append(
                    {
                        "id": str(r["o"]),
                        "code": r["code"],
                        "unit_kind": r["unit_kind"],
                        "relation": r["relation"],
                        "level": depth,
                        "at": r["at"],
                    }
                )
    return {"units": out, "total": total}


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
        物料批：``{target, lots}``（消耗了该物料批的批次，或该物料批装在机台上期间过站的批次，及其下游产出）。
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
        if kind == "wafer":
            out["target"]["unit_kind"] = tgt["unit_kind"]
            out["units"] = {
                "backward": _unit_walk(s, tid, tgt["id"], True),
                "forward": _unit_walk(s, tid, tgt["id"], False),
            }
    elif kind == "equipment":
        out["lots"] = _lots_by(
            s, tid, sa.and_(h.c.equipment_id == tgt["id"], h.c.action == "track_in")
        )
    else:
        used: list[Row] = []
        for u in find(
            s, tid, "lot_material_use", order="at", material_lot_id=tgt["id"]
        ):
            lot = one(s, tid, "lot", u["lot_id"])
            used.append(
                {
                    "id": str(u["lot_id"]),
                    "code": lot and lot["code"],
                    "product": lot and _code(s, tid, "product", lot["product_id"]),
                    "step_seq": (
                        one(s, tid, "route_step", u["route_step_id"]) or {}
                    ).get("seq"),
                    "operation": _code(s, tid, "operation", u["operation_id"]),
                    "equipment": _code(s, tid, "equipment", u["equipment_id"]),
                    "qty": u["qty"],
                    "at": u["at"],
                    "consumed": [{"material_lot": tgt["code"], "qty": u["qty"]}],
                }
            )
        # 该物料批装在机台上期间过站（Track In）的批次
        mt = TABLES["equipment_material_mount"]
        for m in (
            conn(s)
            .execute(
                sa.select(mt).where(
                    mt.c.tenant_id == tid, mt.c.material_lot_id == tgt["id"]
                )
            )
            .mappings()
        ):
            end = h.c.at <= m["unmounted_at"] if m["unmounted_at"] else sa.true()
            for u in _lots_by(
                s,
                tid,
                sa.and_(
                    h.c.action == "track_in",
                    h.c.equipment_id == m["equipment_id"],
                    h.c.at >= m["mounted_at"],
                    end,
                ),
            ):
                u["position"] = m["position"]
                used.append(u)
        for u in used:
            u["forward"] = _walk(s, tid, uuid.UUID(u["id"]), False)
        out["lots"] = used
    return jsonable(out)  # type: ignore[no-any-return]


# ---------------- 晶圆级履历与晶圆状态 ----------------
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


def wafer_status(s: Session, tid: uuid.UUID, lot_id: uuid.UUID) -> Row:
    """晶圆状态：按槽位排列批次的晶圆（容量取载具类型，缺省 25），含状态与返工次数。

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
    maps = current_maps(s, tid, [w["id"] for w in ws], with_dies=False)
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
                    "die_map": _map_brief(maps.get(w["id"])),
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


def _map_brief(m: Row | None) -> Row | None:
    return m and {
        "id": str(m["id"]),
        "test_kind": m["test_kind"],
        "gross": m["gross"],
        "good": m["good"],
        "yield_pct": m["yield_pct"],
    }
