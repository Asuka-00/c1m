"""载具使用计数与清洗到期（检查与作业共用）。"""

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlmodel import Session

from app.mes.common.query import one
from app.mes.common.rows import _upd

Row = dict[str, Any]


def clean_due(s: Session, tid: uuid.UUID, car: Row) -> datetime | None:
    """载具下次清洗到期时间（载具类型未设清洗周期时为 None）。"""
    ct = one(s, tid, "carrier_type", car["carrier_type_id"])
    days = (ct or {}).get("clean_interval_days")
    if not days:
        return None
    base: datetime = car.get("last_cleaned_at") or car["created_at"]
    return base + timedelta(days=int(days))


def count_use(s: Session, tid: uuid.UUID, carrier_id: Any, user: Any) -> None:
    """Track In 时载具使用次数 +1。"""
    car = one(s, tid, "carrier", carrier_id) if carrier_id else None
    if car:
        _upd(s, tid, "carrier", car["id"], user, use_count=(car["use_count"] or 0) + 1)
