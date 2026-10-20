"""工厂实体的 CRUD 校验器。"""

import uuid

from sqlmodel import Session

from app.core import error_codes as ec
from app.core.spec.engine import Entity
from app.core.spec.errors import MesError, fe
from app.core.spec.validate import validator
from app.mes.common.validators import Row


@validator("shift")
def _shift(_s: Session, _t: uuid.UUID, _e: Entity, row: Row, _old: Row | None) -> None:
    st, en = row.get("start_time"), row.get("end_time")
    if st and en:
        if st == en:
            raise MesError(
                [
                    fe(
                        "end_time",
                        ec.END_TIME_DIFFERS,
                        "end_time: must differ from start_time",
                    )
                ]
            )
        if (en < st) != bool(row.get("crosses_midnight")):
            raise MesError(
                [
                    fe(
                        "crosses_midnight",
                        ec.CROSSES_MIDNIGHT,
                        "crosses_midnight: must be set iff end is before start",
                    )
                ]
            )


@validator("work_calendar")
def _calendar(
    _s: Session, _t: uuid.UUID, _e: Entity, row: Row, _old: Row | None
) -> None:
    if not 2000 <= (row.get("year") or 0) <= 2100:
        raise MesError(
            [fe("year", ec.FIELD_RANGE, "year: must be 2000..2100", min=2000, max=2100)]
        )
