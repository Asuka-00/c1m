"""执行相关实体的 CRUD 校验器。"""

import uuid
from typing import Any

from sqlmodel import Session

from app.core.spec.engine import Entity
from app.core.spec.errors import MesError
from app.core.spec.validate import validator
from app.mes.execution.checks import service as ck

Row = dict[str, Any]


# ---------------- CRUD validators ----------------
@validator("tool")
def _tool(_s: Session, _t: uuid.UUID, _e: Entity, row: Row, _o: Row | None) -> None:
    errs = []
    if (row.get("usage_count") or 0) < 0:
        errs.append(("usage_count", "usage_count: must be >= 0"))
    if row.get("max_usage") is not None and row["max_usage"] < 1:
        errs.append(("max_usage", "max_usage: must be >= 1"))
    if row.get("warn_pct") is not None and not 1 <= row["warn_pct"] <= 100:
        errs.append(("warn_pct", "warn_pct: must be 1..100"))
    if errs:
        raise MesError(errs)


@validator("material_lot")
def _material_lot(
    _s: Session, _t: uuid.UUID, _e: Entity, row: Row, _o: Row | None
) -> None:
    if (row.get("qty_remaining") or 0) < 0:
        raise MesError([("qty_remaining", "qty_remaining: must be >= 0")])
    if row.get("initial_qty") is None:
        row["initial_qty"] = row.get("qty_remaining")


@validator("check_rule")
def _check_rule(
    _s: Session, _t: uuid.UUID, _e: Entity, row: Row, _o: Row | None
) -> None:
    if row.get("check_type") not in ck.CHECKS:
        raise MesError([("check_type", "check_type: not implemented")])
    p = row.get("params")
    if p is not None and not isinstance(p, dict):
        raise MesError([("params", "params: must be a JSON object")])


@validator("check_binding")
def _check_binding(
    _s: Session, _t: uuid.UUID, _e: Entity, row: Row, _o: Row | None
) -> None:
    for sc in ck.SPECIFICITY:  # 只保留与作用域对应的引用字段
        if sc != row.get("scope"):
            row[f"{sc}_id"] = None
