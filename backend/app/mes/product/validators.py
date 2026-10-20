"""产品实体的 CRUD 校验器。"""

import uuid

import sqlalchemy as sa
from sqlmodel import Session

from app.core import error_codes as ec
from app.core.spec.base import conn
from app.core.spec.engine import TABLES, Entity
from app.core.spec.errors import FieldError, MesError, fe
from app.core.spec.validate import validator
from app.mes.common.validators import Row, _get


@validator("uom_conversion")
def _uom_conv(
    s: Session, tid: uuid.UUID, _e: Entity, row: Row, _old: Row | None
) -> None:
    errs: list[FieldError] = []
    if row.get("from_uom_id") == row.get("to_uom_id"):
        errs.append(fe("to_uom", ec.UOM_DIFFERS, "to_uom: must differ from from_uom"))
    if (row.get("factor") or 0) <= 0:
        errs.append(fe("factor", ec.FIELD_GT, "factor: must be > 0", min=0))
    a, b = (
        _get(s, tid, "uom", row.get("from_uom_id")),
        _get(s, tid, "uom", row.get("to_uom_id")),
    )
    if a and b and a["dimension"] != b["dimension"]:
        errs.append(fe("to_uom", ec.UOM_DIMENSIONS, "to_uom: dimensions differ"))
    if errs:
        raise MesError(errs)


@validator("carrier_type")
def _carrier_type(
    _s: Session, _t: uuid.UUID, _e: Entity, row: Row, _old: Row | None
) -> None:
    if not 1 <= (row.get("capacity") or 0) <= 50:
        raise MesError(
            [fe("capacity", ec.FIELD_RANGE, "capacity: must be 1..50", min=1, max=50)]
        )


@validator("product:activate")
def _product_activate(
    s: Session, tid: uuid.UUID, _e: Entity, row: Row, _old: Row | None
) -> None:
    """产品仅在绑定了 Active 默认路线时才能激活。"""
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
                fe(
                    "product_route",
                    ec.PRODUCT_NEEDS_DEFAULT_ROUTE,
                    "product: needs an active route bound as default before activation",
                )
            ]
        )
