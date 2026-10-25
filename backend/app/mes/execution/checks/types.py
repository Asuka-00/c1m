"""内置检查类型：设备、配方、光罩、物料、工具、载具、Q-Time、Hold、工单、DC、抽样。"""

import uuid
from datetime import date, timedelta
from typing import Any

from fastapi import HTTPException

from app.mes.common.query import find, one
from app.mes.common.uom import convert
from app.mes.equipment.service import e10_current, pm_status, tool_life
from app.mes.execution.carrier.usage import clean_due
from app.mes.execution.checks.registry import Ctx, Msg, check_type, messages
from app.mes.lot.service import qtime_status

Row = dict[str, Any]
Outcome = tuple[
    str, Msg | list[Msg], Row
]  # ("pass" | "fail" | "warn" | "na", 说明, 数据)

# 消息模板：键 -> 英文模板（前端按 mes.checkMsg.<检查类型>.<键> 翻译；状态类参数为枚举值）
C = messages(
    "common",
    no_equipment_selected="no equipment selected",
    no_equipment="no equipment",
    no_operation="no operation",
    no_carrier="no carrier",
)


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
M_E10 = messages(
    "e10_available",
    ok="{equipment} is {state} ({category})",
    bad="{equipment} is {state} ({category}); needs {allowed}",
)


@check_type("e10_available")
def _e10(ctx: Ctx, p: Row) -> Outcome:
    eq = ctx.equipment
    if not eq:
        return "fail", C("no_equipment_selected"), {}
    st = e10_current(ctx.s, ctx.tid, eq)
    allowed = p.get("allowed") or ["SBY", "PRD"]
    cat = st and st["e10_category"]
    data = {"equipment": eq["code"], "state": st and st["code"], "category": cat}
    v = {"equipment": eq["code"], "state": st and st["code"], "category": cat}
    if cat in allowed:
        return "pass", M_E10("ok", **v), data
    return "fail", M_E10("bad", **v, allowed="/".join(allowed)), data


M_CAP = messages(
    "eqp_capability",
    not_allowed="{equipment} is not allowed at this step",
    no_capability="{equipment} has no capability for {operation}",
    not_required="no capability records (not required)",
    not_qualified="{equipment} is not qualified for {operation} with this recipe",
    qualified="{equipment} qualified for {operation}",
)


@check_type("eqp_capability")
def _capability(ctx: Ctx, p: Row) -> Outcome:
    eq = ctx.equipment
    if not eq:
        return "fail", C("no_equipment_selected"), {}
    allowed = allowed_equipment_ids(ctx)
    if allowed and eq["id"] not in allowed:
        return "fail", M_CAP("not_allowed", equipment=eq["code"]), {}
    if not ctx.op:
        return "na", C("no_operation"), {}
    v = {"equipment": eq["code"], "operation": ctx.op["code"]}
    caps = find(
        ctx.s,
        ctx.tid,
        "equipment_capability",
        equipment_id=eq["id"],
        operation_id=ctx.op["id"],
    )
    if not caps:
        if p.get("require_capability", True):
            return "fail", M_CAP("no_capability", **v), {}
        return "pass", M_CAP("not_required"), {}
    rid = ctx.recipe and ctx.recipe["id"]
    ok = [
        c
        for c in caps
        if c["is_qualified"]
        and (not c["qualified_until"] or c["qualified_until"] >= ctx.today)
        and (c["recipe_id"] is None or c["recipe_id"] == rid)
    ]
    if not ok:
        return "fail", M_CAP("not_qualified", **v), {}
    return "pass", M_CAP("qualified", **v), {}


M_RCP = messages(
    "recipe_active",
    required="recipe required",
    none="no recipe",
    status="recipe {recipe} v{version} is {status}",
    not_allowed="recipe {recipe} is not allowed at this step",
    other_type="recipe {recipe} is for another equipment type",
    not_enabled="recipe {recipe} is not enabled on {equipment}",
    active="recipe {recipe} v{version} active",
)


@check_type("recipe_active")
def _recipe(ctx: Ctx, _p: Row) -> Outcome:
    allowed = {r["recipe_id"] for r in ctx.resources() if r["recipe_id"]}
    rc = ctx.recipe
    if not rc:
        return ("fail", M_RCP("required"), {}) if allowed else ("na", M_RCP("none"), {})
    v = {"recipe": rc["code"], "version": rc["version"]}
    if rc["status"] != "active":
        return "fail", M_RCP("status", **v, status=rc["status"]), {}
    if allowed and rc["id"] not in allowed:
        return "fail", M_RCP("not_allowed", recipe=rc["code"]), {}
    eq = ctx.equipment
    if eq:
        if (
            eq.get("equipment_type_id")
            and rc["equipment_type_id"] != eq["equipment_type_id"]
        ):
            return "fail", M_RCP("other_type", recipe=rc["code"]), {}
        maps = find(ctx.s, ctx.tid, "recipe_equipment", recipe_id=rc["id"])
        if maps and not any(
            m["equipment_id"] == eq["id"] and m["is_enabled"] for m in maps
        ):
            return (
                "fail",
                M_RCP("not_enabled", recipe=rc["code"], equipment=eq["code"]),
                {},
            )
    return "pass", M_RCP("active", **v), {}


M_RMT = messages(
    "recipe_match",
    na="no recipe / equipment",
    not_enabled="recipe {recipe} is not enabled on {equipment}",
    not_reported="equipment recipe not reported (expect {expect})",
    enabled="recipe {recipe} enabled on {equipment}",
    differs="equipment recipe {got} differs from {expect}",
    matches="equipment recipe {got} matches",
)


@check_type("recipe_match")
def _recipe_match(ctx: Ctx, p: Row) -> Outcome:
    """配方-设备映射：所选配方须在该设备上启用；设备上报的设备端配方名须一致。

    参数：``require_report``（bool）为真时必须上报设备端配方名。
    """
    rc, eq = ctx.recipe, ctx.equipment
    if not rc or not eq:
        return "na", M_RMT("na"), {}
    v = {"recipe": rc["code"], "equipment": eq["code"]}
    m = next(
        (
            x
            for x in find(ctx.s, ctx.tid, "recipe_equipment", recipe_id=rc["id"])
            if x["equipment_id"] == eq["id"]
        ),
        None,
    )
    if not m or not m["is_enabled"]:
        return "fail", M_RMT("not_enabled", **v), {}
    expect = m["eqp_recipe"] or rc["code"]
    got = ctx.eqp_recipe
    if not got:
        if (p or {}).get("require_report"):
            return "fail", M_RMT("not_reported", expect=expect), {}
        return "pass", M_RMT("enabled", **v), {}
    if got.strip() != expect:
        return (
            "fail",
            M_RMT("differs", got=got, expect=expect),
            {"expect": expect, "got": got},
        )
    return "pass", M_RMT("matches", got=got), {}


M_PM = messages(
    "pm_due",
    overdue="{equipment} PM overdue: {plans}",
    due_soon="{equipment} PM due soon: {plans}",
    ok="{equipment} PM ok",
    no_plan="no PM plan",
)


@check_type("pm_due")
def _pm_due(ctx: Ctx, _p: Row) -> Outcome:
    """设备 PM 未超期：任一适用 PM 计划到期即失败（预警仅提示）。"""
    eq = ctx.equipment
    if not eq:
        return "na", C("no_equipment"), {}
    st = pm_status(ctx.s, ctx.tid, eq, ctx.at)
    due = [x["plan"] for x in st if x["due"]]
    if due:
        msg = M_PM("overdue", equipment=eq["code"], plans=", ".join(due))
        return "fail", msg, {"pm": st}
    warn = [x["plan"] for x in st if x["warn"]]
    if warn:
        msg = M_PM("due_soon", equipment=eq["code"], plans=", ".join(warn))
        return "pass", msg, {"pm": st}
    if st:
        return "pass", M_PM("ok", equipment=eq["code"]), {}
    return "na", M_PM("no_plan"), {}


M_RET = messages(
    "reticle_available",
    not_required="no reticle required",
    required="reticle required",
    not_allowed="reticle {reticle} is not allowed at this step",
    status="reticle {reticle} is {status}",
    available="reticle {reticle} available",
)


@check_type("reticle_available")
def _reticle(ctx: Ctx, _p: Row) -> Outcome:
    allowed = {r["reticle_id"] for r in ctx.resources("reticle") if r["reticle_id"]}
    if not allowed:
        return "na", M_RET("not_required"), {}
    rt = ctx.reticle
    if not rt:
        return "fail", M_RET("required"), {}
    if rt["id"] not in allowed:
        return "fail", M_RET("not_allowed", reticle=rt["code"]), {}
    if rt["status_code"] != "available":
        return "fail", M_RET("status", reticle=rt["code"], status=rt["status_code"]), {}
    return "pass", M_RET("available", reticle=rt["code"]), {}


M_MAT = messages(
    "material_sufficient",
    none="no material consumption",
    short="{material}: need {need}, available {available}",
    ok="materials sufficient",
)


@check_type("material_sufficient")
def _material(ctx: Ctx, _p: Row) -> Outcome:
    if not ctx.material_needs:
        return "na", M_MAT("none"), {}
    short = [n for n in ctx.material_needs if n["available"] + 1e-9 < n["need"]]
    data = {"needs": ctx.material_needs}
    if short:
        msgs = [
            M_MAT(
                "short",
                material=n["material_code"],
                need=f"{n['need']:g}",
                available=f"{n['available']:g}",
            )
            for n in short
        ]
        return "fail", msgs, data
    return "pass", M_MAT("ok"), data


M_BOM = messages(
    "bom_over",
    none="no BOM consumption to compare",
    over="over the BOM quantity: {items}",
    ok="within the BOM quantity",
)


def over_bom(ctx: Ctx) -> list[Row]:
    """本工步物料用量超过工单锁定 BOM 标准用量（含损耗率）的物料。

    BOM 明细按工序对应；用量单位不同时换算，无换算关系的跳过不比较。
    """
    bom_id = (ctx.wo or {}).get("bom_id")
    lines = (
        find(
            ctx.s,
            ctx.tid,
            "bom_line",
            bom_id=bom_id,
            operation_id=ctx.step["operation_id"],
        )
        if bom_id
        else []
    )
    over = []
    for n in ctx.material_needs:
        for ln in (x for x in lines if x["material_id"] == n["material_id"]):
            plan = float(ln["qty"]) * (
                ctx.lot["qty"] if ln["qty_basis"] == "per_unit" else 1
            )
            plan *= 1 + float(ln["scrap_rate"] or 0) / 100
            actual = n["need"]
            try:
                if n["uom_id"] != ln["uom_id"]:
                    actual = convert(ctx.s, ctx.tid, n["uom_id"], ln["uom_id"], actual)[
                        "value"
                    ]
            except HTTPException:
                continue
            if actual > plan + 1e-9:
                over.append(
                    {
                        "material": n["material_code"],
                        "actual": round(actual, 6),
                        "plan": round(plan, 6),
                    }
                )
    return over


def bom_over_msg(over: list[Row]) -> Msg:
    """超量说明：``物料 实际>标准`` 逐项列出。"""
    items = ", ".join(f"{o['material']} {o['actual']:g}>{o['plan']:g}" for o in over)
    return M_BOM("over", items=items)


@check_type("bom_over")
def _bom_over(ctx: Ctx, _p: Row) -> Outcome:
    if not (ctx.wo or {}).get("bom_id"):
        return "na", M_BOM("none"), {}
    over = over_bom(ctx)
    if over:
        return "warn", bom_over_msg(over), {"over": over}
    return "pass", M_BOM("ok"), {}


M_TOOL = messages(
    "tool_life",
    none="no tool required",
    required="tool of type {fixture} required",
    status="tool {tool} is {status}",
    life_reached="tool {tool} reached its life ({used}/{max})",
    expired="tool {tool} expired on {date}",
    near_end="tool {tool} near end of life ({used}/{max})",
    expires="tool {tool} expires on {date}",
    ok="tools available",
)


@check_type("tool_life")
def _tool(ctx: Ctx, p: Row) -> Outcome:
    types = {r["fixture_id"] for r in ctx.resources("fixture") if r["fixture_id"]}
    if not types:
        return "na", M_TOOL("none"), {}
    by_type = {t["fixture_id"]: t for t in ctx.tools}
    warn: list[Msg] = []
    for fid in types:
        t = by_type.get(fid)
        fx = one(ctx.s, ctx.tid, "fixture", fid)
        if not t:
            return "fail", M_TOOL("required", fixture=fx and fx["code"]), {}
        if t["tool_status"] not in ("available", "in_use"):
            return "fail", M_TOOL("status", tool=t["code"], status=t["tool_status"]), {}
        mx, used = tool_life(ctx.s, ctx.tid, t)
        life = {"tool": t["code"], "used": used, "max": mx}
        if mx and used >= mx:
            return "fail", M_TOOL("life_reached", **life), {}
        exp = {"tool": t["code"], "date": str(t["expiry_date"])}
        if t["expiry_date"] and t["expiry_date"] < ctx.today:
            return "fail", M_TOOL("expired", **exp), {}
        if mx and used >= mx * (t["warn_pct"] or 90) / 100:
            warn.append(M_TOOL("near_end", **life))
        days = int(p.get("expiry_warn_days", 7))
        if t["expiry_date"] and (t["expiry_date"] - ctx.today).days <= days:
            warn.append(M_TOOL("expires", **exp))
    if warn:
        return "warn", warn, {}
    return "pass", M_TOOL("ok"), {}


M_CAR = messages(
    "carrier_available",
    ok="carrier {carrier} {status}",
    bad="carrier {carrier} is {status}",
)


@check_type("carrier_available")
def _carrier(ctx: Ctx, _p: Row) -> Outcome:
    c = ctx.carrier or one(ctx.s, ctx.tid, "carrier", ctx.lot.get("carrier_id"))
    if not c:
        return "na", C("no_carrier"), {}
    v = {"carrier": c["code"], "status": c["status_code"]}
    if c["status_code"] in ("available", "in_use"):
        return "pass", M_CAR("ok", **v), {}
    return "fail", M_CAR("bad", **v), {}


M_QT = messages(
    "qtime",
    at_track_in="Q-Time is controlled at track in",
    none="no Q-Time rule",
    too_early="Q-Time {rule}: {minutes} min < min {min} min",
    exceeded="Q-Time {rule}: {minutes} min > max {max} min",
    ok="Q-Time ok",
)


@check_type("qtime")
def _qtime(ctx: Ctx, _p: Row) -> Outcome:
    if ctx.trigger == "move_in":  # D23：Q-Time 只在 Track In 管控，Move In 不再读
        return "na", M_QT("at_track_in"), {}
    st = qtime_status(ctx.s, ctx.tid, ctx.lot, ctx.step, ctx.at)
    if not st:
        return "na", M_QT("none"), {}
    bad = [x for x in st if x["too_early"] or x["exceeded"]]
    data = {"qtime": [{"rule": x["rule"]["code"], "minutes": x["minutes"]} for x in st]}
    if bad:
        x = bad[0]
        r = x["rule"]
        v = {"rule": r["code"], "minutes": f"{x['minutes']:g}"}
        if x["too_early"]:
            return "fail", M_QT("too_early", **v, min=r["min_minutes"]), data
        return "fail", M_QT("exceeded", **v, max=r["max_minutes"]), data
    return "pass", M_QT("ok"), data


M_HOLD = messages(
    "lot_hold",
    on_hold="lot is on hold",
    ok="not on hold",
    held="on hold: {lots}",
    none_held="no lot on hold",
)


@check_type("lot_hold")
def _hold(ctx: Ctx, _p: Row) -> Outcome:
    if ctx.lot["on_hold"]:
        return "fail", M_HOLD("on_hold"), {}
    return "pass", M_HOLD("ok"), {}


M_WO = messages("wo_status", ok="work order {status}", bad="work order is {status}")


@check_type("wo_status")
def _wo(ctx: Ctx, _p: Row) -> Outcome:
    st = ctx.wo and ctx.wo["wo_status"]
    if st in ("released", "in_progress"):
        return "pass", M_WO("ok", status=st), {}
    return "fail", M_WO("bad", status=st), {}


M_DC = messages(
    "dc_complete",
    none="no data collection required",
    missing="missing DC values: {items}",
    ok="DC complete",
)


@check_type("dc_complete")
def _dc(ctx: Ctx, _p: Row) -> Outcome:
    smp = ctx.sampling or {}
    if not smp.get("sampled") or not smp.get("items"):
        return "na", M_DC("none"), {}
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
        items = ", ".join(missing[:8]) + (" …" if len(missing) > 8 else "")
        return "fail", M_DC("missing", items=items), {}
    return "pass", M_DC("ok"), {}


M_OOS = messages(
    "oos",
    bad="{count} value(s) out of spec",
    ok="all values in spec",
    none="no DC values",
    values="OOS ({action}): {values}",
)


@check_type("oos")
def _oos(ctx: Ctx, _p: Row) -> Outcome:
    bad = [d for d in ctx.dc if d.get("is_oos")]
    if bad:
        return "fail", M_OOS("bad", count=len(bad)), {}
    return ("pass", M_OOS("ok"), {}) if ctx.dc else ("na", M_OOS("none"), {})


M_OOC = messages(
    "ooc",
    bad="{count} item(s) out of control",
    ok="process in control",
    none="no DC values",
    values="OOC ({action}): {values}",
)


@check_type("ooc")
def _ooc(ctx: Ctx, _p: Row) -> Outcome:
    bad = {d["code"] for d in ctx.dc if d.get("ooc_rules")}
    if bad:
        return "fail", M_OOC("bad", count=len(bad)), {}
    return ("pass", M_OOC("ok"), {}) if ctx.dc else ("na", M_OOC("none"), {})


M_SMP = messages(
    "sampling",
    no_operation="no operation",
    no_plan="no DC plan",
    every_lot="every lot (no sampling rule)",
    rule_sampled="rule {rule}: lot {n}, every {freq} → sampled",
    rule_skipped="rule {rule}: lot {n}, every {freq} → skipped",
    sampled="sampled",
    not_sampled="not sampled",
)


@check_type("sampling")
def _sampling(ctx: Ctx, _p: Row) -> Outcome:
    smp = ctx.sampling or {}
    reason = smp.get("reason") or ("sampled" if smp.get("sampled") else "not_sampled")
    return (
        "pass",
        M_SMP(reason, **(smp.get("reason_params") or {})),
        {"sampled": smp.get("sampled")},
    )


# ---------------- resolution ----------------
M_RW = messages(
    "rework_limit",
    builtin="evaluated when entering a rework route",
    reached="rework limit reached at step {step}: {count} / {max}",
    ok="rework {next} / {max}",
)


@check_type("rework_limit")
def _rework_limit(_ctx: Ctx, _p: Row) -> Outcome:
    # 内置于 Move Out 返工逻辑（工步 max_rework）；此处仅作为开关存在
    return "na", M_RW("builtin"), {}


M_ADJ = messages(
    "qty_adjust_limit",
    builtin="evaluated by scrap / bonus",
    exceeds="adjust qty {qty} exceeds {pct}% of lot qty {base}",
    within="within {pct}%",
)


@check_type("qty_adjust_limit")
def _qty_adjust_limit(_ctx: Ctx, _p: Row) -> Outcome:
    # 内置于报废 / 补数逻辑（参数 max_pct，默认 10）；此处仅作为开关存在
    return "na", M_ADJ("builtin"), {}


M_SM = messages("split_merge_rule", builtin="evaluated by the split / merge service")


@check_type("split_merge_rule")
def _split_merge(_ctx: Ctx, _p: Row) -> Outcome:
    # 拆 / 合批时由拆合批逻辑内置强制执行
    return "na", M_SM("builtin"), {}


M_CHR = messages(
    "chamber_required",
    none="equipment has no chambers",
    select="{equipment}: select a chamber",
    selected="{chambers}",
)


@check_type("chamber_required")
def _chamber_required(ctx: Ctx, _p: Row) -> Outcome:
    """设备带腔体时必须至少选一个腔体。"""
    eq = ctx.equipment
    if not eq or not chambers_of(ctx.s, ctx.tid, eq):
        return "na", M_CHR("none"), {}
    if not ctx.chambers:
        return "fail", M_CHR("select", equipment=eq["code"]), {}
    return (
        "pass",
        M_CHR("selected", chambers=", ".join(c["code"] for c in ctx.chambers)),
        {},
    )


M_CHA = messages(
    "chamber_available",
    none="no chamber selected",
    state="{chamber} is {state} ({category})",
    needs="needs {allowed}",
    ok="chambers available",
)


@check_type("chamber_available")
def _chamber_e10(ctx: Ctx, p: Row) -> Outcome:
    """选定腔体的 E10 状态须在允许类别内（默认 SBY / PRD）。"""
    if not ctx.chambers:
        return "na", M_CHA("none"), {}
    allowed = p.get("allowed") or ["SBY", "PRD"]
    bad: list[Msg] = []
    data: Row = {}
    for c in ctx.chambers:
        st = e10_current(ctx.s, ctx.tid, c)
        cat = st and st["e10_category"]
        data[c["code"]] = st and st["code"]
        if cat not in allowed:
            bad.append(
                M_CHA("state", chamber=c["code"], state=st and st["code"], category=cat)
            )
    if bad:
        return "fail", [*bad, M_CHA("needs", allowed="/".join(allowed))], data
    return "pass", M_CHA("ok"), data


M_BAT = messages(
    "batch_same_step",
    single="single lot",
    steps="lots are at different steps",
    equipment="lots are on different equipment",
    carriers="lots are in different carriers",
    ok="{count} lots at the same step",
)


@check_type("batch_same_step")
def _same_step(ctx: Ctx, p: Row) -> Outcome:
    """批量作业：所有批次须在同一工步、同一设备；``same_carrier`` 为真时还须同一载具。"""
    if len(ctx.batch) < 2:
        return "na", M_BAT("single"), {}
    steps = {str(x["current_step_id"]) for x in ctx.batch}
    if len(steps) > 1:
        return "fail", M_BAT("steps"), {}
    # 设备取各批次进站 / 上机的设备，以及本次作业选定的设备（未指定的不参与比较）
    eqs = {str(x["equipment_id"]) for x in ctx.batch if x["equipment_id"]}
    if ctx.equipment:
        eqs.add(str(ctx.equipment["id"]))
    if len(eqs) > 1:
        return "fail", M_BAT("equipment"), {}
    if p.get("same_carrier"):
        cars = {str(x["carrier_id"]) for x in ctx.batch}
        if len(cars) > 1:
            return "fail", M_BAT("carriers"), {}
    return "pass", M_BAT("ok", count=len(ctx.batch)), {}


M_CLN = messages(
    "carrier_clean",
    no_interval="no cleaning interval",
    overdue="carrier {carrier} cleaning overdue",
    due_soon="carrier {carrier} cleaning due soon",
    clean="carrier {carrier} clean",
)


@check_type("carrier_clean")
def _carrier_clean(ctx: Ctx, p: Row) -> Outcome:
    """载具清洗周期：超期拦截，临近到期（warn_hours，默认 24）预警。"""
    c = ctx.carrier or one(ctx.s, ctx.tid, "carrier", ctx.lot.get("carrier_id"))
    if not c:
        return "na", C("no_carrier"), {}
    due = clean_due(ctx.s, ctx.tid, c)
    if not due:
        return "na", M_CLN("no_interval"), {}
    data = {"carrier": c["code"], "due": due.isoformat()}
    if ctx.at > due:
        return "fail", M_CLN("overdue", carrier=c["code"]), data
    if ctx.at > due - timedelta(hours=float(p.get("warn_hours", 24))):
        return "warn", M_CLN("due_soon", carrier=c["code"]), data
    return "pass", M_CLN("clean", carrier=c["code"]), data


M_USE = messages(
    "carrier_usage",
    none="no usage limit",
    limit="carrier {carrier} used {used}/{max}; clean first",
    used="carrier {carrier} used {used}/{max}",
)


@check_type("carrier_usage")
def _carrier_usage(ctx: Ctx, p: Row) -> Outcome:
    """载具使用次数：达到最大次数拦截，达到 warn_pct（默认 90%）预警。"""
    c = ctx.carrier or one(ctx.s, ctx.tid, "carrier", ctx.lot.get("carrier_id"))
    if not c or not c["max_uses"]:
        return "na", M_USE("none"), {}
    used, mx = c["use_count"] or 0, c["max_uses"]
    data = {"carrier": c["code"], "used": used, "max": mx}
    if used >= mx:
        return "fail", M_USE("limit", **data), data
    if used >= mx * float(p.get("warn_pct", 90)) / 100:
        return "warn", M_USE("used", **data), data
    return "pass", M_USE("used", **data), data


M_SORT = messages(
    "sort_order",
    none="no wafer sort",
    changed="wafer order would change",
    kept="wafer order kept",
)
M_NOTE = messages(
    "notice", scheduled="scheduled notice", handover="shift handover rule"
)


@check_type("sort_order")
def _sort_order(ctx: Ctx, _p: Row) -> Outcome:
    """晶圆整理：按晶圆号排序后的槽位须递增（不打乱晶圆顺序）。"""
    if not ctx.sort_map:
        return "na", M_SORT("none"), {}
    slots = [x["slot"] for x in sorted(ctx.sort_map, key=lambda x: x["wafer"]["code"])]
    if slots != sorted(slots):
        return "fail", M_SORT("changed"), {}
    return "pass", M_SORT("kept"), {}


@check_type("wo_due")
def _wo_due(_ctx: Ctx, _p: Row) -> Outcome:
    """工单交期提醒：定时扫描发送通知（开关见 ``switch``），作业时不检查。"""
    return "na", M_NOTE("scheduled"), {}


M_FH = messages(
    "future_hold", pending="{count} future hold(s) at this step", none="no future hold"
)


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
        return "fail", M_FH("pending", count=n), {"count": n}
    return "na", M_FH("none"), {}


M_HOT = messages(
    "hot_lot_limit", not_hot="not a hot lot", count="{hot} hot lots in WIP (max {max})"
)


@check_type("hot_lot_limit")
def _hot_lot_limit(ctx: Ctx, p: Row) -> Outcome:
    """急件在制上限：设为急件时，在制急件数（不含本批）不得超过 ``max``（默认 5）。"""
    pr = ctx.priority
    if not pr or not pr["is_hot"]:
        return "na", M_HOT("not_hot"), {}
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
        return "fail", M_HOT("count", **data), data
    return "pass", M_HOT("count", **data), data


@check_type("handover_ack_other")
def _handover_ack_other(_ctx: Ctx, _p: Row) -> Outcome:
    """接班确认须由交班人以外的用户执行（开关见 ``switch``），作业时不检查。"""
    return "na", M_NOTE("handover"), {}


M_QUAL = messages(
    "operator_qualified",
    ok="{user} qualified for {operation}",
    bad="{user} not qualified for {operation}",
)


@check_type("operator_qualified")
def _operator_qualified(ctx: Ctx, _p: Row) -> Outcome:
    """操作员资质：操作人须持有本工序（及设备类型）的有效认证。"""
    if not ctx.op:
        return "na", C("no_operation"), {}
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
        return "pass", M_QUAL("ok", **data), {**data, "expires": exp}
    return "fail", M_QUAL("bad", **data), data


@check_type("qual_expiry_notice")
def _qual_expiry_notice(_ctx: Ctx, _p: Row) -> Outcome:
    """资质到期提醒：定时扫描发送通知（开关见 ``switch``），作业时不检查。"""
    return "na", M_NOTE("scheduled"), {}
