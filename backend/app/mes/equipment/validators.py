import uuid

import sqlalchemy as sa
from sqlmodel import Session

from app.core.spec.base import conn
from app.core.spec.engine import TABLES, Entity
from app.core.spec.errors import MesError
from app.core.spec.validate import validator
from app.mes.common.validators import Row, _get
from app.mes.process.validators import _type_match


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
    if parent:  # sub-units inherit the parent's equipment type
        pt, cur = parent["equipment_type_id"], row.get("equipment_type_id")
        if cur is None:
            row["equipment_type_id"] = pt
        elif pt is not None and cur != pt:
            raise MesError(
                [
                    (
                        "equipment_type",
                        "equipment_type: must match the parent equipment's type",
                    )
                ]
            )


@validator("equipment_capability")
def _capability(
    s: Session, tid: uuid.UUID, _e: Entity, row: Row, _old: Row | None
) -> None:
    _type_match(s, tid, row.get("recipe_id"), row.get("equipment_id"))
