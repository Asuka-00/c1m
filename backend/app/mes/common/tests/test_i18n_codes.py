"""前端语言包需要翻译的 code 清单（frontend/src/i18n/backend-codes.json）与后端一致。"""

import pytest

from scripts.export_i18n_codes import OUT, TS_OUT, codes, render, render_ts


def test_codes_cover_specs() -> None:
    keys = set(codes())
    assert "mes.entity.lot" in keys and "mes.field.lot.code" in keys
    assert "mes.enum.lot_status.waiting" in keys
    assert "menu.mes-lot-console" in keys and "permName.mes_lot__read" in keys
    assert "error.code_100001" in keys and "error.code_700022" in keys
    assert not any("|" in k for k in keys)


@pytest.mark.skipif(not OUT.parent.exists(), reason="frontend not checked out")
def test_codes_file_up_to_date() -> None:
    assert OUT.read_text(encoding="utf-8") == render()
    assert TS_OUT.read_text(encoding="utf-8") == render_ts()
