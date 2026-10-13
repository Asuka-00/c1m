"""内置检查类型：设备、配方、光罩、物料、工具、载具、Q-Time、Hold、工单、DC、抽样。"""

import uuid
from datetime import date, timedelta
from typing import Any

from app.mes.common.query import find, one
from app.mes.equipment.service import e10_current, pm_status, tool_life
from app.mes.execution.checks.registry import Ctx, check_type
from app.mes.execution.usage import clean_due
from app.mes.lot.service import qtime_status

Row = dict[str, Any]
Outcome = tuple[str, str, Row]  # ("pass" | "fail" | "warn" | "na", 消息, 数据)


def allowed_equipment_ids(ctx: Ctx) -> set[Any]:
    """当前工步允许的设备 id（工步资源 / 工序设备组）。"""
    ids = {r["equipment_id"] for r in ctx.resources("equipment") if r["equipment_id"]}
    for r in ctx.resources("equipment_group"):
        if r["equipment_group_id"]:
            ids |= {
                e["id"]
                for e in find(
                    ctx.s,
                    ctx.tid,
                    "equipment",
                    equipment_group_id=r["equipment_group_id"],
                )
            }
    return ids


def chambers_of(s: Any, tid: uuid.UUID, eq: Row) -> list[Row]:
    """设备下的有效腔体（unit_kind = chamber），按编码排序。"""
    return [
        c
        for c in find(s, tid, "equipment", order="code", parent_id=eq["id"])
        if c["unit_kind"] == "chamber" and c["is_active"]
    ]


# ---------------- built-in checks ----------------
@check_type("e10_available")
def _e10(ctx: Ctx, p: Row) -> Outcome:
    eq = ctx.equipment
    if not eq:
        return "fail", "no equipment selected", {}
    st = e10_current(ctx.s, ctx.tid, eq)
    allowed = p.get("allowed") or ["SBY", "PRD"]
    cat = st and st["e10_category"]
    data = {"equipment": eq["code"], "state": st and st["code"], "category": cat}
    if cat in allowed:
        return "pass", f"{eq['code']} is {st and st['code']} ({cat})", data
    return (
        "fail",
        f"{eq['code']} is {st and st['code']} ({cat}); needs {'/'.join(allowed)}",
        data,
    )


@check_type("eqp_capability")
def _capability(ctx: Ctx, p: Row) -> Outcome:
    eq = ctx.equipment
    if not eq:
        return "fail", "no equipment selected", {}
    allowed = allowed_equipment_ids(ctx)
    if allowed and eq["id"] not in allowed:
        return "fail", f"{eq['code']} is not allowed at this step", {}
    if not ctx.op:
        return "na", "no operation", {}
    caps = find(
        ctx.s,
        ctx.tid,
        "equipment_capability",
        equipment_id=eq["id"],
        operation_id=ctx.op["id"],
    )
    if not caps:
        if p.get("require_capability", True):
            return "fail", f"{eq['code']} has no capability for {ctx.op['code']}", {}
        return "pass", "no capability records (not required)", {}
    rid = ctx.recipe and ctx.recipe["id"]
    ok = [
        c
        for c in caps
        if c["is_qualified"]
        and (not c["qualified_until"] or c["qualified_until"] >= ctx.today)
        and (c["recipe_id"] is None or c["recipe_id"] == rid)
    ]
    if not ok:
        return (
            "fail",
            f"{eq['code']} is not qualified for {ctx.op['code']} with this recipe",
            {},
        )
    return "pass", f"{eq['code']} qualified for {ctx.op['code']}", {}


@check_type("recipe_active")
def _recipe(ctx: Ctx, _p: Row) -> Outcome:
    allowed = {r["recipe_id"] for r in ctx.resources() if r["recipe_id"]}
    rc = ctx.recipe
    if not rc:
        return ("fail", "recipe required", {}) if allowed else ("na", "no recipe", {})
    if rc["status"] != "active":
        return "fail", f"recipe {rc['code']} v{rc['version']} is {rc['status']}", {}
    if allowed and rc["id"] not in allowed:
        return "fail", f"recipe {rc['code']} is not allowed at this step", {}
    eq = ctx.equipment
    if eq:
        if (
            eq.get("equipment_type_id")
            and rc["equipment_type_id"] != eq["equipment_type_id"]
        ):
            return "fail", f"recipe {rc['code']} is for another equipment type", {}
        maps = find(ctx.s, ctx.tid, "recipe_equipment", recipe_id=rc["id"])
        if maps and not any(
            m["equipment_id"] == eq["id"] and m["is_enabled"] for m in maps
        ):
            return "fail", f"recipe {rc['code']} is not enabled on {eq['code']}", {}
    return "pass", f"recipe {rc['code']} v{rc['version']} active", {}


@check_type("recipe_match")
def _recipe_match(ctx: Ctx, p: Row) -> Outcome:
    """配方-设备映射：所选配方须在该设备上启用；设备上报的设备端配方名须一致。

    参数：``require_report``（bool）为真时必须上报设备端配方名。
    """
    rc, eq = ctx.recipe, ctx.equipment
    if not rc or not eq:
        return "na", "no recipe / equipment", {}
    m = next(
        (
            x
            for x in find(ctx.s, ctx.tid, "recipe_equipment", recipe_id=rc["id"])
            if x["equipment_id"] == eq["id"]
        ),
        None,
    )
    if not m or not m["is_enabled"]:
        return "fail", f"recipe {rc['code']} is not enabled on {eq['code']}", {}
    expect = m["eqp_recipe"] or rc["code"]
    got = ctx.eqp_recipe
    if not got:
        if (p or {}).get("require_report"):
            return "fail", f"equipment recipe not reported (expect {expect})", {}
        return "pass", f"recipe {rc['code']} enabled on {eq['code']}", {}
    if got.strip() != expect:
        return (
            "fail",
            f"equipment recipe {got} differs from {expect}",
            {"expect": expect, "got": got},
        )
    return "pass", f"equipment recipe {got} matches", {}


@check_type("pm_due")
def _pm_due(ctx: Ctx, _p: Row) -> Outcome:
    """设备 PM 未超期：任一适用 PM 计划到期即失败（预警仅提示）。"""
    eq = ctx.equipment
    if not eq:
        return "na", "no equipment", {}
    st = pm_status(ctx.s, ctx.tid, eq, ctx.at)
    due = [x["plan"] for x in st if x["due"]]
    if due:
        return "fail", f"{eq['code']} PM overdue: {', '.join(due)}", {"pm": st}
    warn = [x["plan"] for x in st if x["warn"]]
    if warn:
        return "pass", f"{eq['code']} PM due soon: {', '.join(warn)}", {"pm": st}
    return ("pass", f"{eq['code']} PM ok", {}) if st else ("na", "no PM plan", {})


@check_type("reticle_available")
def _reticle(ctx: Ctx, _p: Row) -> Outcome:
    allowed = {r["reticle_id"] for r in ctx.resources("reticle") if r["reticle_id"]}
    if not allowed:
        return "na", "no reticle required", {}
    rt = ctx.reticle
    if not rt:
        return "fail", "reticle required", {}
    if rt["id"] not in allowed:
        return "fail", f"reticle {rt['code']} is not allowed at this step", {}
    if rt["status_code"] != "available":
        return "fail", f"reticle {rt['code']} is {rt['status_code']}", {}
    return "pass", f"reticle {rt['code']} available", {}


@check_type("material_sufficient")
def _material(ctx: Ctx, _p: Row) -> Outcome:
    if not ctx.material_needs:
        return "na", "no material consumption", {}
    short = [n for n in ctx.material_needs if n["available"] + 1e-9 < n["need"]]
    data = {"needs": ctx.material_needs}
    if short:
        return (
            "fail",
            "; ".join(
                f"{n['material_code']}: need {n['need']:g}, available {n['available']:g}"
                for n in short
            ),
            data,
        )
    return "pass", "materials sufficient", data


@check_type("tool_life")
def _tool(ctx: Ctx, p: Row) -> Outcome:
    types = {r["fixture_id"] for r in ctx.resources("fixture") if r["fixture_id"]}
    if not types:
        return "na", "no tool required", {}
    by_type = {t["fixture_id"]: t for t in ctx.tools}
    warn: list[str] = []
    for fid in types:
        t = by_type.get(fid)
        fx = one(ctx.s, ctx.tid, "fixture", fid)
        if not t:
            return "fail", f"tool of type {fx and fx['code']} required", {}
        if t["tool_status"] not in ("available", "in_use"):
            return "fail", f"tool {t['code']} is {t['tool_status']}", {}
        mx, used = tool_life(ctx.s, ctx.tid, t)
        if mx and used >= mx:
            return "fail", f"tool {t['code']} reached its life ({used}/{mx})", {}
        if t["expiry_date"] and t["expiry_date"] < ctx.today:
            return "fail", f"tool {t['code']} expired on {t['expiry_date']}", {}
        if mx and used >= mx * (t["warn_pct"] or 90) / 100:
            warn.append(f"tool {t['code']} near end of life ({used}/{mx})")
        days = int(p.get("expiry_warn_days", 7))
        if t["expiry_date"] and (t["expiry_date"] - ctx.today).days <= days:
            warn.append(f"tool {t['code']} expires on {t['expiry_date']}")
    if warn:
        return "warn", "; ".join(warn), {}
    return "pass", "tools available", {}


@check_type("carrier_available")
def _carrier(ctx: Ctx, _p: Row) -> Outcome:
    c = ctx.carrier or one(ctx.s, ctx.tid, "carrier", ctx.lot.get("carrier_id"))
    if not c:
        return "na", "no carrier", {}
    if c["status_code"] in ("available", "in_use"):
        return "pass", f"carrier {c['code']} {c['status_code']}", {}
    return "fail", f"carrier {c['code']} is {c['status_code']}", {}


@check_type("qtime")
def _qtime(ctx: Ctx, _p: Row) -> Outcome:
    if ctx.trigger == "move_in":  # D23：Q-Time 只在 Track In 管控，Move In 不再读
        return "na", "Q-Time is controlled at track in", {}
    st = qtime_status(ctx.s, ctx.tid, ctx.lot, ctx.step, ctx.at)
    if not st:
        return "na", "no Q-Time rule", {}
    bad = [x for x in st if x["too_early"] or x["exceeded"]]
    data = {"qtime": [{"rule": x["rule"]["code"], "minutes": x["minutes"]} for x in st]}
    if bad:
        x = bad[0]
        r = x["rule"]
        if x["too_early"]:
            return (
                "fail",
                f"Q-Time {r['code']}: {x['minutes']:g} min < min {r['min_minutes']} min",
                data,
            )
        return (
            "fail",
            f"Q-Time {r['code']}: {x['minutes']:g} min > max {r['max_minutes']} min",
            data,
        )
    return "pass", "Q-Time ok", data


@check_type("lot_hold")
def _hold(ctx: Ctx, _p: Row) -> Outcome:
    return (
        ("fail", "lot is on hold", {})
        if ctx.lot["on_hold"]
        else ("pass", "not on hold", {})
    )


@check_type("wo_status")
def _wo(ctx: Ctx, _p: Row) -> Outcome:
    st = ctx.wo and ctx.wo["wo_status"]
    if st in ("released", "in_progress"):
        return "pass", f"work order {st}", {}
    return "fail", f"work order is {st}", {}


@check_type("dc_complete")
def _dc(ctx: Ctx, _p: Row) -> Outcome:
    smp = ctx.sampling or {}
    if not smp.get("sampled") or not smp.get("items"):
        return "na", "no data collection required", {}
    have = {
        (d["measurement_item_id"], d.get("unit_id"))
        for d in ctx.dc
        if d.get("value") is not None
    }
    units = smp.get("unit_ids") or [None]
    missing = [
        f"{it['code']}" + (f"@{u}" if u else "")
        for it in smp["items"]
        for u in units
        if (uuid.UUID(it["measurement_item_id"]), uuid.UUID(u) if u else None)
        not in have
    ]
    if missing:
        return (
            "fail",
            f"missing DC values: {', '.join(missing[:8])}"
            + (" …" if len(missing) > 8 else ""),
            {},
        )
    return "pass", "DC complete", {}


@check_type("oos")
def _oos(ctx: Ctx, _p: Row) -> Outcome:
    bad = [d for d in ctx.dc if d.get("is_oos")]
    if bad:
        return "fail", f"{len(bad)} value(s) out of spec", {}
    return ("pass", "all values in spec", {}) if ctx.dc else ("na", "no DC values", {})


@check_type("sampling")
def _sampling(ctx: Ctx, _p: Row) -> Outcome:
    smp = ctx.sampling or {}
    return (
        "pass",
        smp.get("message") or ("sampled" if smp.get("sampled") else "not sampled"),
        {"sampled": smp.get("sampled")},
    )


# ---------------- resolution ----------------
@check_type("rework_limit")
def _rework_limit(_ctx: Ctx, _p: Row) -> Outcome:
    # 内置于 Move Out 返工逻辑（工步 max_rework）；此处仅作为开关存在
    return "na", "evaluated when entering a rework route", {}


@check_type("qty_adjust_limit")
def _qty_adjust_limit(_ctx: Ctx, _p: Row) -> Outcome:
    # 内置于报废 / 补数逻辑（参数 max_pct，默认 10）；此处仅作为开关存在
    return "na", "evaluated by scrap / bonus", {}


@check_type("split_merge_rule")
def _split_merge(_ctx: Ctx, _p: Row) -> Outcome:
    # 拆 / 合批时由拆合批逻辑内置强制执行
    return "na", "evaluated by the split / merge service", {}


@check_type("chamber_required")
def _chamber_required(ctx: Ctx, _p: Row) -> Outcome:
    """设备带腔体时必须至少选一个腔体。"""
    eq = ctx.equipment
    if not eq or not chambers_of(ctx.s, ctx.tid, eq):
        return "na", "equipment has no chambers", {}
    if not ctx.chambers:
        return "fail", f"{eq['code']}: select a chamber", {}
    return "pass", ", ".join(c["code"] for c in ctx.chambers), {}


@check_type("chamber_available")
def _chamber_e10(ctx: Ctx, p: Row) -> Outcome:
    """选定腔体的 E10 状态须在允许类别内（默认 SBY / PRD）。"""
    if not ctx.chambers:
        return "na", "no chamber selected", {}
    allowed = p.get("allowed") or ["SBY", "PRD"]
    bad, data = [], {}
    for c in ctx.chambers:
        st = e10_current(ctx.s, ctx.tid, c)
        cat = st and st["e10_category"]
        data[c["code"]] = st and st["code"]
        if cat not in allowed:
            bad.append(f"{c['code']} is {st and st['code']} ({cat})")
    if bad:
        return "fail", "; ".join(bad) + f"; needs {'/'.join(allowed)}", data
    return "pass", "chambers available", data


@check_type("batch_same_step")
def _same_step(ctx: Ctx, p: Row) -> Outcome:
    """批量作业：所有批次须在同一工步；``same_carrier`` 为真时还须同一载具。"""
    if len(ctx.batch) < 2:
        return "na", "single lot", {}
    steps = {str(x["current_step_id"]) for x in ctx.batch}
    if len(steps) > 1:
        return "fail", "lots are at different steps", {}
    if p.get("same_carrier"):
        cars = {str(x["carrier_id"]) for x in ctx.batch}
        if len(cars) > 1:
            return "fail", "lots are in different carriers", {}
    return "pass", f"{len(ctx.batch)} lots at the same step", {}


@check_type("carrier_clean")
def _carrier_clean(ctx: Ctx, p: Row) -> Outcome:
    """载具清洗周期：超期拦截，临近到期（warn_hours，默认 24）预警。"""
    c = ctx.carrier or one(ctx.s, ctx.tid, "carrier", ctx.lot.get("carrier_id"))
    if not c:
        return "na", "no carrier", {}
    due = clean_due(ctx.s, ctx.tid, c)
    if not due:
        return "na", "no cleaning interval", {}
    data = {"carrier": c["code"], "due": due.isoformat()}
    if ctx.at > due:
        return "fail", f"carrier {c['code']} cleaning overdue", data
    if ctx.at > due - timedelta(hours=float(p.get("warn_hours", 24))):
        return "warn", f"carrier {c['code']} cleaning due soon", data
    return "pass", f"carrier {c['code']} clean", data


@check_type("carrier_usage")
def _carrier_usage(ctx: Ctx, p: Row) -> Outcome:
    """载具使用次数：达到最大次数拦截，达到 warn_pct（默认 90%）预警。"""
    c = ctx.carrier or one(ctx.s, ctx.tid, "carrier", ctx.lot.get("carrier_id"))
    if not c or not c["max_uses"]:
        return "na", "no usage limit", {}
    used, mx = c["use_count"] or 0, c["max_uses"]
    data = {"carrier": c["code"], "used": used, "max": mx}
    if used >= mx:
        return "fail", f"carrier {c['code']} used {used}/{mx}; clean first", data
    if used >= mx * float(p.get("warn_pct", 90)) / 100:
        return "warn", f"carrier {c['code']} used {used}/{mx}", data
    return "pass", f"carrier {c['code']} used {used}/{mx}", data


@check_type("sort_order")
def _sort_order(ctx: Ctx, _p: Row) -> Outcome:
    """晶圆整理：按晶圆号排序后的槽位须递增（不打乱晶圆顺序）。"""
    if not ctx.sort_map:
        return "na", "no wafer sort", {}
    slots = [x["slot"] for x in sorted(ctx.sort_map, key=lambda x: x["wafer"]["code"])]
    if slots != sorted(slots):
        return "fail", "wafer order would change", {}
    return "pass", "wafer order kept", {}


@check_type("wo_due")
def _wo_due(_ctx: Ctx, _p: Row) -> Outcome:
    """工单交期提醒：定时扫描发送通知（开关见 ``switch``），作业时不检查。"""
    return "na", "scheduled notice", {}


@check_type("future_hold")
def _future_hold(ctx: Ctx, _p: Row) -> Outcome:
    """预约 Hold：Move In 时触发当前工步的预约 Hold（关闭后不触发）。"""
    n = len(
        find(
            ctx.s,
            ctx.tid,
            "future_hold",
            lot_id=ctx.lot["id"],
            route_step_id=ctx.step["id"],
            fh_status="active",
        )
    )
    if n:
        return "fail", f"{n} future hold(s) at this step", {"count": n}
    return "na", "no future hold", {}


@check_type("hot_lot_limit")
def _hot_lot_limit(ctx: Ctx, p: Row) -> Outcome:
    """急件在制上限：设为急件时，在制急件数（不含本批）不得超过 ``max``（默认 5）。"""
    pr = ctx.priority
    if not pr or not pr["is_hot"]:
        return "na", "not a hot lot", {}
    hot = {x["id"] for x in find(ctx.s, ctx.tid, "lot_priority", is_hot=True)}
    n = sum(
        1
        for x in find(ctx.s, ctx.tid, "lot")
        if x["priority_id"] in hot
        and x["id"] != ctx.lot["id"]
        and x["lot_status"] in ("waiting", "moved_in", "running", "tracked_out")
    )
    mx = int(p.get("max", 5))
    data = {"hot": n, "max": mx}
    if n >= mx:
        return "fail", f"{n} hot lots in WIP (max {mx})", data
    return "pass", f"{n} hot lots in WIP (max {mx})", data


@check_type("handover_ack_other")
def _handover_ack_other(_ctx: Ctx, _p: Row) -> Outcome:
    """接班确认须由交班人以外的用户执行（开关见 ``switch``），作业时不检查。"""
    return "na", "shift handover rule", {}


@check_type("operator_qualified")
def _operator_qualified(ctx: Ctx, _p: Row) -> Outcome:
    """操作员资质：操作人须持有本工序（及设备类型）的有效认证。"""
    if not ctx.op:
        return "na", "no operation", {}
    user = ctx.operator or ""
    et = (ctx.equipment or {}).get("equipment_type_id")
    today = ctx.at.date() if ctx.at else date.today()
    data = {"user": user, "operation": ctx.op["code"]}
    for q in find(
        ctx.s,
        ctx.tid,
        "operator_qual",
        username=user,
        operation_id=ctx.op["id"],
        is_active=True,
    ):
        if q["equipment_type_id"] and q["equipment_type_id"] != et:
            continue
        if q["expires_on"] and q["expires_on"] < today:
            continue
        exp = q["expires_on"] and str(q["expires_on"])
        return (
            "pass",
            f"{user} qualified for {ctx.op['code']}",
            {**data, "expires": exp},
        )
    return "fail", f"{user} not qualified for {ctx.op['code']}", data


@check_type("qual_expiry_notice")
def _qual_expiry_notice(_ctx: Ctx, _p: Row) -> Outcome:
    """资质到期提醒：定时扫描发送通知（开关见 ``switch``），作业时不检查。"""
    return "na", "scheduled notice", {}
