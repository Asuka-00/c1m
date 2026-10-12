"""Every MES entity/field/enum label exists in zh-CN/ja/en and the generated
frontend bundles are up to date."""

import pytest

from app.core.spec.engine import ENTITIES, ENUMS, MODULES, split_label
from app.mes.common.meta import LANGS
from scripts.export_mes_i18n import OUT, render


def test_labels_complete() -> None:
    for e in ENTITIES.values():
        assert all(split_label(e.label).values()), e.code
    for vals in ENUMS.values():
        for _, lbl in vals:
            assert all(split_label(lbl).values()), lbl
    for lbl, _ in MODULES.values():
        assert all(split_label(lbl).values())


@pytest.mark.skipif(not OUT.parent.exists(), reason="frontend not checked out")
@pytest.mark.parametrize("lang", LANGS)
def test_bundle_up_to_date(lang: str) -> None:
    assert (OUT / f"{lang}.json").read_text() == render(lang)
