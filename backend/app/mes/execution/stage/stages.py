"""阶段入口：Move In、Track In、Move Out、阶段分发与检查预览。"""

import uuid
from typing import Any

from fastapi import HTTPException
from sqlmodel import Session

from app.core import error_codes as ec
from app.core.spec.audit import audit
from app.core.spec.base import now
from app.core.spec.engine import ENTITIES
from app.core.spec.errors import FieldError, coded, fe, http_422
from app.core.spec.serialize import serialize
from app.mes.common.query import one
from app.mes.common.rows import _upd
from app.mes.equipment.service import e10_apply
from app.mes.execution.carrier.usage import count_use
from app.mes.execution.checks import service as ck
from app.mes.execution.hold.future import trigger
from app.mes.execution.hold.qtime import _qtime_actions
from app.mes.execution.stage.common import _brief, _guard, _ov, _relocate, _result
from app.mes.execution.stage.constants import NEXT_STAGE
from app.mes.execution.stage.context import build_ctx
from app.mes.execution.stage.recipe_run import open_run
from app.mes.execution.stage.rework import rework_limit_result
from app.mes.execution.stage.track_out import track_out
from app.mes.lot.service import history, lock_lot, units

Row = dict[str, Any]
LOT = ENTITIES["lot"]


def move_in(s: Session, tid: uuid.UUID, lot_id: uuid.UUID, body: Row, user: Any) -> Row:
    """Move In：进站到当前工步（Q-Time 超时处置、预约 Hold、move_in 检查）。

    Args:
        s: 数据库会话。
        tid: 租户 id。
        lot_id: 批次 id。
        body: 请求载荷（放行标记与原因等）。
        user: 操作人。

    Returns:
        阶段结果（批次、检查结果、事件）。
    """
    lot = lock_lot(s, tid, lot_id)
    _guard(lot, "move_in")
    step = one(s, tid, "route_step", lot["current_step_id"])
    assert step
    # D19：Move In 不再停表，也不做 Q-Time 超时处置（改在 Track In / 定时扫描）
    ctx = build_ctx(s, tid, lot, "move_in", body)
    if ck.enabled(ctx, "future_hold"):
        fired = trigger(s, tid, lot, step, user)
        if fired:
            s.commit()
            return _result(s, tid, lot_id, [], future_hold=fired)
    if ctx.equipment and ctx.equipment["unit_kind"] != "main":
        raise http_422(
            [
                fe(
                    "equipment_id",
                    ec.EQUIPMENT_NOT_MAIN,
                    "equipment_id: select a main equipment unit",
                )
            ]
        )
    results = ck.evaluate(
        ctx,
        user,
        override=body.get("override", False),
        reason=body.get("override_reason"),
    )
    eq = ctx.equipment
    _upd(
        s,
        tid,
        "lot",
        lot["id"],
        user,
        lot_status="moved_in",
        equipment_id=eq and eq["id"],
        stage_at=now(),
    )
    lot.update(lot_status="moved_in", equipment_id=eq and eq["id"])
    history(
        s,
        tid,
        lot,
        "move_in",
        user,
        step=step,
        from_status="waiting",
        equipment_id=eq and eq["id"],
        details={"checks": _brief(results), **_ov(body, results)},
    )
    audit(s, tid, LOT, "move_in", lot, user, {"lot_status": ("waiting", "moved_in")})
    s.commit()
    return _result(s, tid, lot_id, results)


def track_in(
    s: Session, tid: uuid.UUID, lot_id: uuid.UUID, body: Row, user: Any
) -> Row:
    """Track In：选定设备 / 配方 / 工具开始加工（track_in 检查、E10 迁移），批次进入 Running。"""
    lot = lock_lot(s, tid, lot_id)
    _guard(lot, "track_in")
    step = one(s, tid, "route_step", lot["current_step_id"])
    assert step
    # D19 停表点：已超时则处置；D22 转 Hold 后提交并返回 200（qtime="hold"，未进站）
    q = _qtime_actions(s, tid, lot, step, user)
    if q:
        s.commit()
        return _result(s, tid, lot_id, [], qtime=q)
    ctx = build_ctx(s, tid, lot, "track_in", body)
    eq = ctx.equipment
    errs: list[FieldError] = []
    if not eq and ck.allowed_equipment_ids(ctx):
        errs.append(
            fe(
                "equipment_id",
                ec.EQUIPMENT_REQUIRED,
                "equipment_id: required for track in",
            )
        )
    elif eq and (eq["unit_kind"] != "main" or not eq["is_active"]):
        errs.append(
            fe(
                "equipment_id",
                ec.EQUIPMENT_NOT_MAIN,
                "equipment_id: select an active main equipment unit",
            )
        )
    for c in ctx.chambers:
        if not eq or c["parent_id"] != eq["id"] or c["unit_kind"] != "chamber":
            errs.append(
                fe(
                    "chamber_ids",
                    ec.CHAMBER_NOT_OF_EQUIPMENT,
                    f"chamber_ids: {c['code']} is not a chamber of the equipment",
                    chamber=c["code"],
                )
            )
        elif not c["is_active"]:
            errs.append(
                fe(
                    "chamber_ids",
                    ec.CHAMBER_INACTIVE,
                    f"chamber_ids: {c['code']} is inactive",
                    chamber=c["code"],
                )
            )
    if not ctx.recipe and any(r["recipe_id"] for r in ctx.resources()):
        errs.append(
            fe("recipe_id", ec.RECIPE_REQUIRED, "recipe_id: required at this step")
        )
    for fid in {r["fixture_id"] for r in ctx.resources("fixture") if r["fixture_id"]}:
        if not any(t["fixture_id"] == fid for t in ctx.tools):
            fx = one(s, tid, "fixture", fid)
            errs.append(
                fe(
                    "tool_ids",
                    ec.TOOL_REQUIRED,
                    f"tool_ids: a {fx and fx['code']} tool is required",
                    fixture=fx and fx["code"],
                )
            )
    if errs:
        raise http_422(errs)
    eid = eq and eq["id"]
    results = ck.evaluate(
        ctx,
        user,
        override=body.get("override", False),
        reason=body.get("override_reason"),
    )
    xc = {
        "reticle_id": ctx.reticle and str(ctx.reticle["id"]),
        "tool_ids": [str(t["id"]) for t in ctx.tools],
        "material_lot_ids": [str(m["id"]) for m in ctx.material_lots],
        "chamber_ids": [str(c["id"]) for c in ctx.chambers],
    }
    for t in ctx.tools:
        _upd(s, tid, "tool", t["id"], user, tool_status="in_use", equipment_id=eid)
    if ctx.carrier and ctx.carrier["id"] != lot["carrier_id"]:
        _upd(s, tid, "lot", lot["id"], user, carrier_id=ctx.carrier["id"])
    for u in units(s, tid, lot["id"]):
        _upd(s, tid, "wafer", u["id"], user, wafer_status="processing")
    _upd(
        s,
        tid,
        "lot",
        lot["id"],
        user,
        lot_status="running",
        equipment_id=eid,
        recipe_id=ctx.recipe and ctx.recipe["id"],
        exec_ctx=xc,
        stage_at=now(),
    )
    lot.update(lot_status="running", equipment_id=eid)
    open_run(ctx, user)
    count_use(s, tid, (ctx.carrier or {}).get("id") or lot["carrier_id"], user)
    e10 = e10_apply(s, tid, eq, "track_in", user, lot) if eq else None
    for c in ctx.chambers:
        e10_apply(s, tid, c, "track_in", user, lot)
    history(
        s,
        tid,
        lot,
        "track_in",
        user,
        step=ctx.step,
        from_status="moved_in",
        equipment_id=eid,
        recipe_id=ctx.recipe and ctx.recipe["id"],
        details={
            "checks": _brief(results),
            "tools": [t["code"] for t in ctx.tools],
            "reticle": ctx.reticle and ctx.reticle["code"],
            "carrier": ctx.carrier and ctx.carrier["code"],
            "chambers": [c["code"] for c in ctx.chambers],
            "e10": e10,
            **_ov(body, results),
        },
    )
    audit(
        s,
        tid,
        LOT,
        "track_in",
        lot,
        user,
        {"lot_status": ("moved_in", "running"), "equipment": (None, eq and eq["code"])},
    )
    s.commit()
    return _result(s, tid, lot_id, results, e10=e10)


def move_out(
    s: Session, tid: uuid.UUID, lot_id: uuid.UUID, body: Row, user: Any
) -> Row:
    """Move Out：出站并移动到下一工步（含子路线 / 返工路线返回）；最后一步完成时批次结束。"""
    lot = lock_lot(s, tid, lot_id)
    _guard(lot, "move_out")
    ctx = build_ctx(s, tid, lot, "move_out", body)
    rework = bool(body.get("rework")) or bool(lot["pending_rework"])
    lim = rework_limit_result(ctx) if rework else None
    results = ck.evaluate(
        ctx,
        user,
        extra=[lim] if lim else None,
        override=body.get("override", False),
        reason=body.get("override_reason"),
    )
    nxt = _relocate(
        s,
        tid,
        lot,
        ctx.step,
        user,
        branch=bool(body.get("branch")) and not rework,
        rework=rework,
    )
    if rework:
        n = (lot.get("rework_count") or 0) + 1
        _upd(s, tid, "lot", lot["id"], user, rework_count=n)
        lot["rework_count"] = n
    audit(
        s,
        tid,
        LOT,
        "move_out",
        lot,
        user,
        {"lot_status": ("tracked_out", lot["lot_status"])},
    )
    s.commit()
    return _result(
        s,
        tid,
        lot_id,
        results,
        next_step=nxt and {"id": str(nxt["id"]), "seq": nxt["seq"]},
    )


STAGE_FN = {
    "move_in": move_in,
    "track_in": track_in,
    "track_out": track_out,
    "move_out": move_out,
}


def run_stage(
    s: Session, tid: uuid.UUID, lot_id: uuid.UUID, stage: str, body: Row, user: Any
) -> Row:
    """执行指定阶段，然后依次执行新当前工步上配置为自动的阶段。

    Args:
        s: 数据库会话。
        tid: 租户 id。
        lot_id: 批次 id。
        stage: 阶段（move_in / track_in / track_out / move_out）。
        body: 请求载荷。
        user: 操作人。

    Returns:
        最后一个阶段的结果，附带自动阶段列表。

    Raises:
        HTTPException: 阶段与批次当前状态不符或批次已 Hold（422）。
        CheckBlocked: 检查阻断。
    """
    out = STAGE_FN[stage](s, tid, lot_id, body, user)
    if body.get("override") and any(
        r["result"] == "overridden" for r in out["results"]
    ):
        lot = one(s, tid, "lot", lot_id)
        if lot:
            history(
                s,
                tid,
                lot,
                "override",
                user,
                details={
                    "stage": stage,
                    "reason": body.get("override_reason"),
                    "rules": [
                        r["rule_code"] or r["check_type"]
                        for r in out["results"]
                        if r["result"] == "overridden"
                    ],
                },
            )
            s.commit()
    auto: list[Row] = []
    for _ in range(40):
        lot = one(s, tid, "lot", lot_id)
        if not lot or lot["on_hold"] or lot["lot_status"] not in NEXT_STAGE:
            break
        nxt = NEXT_STAGE[lot["lot_status"]]
        step = one(s, tid, "route_step", lot["current_step_id"])
        if not step or not step[f"auto_{nxt}"]:
            break
        try:
            r = STAGE_FN[nxt](s, tid, lot_id, {}, user)
            auto.append({"stage": nxt, "ok": True, "results": r["results"]})
        except HTTPException as ex:
            s.rollback()
            auto.append({"stage": nxt, "ok": False, "error": ex.detail})
            break
    out["auto"] = auto
    lot = one(s, tid, "lot", lot_id)
    out["lot"] = serialize(s, tid, LOT, [lot])[0] if lot else None
    return out


def preview(
    s: Session, tid: uuid.UUID, lot_id: uuid.UUID, stage: str, body: Row, user: Any
) -> list[Row]:
    """预览阶段检查结果（不执行、不写日志）。"""
    lot = one(s, tid, "lot", lot_id)
    if not lot:
        raise coded(404, ec.RECORD_NOT_FOUND, "Record not found")
    ctx = build_ctx(s, tid, lot, stage, body)
    res = ck.evaluate(ctx, user, preview=True)
    s.commit()
    return res
