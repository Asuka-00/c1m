"""按 bin 拆批（B8，bom-p1-tasks B8 / bom.md §12）。

复用 B5 的单位转换事件（transform_type=bin_split）：整批拆，母批 → converted。

- 每片晶圆的各 bin 数量：有坐标图取其 bin 数量（优先关联到本批次的版本，D39 lot_id），
  这时不允许人工录入；没有坐标图时必须人工录入各 bin 数量并填原因码，合计须等于产品
  gross die（输入良品 + 不良），否则 422 ``bin_split_qty_mismatch``；
- 排除类 bin 由定义集的 ``bin_type`` 决定（不写死 bin 码），不进子批；
- 守恒：坐标图晶圆调 B4 :func:`check_split`（子批合计 + 排除 = 坐标总数）；
- 子批：默认每个 bin 一个子批，也可用 ``outputs`` 把几个 bin 合成一个子批；子批带
  ``bin_code``，继承客户字段；不给 ``route_id`` 时留在母批当前工步，给了从该路线首工步开始；
- 位置映射：坐标图晶圆每颗 die 一行 ``unit_origin``（坐标 + bin 码）。
- 事件的输入行记下所用坐标图版本 id、bin 定义集与版本号、各 bin 数量。
"""

import uuid
from collections import defaultdict
from typing import Any

from sqlmodel import Session

from app.core.spec.errors import http_422
from app.mes.common.query import one
from app.mes.execution.transform import _qty_error, check_lots, execute
from app.mes.lot.service import lock_lots, units
from app.mes.map import service as map_svc
from app.mes.map.specs import EXCLUDED_BIN_TYPES, GOOD_BIN_TYPES

Row = dict[str, Any]


def _bin_key(code: str) -> tuple[int, Any]:
    return (0, int(code)) if code.isdigit() else (1, code)


def _plan(s: Session, tid: uuid.UUID, body: Row) -> Row:
    errs: list[tuple[Any, str]] = []
    lots = check_lots(s, tid, body)
    first = lots[0]
    manual = {
        m["wafer_id"]: (j, m) for j, m in enumerate(body.get("manual_bins") or [])
    }
    wafers: dict[Any, Row] = {}
    for i, lot in enumerate(lots):
        ws = [u for u in units(s, tid, lot["id"]) if u["unit_kind"] == "wafer"]
        if not ws:
            errs.append(
                (("input_lot_ids", i), f"{lot['code']}: no wafer units to split")
            )
        for w in ws:
            m = map_svc.map_for_wafer(s, tid, w["code"], lot["id"])
            mg = manual.pop(w["id"], None)
            info: Row = {"wafer": w, "lot": lot, "map": m}
            if m:
                if mg:
                    errs.append(
                        (
                            ("manual_bins", mg[0], "wafer_id"),
                            f"{w['code']}: has a substrate map; manual bins not allowed",
                        )
                    )
                types = map_svc.bin_types(s, tid, m["bin_set_id"])
                bs = one(s, tid, "bin_set", m["bin_set_id"]) or {}
                counts = {str(k): int(v) for k, v in (m["bin_counts"] or {}).items()}
                split = {
                    b: n
                    for b, n in counts.items()
                    if n > 0 and types.get(b) not in EXCLUDED_BIN_TYPES
                }
                excluded = sum(counts.values()) - sum(split.values())
                good = sum(
                    n for b, n in split.items() if types.get(b) in GOOD_BIN_TYPES
                )
                info |= {
                    "total": m["total_qty"],
                    "excluded": excluded,
                    "split": split,
                    "good": good,
                    "fail": sum(split.values()) - good,
                    "source": "map",
                    "bin_set_id": m["bin_set_id"],
                    "bin_set_code": bs.get("code"),
                    "bin_set_version": bs.get("version"),
                    "bin_counts": counts,
                }
            elif mg:
                j, entry = mg
                split = defaultdict(int)
                for k, b in enumerate(entry["bins"]):
                    if b["bin_code"] in split:
                        errs.append(
                            (("manual_bins", j, "bins", k, "bin_code"), "duplicate bin")
                        )
                    split[b["bin_code"]] += b["qty"]
                prod = one(s, tid, "product", lot["product_id"]) or {}
                gd = prod.get("gross_die")
                tot = sum(split.values())
                if not gd:
                    errs.append(
                        (
                            ("manual_bins", j, "wafer_id"),
                            f"{w['code']}: product has no gross die to check bins against",
                        )
                    )
                elif tot != gd:
                    raise _qty_error(
                        "bin_split_qty_mismatch",
                        f"{w['code']}: bins total {tot} != good + fail {gd}",
                        wafer=w["code"],
                        bins_qty=tot,
                        expected_qty=gd,
                        loc=["body", "manual_bins", j, "bins"],
                    )
                split = {b: n for b, n in split.items() if n > 0}
                info |= {
                    "total": tot,
                    "excluded": 0,
                    "split": split,
                    "good": None,
                    "fail": None,
                    "source": "manual",
                    "bin_counts": dict(split),
                }
            else:
                errs.append(
                    (
                        ("manual_bins",),
                        f"{w['code']}: no substrate map; enter bin quantities with a reason",
                    )
                )
                continue
            wafers[w["id"]] = info
    for wid, (j, _m) in manual.items():
        errs.append(
            (("manual_bins", j, "wafer_id"), f"wafer {wid} is not an input wafer")
        )
    if any(x["source"] == "manual" for x in wafers.values()) and not body.get(
        "reason_id"
    ):
        errs.append((("reason_id",), "reason required for manual bin quantities"))
    if body.get("reason_id") and not one(s, tid, "reason_code", body["reason_id"]):
        errs.append((("reason_id",), "reason not found"))
    if errs:
        raise http_422(errs)
    # 守恒：子批合计 + 排除 = 坐标图总数（坐标图晶圆）
    for x in wafers.values():
        if x["map"]:
            map_svc.check_split(x["map"], sum(x["split"].values()))
    present = sorted({b for x in wafers.values() for b in x["split"]}, key=_bin_key)
    # 输出分组
    groups = body.get("outputs") or [{"bin_codes": [b]} for b in present]
    owner: dict[str, int] = {}
    outs: list[Row] = []
    same_step = len({(lt["route_id"], lt["current_step_id"]) for lt in lots}) == 1
    for k, g in enumerate(groups):
        for j, b in enumerate(g["bin_codes"]):
            if b in owner:
                errs.append(
                    (("outputs", k, "bin_codes", j), f"bin {b} already in an output")
                )
            elif b not in present:
                errs.append(
                    (("outputs", k, "bin_codes", j), f"bin {b} has no dies to split")
                )
            owner.setdefault(b, k)
        pid = g.get("product_id") or first["product_id"]
        if g.get("product_id") and not one(s, tid, "product", pid):
            errs.append((("outputs", k, "product_id"), "product not found"))
        rid = g.get("route_id")
        if rid and not one(s, tid, "route", rid):
            errs.append((("outputs", k, "route_id"), "route not found"))
        if not rid and not same_step:
            errs.append(
                (
                    ("outputs", k, "route_id"),
                    "input lots are at different steps; route required",
                )
            )
        codes = [b for b in g["bin_codes"] if b in present]
        qty = sum(x["split"].get(b, 0) for x in wafers.values() for b in codes)
        outs.append(
            {
                "bin_codes": codes,
                "bin_code": ",".join(codes),
                "product_id": pid,
                "route_id": rid,
                "track_unit_kind": "die",
                "qty": qty,
                "die_qty": qty,
            }
        )
    if errs:
        raise http_422(errs)
    missing = [b for b in present if b not in owner]
    if missing:
        raise _qty_error(
            "bin_split_unassigned",
            f"bins not assigned to any output: {', '.join(missing)}",
            bin_codes=missing,
        )
    return {"lots": lots, "wafers": wafers, "outputs": outs, "warnings": []}


def _brief(p: Row) -> Row:
    return {
        "inputs": [
            {
                "lot": x["lot"]["code"],
                "wafer": x["wafer"]["code"],
                "wafer_id": str(x["wafer"]["id"]),
                "bin_source": x["source"],
                "substrate_map_id": x["map"] and str(x["map"]["id"]),
                "map_version": x["map"] and x["map"]["map_version"],
                "bin_set": x["map"]
                and {"code": x["bin_set_code"], "version": x["bin_set_version"]},
                "total_qty": x["total"],
                "excluded_qty": x["excluded"],
                "bin_counts": x["bin_counts"],
                "split_counts": x["split"],
                "children_qty": sum(x["split"].values()),
                "conserved": sum(x["split"].values()) + x["excluded"] == x["total"],
            }
            for x in p["wafers"].values()
        ],
        "outputs": [
            {
                "bin_code": o["bin_code"],
                "bin_codes": o["bin_codes"],
                "product_id": str(o["product_id"]),
                "route_id": o["route_id"] and str(o["route_id"]),
                "qty": o["qty"],
            }
            for o in p["outputs"]
        ],
        "warnings": p["warnings"],
    }


def preview(s: Session, tid: uuid.UUID, body: Row) -> Row:
    """校验按 bin 拆批方案：逐片晶圆的各 bin 数量与守恒、各子批数量（不写库）。"""
    return _brief(_plan(s, tid, body))


def _alloc(s: Session, tid: uuid.UUID, p: Row) -> None:
    cells = {
        wid: (map_svc.all_cells(s, tid, x["map"]) if x["map"] else None)
        for wid, x in p["wafers"].items()
    }
    for o in p["outputs"]:
        want = set(o["bin_codes"])
        o["alloc"] = []
        for wid, x in p["wafers"].items():
            n = sum(x["split"].get(b, 0) for b in want)
            if not n:
                continue
            cs = cells[wid]
            coords = (
                [(r, c, b) for r, c, b in cs if b in want] if cs is not None else None
            )
            o["alloc"].append((x, n, coords))


def bin_split(s: Session, tid: uuid.UUID, body: Row, user: Any) -> Row:
    """执行按 bin 拆批，返回转换事件、子批（带 bin_code）、客户信息与提示。"""
    _plan(s, tid, body)
    lock_lots(s, tid, body["input_lot_ids"])
    p = _plan(s, tid, body)
    _alloc(s, tid, p)
    return execute(s, tid, {**body, "transform_type": "bin_split"}, user, p)
