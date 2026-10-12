"""Configurable execution checks.

* CHECKS: pluggable registry `check_type -> fn(ctx, params) -> Outcome`;
  register new types with ``@check_type("code", "en|zh|ja")``.
* Bindings (trigger + scope) are resolved most-specific-wins:
  route step > equipment > operation > equipment type > product.
* Every evaluated rule is written to mes_check_log (pass/warn/block/overridden);
  a block raises CheckBlocked unless overridden (mes.exec:override + reason).
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import sqlalchemy as sa
from fastapi import HTTPException
from sqlmodel import Session

from app.core.spec.engine import ENTITIES, ENUMS, TABLES
from app.core.spec.service import audit, conn, now, to_json

Row = dict[str, Any]
Outcome = tuple[str, str, Row]  # ("pass" | "fail" | "warn" | "na", message, data)


def jsonable(v: Any) -> Any:
    if isinstance(v, dict):
        return {k: jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [jsonable(x) for x in v]
    return to_json(v)


# ---------------- tiny query helpers ----------------
def one(s: Session, tid: uuid.UUID, code: str, rid: Any) -> Row | None:
    if rid is None:
        return None
    t = TABLES[code]
    r = (
        conn(s)
        .execute(sa.select(t).where(t.c.tenant_id == tid, t.c.id == rid))
        .mappings()
        .first()
    )
    return dict(r) if r else None


def find(
    s: Session, tid: uuid.UUID, code: str, order: str | None = None, **eq: Any
) -> list[Row]:
    t = TABLES[code]
    stmt = sa.select(t).where(t.c.tenant_id == tid)
    for k, v in eq.items():
        stmt = stmt.where(t.c[k].is_(None) if v is None else t.c[k] == v)
    if order:
        stmt = stmt.order_by(t.c[order])
    return [dict(r) for r in conn(s).execute(stmt).mappings()]


# ---------------- context ----------------
@dataclass
class Ctx:
    s: Session
    tid: uuid.UUID
    trigger: str
    lot: Row
    step: Row
    op: Row | None = None
    product: Row | None = None
    wo: Row | None = None
    equipment: Row | None = None
    recipe: Row | None = None
    reticle: Row | None = None
    carrier: Row | None = None
    tools: list[Row] = field(default_factory=list)
    material_lots: list[Row] = field(default_factory=list)
    dc: list[Row] = field(default_factory=list)  # entered values (+ is_oos)
    sampling: Row | None = None  # decision from execution.sampling()
    material_needs: list[Row] = field(default_factory=list)
    at: datetime = field(default_factory=now)

    def resources(self, kind: str | None = None) -> list[Row]:
        return [
            r
            for r in find(
                self.s, self.tid, "step_resource", route_step_id=self.step["id"]
            )
            if kind is None or r["resource_kind"] == kind
        ]

    @property
    def today(self) -> date:
        return self.at.date()


CheckFn = Callable[[Ctx, Row], Outcome]
CHECKS: dict[str, CheckFn] = {}


def check_type(code: str, label: str | None = None) -> Callable[[CheckFn], CheckFn]:
    """Register a check implementation (adds the enum value for new types)."""

    def deco(fn: CheckFn) -> CheckFn:
        CHECKS[code] = fn
        if label and code not in {c for c, _ in ENUMS["check_type"]}:
            ENUMS["check_type"].append((code, label))
        return fn

    return deco


# ---------------- E10 helpers ----------------
def e10_current(s: Session, tid: uuid.UUID, eq: Row) -> Row | None:
    st = one(s, tid, "e10_state", eq.get("e10_state_id") or eq.get("initial_state_id"))
    if st:
        return st
    init = [r for r in find(s, tid, "e10_state", order="sort_order") if r["is_initial"]]
    return init[0] if init else None


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


def tool_life(s: Session, tid: uuid.UUID, tool: Row) -> tuple[int | None, int]:
    """(max usage: tool override or the tool type's max uses, current usage)."""
    fx = one(s, tid, "fixture", tool["fixture_id"])
    mx = tool["max_usage"] or (fx["max_uses"] if fx else None)
    return (int(mx) if mx else None), int(tool["usage_count"] or 0)


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


def qtime_clock(
    s: Session, tid: uuid.UUID, lot_id: Any, step_id: Any, until: datetime | None
) -> datetime | None:
    """Start of a Q-Time clock: the lot's last move-out of `step_id`, inherited
    through genealogy (split parent / merge sources, before the event). An own
    move-out after the event supersedes it; otherwise the earliest (strictest)
    start wins."""
    h, g = TABLES["lot_history"], TABLES["lot_genealogy"]
    q = sa.select(sa.func.max(h.c.at)).where(
        h.c.tenant_id == tid,
        h.c.lot_id == lot_id,
        h.c.route_step_id == step_id,
        h.c.action == "move_out",
    )
    if until is not None:
        q = q.where(h.c.at <= until)
    own = conn(s).execute(q).scalar()
    gq = sa.select(g.c.parent_lot_id, g.c.at).where(
        g.c.tenant_id == tid, g.c.child_lot_id == lot_id
    )
    if until is not None:
        gq = gq.where(g.c.at <= until)
    cands = [own] if own else []
    for parent, at in conn(s).execute(gq).all():
        if own and own > at:
            continue
        c = qtime_clock(s, tid, parent, step_id, at)
        if c:
            cands.append(c)
    return min(cands) if cands else None


def qtime_status(
    s: Session, tid: uuid.UUID, lot: Row, step: Row, at: datetime
) -> list[Row]:
    """Q-Time rules ending at `step`: elapsed minutes since move-out of from_step."""
    out = []
    for r in find(s, tid, "qtime_rule", to_step_id=step["id"]):
        if r["product_id"] and r["product_id"] != lot["product_id"]:
            continue
        last = qtime_clock(s, tid, lot["id"], r["from_step_id"], None)
        if last is None:
            continue
        mins = (at - last).total_seconds() / 60
        out.append(
            {
                "rule": r,
                "since": last,
                "minutes": round(mins, 1),
                "too_early": bool(r["min_minutes"] and mins < r["min_minutes"]),
                "exceeded": bool(r["max_minutes"] and mins > r["max_minutes"]),
            }
        )
    return out


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


SPECIFICITY = {
    "route_step": 5,
    "equipment": 4,
    "operation": 3,
    "equipment_type": 2,
    "product": 1,
}


def _matches(b: Row, ctx: Ctx) -> bool:
    eq = ctx.equipment or {}
    match b["scope"]:
        case "route_step":
            return bool(b["route_step_id"] == ctx.step["id"])
        case "equipment":
            return bool(eq) and bool(b["equipment_id"] == eq.get("id"))
        case "operation":
            return bool(ctx.op) and bool(b["operation_id"] == (ctx.op or {}).get("id"))
        case "equipment_type":
            return bool(eq) and bool(
                b["equipment_type_id"] == eq.get("equipment_type_id")
            )
        case "product":
            return bool(b["product_id"] == ctx.lot["product_id"])
    return False


def resolve(ctx: Ctx) -> list[tuple[Row, Row]]:
    """(plan, rule) pairs of the most specific matching bindings."""
    bs = [
        b
        for b in find(
            ctx.s, ctx.tid, "check_binding", trigger=ctx.trigger, is_active=True
        )
        if _matches(b, ctx)
    ]
    if not bs:
        return []
    top = max(SPECIFICITY[b["scope"]] for b in bs)
    out: list[tuple[Row, Row]] = []
    seen: set[Any] = set()
    for b in bs:
        if SPECIFICITY[b["scope"]] != top:
            continue
        plan = one(ctx.s, ctx.tid, "check_plan", b["check_plan_id"])
        if not plan or not plan["is_active"]:
            continue
        for it in find(
            ctx.s, ctx.tid, "check_plan_item", order="seq", check_plan_id=plan["id"]
        ):
            rule = one(ctx.s, ctx.tid, "check_rule", it["check_rule_id"])
            if rule and rule["is_active"] and rule["id"] not in seen:
                seen.add(rule["id"])
                out.append((plan, rule))
    return out


# ---------------- evaluation ----------------
class CheckBlocked(HTTPException):
    def __init__(self, results: list[Row]) -> None:
        super().__init__(
            status_code=409, detail={"code": "check_blocked", "results": results}
        )


def result(
    check: str,
    outcome: str,
    msg: str,
    *,
    severity: str = "block",
    rule: Row | None = None,
    plan: Row | None = None,
    data: Row | None = None,
    overridable: bool = True,
) -> Row:
    res = {"fail": severity, "warn": "warn", "pass": "pass", "na": "pass"}[outcome]
    return {
        "check_type": check,
        "rule_id": rule and str(rule["id"]),
        "rule_code": rule and rule["code"],
        "rule_name": rule and rule["name"],
        "plan_code": plan and plan["code"],
        "plan_id": plan and str(plan["id"]),
        "severity": severity,
        "result": res,
        "applicable": outcome != "na",
        "message": msg,
        "overridable": overridable,
        "data": jsonable(data or {}),
    }


def run(ctx: Ctx) -> list[Row]:
    out = []
    for plan, rule in resolve(ctx):
        fn = CHECKS.get(rule["check_type"])
        if fn is None:
            out.append(
                result(
                    rule["check_type"],
                    "warn",
                    "check type not implemented",
                    rule=rule,
                    plan=plan,
                )
            )
            continue
        oc, msg, data = fn(ctx, rule.get("params") or {})
        out.append(
            result(
                rule["check_type"],
                oc,
                msg,
                severity=rule["severity"],
                rule=rule,
                plan=plan,
                data=data,
            )
        )
    return out


def evaluate(
    ctx: Ctx,
    user: Any,
    *,
    extra: list[Row] | None = None,
    override: bool = False,
    reason: str | None = None,
    preview: bool = False,
) -> list[Row]:
    """Run bound rules (+ intrinsic `extra` results), log every result.

    Raises CheckBlocked (after committing the log) when a block remains."""
    results = [*(extra or []), *run(ctx)]
    blocks = [r for r in results if r["result"] == "block"]
    hard = [r for r in blocks if not r["overridable"]]
    do_override = bool(override and blocks and not hard and not preview)
    if do_override and not (reason or "").strip():
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "loc": ["body", "override_reason"],
                    "msg": "override_reason: required",
                    "type": "value_error",
                }
            ],
        )
    if do_override:
        for r in blocks:
            r["result"] = "overridden"
    t = TABLES["check_log"]
    email = getattr(user, "email", None)
    for r in results:
        conn(ctx.s).execute(
            sa.insert(t).values(
                id=uuid.uuid4(),
                tenant_id=ctx.tid,
                lot_id=ctx.lot["id"],
                trigger=ctx.trigger,
                route_step_id=ctx.step["id"],
                equipment_id=ctx.equipment and ctx.equipment["id"],
                check_rule_id=r["rule_id"] and uuid.UUID(r["rule_id"]),
                check_plan_id=r["plan_id"] and uuid.UUID(r["plan_id"]),
                check_type=r["check_type"],
                severity=r["severity"],
                result=r["result"],
                message=r["message"][:500],
                context={"preview": preview, **r["data"]},
                override_reason=reason if r["result"] == "overridden" else None,
                user_email=email,
                created_at=ctx.at,
                created_by=getattr(user, "id", None),
            )
        )
    if do_override:
        audit(
            ctx.s,
            ctx.tid,
            ENTITIES["lot"],
            "override",
            ctx.lot,
            user,
            {
                "override": (None, [r["rule_code"] or r["check_type"] for r in blocks]),
                "reason": (None, reason),
            },
        )
    if blocks and not do_override and not preview:
        ctx.s.commit()  # keep the log (and auto actions) of the blocked attempt
        raise CheckBlocked(results)
    return results
