"""CRUD validators of process entities."""

import uuid
from typing import Any

import sqlalchemy as sa
from sqlmodel import Session

from app.core.spec.base import conn
from app.core.spec.engine import TABLES, Entity
from app.core.spec.errors import MesError
from app.core.spec.validate import validator
from app.mes.common.validators import Row, _get
from app.mes.equipment.service import check_recipe_equipment_type


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


@validator("recipe_equipment")
def _recipe_eqp(
    s: Session, tid: uuid.UUID, _e: Entity, row: Row, _old: Row | None
) -> None:
    check_recipe_equipment_type(s, tid, row.get("recipe_id"), row.get("equipment_id"))
