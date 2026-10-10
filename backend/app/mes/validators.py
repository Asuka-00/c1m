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
