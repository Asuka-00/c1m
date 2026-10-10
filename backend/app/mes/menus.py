"""Backend-driven menus for MES entities: one top-level group per module."""

from app.mes.core import ENTITIES, MODULES, perm

MenuTuple = tuple[
    str, str | None, str, str | None, str | None, str | None, int, str | None
]

MODULE_ICONS = {
    "common": "Wrench",
    "org": "Factory",
    "equipment": "Cpu",
    "product": "Package",
    "process": "Workflow",
    "quality": "BadgeCheck",
    "lot": "Layers",
}


def mes_menus() -> list[MenuTuple]:
    out: list[MenuTuple] = []
    for m, (lbl, order) in MODULES.items():
        ents = [
            e
            for e in ENTITIES.values()
            if e.module == m and not e.internal and not e.parent
        ]
        if not ents:
            continue
        out.append(
            (
                f"mes-{m}",
                None,
                f"MES · {lbl.split('|')[0]}",
                None,
                MODULE_ICONS[m],
                None,
                100 + order,
                None,
            )
        )
        for i, e in enumerate(sorted(ents, key=lambda x: x.order)):
            out.append(
                (
                    f"mes-{e.code}",
                    f"mes-{m}",
                    e.label.split("|")[0],
                    f"/mes/{e.url}",
                    e.icon,
                    f"mes:{e.code}",
                    i * 10,
                    perm(m, "read"),
                )
            )
    return out
