"""查询参数里的日期 / 时间（D77 补充一 / 二 / 三，统一错误格式）。

- date：只接受严格 ``YYYY-MM-DD``（且是真实日期）；其它任何写法（``2026/10/01``、
  带时间、``2026-02-30`` 等）→ 422 ``value_error``，``ctx.reason=pattern``。
- datetime：ISO 8601 且必须带偏移（``Z`` / ``±hh:mm``）；只给日期或无偏移 →
  422 ``timezone_required``；无法解析 → 422 ``value_error``，``ctx.reason=pattern``。
- 区间：两端格式都合法后再比较，``from > to`` → 422 ``value_error``，
  ``ctx.reason=range_inverted``，loc 指向 ``*_from``。
- loc 一律 ``["query", 参数名]``。
"""

import re
from datetime import date, datetime
from typing import Annotated, Any

from fastapi import Query

from app.core.spec.errors import err_422

DATE_PATTERN = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
_DATE_RE = re.compile(DATE_PATTERN)


def _pattern(name: str, raw: str, what: str) -> Exception:
    return err_422(
        ["query", name],
        f"{name}: expected {what}",
        "value_error",
        {"reason": "pattern"},
        input=raw,
    )


def parse_date(name: str, raw: str | None) -> date | None:
    """严格 ``YYYY-MM-DD``；空值返回 None。"""
    if raw is None or raw == "":
        return None
    if not _DATE_RE.fullmatch(raw):
        raise _pattern(name, raw, "YYYY-MM-DD")
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise _pattern(name, raw, "a valid date YYYY-MM-DD") from None


def parse_datetime(name: str, raw: str | None) -> datetime | None:
    """带偏移的 ISO 8601 时间；空值返回 None。"""
    if raw is None or raw == "":
        return None
    try:
        v = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        raise _pattern(name, raw, "ISO 8601 date-time with offset") from None
    if v.tzinfo is None:
        raise err_422(
            ["query", name],
            f"{name}: timezone offset required (Z or +hh:mm)",
            "timezone_required",
            input=raw,
        )
    return v


def check_range(from_name: str, a: Any, b: Any) -> None:
    """两端都有值且 ``a > b`` → 422 value_error / range_inverted（loc 指向 from）。"""
    if a is not None and b is not None and a > b:
        to_name = (
            from_name.removesuffix("from") + "to"
            if from_name.endswith("from")
            else "to"
        )
        raise err_422(
            ["query", from_name],
            f"{from_name} is after {to_name}",
            "value_error",
            {"reason": "range_inverted"},
        )


def date_query(alias: str | None = None) -> Any:
    """Openapi 声明 format=date + pattern；运行时按字符串收，由 :func:`parse_date` 校验。"""
    return Query(
        alias=alias,
        json_schema_extra={"format": "date", "pattern": DATE_PATTERN},
    )


def datetime_query(alias: str | None = None) -> Any:
    """OpenAPI 中声明 format=date-time；运行时由 :func:`parse_datetime` 校验。"""
    return Query(alias=alias, json_schema_extra={"format": "date-time"})


DateQ = Annotated[str | None, date_query()]
DateTimeQ = Annotated[str | None, datetime_query()]
