import uuid

import sqlalchemy as sa
from sqlmodel import Session

from app.core.spec.base import conn
from app.core.spec.engine import TABLES, Entity
from app.core.spec.errors import MesError
from app.core.spec.validate import validator
from app.mes.common.validators import Row, _get


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


@validator("carrier_type")
def _carrier_type(
    _s: Session, _t: uuid.UUID, _e: Entity, row: Row, _old: Row | None
) -> None:
    if not 1 <= (row.get("capacity") or 0) <= 50:
        raise MesError([("capacity", "capacity: must be 1..50")])


@validator("product:activate")
def _product_activate(
    s: Session, tid: uuid.UUID, _e: Entity, row: Row, _old: Row | None
) -> None:
    """A product can go Active only with an Active route bound as default."""
    pr, rt = TABLES["product_route"], TABLES["route"]
    ok = (
        conn(s)
        .execute(
            sa.select(pr.c.id)
            .join(rt, rt.c.id == pr.c.route_id)
            .where(
                pr.c.tenant_id == tid,
                pr.c.product_id == row["id"],
                pr.c.is_default.is_(True),
                rt.c.status == "active",
            )
        )
        .first()
    )
    if not ok:
        raise MesError(
            [
                (
                    "product_route",
                    "product: needs an active route bound as default before activation",
                )
            ]
        )
