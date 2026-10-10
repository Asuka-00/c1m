"""Entity-specific validation rules (registered with @validator)."""

import uuid
from typing import Any

from sqlmodel import Session

from app.mes.coderule import check_pattern
from app.mes.core import Entity
from app.mes.service import MesError, validator

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
