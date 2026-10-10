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
