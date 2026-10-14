"""站点日期：有效期类判断里的「今天」按站点时区取（D74 第 7 条），与 D54 导出共用时区来源。"""

import uuid
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlmodel import Session

from app.core.spec.excel import DEFAULT_TZ, tenant_tz


def site_today(s: Session, tid: uuid.UUID, at: datetime | None = None) -> date:
    """返回 ``at``（默认当前 UTC 时间）在站点时区下的日期；无时区的 ``at`` 按 UTC 处理。"""
    t = at or datetime.now(UTC)
    if t.tzinfo is None:
        t = t.replace(tzinfo=UTC)
    return t.astimezone(tenant_tz(s, tid)).date()


def site_day_bounds(
    s: Session, tid: uuid.UUID, day: date, days: int = 1
) -> tuple[datetime, datetime]:
    """站点时区下 ``day`` 起 ``days`` 天的半开区间 [当日 00:00, 末日次日 00:00)，转为 UTC。"""
    tz = tenant_tz(s, tid)
    a = datetime.combine(day, time.min, tz)
    b = datetime.combine(day + timedelta(days=days), time.min, tz)
    return a.astimezone(UTC), b.astimezone(UTC)


def default_today() -> date:
    """默认站点时区（Asia/Taipei）下的今天：仅用于还没有租户 / 会话的模块级演示数据。"""
    return datetime.now(ZoneInfo(DEFAULT_TZ)).date()
