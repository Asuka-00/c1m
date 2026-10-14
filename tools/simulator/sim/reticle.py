"""P3 光罩补录时间本地预校验（D82 第 4 点 + D82 续）：只做提示，以后端为准。

适用字段：mount 的 ``mounted_at``、incident 的 ``occurred_at``、unmount 的 ``unmounted_at``（后端 D80 提交一并覆盖）。
都可选，不传由后端取当前时间。按 D81 顺序分两段：

- body 阶段（先于 404）：不带时区 → 422 ``timezone_required``；比服务器当前时间晚 **超过** 5 分钟 →
  422 ``value_error`` ctx.reason=future_time（正好 5:00 放行）
- 业务阶段（404 之后）：早于该光罩最近一次下机/事件时间 → 409 ``time_out_of_order``；
  ``unmounted_at`` 早于对应那次 ``mounted_at`` 也是 409，相等合法

D82 续二（03:19）：
- 时间先后基准 = 状态履历与历次下机时间中最晚者，usage / 检查记录不计（mount / unmount）；
- incident 的基准额外计入最近一次 usage：occurred_at 早于最近 usage → 409 ``time_out_of_order``；
- incident 顺带下机：带 occurred_at 用它作下机时间，否则服务器当前时间；
  occurred_at 早于当前这次 mounted_at → 整体 409（不入库、不 Hold、不下机、不发事件）。
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

BACKFILL_FIELDS = {"mount": "mounted_at", "incident": "occurred_at", "unmount": "unmounted_at"}
FUTURE_TOLERANCE = timedelta(minutes=5)
TIMEZONE_REQUIRED = {"type": "timezone_required"}
FUTURE_TIME = {"type": "value_error", "ctx": {"reason": "future_time"}}
TIME_OUT_OF_ORDER = {"status": 409, "code": "time_out_of_order"}

_REL = re.compile(r"\$now([+-])(\d+)([smh])")


def resolve_relative(value: Any, now: datetime) -> Any:
    """场景里的相对时间 ``$now+299s`` / ``$now-1h`` → 带 Z 的 ISO 串；其他原样返回。"""
    if not isinstance(value, str):
        return value
    m = _REL.fullmatch(value)
    if m is None:
        return value
    sign, n, unit = m.groups()
    delta = timedelta(**{{"s": "seconds", "m": "minutes", "h": "hours"}[unit]: int(n)})
    t = now + delta if sign == "+" else now - delta
    return t.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def check_backfill_time(value: Any, now: datetime) -> list[dict[str, Any]]:
    """body 阶段：None/未传放行；非法串 datetime_parsing；无时区 timezone_required；> now+5min future_time。"""
    if value is None:
        return []
    if not isinstance(value, str) or (t := _parse(value)) is None:
        return [{"type": "datetime_parsing"}]
    if t.tzinfo is None or t.utcoffset() is None:
        return [TIMEZONE_REQUIRED]
    if t - now > FUTURE_TOLERANCE:
        return [FUTURE_TIME]
    return []


def check_time_order(value: datetime, floor: datetime | None) -> dict[str, Any] | None:
    """业务阶段：value 早于 floor（最近一次下机/事件，或对应 mounted_at）→ 409；相等合法。"""
    if floor is not None and value < floor:
        return TIME_OUT_OF_ORDER
    return None


def time_floor(
    kind: str,
    status_times: list[datetime] = (),  # type: ignore[assignment]
    unmount_times: list[datetime] = (),  # type: ignore[assignment]
    usage_times: list[datetime] = (),  # type: ignore[assignment]
) -> datetime | None:
    """D82 续二：先后基准。mount/unmount = max(状态履历, 历次下机)；incident 另加最近一次 usage。检查记录永不计入。"""
    pool = [*status_times, *unmount_times]
    if kind == "incident":
        pool += list(usage_times)
    return max(pool, default=None)


def check_incident(occurred: datetime, floor: datetime | None, mounted_at: datetime | None) -> dict[str, Any] | None:
    """incident 业务阶段：早于基准（含最近 usage）或早于当前这次 mounted_at → 整体 409；相等合法。"""
    return check_time_order(occurred, floor) or check_time_order(occurred, mounted_at)


def incident_unmount_time(occurred: datetime | None, now: datetime) -> datetime:
    """incident 顺带下机的下机时间：带了 occurred_at 用它，否则服务器当前时间。"""
    return occurred if occurred is not None else now
