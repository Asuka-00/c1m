"""D60：定点字段（scale）超出小数位一律 too_many_decimals，不舍入。"""

from decimal import Decimal

import pytest

from app.core.spec.engine import F
from app.core.spec.serialize import TooManyDecimals, coerce


@pytest.mark.parametrize("v", ["1.1234567", "0.0000001", 1.1234567, "1e-7"])
def test_scale6_too_many_decimals(v: object) -> None:
    with pytest.raises(TooManyDecimals) as ex:
        coerce(F("q", "float", "Q", scale=6), v)
    assert ex.value.code == "too_many_decimals"


@pytest.mark.parametrize(
    ("v", "out"),
    [("1.123456", "1.123456"), ("1.1234560", "1.123456"), (2, "2"), ("1E+3", "1000")],
)
def test_scale6_ok_no_rounding(v: object, out: str) -> None:
    assert coerce(F("q", "float", "Q", scale=6), v) == Decimal(out)


def test_scale4() -> None:
    f = F("r", "float", "R", scale=4)
    assert coerce(f, "0.1234") == Decimal("0.1234")
    with pytest.raises(TooManyDecimals):
        coerce(f, "0.12345")
