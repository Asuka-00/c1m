"""Work-order lifecycle and lot start (no track-in/out, no inventory).

Status machine (action: from -> to):
  release   draft -> released          (product + default route active, ID rules, qty)
  hold      released|in_progress -> on_hold
  resume    on_hold -> status before the hold
  complete  in_progress -> completed
  close     completed -> closed
  cancel    draft|released (nothing started) -> cancelled
Lot start moves released -> in_progress; undoing every start moves it back.
"""

import math
import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.mes import coderule
from app.mes.core import ENTITIES, TABLES, Entity
from app.mes.service import (
    MesError,
    audit,
    conn,
    get_row,
    http_422,
    now,
    validator,
)

Row = dict[str, Any]
WO, LOT, WAFER = (ENTITIES[c] for c in ("work_order", "lot", "wafer"))

TRANSITIONS: dict[str, tuple[set[str], str | None]] = {
    "release": ({"draft"}, "released"),
    "hold": ({"released", "in_progress"}, "on_hold"),
    "resume": ({"on_hold"}, None),  # back to held_from
    "complete": ({"in_progress"}, "completed"),
    "close": ({"completed"}, "closed"),
    "cancel": ({"draft", "released"}, "cancelled"),
}
STARTABLE = {"released", "in_progress"}
# fields that stay editable after release
LATE_EDIT = {"remarks", "due_date", "description", "attrs", "customer", "order_ref"}


def _one(s: Session, tid: uuid.UUID, code: str, rid: Any) -> Row | None:
    if rid is None:
        return None
    t = TABLES[code]
    r = (
        conn(s)
        .execute(sa.select(t).where(t.c.tenant_id == tid, t.c.id == rid))
        .mappings()
        .first()
    )
    return dict(r) if r else None


def _err(field: str, msg: str) -> MesError:
    return MesError([(field, f"{field}: {msg}")])


# ---------------- generic CRUD hooks ----------------
@validator("work_order:prefill")
def _prefill(s: Session, tid: uuid.UUID, _e: Entity, row: Row, old: Row | None) -> None:
    if not row.get("priority_id") and row.get("lot_type_id"):
        lt = _one(s, tid, "lot_type", row["lot_type_id"])
        if lt:
            row["priority_id"] = lt["default_priority_id"]
    if old is None and not row.get("code"):
        t = TABLES["code_rule"]
        rule = (
            conn(s)
            .execute(
                sa.select(t)
                .where(t.c.tenant_id == tid, t.c.target == "work_order")
                .order_by(t.c.code)
            )
            .mappings()
            .first()
        )
        if not rule:
            raise _err("code", "no code rule for work orders; enter a WO number")
        row["code"] = coderule.generate(s, tid, dict(rule), 1, commit=False)[0]


@validator("work_order")
def _work_order(
    _s: Session, _tid: uuid.UUID, _e: Entity, row: Row, old: Row | None
) -> None:
    errs: list[tuple[str, str]] = []
    if old and old["wo_status"] != "draft":
        changed = [
            f.name
            for f in WO.all_fields
            if not f.system
            and f.name not in LATE_EDIT
            and row.get(f.column) != old.get(f.column)
        ]
        if changed:
            raise _err(
                changed[0],
                "only remarks, due date and references can change after release",
            )
    if (row.get("planned_qty") or 0) < 1:
        errs.append(("planned_qty", "planned_qty: must be >= 1"))
    if not 0 <= (row.get("over_start_limit_pct") or 0) <= 100:
        errs.append(("over_start_limit_pct", "over_start_limit_pct: must be 0..100"))
    a, b = row.get("planned_start"), row.get("due_date")
    if a and b and a > b:
        errs.append(("due_date", "due_date: must not be before planned_start"))
    if errs:
        raise MesError(errs)


@validator("work_order:delete")
def _wo_delete(
    _s: Session, _t: uuid.UUID, _e: Entity, row: Row, _o: Row | None
) -> None:
    if row["wo_status"] != "draft":
        raise _err(
            "wo_status", "only draft work orders can be deleted (cancel instead)"
        )


# ---------------- helpers ----------------
def cap(wo: Row) -> int:
    """Max wafers that may be started: planned * (1 + limit%), rounded down."""
    return int(
        math.floor(
            float(wo["planned_qty"])
            * (1 + float(wo["over_start_limit_pct"] or 0) / 100)
            + 1e-9
        )
    )


def default_route(s: Session, tid: uuid.UUID, product_id: Any) -> Row | None:
    pr, rt = TABLES["product_route"], TABLES["route"]
    r = (
        conn(s)
        .execute(
            sa.select(rt)
            .join(pr, pr.c.route_id == rt.c.id)
            .where(
                pr.c.tenant_id == tid,
                pr.c.product_id == product_id,
                pr.c.is_default.is_(True),
                rt.c.status == "active",
            )
        )
        .mappings()
        .first()
    )
    return dict(r) if r else None


def _steps(s: Session, tid: uuid.UUID, route_id: Any) -> list[Row]:
    t = TABLES["route_step"]
    return [
        dict(r)
        for r in conn(s)
        .execute(
            sa.select(t)
            .where(t.c.tenant_id == tid, t.c.route_id == route_id)
            .order_by(t.c.seq)
        )
        .mappings()
    ]


def first_step(s: Session, tid: uuid.UUID, route_id: Any) -> tuple[Row | None, Any]:
    """(first top-level step, site id of the first real operation)."""
    steps = _steps(s, tid, route_id)
    if not steps:
        return None, None
    site, depth = None, 0
    cur: Row | None = steps[0]
    while cur and depth < 5:
        if cur.get("operation_id"):
            op = _one(s, tid, "operation", cur["operation_id"])
            area = _one(s, tid, "area", op and op["area_id"])
            site = area and area["site_id"]
            break
        sub = _steps(s, tid, cur.get("sub_route_id"))
        cur, depth = (sub[0] if sub else None), depth + 1
    return steps[0], site


def _rules(s: Session, tid: uuid.UUID, wo: Row) -> tuple[Row, Row, Row]:
    lt = _one(s, tid, "lot_type", wo["lot_type_id"])
    if not lt:
        raise _err("lot_type", "not found")
    lr = _one(s, tid, "code_rule", lt["lot_id_rule_id"])
    wr = _one(s, tid, "code_rule", lt["wafer_id_rule_id"])
    if not lr or lr["target"] != "lot" or not wr or wr["target"] != "wafer":
        raise _err("lot_type", "lot type needs a lot ID rule and a wafer ID rule")
    return lt, lr, wr


def _set(
    s: Session, tid: uuid.UUID, wo: Row, user: Any, action: str, **values: Any
) -> Row:
    t = TABLES["work_order"]
    values.update(updated_at=now(), updated_by=getattr(user, "id", None))
    conn(s).execute(
        sa.update(t).where(t.c.tenant_id == tid, t.c.id == wo["id"]).values(**values)
    )
    new = get_row(s, WO, tid, wo["id"])
    changes = {
        k: (wo.get(k), new[k])
        for k in values
        if k not in ("updated_at", "updated_by") and wo.get(k) != new[k]
    }
    audit(s, tid, WO, action, new, user, changes)
    return new


# ---------------- transitions ----------------
def transition(
    s: Session, tid: uuid.UUID, wo_id: uuid.UUID, action: str, user: Any
) -> Row:
    if action not in TRANSITIONS:
        raise http_422([("action", f"action: must be one of {', '.join(TRANSITIONS)}")])
    wo = get_row(s, WO, tid, wo_id)
    allowed, to = TRANSITIONS[action]
    if wo["wo_status"] not in allowed:
        raise http_422(
            [
                (
                    "wo_status",
                    f"wo_status: cannot {action} a {wo['wo_status']} work order",
                )
            ]
        )
    extra: Row = {}
    if action == "release":
        errs: list[tuple[str, str]] = []
        prod = _one(s, tid, "product", wo["product_id"])
        route = default_route(s, tid, wo["product_id"])
        if not prod or prod["status"] != "active":
            errs.append(("product", "product: must be active"))
        if not route:
            errs.append(("route", "route: product has no active default route"))
        if wo["planned_qty"] < 1:
            errs.append(("planned_qty", "planned_qty: must be >= 1"))
        try:
            _rules(s, tid, wo)
        except MesError as ex:
            errs += ex.errors
        if route and not _steps(s, tid, route["id"]):
            errs.append(("route", "route: has no steps"))
        if errs:
            raise http_422(errs)
        assert prod and route
        extra = {
            "route_id": route["id"],
            "product_version": prod["version"],
            "route_version": route["version"],
            "released_at": now(),
            "released_by": getattr(user, "email", None),
        }
    elif action == "hold":
        extra = {"held_from": wo["wo_status"]}
    elif action == "resume":
        to, extra = wo["held_from"] or "released", {"held_from": None}
    elif action == "cancel" and wo["started_qty"]:
        raise http_422([("wo_status", "wo_status: lots were started; undo them first")])
    new = _set(s, tid, wo, user, action, wo_status=to, **extra)
    s.commit()
    return new


# ---------------- lot start ----------------
def plan(
    s: Session, tid: uuid.UUID, wo_id: uuid.UUID, lot_size: int | None, qty: int | None
) -> Row:
    """Proposed split (nothing is reserved): lot numbers / wafer IDs are previews."""
    wo = get_row(s, WO, tid, wo_id)
    lt, lr, wr = _rules(s, tid, wo)
    size = lot_size or lt["max_wafers"] or 25
    if not 1 <= size <= (lt["max_wafers"] or 25):
        raise http_422([("lot_size", f"lot_size: must be 1..{lt['max_wafers']}")])
    room = max(0, cap(wo) - wo["started_qty"])
    want = (
        qty
        if qty is not None
        else max(0, min(room, wo["planned_qty"] - wo["started_qty"]))
    )
    sizes = [size] * (want // size) + ([want % size] if want % size else [])
    lot_nos = coderule.preview(s, tid, lr, len(sizes)) if sizes else []
    step, site = first_step(s, tid, wo["route_id"]) if wo["route_id"] else (None, None)
    return {
        "work_order_id": str(wo["id"]),
        "wo_status": wo["wo_status"],
        "planned_qty": wo["planned_qty"],
        "started_qty": wo["started_qty"],
        "max_qty": cap(wo),
        "remaining": room,
        "lot_size": size,
        "max_lot_size": lt["max_wafers"],
        "first_step_id": step and str(step["id"]),
        "first_step_seq": step and step["seq"],
        "site_id": site and str(site),
        "lots": [
            {
                "lot_no": lot_nos[i],
                "qty": n,
                "slots": list(range(1, n + 1)),
                "wafer_ids": [
                    coderule.render(wr, k, now(), {"LOT": lot_nos[i], "SLOT": k})
                    for k in range(1, n + 1)
                ],
            }
            for i, n in enumerate(sizes)
        ],
    }


def _carrier_busy(s: Session, tid: uuid.UUID, carrier_id: Any) -> bool:
    t = TABLES["lot"]
    return (
        conn(s)
        .execute(
            sa.select(t.c.id).where(
                t.c.tenant_id == tid,
                t.c.carrier_id == carrier_id,
                t.c.lot_status.in_(["waiting", "processing", "on_hold"]),
            )
        )
        .first()
        is not None
    )


def start(
    s: Session,
    tid: uuid.UUID,
    wo_id: uuid.UUID,
    lots: list[Row],
    user: Any,
    *,
    demo: bool = False,
) -> list[Row]:
    wo = get_row(s, WO, tid, wo_id)
    if wo["wo_status"] not in STARTABLE:
        raise http_422(
            [
                (
                    "wo_status",
                    f"wo_status: cannot start lots on a {wo['wo_status']} work order",
                )
            ]
        )
    lt, lr, wr = _rules(s, tid, wo)
    errs: list[tuple[str, str]] = []
    if not lots:
        errs.append(("lots", "lots: at least one lot"))
    total = sum(int(x.get("qty") or 0) for x in lots)
    if wo["started_qty"] + total > cap(wo):
        errs.append(
            (
                "lots",
                f"lots: started {wo['started_qty']} + {total} exceeds the limit {cap(wo)} (planned {wo['planned_qty']} + {wo['over_start_limit_pct'] or 0}%)",
            )
        )
    seen: set[Any] = set()
    for i, x in enumerate(lots, 1):
        n = int(x.get("qty") or 0)
        if not 1 <= n <= (lt["max_wafers"] or 25):
            errs.append(
                (f"lots.{i}.qty", f"lot {i}: qty must be 1..{lt['max_wafers']}")
            )
        slots = x.get("slots") or list(range(1, n + 1))
        x["slots"] = slots
        width = 25
        if x.get("carrier_id"):
            cid = uuid.UUID(str(x["carrier_id"]))
            x["carrier_id"] = cid
            car = _one(s, tid, "carrier", cid)
            ct = car and _one(s, tid, "carrier_type", car["carrier_type_id"])
            if not car or not ct:
                errs.append((f"lots.{i}.carrier", f"lot {i}: carrier not found"))
                continue
            width = ct["capacity"]
            if car["status_code"] != "available":
                errs.append(
                    (
                        f"lots.{i}.carrier",
                        f"lot {i}: carrier {car['code']} is not available",
                    )
                )
            if cid in seen or _carrier_busy(s, tid, cid):
                errs.append(
                    (
                        f"lots.{i}.carrier",
                        f"lot {i}: carrier {car['code']} is already in use",
                    )
                )
            seen.add(cid)
        if not x.get("carrier_id"):
            width = max(width, n)
        if (
            len(slots) != n
            or len(set(slots)) != n
            or not all(1 <= int(k) <= width for k in slots)
        ):
            errs.append(
                (
                    f"lots.{i}.slots",
                    f"lot {i}: {n} distinct slots within 1..{width} required",
                )
            )
        srcs = x.get("wafer_sources") or []
        if srcs and len(srcs) != n:
            errs.append((f"lots.{i}.wafer_sources", f"lot {i}: one source per wafer"))
    if errs:
        raise http_422(errs)
    step, site = first_step(s, tid, wo["route_id"])
    if not step:
        raise http_422([("route", "route: has no steps")])
    lot_nos = coderule.generate(s, tid, lr, len(lots), commit=False)
    at, c, out = now(), conn(s), []
    seq_wafer = "{SEQ" in wr["pattern"]
    tag = {"_demo": True} if demo else {}
    for lot_no, x in zip(lot_nos, lots, strict=True):
        lid = uuid.uuid4()
        sysv = {
            "tenant_id": tid,
            "created_at": at,
            "updated_at": at,
            "created_by": getattr(user, "id", None),
            "updated_by": getattr(user, "id", None),
        }
        c.execute(
            sa.insert(TABLES["lot"]).values(
                id=lid,
                code=lot_no,
                work_order_id=wo["id"],
                product_id=wo["product_id"],
                route_id=wo["route_id"],
                lot_type_id=wo["lot_type_id"],
                priority_id=wo["priority_id"],
                qty=int(x["qty"]),
                site_id=site,
                current_step_id=step["id"],
                lot_status="waiting",
                carrier_id=x.get("carrier_id"),
                source_ref=x.get("source_ref") or None,
                started_at=at,
                started_by=getattr(user, "email", None),
                attrs=dict(tag),
                **sysv,
            )
        )
        srcs = x.get("wafer_sources") or [None] * int(x["qty"])
        for k, src in zip(x["slots"], srcs, strict=True):
            ctx = {"LOT": lot_no, "SLOT": int(k)}
            wid = (
                coderule.generate(s, tid, wr, 1, ctx, commit=False)[0]
                if seq_wafer
                else coderule.render(wr, int(k), at, ctx)
            )
            c.execute(
                sa.insert(TABLES["wafer"]).values(
                    id=uuid.uuid4(),
                    code=wid,
                    lot_id=lid,
                    slot=int(k),
                    wafer_status="waiting",
                    source_ref=src or None,
                    attrs=dict(tag),
                    **sysv,
                )
            )
        lot = get_row(s, LOT, tid, lid)
        audit(
            s,
            tid,
            LOT,
            "start",
            lot,
            user,
            {"work_order": (None, wo["code"]), "qty": (None, lot["qty"])},
        )
        out.append(lot)
    _set(
        s,
        tid,
        wo,
        user,
        "start",
        started_qty=wo["started_qty"] + total,
        wo_status="in_progress",
    )
    try:
        s.commit()
    except IntegrityError as ex:
        s.rollback()
        raise http_422(
            [("lots", "lots: generated lot / wafer ID already exists")]
        ) from ex
    return out


def undo_start(
    s: Session,
    tid: uuid.UUID,
    wo_id: uuid.UUID,
    lot_ids: list[uuid.UUID] | None,
    user: Any,
) -> int:
    """Delete started lots (+ wafers) that have not been processed yet."""
    wo = get_row(s, WO, tid, wo_id)
    if wo["wo_status"] not in STARTABLE:
        raise http_422(
            [("wo_status", f"wo_status: cannot undo on a {wo['wo_status']} work order")]
        )
    t = TABLES["lot"]
    stmt = sa.select(t).where(t.c.tenant_id == tid, t.c.work_order_id == wo["id"])
    if lot_ids:
        stmt = stmt.where(t.c.id.in_(lot_ids))
    lots = [dict(r) for r in conn(s).execute(stmt).mappings()]
    if not lots:
        raise http_422([("lots", "lots: nothing to undo")])
    step, _ = first_step(s, tid, wo["route_id"])
    busy = [
        x["code"]
        for x in lots
        if x["lot_status"] != "waiting" or x["current_step_id"] != (step and step["id"])
    ]
    if busy:
        raise http_422([("lots", f"lots: already processed: {', '.join(busy)}")])
    n = sum(x["qty"] for x in lots)
    for x in lots:
        audit(s, tid, LOT, "undo_start", x, user, {"work_order": (wo["code"], None)})
    conn(s).execute(sa.delete(t).where(t.c.id.in_([x["id"] for x in lots])))
    left = wo["started_qty"] - n
    _set(
        s,
        tid,
        wo,
        user,
        "undo_start",
        started_qty=left,
        wo_status="in_progress" if left > 0 else "released",
    )
    s.commit()
    return len(lots)
