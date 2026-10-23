"""设备实体的 CRUD 校验器。"""

import uuid
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from sqlmodel import Session

from app.core import error_codes as ec
from app.core.spec.base import conn
from app.core.spec.engine import TABLES, Entity
from app.core.spec.errors import MesError, fe
from app.core.spec.validate import validator
from app.mes.common.validators import Row, _get
from app.mes.equipment.maint import downtime_notify


def check_recipe_equipment_type(
    s: Session, tid: uuid.UUID, recipe_id: Any, equipment_id: Any
) -> None:
    """校验配方适用的设备类型与设备一致。

    Raises:
        HTTPException: 类型不匹配（422）。
    """
    rec, eqp = (
        _get(s, tid, "recipe", recipe_id),
        _get(s, tid, "equipment", equipment_id),
    )
    if (
        rec
        and eqp
        and rec["equipment_type_id"]
        and eqp["equipment_type_id"]
        and rec["equipment_type_id"] != eqp["equipment_type_id"]
    ):
        raise MesError(
            [
                fe(
                    "equipment",
                    ec.EQ_TYPE_DIFFERS_RECIPE,
                    "equipment: type differs from the recipe's equipment type",
                )
            ]
        )


@validator("e10_transition")
def _e10_tr(_s: Session, _t: uuid.UUID, _e: Entity, row: Row, _old: Row | None) -> None:
    if row.get("from_state_id") == row.get("to_state_id"):
        raise MesError(
            [
                fe(
                    "to_state",
                    ec.E10_TO_STATE_DIFFERS,
                    "to_state: must differ from from_state",
                )
            ]
        )


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
                [
                    fe(
                        "is_initial",
                        ec.INITIAL_STATE_EXISTS,
                        f"is_initial: {other} is already the initial state",
                        other=other,
                    )
                ]
            )


@validator("equipment")
def _equipment(
    s: Session, tid: uuid.UUID, _e: Entity, row: Row, _old: Row | None
) -> None:
    kind, parent = row.get("unit_kind"), _get(s, tid, "equipment", row.get("parent_id"))
    if kind == "main" and parent:
        raise MesError(
            [
                fe(
                    "parent",
                    ec.EQ_MAIN_NO_PARENT,
                    "parent: main equipment cannot have a parent",
                )
            ]
        )
    if kind != "main" and not parent:
        raise MesError(
            [
                fe(
                    "parent",
                    ec.EQ_NEEDS_PARENT,
                    f"parent: a {kind} needs a parent equipment",
                    kind=kind,
                )
            ]
        )
    if parent and parent["unit_kind"] not in ("main", "sub_unit"):
        raise MesError(
            [
                fe(
                    "parent",
                    ec.EQ_PARENT_KIND,
                    "parent: must be a main equipment or sub-unit",
                )
            ]
        )
    if parent:  # 子设备继承父设备的设备类型
        pt, cur = parent["equipment_type_id"], row.get("equipment_type_id")
        if cur is None:
            row["equipment_type_id"] = pt
        elif pt is not None and cur != pt:
            raise MesError(
                [
                    fe(
                        "equipment_type",
                        ec.PARENT_TYPE_MISMATCH,
                        "equipment_type: must match the parent equipment's type",
                    )
                ]
            )


@validator("equipment_capability")
def _capability(
    s: Session, tid: uuid.UUID, _e: Entity, row: Row, _old: Row | None
) -> None:
    check_recipe_equipment_type(s, tid, row.get("recipe_id"), row.get("equipment_id"))


@validator("pm_plan")
def _pm_plan(
    _s: Session, _t: uuid.UUID, _e: Entity, row: Row, _old: Row | None
) -> None:
    """PM 计划：须指定设备或设备类型，且至少一种周期（天数 / 批次数）。"""
    if not row.get("equipment_id") and not row.get("equipment_type_id"):
        raise MesError(
            [
                fe(
                    "equipment",
                    ec.PM_TARGET_REQUIRED,
                    "equipment: set equipment or equipment type",
                )
            ]
        )
    if not row.get("interval_days") and not row.get("interval_lots"):
        raise MesError(
            [
                fe(
                    "interval_days",
                    ec.PM_INTERVAL_REQUIRED,
                    "interval_days: set days or lots interval",
                )
            ]
        )
    for f in ("interval_days", "interval_lots"):
        if row.get(f) is not None and row[f] <= 0:
            raise MesError([fe(f, ec.FIELD_GT, f"{f}: must be > 0", min=0)])


@validator("downtime")
def _downtime(
    s: Session, tid: uuid.UUID, _e: Entity, row: Row, old: Row | None
) -> None:
    """停机记录：结束时间须晚于开始时间；新建时发送停机通知（与记录同事务）。"""
    a, b = row.get("start_at"), row.get("end_at")
    if a and b and b <= a:
        raise MesError(
            [fe("end_at", ec.END_AFTER_START, "end_at: must be after start_at")]
        )
    if old is None:
        downtime_notify(s, tid, row)


@validator("equipment_material_mount")
def _mount(s: Session, tid: uuid.UUID, _e: Entity, row: Row, old: Row | None) -> None:
    """上料记录：卸料晚于上料；物料批可用；同一机台上料位同一时间只装一批。"""
    # 无时区的输入按 UTC 处理，才能与库里的 timestamptz 比较
    a, b = (
        d.replace(tzinfo=d.tzinfo or UTC) if d else d
        for d in (row.get("mounted_at"), row.get("unmounted_at"))
    )
    if a and b and b <= a:
        raise MesError(
            [
                fe(
                    "unmounted_at",
                    ec.END_AFTER_START,
                    "unmounted_at: must be after mounted_at",
                )
            ]
        )
    if not a:  # 必填缺失由通用校验报错
        return
    lot = _get(s, tid, "material_lot", row.get("material_lot_id"))
    # 只在新增 / 换批时检查可用性，历史记录不受物料批后续状态影响
    if lot and (old is None or old["material_lot_id"] != lot["id"]):
        if lot["ml_status"] != "available":
            raise MesError(
                [
                    fe(
                        "material_lot",
                        ec.MATERIAL_LOT_UNAVAILABLE,
                        f"material_lot: {lot['code']} is not available",
                        lot=lot["code"],
                    )
                ]
            )
    t = TABLES["equipment_material_mount"]
    far = datetime.max.replace(tzinfo=UTC)
    for o in (
        conn(s)
        .execute(
            sa.select(t).where(
                t.c.tenant_id == tid,
                t.c.equipment_id == row.get("equipment_id"),
                t.c.position == row.get("position"),
                t.c.id != (old["id"] if old else uuid.UUID(int=0)),
            )
        )
        .mappings()
    ):
        # 区间重叠（未卸料视为无穷远）
        if o["mounted_at"] < (b or far) and (o["unmounted_at"] or far) > a:
            raise MesError(
                [
                    fe(
                        "position",
                        ec.MOUNT_POSITION_BUSY,
                        f"position: {row['position']} already holds a material lot",
                        position=row["position"],
                    )
                ]
            )
