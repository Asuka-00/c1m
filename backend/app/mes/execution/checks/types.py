import uuid
from typing import Any

from app.mes.common.query import find, one
from app.mes.equipment.service import e10_current, tool_life
from app.mes.execution.checks.registry import Ctx, check_type
from app.mes.lot.service import qtime_status

Row = dict[str, Any]
Outcome = tuple[str, str, Row]  # ("pass" | "fail" | "warn" | "na", message, data)


def allowed_equipment_ids(ctx: Ctx) -> set[Any]:
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
@check_type("split_merge_rule")
def _split_merge(_ctx: Ctx, _p: Row) -> Outcome:
    # enforced intrinsically by app.mes.splitmerge on split / merge
    return "na", "evaluated by the split / merge service", {}
