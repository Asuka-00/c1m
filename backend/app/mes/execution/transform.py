"""单位转换与谱系（B5，bom.md §7.5 / §10）。

整批转换（不支持部分转换）：输入批次的全部晶圆都要分配；支持多入多出。

- 每片晶圆的良品颗数：有坐标图取最新版本的良品 bin 数（不允许人工改）；没有坐标图时
  可人工录入（必须填原因码），否则用产品主数据的 gross die 并给出提示 ``no_map_gross_die``；
- 守恒：坐标图晶圆调 B4 的 :func:`check_split`（分配颗数 + 不良 + 排除 = 坐标总数，即分配 =
  良品）；其他晶圆分配颗数必须等于良品颗数，否则 422 ``transform_qty_mismatch``；
- 子批：继承客户字段（:func:`inherit_customer`），锁定它自己产品的生效 BOM，从输出路线首
  工步重新开始；条（strip）建单元记录，die 不建，位置写在 ``unit_origin``；
- 母批状态 → 已转换（converted），晶圆标记 converted；谱系 relation=transform。
"""

import uuid
from collections import defaultdict
from typing import Any

import sqlalchemy as sa
from fastapi import HTTPException
from sqlmodel import Session

from app.core.models import actor_name
from app.core.spec.audit import audit
from app.core.spec.base import conn, now
from app.core.spec.engine import ENTITIES, TABLES
from app.core.spec.errors import http_422
from app.core.spec.serialize import serialize
from app.mes.common.query import one
from app.mes.common.rows import _ins, _upd
from app.mes.execution.sm_rules import _child_codes, _genealogy
from app.mes.execution.stages import LOT
from app.mes.lot.service import (
    check_transition,
    customer_info,
    customer_mismatch,
    history,
    inherit_customer,
    lock_lots,
    lot_error,
    same_customer_lot,
    units,
)
from app.mes.map import service as map_svc
from app.mes.planning.service import first_step
from app.mes.process import service as process_svc
from app.mes.product import service as bom_svc

Row = dict[str, Any]
UNIT_LEVEL = {
    "strip": "unit",
    "die": "quantity",
    "package": "quantity",
    "unit": "quantity",
}


def _qty_error(code: str, message: str, **extra: Any) -> HTTPException:
    return HTTPException(
        status_code=422, detail={"code": code, "message": message, **extra}
    )


def _plan(s: Session, tid: uuid.UUID, body: Row) -> Row:
    """校验并生成转换方案（preview 与 commit 共用，不写库）。"""
    errs: list[tuple[Any, str]] = []
    warnings: list[Row] = []
    lots: list[Row] = []
    seen: set[Any] = set()
    for i, lid in enumerate(body["input_lot_ids"]):
        if lid in seen:
            errs.append((("input_lot_ids", i), "duplicate lot"))
            continue
        seen.add(lid)
        lot = one(s, tid, "lot", lid)
        if not lot:
            errs.append((("input_lot_ids", i), "lot not found"))
            continue
        lots.append(lot)
    if errs:
        raise http_422(errs)
    for lot in lots:
        check_transition(lot, "transform")  # 状态 / Hold → 422 lot_status / on_hold
    first = lots[0]
    for lot in lots[1:]:
        if customer_mismatch(first, lot):
            raise lot_error(
                "customer_mismatch",
                f"customer differs: {first['code']} vs {lot['code']}",
                lot,
                action="transform",
            )
        if not same_customer_lot(
            s, first.get("customer_lot_no"), lot.get("customer_lot_no")
        ):
            raise lot_error(
                "customer_lot_mismatch",
                f"customer lot no. differs: {first['code']} vs {lot['code']}",
                lot,
                action="transform",
                target_customer_lot_no=first.get("customer_lot_no"),
                source_customer_lot_no=lot.get("customer_lot_no"),
            )
    # 输入晶圆与良品颗数
    manual = {
        m["wafer_id"]: (j, m) for j, m in enumerate(body.get("manual_good") or [])
    }
    wafers: dict[Any, Row] = {}
    for i, lot in enumerate(lots):
        ws = [u for u in units(s, tid, lot["id"]) if u["unit_kind"] == "wafer"]
        if not ws:
            errs.append(
                (("input_lot_ids", i), f"{lot['code']}: no wafer units to transform")
            )
        for w in ws:
            m = map_svc.latest_map(s, tid, w["code"])
            mg = manual.pop(w["id"], None)
            info: Row = {"wafer": w, "lot": lot, "map": m}
            if m:
                if mg:
                    errs.append(
                        (
                            ("manual_good", mg[0], "wafer_id"),
                            f"{w['code']}: has a substrate map; manual good qty not allowed",
                        )
                    )
                tot, good, ex = (
                    m["total_qty"],
                    m["good_qty"] or 0,
                    m["excluded_qty"] or 0,
                )
                info |= {
                    "total": tot,
                    "good": good,
                    "excluded": ex,
                    "fail": tot - good - ex,
                    "source": "map",
                }
            elif mg:
                g, f = mg[1]["good_qty"], mg[1].get("fail_qty") or 0
                info |= {
                    "total": g + f,
                    "good": g,
                    "excluded": 0,
                    "fail": f,
                    "source": "manual",
                }
            else:
                lot_prod = one(s, tid, "product", lot["product_id"]) or {}
                gd = lot_prod.get("gross_die")
                if not gd:
                    errs.append(
                        (
                            ("manual_good",),
                            f"{w['code']}: no substrate map and product has no gross die; enter good qty with a reason",
                        )
                    )
                    continue
                info |= {
                    "total": gd,
                    "good": gd,
                    "excluded": 0,
                    "fail": 0,
                    "source": "gross_die",
                }
                warnings.append(
                    {
                        "code": "no_map_gross_die",
                        "message": f"{w['code']}: no substrate map; used product gross die {gd}",
                        "wafer": w["code"],
                    }
                )
            wafers[w["id"]] = info
    for wid, (j, _m) in manual.items():
        errs.append(
            (("manual_good", j, "wafer_id"), f"wafer {wid} is not an input wafer")
        )
    if any(x["source"] == "manual" for x in wafers.values()) and not body.get(
        "reason_id"
    ):
        errs.append((("reason_id",), "reason required for manual good qty"))
    if body.get("reason_id") and not one(s, tid, "reason_code", body["reason_id"]):
        errs.append((("reason_id",), "reason not found"))
    # 输出与分配
    alloc: dict[Any, int] = defaultdict(int)
    outs: list[Row] = []
    for k, o in enumerate(body["outputs"]):
        prod = one(s, tid, "product", o["product_id"])
        if not prod:
            errs.append((("outputs", k, "product_id"), "product not found"))
        route = one(s, tid, "route", o["route_id"])
        if not route:
            errs.append((("outputs", k, "route_id"), "route not found"))
        die_qty = 0
        for j, src in enumerate(o["sources"]):
            if src["wafer_id"] not in wafers:
                errs.append(
                    (("outputs", k, "sources", j, "wafer_id"), "not an input wafer")
                )
                continue
            alloc[src["wafer_id"]] += src["qty"]
            die_qty += src["qty"]
        kind = o["track_unit_kind"]
        if kind == "strip":
            if not o.get("qty"):
                errs.append((("outputs", k, "qty"), "strip count required"))
            qty = o.get("qty") or 0
        else:
            if o.get("qty") is not None and o["qty"] != die_qty:
                errs.append(
                    (("outputs", k, "qty"), f"qty must equal allocated dies {die_qty}")
                )
            qty = die_qty
        if die_qty < 1:
            errs.append((("outputs", k, "sources"), "at least one die"))
        outs.append(
            {**o, "qty": qty, "die_qty": die_qty, "product": prod, "route": route}
        )
    if errs:
        raise http_422(errs)
    # 数量守恒（逐片晶圆）
    for wid, x in wafers.items():
        a = alloc.get(wid, 0)
        x["allocated"] = a
        if x["map"]:
            map_svc.check_split(x["map"], a + x["fail"])  # 422 map_qty_mismatch
        elif a != x["good"]:
            raise _qty_error(
                "transform_qty_mismatch",
                f"{x['wafer']['code']}: allocated {a} != good {x['good']}",
                wafer=x["wafer"]["code"],
                allocated_qty=a,
                good_qty=x["good"],
            )
    return {"lots": lots, "wafers": wafers, "outputs": outs, "warnings": warnings}


def _brief_plan(p: Row) -> Row:
    return {
        "inputs": [
            {
                "lot": x["lot"]["code"],
                "wafer": x["wafer"]["code"],
                "wafer_id": str(x["wafer"]["id"]),
                "good_source": x["source"],
                "total_qty": x["total"],
                "good_qty": x["good"],
                "fail_qty": x["fail"],
                "excluded_qty": x["excluded"],
                "allocated_qty": x["allocated"],
                "substrate_map_id": x["map"] and str(x["map"]["id"]),
                "map_version": x["map"] and x["map"]["map_version"],
            }
            for x in p["wafers"].values()
        ],
        "outputs": [
            {
                "product_id": str(o["product_id"]),
                "route_id": str(o["route_id"]),
                "track_unit_kind": o["track_unit_kind"],
                "qty": o["qty"],
                "die_qty": o["die_qty"],
            }
            for o in p["outputs"]
        ],
        "warnings": p["warnings"],
    }


def preview(s: Session, tid: uuid.UUID, body: Row) -> Row:
    """校验转换方案并返回逐片晶圆的良品数与分配、子批数量与提示（不写库）。"""
    return _brief_plan(_plan(s, tid, body))


def transform(s: Session, tid: uuid.UUID, body: Row, user: Any) -> Row:
    """执行单位转换（见模块说明），返回转换事件、子批与提示。"""
    _plan(s, tid, body)  # 先校验（422），再加锁后按最新数据重算
    lock_lots(s, tid, body["input_lot_ids"])
    p = _plan(s, tid, body)
    lots, wafers, outs, warnings = (
        p["lots"],
        p["wafers"],
        p["outputs"],
        list(p["warnings"]),
    )
    at, first = now(), p["lots"][0]
    tr = _ins(
        s,
        tid,
        "unit_transform",
        user,
        transform_type=body["transform_type"],
        route_step_id=first["current_step_id"],
        reason_id=body.get("reason_id"),
        comment=body.get("comment"),
        warnings=warnings,
        username=actor_name(user),
        at=at,
        source="manual",
        external_event_id=None,
    )
    for x in wafers.values():
        _ins(
            s,
            tid,
            "unit_transform_input",
            user,
            unit_transform_id=tr,
            lot_id=x["lot"]["id"],
            wafer_id=x["wafer"]["id"],
            substrate_map_id=x["map"] and x["map"]["id"],
            qty_before=x["total"],
            good_qty=x["good"],
            fail_qty=x["fail"],
            excluded_qty=x["excluded"],
            good_source=x["source"],
        )
    codes = _child_codes(s, tid, first, {}, len(outs))
    # 每片晶圆的良品坐标（按行列顺序依次分给各子批）
    cells = {
        wid: (map_svc.good_cells(s, tid, x["map"]) if x["map"] else None)
        for wid, x in wafers.items()
    }
    taken: dict[Any, int] = defaultdict(int)
    origins: list[Row] = []
    children: list[Row] = []
    sysv = {
        "tenant_id": tid,
        "created_at": at,
        "updated_at": at,
        "created_by": getattr(user, "id", None),
        "updated_by": getattr(user, "id", None),
    }
    for o, code in zip(outs, codes, strict=True):
        step, site = first_step(s, tid, o["route_id"])
        stack: list[Row] = []
        step = step and process_svc.enter_route(s, tid, step, stack, [])
        if not step:
            raise http_422(
                [
                    (
                        ("outputs", outs.index(o), "route_id"),
                        "route has no operation steps",
                    )
                ]
            )
        bom = bom_svc.lock_for_start(s, tid, o["product_id"])
        if bom is None:
            warnings.append(
                {
                    "code": "no_active_bom",
                    "message": f"{code}: product has no active BOM",
                }
            )
        cid = _ins(
            s,
            tid,
            "lot",
            user,
            code=code,
            work_order_id=first["work_order_id"],
            product_id=o["product_id"],
            route_id=o["route_id"],
            lot_type_id=first["lot_type_id"],
            priority_id=first["priority_id"],
            qty=o["qty"],
            tracking_level=UNIT_LEVEL[o["track_unit_kind"]],
            site_id=site or first["site_id"],
            current_step_id=step["id"],
            lot_status="waiting",
            on_hold=False,
            step_in_at=at,
            route_stack=list(stack),
            pending_rework=False,
            scrapped_qty=0,
            received_qty=0,
            rework_count=0,
            bonus_qty=0,
            source_ref=first.get("source_ref"),
            started_at=at,
            started_by=actor_name(user),
            bom_id=bom and bom["id"],
            attrs={"transform_id": str(tr)},
            **inherit_customer(first),
        )
        strips: list[uuid.UUID] = []
        if o["track_unit_kind"] == "strip":
            for n in range(1, o["qty"] + 1):
                strips.append(
                    _ins(
                        s,
                        tid,
                        "wafer",
                        user,
                        code=f"{code}-S{n:02d}",
                        lot_id=cid,
                        unit_kind="strip",
                        slot=None,
                        wafer_status="waiting",
                        rework_count=0,
                    )
                )
        child = one(s, tid, "lot", cid)
        assert child
        children.append(child)
        _ins(
            s,
            tid,
            "unit_transform_output",
            user,
            unit_transform_id=tr,
            lot_id=cid,
            product_id=o["product_id"],
            track_unit_kind=o["track_unit_kind"],
            qty=o["qty"],
            die_qty=o["die_qty"],
        )
        seq = 0
        per_lot: dict[Any, list[int]] = defaultdict(lambda: [0, 0])
        per_codes: dict[Any, list[str]] = defaultdict(list)
        for src in o["sources"]:
            x = wafers[src["wafer_id"]]
            w, n = x["wafer"], src["qty"]
            per_lot[x["lot"]["id"]][0] += n
            per_codes[x["lot"]["id"]].append(w["code"])
            cs = cells[w["id"]]
            base = {
                **sysv,
                "unit_transform_id": tr,
                "child_lot_id": cid,
                "parent_lot_id": x["lot"]["id"],
                "parent_wafer_id": w["id"],
            }
            if cs is not None:
                for r, c in cs[taken[w["id"]] : taken[w["id"]] + n]:
                    seq += 1
                    su = (
                        strips[(seq - 1) * len(strips) // o["die_qty"]]
                        if strips
                        else None
                    )
                    origins.append(
                        {
                            **base,
                            "id": uuid.uuid4(),
                            "child_seq": seq,
                            "child_unit_id": su,
                            "die_row": r,
                            "die_col": c,
                            "qty": 1,
                        }
                    )
                taken[w["id"]] += n
            else:
                origins.append(
                    {
                        **base,
                        "id": uuid.uuid4(),
                        "child_seq": seq + 1,
                        "child_unit_id": None,
                        "die_row": None,
                        "die_col": None,
                        "qty": n,
                    }
                )
                seq += n
        for lid, (n, _) in per_lot.items():
            parent = next(lt for lt in lots if lt["id"] == lid)
            _genealogy(s, tid, parent, child, "transform", n, per_codes[lid], user, at)
        history(
            s,
            tid,
            child,
            "transform",
            user,
            from_status=None,
            comment=body.get("comment"),
            details={
                "transform_id": str(tr),
                "role": "output",
                "from": [lt["code"] for lt in lots],
                "die_qty": o["die_qty"],
            },
        )
        audit(
            s,
            tid,
            LOT,
            "transform",
            child,
            user,
            {"transform": (None, body["transform_type"])},
        )
    if origins:
        conn(s).execute(sa.insert(TABLES["unit_origin"]), origins)
    wt = TABLES["wafer"]
    for lot in lots:
        conn(s).execute(
            sa.update(wt)
            .where(
                wt.c.tenant_id == tid,
                wt.c.lot_id == lot["id"],
                wt.c.wafer_status != "scrapped",
            )
            .values(wafer_status="converted", updated_at=at)
        )
        _upd(
            s,
            tid,
            "lot",
            lot["id"],
            user,
            lot_status="converted",
            carrier_id=None,
            completed_at=at,
        )
        old = lot["lot_status"]
        lot.update(lot_status="converted")
        history(
            s,
            tid,
            lot,
            "transform",
            user,
            from_status=old,
            comment=body.get("comment"),
            details={
                "transform_id": str(tr),
                "role": "input",
                "to": [c["code"] for c in children],
            },
        )
        audit(s, tid, LOT, "transform", lot, user, {"lot_status": (old, "converted")})
    s.commit()
    row = one(s, tid, "unit_transform", tr)
    assert row
    out = serialize(s, tid, ENTITIES["unit_transform"], [row])[0]
    return {
        "transform": out,
        "children": serialize(
            s,
            tid,
            LOT,
            [c for c in (one(s, tid, "lot", x["id"]) for x in children) if c],
        ),
        "customer": customer_info(s, tid, first),
        "warnings": warnings,
    }
