"""站点日期：有效期类判断里的「今天」按站点时区取（D74 第 7 条），与 D54 导出共用时区来源。"""

import uuid
from datetime import UTC, date, datetime

from sqlmodel import Session

from app.core.spec.excel import tenant_tz


def site_today(s: Session, tid: uuid.UUID, at: datetime | None = None) -> date:
    """返回 ``at``（默认当前 UTC 时间）在站点时区下的日期；无时区的 ``at`` 按 UTC 处理。"""
    t = at or datetime.now(UTC)
    if t.tzinfo is None:
        t = t.replace(tzinfo=UTC)
    return t.astimezone(tenant_tz(s, tid)).date()
