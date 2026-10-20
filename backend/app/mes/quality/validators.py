"""质量实体的 CRUD 校验器。"""

import uuid

from sqlmodel import Session

from app.core import error_codes as ec
from app.core.spec.engine import Entity
from app.core.spec.errors import FieldError, MesError, fe
from app.core.spec.validate import validator
from app.mes.common.validators import Row


# ---------------- phase 4 ----------------
def _limits(row: Row) -> list[FieldError]:
    lsl, tgt, usl = row.get("lsl"), row.get("target"), row.get("usl")
    errs: list[FieldError] = []
    if lsl is not None and usl is not None and lsl > usl:
        errs.append(fe("usl", ec.USL_GE_LSL, "usl: must be >= LSL"))
    if tgt is not None and (
        (lsl is not None and tgt < lsl) or (usl is not None and tgt > usl)
    ):
        errs.append(
            fe("target", ec.TARGET_WITHIN_LIMITS, "target: must lie within LSL..USL")
        )
    return errs


@validator("dc_plan_item")
def _dc_item(
    _s: Session, _t: uuid.UUID, _e: Entity, row: Row, _old: Row | None
) -> None:
    errs = _limits(row)
    if (row.get("sites") or 0) < 1:
        errs.append(fe("sites", ec.FIELD_MIN, "sites: must be >= 1", min=1))
    if errs:
        raise MesError(errs)


@validator("sampling_rule")
def _sampling(
    _s: Session, _t: uuid.UUID, _e: Entity, row: Row, _old: Row | None
) -> None:
    errs: list[FieldError] = []
    if (row.get("lot_frequency") or 0) < 1:
        errs.append(
            fe("lot_frequency", ec.FIELD_MIN, "lot_frequency: must be >= 1", min=1)
        )
    if row.get("level") == "wafer":
        if not 1 <= (row.get("wafer_count") or 0) <= 25:
            errs.append(
                fe(
                    "wafer_count",
                    ec.WAFER_COUNT_RANGE,
                    "wafer_count: 1..25 for wafer-level sampling",
                )
            )
        if not row.get("wafer_selection"):
            errs.append(
                fe(
                    "wafer_selection",
                    ec.WAFER_SELECTION_REQUIRED,
                    "wafer_selection: required for wafer-level sampling",
                )
            )
    if row.get("wafer_selection") == "fixed":
        try:
            slots = [
                int(x) for x in (row.get("fixed_slots") or "").split(",") if x.strip()
            ]
        except ValueError:
            slots = []
        if not slots or any(not 1 <= x <= 25 for x in slots):
            errs.append(
                fe(
                    "fixed_slots",
                    ec.FIXED_SLOTS_FORMAT,
                    "fixed_slots: comma separated slots 1..25",
                )
            )
        elif row.get("wafer_count") and len(slots) != row["wafer_count"]:
            errs.append(
                fe(
                    "fixed_slots",
                    ec.FIXED_SLOTS_COUNT,
                    "fixed_slots: count must equal wafer_count",
                )
            )
    if errs:
        raise MesError(errs)
