"""Backend-driven menus for MES entities: one top-level group per module."""

from app.mes.core import ENTITIES, GROUP_LABELS, MODULES, PAGES, perm

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
    "wo": "ClipboardList",
}
# special pages: key -> (module group, path, icon, component, order, permission)
PAGE_MENUS = {
    "mes-lot-start": (
        "wo",
        "/mes/lot-start",
        "PlayCircle",
        "mes-page:lot-start",
        5,
        "mes.lot:start",
    ),
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
                f"mes-g-{m}",
                None,
                GROUP_LABELS[m].split("|")[0]
                if m in GROUP_LABELS
                else f"MES · {lbl.split('|')[0]}",
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
                    f"mes-g-{m}",
                    e.label.split("|")[0],
                    f"/mes/{e.url}",
                    e.icon,
                    f"mes:{e.code}",
                    i * 10,
                    perm(e.pmod, "read"),
                )
            )
        for key, (pm, path, icon, comp, order, p) in PAGE_MENUS.items():
            if pm == m:
                out.append(
                    (
                        key,
                        f"mes-g-{m}",
                        PAGES[key].split("|")[0],
                        path,
                        icon,
                        comp,
                        order,
                        p,
                    )
                )
    return out
