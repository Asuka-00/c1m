"""执行相关实体的 CRUD 校验器。"""

import uuid
from typing import Any

from sqlmodel import Session

from app.core import error_codes as ec
from app.core.spec.engine import Entity
from app.core.spec.errors import MesError, fe
from app.core.spec.validate import validator
from app.mes.execution.checks import service as ck

Row = dict[str, Any]


# ---------------- CRUD validators ----------------
@validator("tool")
def _tool(_s: Session, _t: uuid.UUID, _e: Entity, row: Row, _o: Row | None) -> None:
    errs = []
    if (row.get("usage_count") or 0) < 0:
        errs.append(fe("usage_count", ec.FIELD_MIN, "usage_count: must be >= 0", min=0))
    if row.get("max_usage") is not None and row["max_usage"] < 1:
        errs.append(fe("max_usage", ec.FIELD_MIN, "max_usage: must be >= 1", min=1))
    if row.get("warn_pct") is not None and not 1 <= row["warn_pct"] <= 100:
        errs.append(
            fe("warn_pct", ec.FIELD_RANGE, "warn_pct: must be 1..100", min=1, max=100)
        )
    if errs:
        raise MesError(errs)


@validator("material_lot")
def _material_lot(
    _s: Session, _t: uuid.UUID, _e: Entity, row: Row, _o: Row | None
) -> None:
    if (row.get("qty_remaining") or 0) < 0:
        raise MesError(
            [fe("qty_remaining", ec.FIELD_MIN, "qty_remaining: must be >= 0", min=0)]
        )
    if row.get("initial_qty") is None:
        row["initial_qty"] = row.get("qty_remaining")


@validator("check_rule")
def _check_rule(
    _s: Session, _t: uuid.UUID, _e: Entity, row: Row, _o: Row | None
) -> None:
    if row.get("check_type") not in ck.CHECKS:
        raise MesError(
            [
                fe(
                    "check_type",
                    ec.CHECK_TYPE_NOT_IMPLEMENTED,
                    "check_type: not implemented",
                )
            ]
        )
    p = row.get("params")
    if p is not None and not isinstance(p, dict):
        raise MesError(
            [fe("params", ec.MUST_BE_JSON_OBJECT, "params: must be a JSON object")]
        )


@validator("check_binding")
def _check_binding(
    _s: Session, _t: uuid.UUID, _e: Entity, row: Row, _o: Row | None
) -> None:
    for sc in ck.SPECIFICITY:  # 只保留与作用域对应的引用字段
        if sc != row.get("scope"):
            row[f"{sc}_id"] = None
