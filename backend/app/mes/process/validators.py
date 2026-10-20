"""工艺实体的 CRUD 校验器。"""

import uuid
from typing import Any

import sqlalchemy as sa
from sqlmodel import Session

from app.core import error_codes as ec
from app.core.spec.base import conn
from app.core.spec.engine import TABLES, Entity
from app.core.spec.errors import FieldError, MesError, fe
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
    errs: list[FieldError] = []
    if (row.get("seq") or 0) <= 0:
        errs.append(fe("seq", ec.FIELD_GT, "seq: must be > 0", min=0))
    if row.get("step_type") == "operation":
        if not row.get("operation_id"):
            errs.append(
                fe(
                    "operation",
                    ec.OPERATION_REQUIRED_FOR_STEP,
                    "operation: required for an operation step",
                )
            )
        if row.get("sub_route_id"):
            errs.append(
                fe(
                    "sub_route",
                    ec.SUB_ROUTE_ONLY,
                    "sub_route: only for sub-route steps",
                )
            )
    else:
        sub = _route(s, tid, row.get("sub_route_id"))
        if not sub:
            errs.append(
                fe(
                    "sub_route",
                    ec.SUB_ROUTE_REQUIRED,
                    "sub_route: required for a sub-route step",
                )
            )
        elif sub["route_type"] != "sub":
            errs.append(
                fe(
                    "sub_route",
                    ec.SUB_ROUTE_TYPE,
                    "sub_route: must be a route of type sub",
                )
            )
        elif sub["code"] == (_route(s, tid, row.get("route_id")) or {}).get("code"):
            errs.append(
                fe(
                    "sub_route",
                    ec.SUB_ROUTE_SELF,
                    "sub_route: a route cannot call itself",
                )
            )
    rw = _route(s, tid, row.get("rework_route_id"))
    if row.get("rework_route_id") and (not rw or rw["route_type"] != "rework"):
        errs.append(
            fe(
                "rework_route",
                ec.REWORK_ROUTE_TYPE,
                "rework_route: must be a route of type rework",
            )
        )
    if row.get("branch_to_seq") is not None and not row.get("branch_condition"):
        errs.append(
            fe(
                "branch_condition",
                ec.BRANCH_CONDITION_REQUIRED,
                "branch_condition: required with branch_to_seq",
            )
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
        raise MesError(
            [
                fe(
                    "route",
                    ec.ROUTE_ACTIVATION_STEPS,
                    "route: needs at least one step before activation",
                )
            ]
        )
    seqs = {x["seq"] for x in steps}
    errs: list[FieldError] = []
    for st in steps:
        if st["branch_to_seq"] is not None and st["branch_to_seq"] not in seqs:
            errs.append(
                fe(
                    "route_step",
                    ec.STEP_BRANCH_TARGET,
                    f"step {st['seq']}: branch target {st['branch_to_seq']} does not exist",
                    seq=st["seq"],
                    target=st["branch_to_seq"],
                )
            )
        for k in ("sub_route_id", "rework_route_id"):
            ref = _route(s, tid, st[k])
            if ref and ref["status"] != "active":
                errs.append(
                    fe(
                        "route_step",
                        ec.STEP_REF_INACTIVE,
                        f"step {st['seq']}: {ref['code']} v{ref['version']} is not active",
                        seq=st["seq"],
                        code=ref["code"],
                        version=ref["version"],
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
        fe(
            k,
            (ec.STEP_FIELD_REQUIRED if k == kind else ec.STEP_FIELD_EMPTY),
            f"{k}: {'required' if k == kind else 'must be empty'} for {kind}",
            kind=kind,
        )
        for k in ("equipment", "equipment_group", "reticle", "material", "fixture")
        if bool(row.get(f"{k}_id")) != (k == kind)
    ]
    if row.get("qty") is not None and row["qty"] <= 0:
        errs.append(fe("qty", ec.FIELD_GT, "qty: must be > 0", min=0))
    if errs:
        raise MesError(errs)


@validator("param_spec")
def _param_spec(
    _s: Session, _t: uuid.UUID, _e: Entity, row: Row, _old: Row | None
) -> None:
    lsl, tgt, usl = row.get("lsl"), row.get("target"), row.get("usl")
    errs: list[FieldError] = []
    if not (row.get("operation_id") or row.get("recipe_id")):
        errs.append(
            fe(
                "operation",
                ec.OPERATION_OR_RECIPE,
                "operation: an operation or a recipe is required",
            )
        )
    if lsl is None and usl is None:
        errs.append(fe("lsl", ec.SPEC_LIMIT_REQUIRED, "lsl: give LSL and/or USL"))
    if lsl is not None and usl is not None and lsl > usl:
        errs.append(fe("usl", ec.USL_GE_LSL, "usl: must be >= LSL"))
    if tgt is not None and (
        (lsl is not None and tgt < lsl) or (usl is not None and tgt > usl)
    ):
        errs.append(
            fe("target", ec.TARGET_WITHIN_LIMITS, "target: must lie within LSL..USL")
        )
    if errs:
        raise MesError(errs)


@validator("product_route")
def _product_route(
    s: Session, tid: uuid.UUID, _e: Entity, row: Row, _old: Row | None
) -> None:
    r = _route(s, tid, row.get("route_id"))
    if r and r["route_type"] != "main":
        raise MesError(
            [
                fe(
                    "route",
                    ec.PRODUCT_ROUTE_MAIN_ONLY,
                    "route: products bind to main routes",
                )
            ]
        )
    a, b = row.get("effective_from"), row.get("effective_to")
    if a and b and a > b:
        raise MesError(
            [
                fe(
                    "effective_to",
                    ec.EFFECTIVE_TO_AFTER_FROM,
                    "effective_to: must be after effective_from",
                )
            ]
        )
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
                [
                    fe(
                        "is_default",
                        ec.DEFAULT_ROUTE_EXISTS,
                        "is_default: the product already has a default route",
                    )
                ]
            )


@validator("recipe_equipment")
def _recipe_eqp(
    s: Session, tid: uuid.UUID, _e: Entity, row: Row, _old: Row | None
) -> None:
    check_recipe_equipment_type(s, tid, row.get("recipe_id"), row.get("equipment_id"))
