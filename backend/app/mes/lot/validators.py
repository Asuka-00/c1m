"""批次规则实体的 CRUD 校验器。"""

import uuid

from sqlmodel import Session

from app.core.spec.engine import Entity
from app.core.spec.errors import MesError
from app.core.spec.validate import validator
from app.mes.common.validators import Row, _get


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
    if not 1 <= (row.get("max_wafers") or 0) <= 100000:
        errs.append(("max_wafers", "max_wafers: must be 1..100000"))
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
