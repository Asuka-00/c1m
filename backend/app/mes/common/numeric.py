"""numeric(18,6) 请求体字段校验（光罩 / 工具 / EAP 接口共用）。

D71-5：超过 6 位小数时 422 ``value_error``，``ctx`` 带 ``max_places=6``。
"""

from decimal import Decimal

from pydantic_core import PydanticCustomError

MAX_PLACES = 6


def six(v: Decimal) -> Decimal:
    """最多 6 位小数、有限、绝对值小于 1e12。"""
    if not v.is_finite():
        raise ValueError("must be a finite number")
    if v.as_tuple().exponent < -MAX_PLACES:  # type: ignore[operator]
        raise PydanticCustomError(
            "value_error",
            "Value error, at most {max_places} decimal places",
            {"max_places": MAX_PLACES},
        )
    if abs(v) >= Decimal(10) ** 12:
        raise ValueError("out of range")
    return v
