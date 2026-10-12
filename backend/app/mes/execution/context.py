"""执行上下文：构建检查上下文与批次操作台数据。"""

import uuid
from typing import Any

from fastapi import HTTPException
from sqlmodel import Session

from app.core.spec.base import now
from app.core.spec.engine import ENTITIES
from app.core.spec.errors import http_422
from app.core.spec.serialize import serialize, to_json
from app.mes.common.query import find, one
from app.mes.execution.checks import service as ck
from app.mes.execution.checks.registry import Ctx
from app.mes.execution.constants import NEXT_STAGE, STAGES
from app.mes.execution.consumption import candidate_lots, material_needs
from app.mes.lot.service import TERMINAL, units
from app.mes.process.service import step_after
from app.mes.quality.service import sampling

Row = dict[str, Any]
LOT = ENTITIES["lot"]


# ---------------- context ----------------
def _rows(s: Session, tid: uuid.UUID, code: str, ids: list[Any] | None) -> list[Row]:
    return [r for r in (one(s, tid, code, uuid.UUID(str(i))) for i in (ids or [])) if r]


def build_ctx(s: Session, tid: uuid.UUID, lot: Row, trigger: str, body: Row) -> Ctx:
    """根据批次、触发点与请求载荷构建检查上下文。"""
    step = one(s, tid, "route_step", lot["current_step_id"])
    if not step:
        raise http_422([("lot", "lot: no current step")])
    xc = lot.get("exec_ctx") or {}
    eq_id = body.get("equipment_id") or lot.get("equipment_id")
    eq = one(s, tid, "equipment", eq_id)
    if eq_id and not eq:
        raise http_422([("equipment_id", "equipment_id: not found")])
    rc = one(s, tid, "recipe", body.get("recipe_id") or lot.get("recipe_id"))
    rt = one(s, tid, "reticle", body.get("reticle_id") or xc.get("reticle_id"))
    car = one(s, tid, "carrier", body.get("carrier_id") or lot.get("carrier_id"))
    tools = _rows(s, tid, "tool", body.get("tool_ids") or xc.get("tool_ids"))
    mls = _rows(
        s,
        tid,
        "material_lot",
        body.get("material_lot_ids") or xc.get("material_lot_ids"),
    )
    ctx = Ctx(
        s=s,
        tid=tid,
        trigger=trigger,
        lot=lot,
        step=step,
        op=one(s, tid, "operation", step["operation_id"]),
        product=one(s, tid, "product", lot["product_id"]),
        wo=one(s, tid, "work_order", lot["work_order_id"]),
        equipment=eq,
        recipe=rc,
        reticle=rt,
        carrier=car,
        tools=tools,
        material_lots=mls,
    )
    ctx.material_needs = material_needs(s, tid, step, lot, mls, ctx.at)
    ctx.sampling = sampling(s, tid, lot, step, units(s, tid, lot["id"]))
    return ctx


def context(s: Session, tid: uuid.UUID, lot_id: uuid.UUID) -> Row:
    """批次操作台所需的全部数据（当前阶段、工步、设备候选、物料/工具需求、DC、Hold、Q-Time、拆合批等）。

    Args:
        s: 数据库会话。
        tid: 租户 id。
        lot_id: 批次 id。
    """
    lot = one(s, tid, "lot", lot_id)
    if not lot:
        raise HTTPException(status_code=404, detail="Record not found")
    step = one(s, tid, "route_step", lot["current_step_id"])
    out: Row = {
        "lot": serialize(s, tid, LOT, [lot])[0],
        "next_stage": None
        if lot["lot_status"] in TERMINAL
        else NEXT_STAGE.get(lot["lot_status"]),
    }
    us = units(s, tid, lot["id"], active=False)
    out["units"] = [
        {
            "id": str(u["id"]),
            "code": u["code"],
            "slot": u["slot"],
            "status": u["wafer_status"],
            "unit_kind": u["unit_kind"],
            "rework_count": u["rework_count"],
        }
        for u in us
    ]
    out["holds"] = serialize(
        s,
        tid,
        ENTITIES["lot_hold"],
        find(s, tid, "lot_hold", lot_id=lot["id"], is_active=True),
    )
    out["reasons"] = {
        k: [
            {"id": str(r["id"]), "code": r["code"], "name": r["name"]}
            for r in find(s, tid, "reason_code", order="code", reason_type=k)
            if r["is_active"]
        ]
        for k in ("hold", "release", "scrap", "rework", "jump", "bonus")
    }
    out["stack"] = lot.get("route_stack") or []
    if not step:
        return out
    rt = one(s, tid, "route", step["route_id"])
    # 同一流程的工序工步（跳站目标）
    out["route_steps"] = [
        {
            "id": str(x["id"]),
            "seq": x["seq"],
            "operation": (one(s, tid, "operation", x["operation_id"]) or {}).get(
                "code"
            ),
        }
        for x in find(s, tid, "route_step", order="seq", route_id=step["route_id"])
        if x["operation_id"]
    ]
    op = one(s, tid, "operation", step["operation_id"])
    rw = one(s, tid, "route", step["rework_route_id"])
    out["step"] = {
        "id": str(step["id"]),
        "seq": step["seq"],
        "route_id": str(step["route_id"]),
        "route": rt and f"{rt['code']} v{rt['version']}",
        "operation": op
        and {"id": str(op["id"]), "code": op["code"], "name": op["name"]},
        "branch_to_seq": step["branch_to_seq"],
        "branch_condition": step["branch_condition"],
        "rework_route": rw and f"{rw['code']} v{rw['version']}",
        "rework_return": step["rework_return"],
        "auto": {k: bool(step[f"auto_{k}"]) for k in STAGES},
        "is_last": step_after(s, tid, step) is None
        and not (lot.get("route_stack") or []),
    }
    res = find(s, tid, "step_resource", route_step_id=step["id"])
    ctx = Ctx(s=s, tid=tid, trigger="move_in", lot=lot, step=step, op=op)
    eq_ids = ck.allowed_equipment_ids(ctx)
    if not eq_ids and op:
        eq_ids = {
            c["equipment_id"]
            for c in find(s, tid, "equipment_capability", operation_id=op["id"])
        }
    eqs = (
        [e for e in (one(s, tid, "equipment", i) for i in eq_ids) if e]
        if eq_ids
        else [
            e
            for e in find(s, tid, "equipment", order="code", unit_kind="main")
            if e["is_active"]
        ]
    )

    def _eq(e: Row) -> Row:
        st = ck.e10_current(s, tid, e)
        return {
            "id": str(e["id"]),
            "code": e["code"],
            "name": e["name"],
            "state": st and st["code"],
            "category": st and st["e10_category"],
            "color": st and st["color"],
        }

    out["equipment"] = sorted((_eq(e) for e in eqs), key=lambda x: x["code"])
    rids = {r["recipe_id"] for r in res if r["recipe_id"]}
    out["recipes"] = [
        {
            "id": str(r["id"]),
            "code": r["code"],
            "name": r["name"],
            "version": r["version"],
            "status": r["status"],
            "equipment_type_id": str(r["equipment_type_id"]),
        }
        for r in (one(s, tid, "recipe", i) for i in rids)
        if r
    ]
    out["reticles"] = [
        {"id": str(r["id"]), "code": r["code"], "status": r["status_code"]}
        for r in (
            one(s, tid, "reticle", x["reticle_id"])
            for x in res
            if x["resource_kind"] == "reticle" and x["reticle_id"]
        )
        if r
    ]
    out["tools"] = []
    for x in res:
        if x["resource_kind"] == "fixture" and x["fixture_id"]:
            fx = one(s, tid, "fixture", x["fixture_id"])
            opts = []
            for t in find(s, tid, "tool", order="code", fixture_id=x["fixture_id"]):
                mx, used = ck.tool_life(s, tid, t)
                opts.append(
                    {
                        "id": str(t["id"]),
                        "code": t["code"],
                        "status": t["tool_status"],
                        "usage": used,
                        "max": mx,
                        "expiry": to_json(t["expiry_date"]),
                        "warn_pct": t["warn_pct"],
                    }
                )
            out["tools"].append(
                {
                    "fixture": fx
                    and {"id": str(fx["id"]), "code": fx["code"], "name": fx["name"]},
                    "options": opts,
                }
            )
    at = now()
    out["materials"] = []
    for n in material_needs(s, tid, step, lot, [], at):
        uom = one(s, tid, "uom", n["uom_id"])
        out["materials"].append(
            {
                "material_id": str(n["material_id"]),
                "material": n["material_code"],
                "need": n["need"],
                "basis": n["basis"],
                "uom": uom and uom["code"],
                "options": [
                    {
                        "id": str(m["id"]),
                        "code": m["code"],
                        "qty": m["qty_remaining"],
                        "expiry": to_json(m["expiry_date"]),
                        "location": m["location"],
                    }
                    for m in candidate_lots(s, tid, n["material_id"], at)
                ],
            }
        )
    out["dc"] = sampling(s, tid, lot, step, units(s, tid, lot["id"]))
    out["qtime"] = [
        {
            "rule": x["rule"]["code"],
            "minutes": x["minutes"],
            "min": x["rule"]["min_minutes"],
            "max": x["rule"]["max_minutes"],
            "exceeded": x["exceeded"],
            "too_early": x["too_early"],
        }
        for x in ck.qtime_status(s, tid, lot, step, at)
    ]
    out["tracking_level"] = lot["tracking_level"] or "wafer"
    out["exec_ctx"] = lot.get("exec_ctx") or {}
    return out
