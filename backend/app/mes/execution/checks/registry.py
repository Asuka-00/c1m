"""可配置检查：检查上下文、检查类型注册表、绑定解析与评估。"""

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
Outcome = tuple[str, str, Row]  # ("pass" | "fail" | "warn" | "na", 消息, 数据)


# ---------------- context ----------------
@dataclass
class Ctx:
    """一次检查评估的上下文。

    Attributes:
        s: 数据库会话。
        tid: 租户 id。
        trigger: 触发点（move_in / track_in / track_out / move_out / split / merge）。
        lot: 批次行。
        step: 当前工步。
        op / product / wo: 工序、产品、工单（可为空）。
        equipment / recipe / reticle / carrier: 本次选定的资源（可为空）。
        eqp_recipe: 设备上报 / 扫描的设备端配方名（可为空）。
        tools / material_lots: 选定的工具与线边批次。
        dc: 录入的 DC 值。
        sampling: 抽样判定结果。
        material_needs: 物料需求计算结果。
        at: 评估时间。
    """

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
    eqp_recipe: str | None = None  # 设备上报 / 扫描的设备端配方名
    reticle: Row | None = None
    carrier: Row | None = None
    tools: list[Row] = field(default_factory=list)
    material_lots: list[Row] = field(default_factory=list)
    dc: list[Row] = field(default_factory=list)  # 录入的 DC 值（含 is_oos 超规标记）
    sampling: Row | None = None  # 抽样判定结果（quality.dc.sampling）
    material_needs: list[Row] = field(default_factory=list)
    at: datetime = field(default_factory=now)

    def resources(self, kind: str | None = None) -> list[Row]:
        """当前工步上指定类别（material / tool / reticle ...）的资源需求。"""
        return [
            r
            for r in find(
                self.s, self.tid, "step_resource", route_step_id=self.step["id"]
            )
            if kind is None or r["resource_kind"] == kind
        ]

    @property
    def today(self) -> date:
        """当前日期（有效期类检查使用）。"""
        return self.at.date()


CheckFn = Callable[[Ctx, Row], Outcome]
CHECKS: dict[str, CheckFn] = {}


def check_type(code: str, label: str | None = None) -> Callable[[CheckFn], CheckFn]:
    """注册检查实现（装饰器）；新类型会追加到 check_type 枚举。

    Args:
        code: 检查类型编码。
        label: 三语标签。
    """

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
    """解析当前上下文生效的 (检查方案, 检查规则) 列表。

    仅保留最具体作用域的绑定（工步 > 设备 > 工序 > 设备类型 > 产品，见 SPECIFICITY）；
    同一规则只出现一次，停用的方案 / 规则被忽略。
    """
    bs = [
        b
        for b in find(
            ctx.s, ctx.tid, "check_binding", trigger=ctx.trigger, is_active=True
        )
        if _matches(b, ctx)
    ]
    if not bs:
        return []
    # 绑定优先级：只取最具体作用域的绑定（SPECIFICITY 数值越大越具体），
    # 更宽泛作用域的绑定被覆盖而非叠加
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


def control_rule(ctx: Ctx, check: str) -> Row | None:
    """当前上下文中决定某类内置管控的规则（最具体作用域优先），无则 None。"""
    bs = sorted(
        (
            b
            for b in find(
                ctx.s, ctx.tid, "check_binding", trigger=ctx.trigger, is_active=True
            )
            if _matches(b, ctx)
        ),
        key=lambda b: -SPECIFICITY[b["scope"]],
    )
    for b in bs:
        plan = one(ctx.s, ctx.tid, "check_plan", b["check_plan_id"])
        if not plan or not plan["is_active"]:
            continue
        for it in find(
            ctx.s, ctx.tid, "check_plan_item", order="seq", check_plan_id=plan["id"]
        ):
            rule = one(ctx.s, ctx.tid, "check_rule", it["check_rule_id"])
            if rule and rule["is_active"] and rule["check_type"] == check:
                return rule
    return None


def enabled(ctx: Ctx, check: str) -> bool:
    """某类管控在当前上下文是否开启（内置管控的统一开关）。

    在所有命中的有效绑定中，按作用域由具体到宽泛查找包含该检查类型的有效规则，
    第一条命中规则的严重度决定开关：``off`` 为关闭，其余为开启；无任何命中时默认开启。

    Args:
        ctx: 检查上下文（使用其触发时机与工步 / 设备 / 产品）。
        check: 检查类型编码。

    Returns:
        是否开启。
    """
    rule = control_rule(ctx, check)
    return rule is None or rule["severity"] != "off"


# ---------------- evaluation ----------------
class CheckBlocked(HTTPException):
    """存在未被放行的阻断检查结果（409，detail.code = check_blocked）。"""

    def __init__(self, results: list[Row]) -> None:
        """以检查结果列表构造 409 响应。"""
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
    """构造一条检查结果。

    Args:
        check: 检查类型编码。
        outcome: ``pass`` / ``warn`` / ``fail`` / ``na``（fail 按 severity 映射为 block 或 warn，na 视为不适用）。
        msg: 说明。
        severity: 规则配置的严重度。
        rule: 来源规则。
        plan: 来源方案。
        data: 附加数据。
        overridable: 阻断时是否允许有权限者强制放行。
    """
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
    """执行全部生效规则，返回检查结果列表（不写日志）。"""
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
        if rule["severity"] == "off":
            out.append(
                result(
                    rule["check_type"],
                    "na",
                    f"control disabled by rule {rule['code']}",
                    severity="warn",
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
    """执行检查并记录每条结果。

    Args:
        ctx: 检查上下文。
        user: 操作人。
        extra: 内置的附加结果（如 Hold、Q-Time），与规则结果一并处理。
        override: 是否请求强制放行。
        reason: 放行原因（放行时必填）。
        preview: 仅预览（不写日志、不抛阻断）。

    Returns:
        检查结果列表。

    Raises:
        CheckBlocked: 仍存在阻断（先提交检查日志再抛出）。
        HTTPException: 放行但未填写原因（422）。
    """
    results = [*(extra or []), *run(ctx)]
    blocks = [r for r in results if r["result"] == "block"]
    hard = [r for r in blocks if not r["overridable"]]
    # 仅当所有阻断都可放行（无硬阻断）且非预览时才允许强制放行
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
        ctx.s.commit()  # 先提交：保留被阻断尝试的检查日志（及自动处置）
        raise CheckBlocked(results)
    return results
