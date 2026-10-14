"""Track Out：DC 录入、超规处置、扣料、报废/返工、E10、工具使用次数。"""

import uuid
from typing import Any

from sqlmodel import Session

from app.core.models import actor_name
from app.core.spec.audit import audit
from app.core.spec.base import now
from app.core.spec.engine import ENTITIES
from app.core.spec.errors import http_422
from app.mes.common.query import find, one
from app.mes.common.rows import _ins, _upd
from app.mes.equipment.service import e10_apply
from app.mes.execution import bom_usage
from app.mes.execution.checks import service as ck
from app.mes.execution.constants import OOS_RANK
from app.mes.execution.consumption import _consume, usage_type
from app.mes.execution.context import build_ctx
from app.mes.execution.events import OOS, notify_lot
from app.mes.execution.hold import default_reason, hold_lot
from app.mes.execution.recipe_run import close_run
from app.mes.execution.stage_common import _brief, _guard, _ov, _result
from app.mes.lot.service import history, lock_lot, units
from app.mes.process.service import step_after
from app.mes.quality.service import out_of_spec

Row = dict[str, Any]
LOT = ENTITIES["lot"]


def track_out(
    s: Session, tid: uuid.UUID, lot_id: uuid.UUID, body: Row, user: Any
) -> Row:
    """Track Out：完成加工。

    依次处理报废 / 返工单元、DC 数据（超规按计划处置）、物料扣减（硬性要求，不可放行）、
    工具使用次数、E10 迁移，并写历史。

    Args:
        s: 数据库会话。
        tid: 租户 id。
        lot_id: 批次 id。
        body: ``{dc, scrap, rework_units, materials, ...}``。
        user: 操作人。

    Returns:
        阶段结果。
    """
    lot = lock_lot(s, tid, lot_id)
    _guard(lot, "track_out")
    ctx = build_ctx(s, tid, lot, "track_out", body)
    level = lot["tracking_level"] or "wafer"
    us = {str(u["id"]): u for u in units(s, tid, lot["id"])}
    errs: list[tuple[str, str]] = []
    # 报废 / 返工
    scrap_units: list[tuple[Row, Row]] = []
    scrap_qty: list[tuple[int, Row]] = []
    for i, x in enumerate(body.get("scrap") or [], 1):
        r = one(s, tid, "reason_code", x.get("reason_id"))
        if not r or r["reason_type"] != "scrap":
            errs.append(
                (f"scrap.{i}.reason_id", f"scrap {i}: a scrap reason code is required")
            )
            continue
        if level == "quantity":
            n = int(x.get("qty") or 0)
            if n < 1:
                errs.append((f"scrap.{i}.qty", f"scrap {i}: qty must be >= 1"))
            scrap_qty.append((n, r))
        else:
            u = us.get(str(x.get("unit_id")))
            if not u:
                errs.append((f"scrap.{i}.unit_id", f"scrap {i}: unit not in this lot"))
            else:
                scrap_units.append((u, r))
    if level == "quantity" and sum(n for n, _ in scrap_qty) > lot["qty"]:
        errs.append(("scrap", f"scrap: total exceeds lot qty {lot['qty']}"))
    if len({u["id"] for u, _ in scrap_units}) != len(scrap_units):
        errs.append(("scrap", "scrap: a unit is listed twice"))
    rework_units: list[tuple[Row, Row]] = []
    for i, x in enumerate(body.get("rework_units") or [], 1):
        r = one(s, tid, "reason_code", x.get("reason_id"))
        u = us.get(str(x.get("unit_id")))
        if not r or r["reason_type"] != "rework" or not u:
            errs.append(
                (
                    f"rework_units.{i}",
                    f"rework {i}: unit of this lot + rework reason required",
                )
            )
        else:
            rework_units.append((u, r))
    # DC 数据
    smp = ctx.sampling or {}
    items = {it["measurement_item_id"]: it for it in smp.get("items") or []}
    dc: list[Row] = []
    for i, d in enumerate(body.get("dc") or [], 1):
        it = items.get(str(d.get("measurement_item_id")))
        if not it:
            errs.append((f"dc.{i}", f"dc {i}: measurement item not in the DC plan"))
            continue
        if d.get("value") is None or d.get("value") == "":
            continue
        try:
            v = float(d["value"])
        except TypeError, ValueError:
            errs.append((f"dc.{i}.value", f"dc {i}: value must be a number"))
            continue
        uid = d.get("unit_id")
        if uid and str(uid) not in {str(k) for k in us}:
            errs.append((f"dc.{i}.unit_id", f"dc {i}: unit not in this lot"))
            continue
        dc.append(
            {
                "measurement_item_id": uuid.UUID(it["measurement_item_id"]),
                "unit_id": uuid.UUID(str(uid)) if uid else None,
                "site_no": int(d.get("site_no") or 1),
                "value": v,
                "is_oos": out_of_spec(it, v),
                "oos_action": it["oos_action"],
                "code": it["code"],
            }
        )
    if errs:
        raise http_422(errs)
    ctx.dc = dc
    # 内置管控开关（卡控规则 severity = off 时关闭，见 checks.enabled）
    oos_on = ck.enabled(ctx, "oos")
    if not oos_on:
        for d in dc:
            d["oos_action"] = None
    # 物料：硬性要求（不可强制放行；material_sufficient 关闭时不拦截）
    short = [
        n
        for n in ctx.material_needs
        if sum(a["qty"] for a in n["allocation"]) + 1e-9 < n["need"]
    ]
    if short and ck.enabled(ctx, "material_sufficient"):
        raise http_422(
            [
                (
                    "material_lot_ids",
                    "material_lot_ids: insufficient "
                    + "; ".join(
                        f"{n['material_code']} need {n['need']:g}" for n in short
                    ),
                )
            ]
        )
    oos = [d for d in dc if d["is_oos"] and oos_on]
    worst = max(
        (d["oos_action"] for d in oos), key=lambda a: OOS_RANK.get(a, 0), default=None
    )
    extra = []
    if oos:
        msg = "; ".join(f"{d['code']}={d['value']:g}" for d in oos[:6])
        extra.append(
            ck.result(
                "oos",
                "fail" if worst == "block" else "warn",
                f"OOS ({worst}): {msg}",
                severity="block" if worst == "block" else "warn",
                data={"action": worst, "values": len(oos)},
            )
        )
    results = ck.evaluate(
        ctx,
        user,
        extra=extra,
        override=body.get("override", False),
        reason=body.get("override_reason"),
    )
    at, email = now(), actor_name(user)
    for d in dc:
        _ins(
            s,
            tid,
            "dc_result",
            user,
            lot_id=lot["id"],
            unit_id=d["unit_id"],
            route_step_id=ctx.step["id"],
            dc_plan_id=uuid.UUID(smp["dc_plan_id"]),
            measurement_item_id=d["measurement_item_id"],
            site_no=d["site_no"],
            value=d["value"],
            is_oos=d["is_oos"],
            oos_action=d["oos_action"] if d["is_oos"] and oos_on else None,
            username=email,
        )
    consumed = _consume(
        s,
        tid,
        ctx.material_needs,
        user,
        lot=lot,
        step=ctx.step,
        usage=usage_type(s, tid, lot, ctx.step),
    )
    # BOM 出站比对（只提示）：基准 = 本工步进站时的良品数（扣报废前的批次数量）
    bom_rows = bom_usage.compare(
        s,
        tid,
        lot,
        lot["qty"],
        operation_id=ctx.step["operation_id"],
        is_last=step_after(s, tid, ctx.step) is None
        and not (lot.get("route_stack") or []),
    )
    bom_warn = bom_usage.over_warning(bom_usage.new_overs(s, tid, lot, bom_rows))
    tools = []
    for t in ctx.tools:
        mx, used = ck.tool_life(s, tid, t)
        used += 1
        st = "available"
        if mx and used >= mx:
            st = "pending_maintenance"
        if t["expiry_date"] and t["expiry_date"] < at.date():
            st = "expired"
        _upd(s, tid, "tool", t["id"], user, usage_count=used, tool_status=st)
        tools.append({"tool": t["code"], "usage": used, "max": mx, "status": st})
    n_scrap = len(scrap_units) + sum(n for n, _ in scrap_qty)
    for u, r in scrap_units:
        _upd(
            s,
            tid,
            "wafer",
            u["id"],
            user,
            wafer_status="scrapped",
            scrap_reason_id=r["id"],
        )
        history(
            s,
            tid,
            lot,
            "scrap",
            user,
            step=ctx.step,
            unit_id=u["id"],
            qty=1,
            reason_id=r["id"],
            equipment_id=lot["equipment_id"],
        )
    for n, r in scrap_qty:
        history(
            s,
            tid,
            lot,
            "scrap",
            user,
            step=ctx.step,
            qty=n,
            reason_id=r["id"],
            equipment_id=lot["equipment_id"],
        )
    for u, r in rework_units:
        _upd(
            s,
            tid,
            "wafer",
            u["id"],
            user,
            wafer_status="rework",
            rework_count=(u["rework_count"] or 0) + 1,
        )
        history(
            s,
            tid,
            lot,
            "rework",
            user,
            step=ctx.step,
            unit_id=u["id"],
            qty=1,
            reason_id=r["id"],
        )
    scrapped = {u["id"] for u, _ in scrap_units} | {u["id"] for u, _ in rework_units}
    for u in us.values():
        if u["id"] not in scrapped and u["wafer_status"] == "processing":
            _upd(s, tid, "wafer", u["id"], user, wafer_status="waiting")
    qty = lot["qty"] - n_scrap
    status = "tracked_out" if qty > 0 else "scrapped"
    pending = bool(rework_units) or worst == "rework"
    _upd(
        s,
        tid,
        "lot",
        lot["id"],
        user,
        lot_status=status,
        qty=qty,
        scrapped_qty=(lot["scrapped_qty"] or 0) + n_scrap,
        stage_at=at,
        pending_rework=pending and bool(ctx.step["rework_route_id"]),
    )
    lot.update(lot_status=status, qty=qty)
    close_run(s, tid, lot, user)
    eq = one(s, tid, "equipment", lot["equipment_id"])
    e10 = e10_apply(s, tid, eq, "track_out", user, lot) if eq else None
    # 腔体：同腔体仍有其他运行中批次时不迁移
    busy = (
        {
            c
            for o in find(
                s, tid, "lot", equipment_id=lot["equipment_id"], lot_status="running"
            )
            if o["id"] != lot["id"]
            for c in (o.get("exec_ctx") or {}).get("chamber_ids") or []
        }
        if lot["equipment_id"]
        else set()
    )
    for cid in (lot.get("exec_ctx") or {}).get("chamber_ids") or []:
        ch = one(s, tid, "equipment", uuid.UUID(cid))
        if ch and cid not in busy:
            e10_apply(s, tid, ch, "track_out", user, lot)
    history(
        s,
        tid,
        lot,
        "track_out",
        user,
        step=ctx.step,
        from_status="running",
        equipment_id=lot["equipment_id"],
        recipe_id=lot["recipe_id"],
        details={
            "checks": _brief(results),
            "dc": len(dc),
            "oos": len(oos),
            "oos_action": worst,
            "scrap": n_scrap,
            "consumed": consumed,
            "bom_usage": bom_rows,
            "tools": tools,
            "e10": e10,
            "sampling": smp.get("message"),
            **_ov(body, results),
        },
    )
    if bom_warn:
        history(
            s,
            tid,
            lot,
            "bom_over_consumption",
            user,
            step=ctx.step,
            comment=bom_warn["message"][:300],
            details={"lines": bom_warn["lines"]},
        )
    if oos:
        history(
            s,
            tid,
            lot,
            "oos",
            user,
            step=ctx.step,
            details={
                "action": worst,
                "values": [{"item": d["code"], "value": d["value"]} for d in oos],
            },
        )
        oos_items = ", ".join(f"{d['code']}={d['value']:g}" for d in oos[:5])
        notify_lot(
            s,
            tid,
            OOS,
            lot,
            f"OOS on {lot['code']} step {ctx.step['seq']}: {oos_items} ({worst})",
            {"step": ctx.step["seq"], "items": oos_items, "action": worst or ""},
        )
    if worst == "auto_hold" and status != "scrapped":
        mi = one(
            s,
            tid,
            "measurement_item",
            next(
                d["measurement_item_id"] for d in oos if d["oos_action"] == "auto_hold"
            ),
        )
        reason = one(
            s, tid, "reason_code", mi and mi["oos_reason_id"]
        ) or default_reason(s, tid, "hold")
        hold_lot(
            s,
            tid,
            lot,
            user,
            reason,
            hold_type="auto",
            source="oos",
            comment="OOS: " + ", ".join(f"{d['code']}={d['value']:g}" for d in oos[:5]),
        )
    if status == "scrapped":
        history(
            s,
            tid,
            lot,
            "scrap",
            user,
            step=ctx.step,
            qty=0,
            details={"lot": "all units scrapped"},
        )
    audit(
        s,
        tid,
        LOT,
        "track_out",
        lot,
        user,
        {"lot_status": ("running", status), "qty": (lot["qty"] + n_scrap, qty)},
    )
    s.commit()
    return _result(
        s,
        tid,
        lot_id,
        results,
        e10=e10,
        oos_action=worst,
        consumed=consumed,
        tools=tools,
        bom_usage=bom_usage.as_strings(bom_rows),  # D50
        warnings=[bom_usage.warning_out(bom_warn)] if bom_warn else [],
    )
