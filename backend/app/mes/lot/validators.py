"""批次规则实体的 CRUD 校验器。"""

import uuid

from fastapi import HTTPException
from sqlmodel import Session

from app.core import error_codes as ec
from app.core.spec.base import now
from app.core.spec.engine import Entity
from app.core.spec.errors import FieldError, MesError, fe
from app.core.spec.validate import validator
from app.mes.common.validators import Row, _get


@validator("lot_priority")
def _priority(
    _s: Session, _t: uuid.UUID, _e: Entity, row: Row, _old: Row | None
) -> None:
    if not 1 <= (row.get("level") or 0) <= 99:
        raise MesError(
            [fe("level", ec.FIELD_RANGE, "level: must be 1..99", min=1, max=99)]
        )


@validator("lot_type")
def _lot_type(
    s: Session, tid: uuid.UUID, _e: Entity, row: Row, _old: Row | None
) -> None:
    errs: list[FieldError] = []
    for k, target in (("lot_id_rule", "lot"), ("wafer_id_rule", "wafer")):
        r = _get(s, tid, "code_rule", row.get(f"{k}_id"))
        if r and r["target"] != target:
            errs.append(
                fe(
                    k,
                    ec.CODE_RULE_TARGET,
                    f"{k}: must be a code rule for {target} IDs",
                    target=target,
                )
            )
    if not 1 <= (row.get("max_wafers") or 0) <= 100000:
        errs.append(
            fe(
                "max_wafers",
                ec.FIELD_RANGE,
                "max_wafers: must be 1..100000",
                min=1,
                max=100000,
            )
        )
    if errs:
        raise MesError(errs)


@validator("split_merge_rule")
def _split_merge(
    _s: Session, _t: uuid.UUID, _e: Entity, row: Row, _old: Row | None
) -> None:
    errs: list[FieldError] = []
    if row.get("allow_split") and (row.get("max_children") or 0) < 2:
        errs.append(
            fe(
                "max_children",
                ec.MAX_CHILDREN_MIN,
                "max_children: must be >= 2 when splitting is allowed",
            )
        )
    if (row.get("min_wafers") or 0) < 1:
        errs.append(fe("min_wafers", ec.FIELD_MIN, "min_wafers: must be >= 1", min=1))
    if errs:
        raise MesError(errs)


@validator("qtime_rule:payload")
def _qtime_action(
    _s: Session, _t: uuid.UUID, _e: Entity, data: Row, _old: Row | None
) -> None:
    """D26：Q-Time 处置不再支持 scrap → 422 qtime_action_invalid。"""
    if data.get("action") == "scrap":
        raise HTTPException(
            status_code=422,
            detail={
                "code": ec.QTIME_ACTION_INVALID,
                "message": "Q-Time action 'scrap' is no longer supported; use hold or rework",
                "action": "scrap",
            },
        )


@validator("qtime_rule")
def _qtime(s: Session, tid: uuid.UUID, _e: Entity, row: Row, _old: Row | None) -> None:
    errs: list[FieldError] = []
    a, b = (
        _get(s, tid, "route_step", row.get("from_step_id")),
        _get(s, tid, "route_step", row.get("to_step_id")),
    )
    for k, st in (("from_step", a), ("to_step", b)):
        if st and st["route_id"] != row.get("route_id"):
            errs.append(
                fe(k, ec.STEP_OF_ROUTE, f"{k}: must be a step of the selected route")
            )
    if a and b and a["seq"] >= b["seq"]:
        errs.append(
            fe("to_step", ec.STEP_AFTER_FROM, "to_step: must come after from_step")
        )
    lo, hi = row.get("min_minutes"), row.get("max_minutes")
    if lo is None and hi is None:
        errs.append(
            fe(
                "max_minutes",
                ec.QTIME_NEED_TIME,
                "max_minutes: give a min and/or max time",
            )
        )
    if (lo is not None and lo < 0) or (hi is not None and hi <= 0):
        errs.append(
            fe(
                "max_minutes",
                ec.QTIME_TIME_POSITIVE,
                "max_minutes: times must be positive",
            )
        )
    if lo is not None and hi is not None and lo > hi:
        errs.append(
            fe(
                "max_minutes",
                ec.QTIME_MAX_GE_MIN,
                "max_minutes: must be >= min_minutes",
            )
        )
    # D24 补充：停用 → 启用时记启用时间，只对此后开始计时的批次生效（不追溯）
    if _old is not None and _old.get("is_active") is False and row.get("is_active"):
        row["active_since"] = now()
    if errs:
        raise MesError(errs)
