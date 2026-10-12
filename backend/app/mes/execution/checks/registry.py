import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import sqlalchemy as sa
from fastapi import HTTPException
from sqlmodel import Session

from app.core.spec.audit import audit
from app.core.spec.base import conn, now
from app.core.spec.engine import ENTITIES, ENUMS, TABLES
from app.mes.common.query import find, jsonable, one

Row = dict[str, Any]
Outcome = tuple[str, str, Row]  # ("pass" | "fail" | "warn" | "na", message, data)


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
