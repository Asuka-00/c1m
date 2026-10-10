"""Entity-specific validation rules (registered with @validator)."""

import uuid
from typing import Any

import sqlalchemy as sa
from sqlmodel import Session

from app.mes.coderule import check_pattern
from app.mes.core import TABLES, Entity
from app.mes.service import MesError, conn, validator

Row = dict[str, Any]


@validator("code_rule")
def _code_rule(
    _s: Session, _t: uuid.UUID, _e: Entity, row: Row, _old: Row | None
) -> None:
    errs = check_pattern(row.get("pattern") or "")
    w = row.get("seq_width") or 0
    if not 1 <= w <= 12:
        errs.append(("seq_width", "seq_width: must be 1..12"))
    if (row.get("seq_start") or 0) < 0:
        errs.append(("seq_start", "seq_start: must be >= 0"))
    if errs:
        raise MesError(errs)


@validator("shift")
def _shift(_s: Session, _t: uuid.UUID, _e: Entity, row: Row, _old: Row | None) -> None:
    st, en = row.get("start_time"), row.get("end_time")
    if st and en:
        if st == en:
            raise MesError([("end_time", "end_time: must differ from start_time")])
        if (en < st) != bool(row.get("crosses_midnight")):
            raise MesError(
                [
                    (
                        "crosses_midnight",
                        "crosses_midnight: must be set iff end is before start",
                    )
                ]
            )


@validator("work_calendar")
def _calendar(
    _s: Session, _t: uuid.UUID, _e: Entity, row: Row, _old: Row | None
) -> None:
    if not 2000 <= (row.get("year") or 0) <= 2100:
        raise MesError([("year", "year: must be 2000..2100")])


@validator("attr_def")
def _attr_def(
    _s: Session, _t: uuid.UUID, _e: Entity, row: Row, _old: Row | None
) -> None:
    if row.get("data_type") == "select" and not (
        row.get("options") or row.get("dict_type_id")
    ):
        raise MesError([("options", "options: a select needs options or a dictionary")])


# ---------------- phase 2 ----------------
def _get(session: Session, tid: uuid.UUID, code: str, rid: Any) -> Row | None:
    if rid is None:
        return None
    t = TABLES[code]
    r = (
        conn(session)
        .execute(sa.select(t).where(t.c.tenant_id == tid, t.c.id == rid))
        .mappings()
        .first()
    )
    return dict(r) if r else None


@validator("uom_conversion")
def _uom_conv(
    s: Session, tid: uuid.UUID, _e: Entity, row: Row, _old: Row | None
) -> None:
    errs: list[tuple[str, str]] = []
    if row.get("from_uom_id") == row.get("to_uom_id"):
        errs.append(("to_uom", "to_uom: must differ from from_uom"))
    if (row.get("factor") or 0) <= 0:
        errs.append(("factor", "factor: must be > 0"))
    a, b = (
        _get(s, tid, "uom", row.get("from_uom_id")),
        _get(s, tid, "uom", row.get("to_uom_id")),
    )
    if a and b and a["dimension"] != b["dimension"]:
        errs.append(("to_uom", "to_uom: dimensions differ"))
    if errs:
        raise MesError(errs)


@validator("e10_transition")
def _e10_tr(_s: Session, _t: uuid.UUID, _e: Entity, row: Row, _old: Row | None) -> None:
    if row.get("from_state_id") == row.get("to_state_id"):
        raise MesError([("to_state", "to_state: must differ from from_state")])


@validator("e10_state")
def _e10_state(
    s: Session, tid: uuid.UUID, _e: Entity, row: Row, old: Row | None
) -> None:
    if row.get("is_initial"):
        t = TABLES["e10_state"]
        other = (
            conn(s)
            .execute(
                sa.select(t.c.code).where(
                    t.c.tenant_id == tid,
                    t.c.is_initial.is_(True),
                    t.c.id != (old or {}).get("id"),
                )
            )
            .scalar()
        )
        if other:
            raise MesError(
                [("is_initial", f"is_initial: {other} is already the initial state")]
            )


@validator("equipment")
def _equipment(
    s: Session, tid: uuid.UUID, _e: Entity, row: Row, _old: Row | None
) -> None:
    kind, parent = row.get("unit_kind"), _get(s, tid, "equipment", row.get("parent_id"))
    if kind == "main" and parent:
        raise MesError([("parent", "parent: main equipment cannot have a parent")])
    if kind != "main" and not parent:
        raise MesError([("parent", f"parent: a {kind} needs a parent equipment")])
    if parent and parent["unit_kind"] not in ("main", "sub_unit"):
        raise MesError([("parent", "parent: must be a main equipment or sub-unit")])
    if parent:  # sub-units inherit the parent's equipment type
        pt, cur = parent["equipment_type_id"], row.get("equipment_type_id")
        if cur is None:
            row["equipment_type_id"] = pt
        elif pt is not None and cur != pt:
            raise MesError(
                [
                    (
                        "equipment_type",
                        "equipment_type: must match the parent equipment's type",
                    )
                ]
            )


@validator("carrier_type")
def _carrier_type(
    _s: Session, _t: uuid.UUID, _e: Entity, row: Row, _old: Row | None
) -> None:
    if not 1 <= (row.get("capacity") or 0) <= 50:
        raise MesError([("capacity", "capacity: must be 1..50")])


# ---------------- phase 3 ----------------
def _route(s: Session, tid: uuid.UUID, rid: Any) -> Row | None:
    return _get(s, tid, "route", rid)


@validator("route_step")
def _route_step(
    s: Session, tid: uuid.UUID, _e: Entity, row: Row, _old: Row | None
) -> None:
    errs: list[tuple[str, str]] = []
    if (row.get("seq") or 0) <= 0:
        errs.append(("seq", "seq: must be > 0"))
    if row.get("step_type") == "operation":
        if not row.get("operation_id"):
            errs.append(("operation", "operation: required for an operation step"))
        if row.get("sub_route_id"):
            errs.append(("sub_route", "sub_route: only for sub-route steps"))
    else:
        sub = _route(s, tid, row.get("sub_route_id"))
        if not sub:
            errs.append(("sub_route", "sub_route: required for a sub-route step"))
        elif sub["route_type"] != "sub":
            errs.append(("sub_route", "sub_route: must be a route of type sub"))
        elif sub["code"] == (_route(s, tid, row.get("route_id")) or {}).get("code"):
            errs.append(("sub_route", "sub_route: a route cannot call itself"))
    rw = _route(s, tid, row.get("rework_route_id"))
    if row.get("rework_route_id") and (not rw or rw["route_type"] != "rework"):
        errs.append(("rework_route", "rework_route: must be a route of type rework"))
    if row.get("branch_to_seq") is not None and not row.get("branch_condition"):
        errs.append(
            ("branch_condition", "branch_condition: required with branch_to_seq")
        )
    if errs:
        raise MesError(errs)


@validator("route:activate")
def _route_activate(
    s: Session, tid: uuid.UUID, _e: Entity, row: Row, _old: Row | None
) -> None:
    t = TABLES["route_step"]
    steps = [
        dict(r)
        for r in conn(s)
        .execute(sa.select(t).where(t.c.tenant_id == tid, t.c.route_id == row["id"]))
        .mappings()
    ]
    if not steps:
        raise MesError([("route", "route: needs at least one step before activation")])
    seqs = {x["seq"] for x in steps}
    errs: list[tuple[str, str]] = []
    for st in steps:
        if st["branch_to_seq"] is not None and st["branch_to_seq"] not in seqs:
            errs.append(
                (
                    "route_step",
                    f"step {st['seq']}: branch target {st['branch_to_seq']} does not exist",
                )
            )
        for k in ("sub_route_id", "rework_route_id"):
            ref = _route(s, tid, st[k])
            if ref and ref["status"] != "active":
                errs.append(
                    (
                        "route_step",
                        f"step {st['seq']}: {ref['code']} v{ref['version']} is not active",
                    )
                )
    if errs:
        raise MesError(errs)


@validator("step_resource")
def _step_resource(
    _s: Session, _t: uuid.UUID, _e: Entity, row: Row, _old: Row | None
) -> None:
    kind = row.get("resource_kind")
    errs = [
        (k, f"{k}: {'required' if k == kind else 'must be empty'} for {kind}")
        for k in ("equipment", "equipment_group", "reticle", "material", "fixture")
        if bool(row.get(f"{k}_id")) != (k == kind)
    ]
    if row.get("qty") is not None and row["qty"] <= 0:
        errs.append(("qty", "qty: must be > 0"))
    if errs:
        raise MesError(errs)


@validator("param_spec")
def _param_spec(
    _s: Session, _t: uuid.UUID, _e: Entity, row: Row, _old: Row | None
) -> None:
    lsl, tgt, usl = row.get("lsl"), row.get("target"), row.get("usl")
    errs: list[tuple[str, str]] = []
    if not (row.get("operation_id") or row.get("recipe_id")):
        errs.append(("operation", "operation: an operation or a recipe is required"))
    if lsl is None and usl is None:
        errs.append(("lsl", "lsl: give LSL and/or USL"))
    if lsl is not None and usl is not None and lsl > usl:
        errs.append(("usl", "usl: must be >= LSL"))
    if tgt is not None and (
        (lsl is not None and tgt < lsl) or (usl is not None and tgt > usl)
    ):
        errs.append(("target", "target: must lie within LSL..USL"))
    if errs:
        raise MesError(errs)


@validator("product_route")
def _product_route(
    s: Session, tid: uuid.UUID, _e: Entity, row: Row, _old: Row | None
) -> None:
    r = _route(s, tid, row.get("route_id"))
    if r and r["route_type"] != "main":
        raise MesError([("route", "route: products bind to main routes")])
    a, b = row.get("effective_from"), row.get("effective_to")
    if a and b and a > b:
        raise MesError([("effective_to", "effective_to: must be after effective_from")])
    if row.get("is_default"):
        pr = TABLES["product_route"]
        other = (
            conn(s)
            .execute(
                sa.select(pr.c.id).where(
                    pr.c.tenant_id == tid,
                    pr.c.product_id == row.get("product_id"),
                    pr.c.is_default.is_(True),
                    pr.c.id != row.get("id", uuid.uuid4()),
                )
            )
            .first()
        )
        if other:
            raise MesError(
                [("is_default", "is_default: the product already has a default route")]
            )


def _type_match(s: Session, tid: uuid.UUID, recipe_id: Any, equipment_id: Any) -> None:
    rec, eqp = (
        _get(s, tid, "recipe", recipe_id),
        _get(s, tid, "equipment", equipment_id),
    )
    if (
        rec
        and eqp
        and rec["equipment_type_id"]
        and eqp["equipment_type_id"]
        and rec["equipment_type_id"] != eqp["equipment_type_id"]
    ):
        raise MesError(
            [("equipment", "equipment: type differs from the recipe's equipment type")]
        )


@validator("recipe_equipment")
def _recipe_eqp(
    s: Session, tid: uuid.UUID, _e: Entity, row: Row, _old: Row | None
) -> None:
    _type_match(s, tid, row.get("recipe_id"), row.get("equipment_id"))


@validator("equipment_capability")
def _capability(
    s: Session, tid: uuid.UUID, _e: Entity, row: Row, _old: Row | None
) -> None:
    _type_match(s, tid, row.get("recipe_id"), row.get("equipment_id"))


# ---------------- phase 4 ----------------
def _limits(row: Row) -> list[tuple[str, str]]:
    lsl, tgt, usl = row.get("lsl"), row.get("target"), row.get("usl")
    errs: list[tuple[str, str]] = []
    if lsl is not None and usl is not None and lsl > usl:
        errs.append(("usl", "usl: must be >= LSL"))
    if tgt is not None and (
        (lsl is not None and tgt < lsl) or (usl is not None and tgt > usl)
    ):
        errs.append(("target", "target: must lie within LSL..USL"))
    return errs


@validator("dc_plan_item")
def _dc_item(
    _s: Session, _t: uuid.UUID, _e: Entity, row: Row, _old: Row | None
) -> None:
    errs = _limits(row)
    if (row.get("sites") or 0) < 1:
        errs.append(("sites", "sites: must be >= 1"))
    if errs:
        raise MesError(errs)


@validator("sampling_rule")
def _sampling(
    _s: Session, _t: uuid.UUID, _e: Entity, row: Row, _old: Row | None
) -> None:
    errs: list[tuple[str, str]] = []
    if (row.get("lot_frequency") or 0) < 1:
        errs.append(("lot_frequency", "lot_frequency: must be >= 1"))
    if row.get("level") == "wafer":
        if not 1 <= (row.get("wafer_count") or 0) <= 25:
            errs.append(("wafer_count", "wafer_count: 1..25 for wafer-level sampling"))
        if not row.get("wafer_selection"):
            errs.append(
                (
                    "wafer_selection",
                    "wafer_selection: required for wafer-level sampling",
                )
            )
    if row.get("wafer_selection") == "fixed":
        try:
            slots = [
                int(x) for x in (row.get("fixed_slots") or "").split(",") if x.strip()
            ]
        except ValueError:
            slots = []
        if not slots or any(not 1 <= x <= 25 for x in slots):
            errs.append(("fixed_slots", "fixed_slots: comma separated slots 1..25"))
        elif row.get("wafer_count") and len(slots) != row["wafer_count"]:
            errs.append(("fixed_slots", "fixed_slots: count must equal wafer_count"))
    if errs:
        raise MesError(errs)


@validator("lot_priority")
def _priority(
    _s: Session, _t: uuid.UUID, _e: Entity, row: Row, _old: Row | None
) -> None:
    if not 1 <= (row.get("level") or 0) <= 99:
        raise MesError([("level", "level: must be 1..99")])


@validator("lot_type")
def _lot_type(
    s: Session, tid: uuid.UUID, _e: Entity, row: Row, _old: Row | None
) -> None:
    errs: list[tuple[str, str]] = []
    for k, target in (("lot_id_rule", "lot"), ("wafer_id_rule", "wafer")):
        r = _get(s, tid, "code_rule", row.get(f"{k}_id"))
        if r and r["target"] != target:
            errs.append((k, f"{k}: must be a code rule for {target} IDs"))
    if not 1 <= (row.get("max_wafers") or 0) <= 50:
        errs.append(("max_wafers", "max_wafers: must be 1..50"))
    if errs:
        raise MesError(errs)


@validator("split_merge_rule")
def _split_merge(
    _s: Session, _t: uuid.UUID, _e: Entity, row: Row, _old: Row | None
) -> None:
    errs: list[tuple[str, str]] = []
    if row.get("allow_split") and (row.get("max_children") or 0) < 2:
        errs.append(
            ("max_children", "max_children: must be >= 2 when splitting is allowed")
        )
    if (row.get("min_wafers") or 0) < 1:
        errs.append(("min_wafers", "min_wafers: must be >= 1"))
    if errs:
        raise MesError(errs)


@validator("qtime_rule")
def _qtime(s: Session, tid: uuid.UUID, _e: Entity, row: Row, _old: Row | None) -> None:
    errs: list[tuple[str, str]] = []
    a, b = (
        _get(s, tid, "route_step", row.get("from_step_id")),
        _get(s, tid, "route_step", row.get("to_step_id")),
    )
    for k, st in (("from_step", a), ("to_step", b)):
        if st and st["route_id"] != row.get("route_id"):
            errs.append((k, f"{k}: must be a step of the selected route"))
    if a and b and a["seq"] >= b["seq"]:
        errs.append(("to_step", "to_step: must come after from_step"))
    lo, hi = row.get("min_minutes"), row.get("max_minutes")
    if lo is None and hi is None:
        errs.append(("max_minutes", "max_minutes: give a min and/or max time"))
    if (lo is not None and lo < 0) or (hi is not None and hi <= 0):
        errs.append(("max_minutes", "max_minutes: times must be positive"))
    if lo is not None and hi is not None and lo > hi:
        errs.append(("max_minutes", "max_minutes: must be >= min_minutes"))
    if errs:
        raise MesError(errs)


@validator("product:activate")
def _product_activate(
    s: Session, tid: uuid.UUID, _e: Entity, row: Row, _old: Row | None
) -> None:
    """A product can go Active only with an Active route bound as default."""
    pr, rt = TABLES["product_route"], TABLES["route"]
    ok = (
        conn(s)
        .execute(
            sa.select(pr.c.id)
            .join(rt, rt.c.id == pr.c.route_id)
            .where(
                pr.c.tenant_id == tid,
                pr.c.product_id == row["id"],
                pr.c.is_default.is_(True),
                rt.c.status == "active",
            )
        )
        .first()
    )
    if not ok:
        raise MesError(
            [
                (
                    "product_route",
                    "product: needs an active route bound as default before activation",
                )
            ]
        )
