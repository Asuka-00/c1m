"""MES 公共实体的 CRUD 校验器（含共享查找工具）。"""

import uuid
from typing import Any

import sqlalchemy as sa
from sqlmodel import Session

from app.core.spec.base import conn
from app.core.spec.engine import TABLES, Entity
from app.core.spec.errors import MesError, http_422
from app.core.spec.validate import validator
from app.mes.common.coderule import check_pattern

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


def reject_unwritable(e: Entity, data: Row) -> None:
    """P1 新增接口的严格载荷（bom.md §12）：系统字段 / 未知字段一律 422 ``unknown_field``（D65），不再静默忽略。

    可写键：非系统字段的字段名、列名（``<ref>_id``）及 ``attrs``。只用于 P1 新增实体，
    已有实体的通用增删改查保持原行为。
    """
    ok = {"attrs"}
    for f in e.all_fields:
        if not f.system:
            ok |= {f.name, f.column}
    bad = sorted(k for k in data if k not in ok)
    if bad:
        raise http_422([(k, f"{k}: unknown field", "unknown_field") for k in bad])
