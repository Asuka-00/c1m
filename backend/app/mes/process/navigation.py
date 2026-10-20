"""路线导航：工步顺序、子路线进入 / 返回、下一位置。"""

import uuid
from typing import Any

from fastapi import HTTPException
from sqlmodel import Session

from app.core import error_codes as ec
from app.core.spec.errors import fe, http_422
from app.mes.common.query import find, one

Row = dict[str, Any]


# ---------------- route navigation ----------------
def route_steps(s: Session, tid: uuid.UUID, route_id: Any) -> list[Row]:
    """路线的工步，按序号排序。"""
    return find(s, tid, "route_step", order="seq", route_id=route_id)


def step_after(s: Session, tid: uuid.UUID, step: Row) -> Row | None:
    """同一路线中的下一工步，已是最后一步时为 None。"""
    return next(
        (x for x in route_steps(s, tid, step["route_id"]) if x["seq"] > step["seq"]),
        None,
    )


def enter_route(
    s: Session, tid: uuid.UUID, step: Row | None, stack: list[Row], ev: list[Row]
) -> Row | None:
    """逐层进入子路线，直到到达一个工序工步。"""
    depth = 0
    while step is not None and step["step_type"] == "sub_route" and depth < 10:
        sub = route_steps(s, tid, step["sub_route_id"])
        rt = one(s, tid, "route", step["sub_route_id"])
        if not sub:
            step = step_after(s, tid, step)
            continue
        stack.append(
            {
                "kind": "sub_route",
                "route_id": str(step["route_id"]),
                "step_id": str(step["id"]),
            }
        )
        ev.append({"action": "sub_route", "route": rt and rt["code"], "step": step})
        step, depth = sub[0], depth + 1
    if step is None and stack:
        return pop_route(s, tid, stack, ev)
    return step


def pop_route(
    s: Session, tid: uuid.UUID, stack: list[Row], ev: list[Row]
) -> Row | None:
    """离开当前子路线 / 返工路线（已到末尾），按返回方式回到上层路线。"""
    while stack:
        fr = stack.pop()
        caller = one(s, tid, "route_step", uuid.UUID(fr["step_id"]))
        if caller is None:
            continue
        ev.append({"action": "return", "kind": fr["kind"], "step": caller})
        if fr["kind"] == "rework" and fr.get("return", "same_step") == "same_step":
            return caller
        nxt = step_after(s, tid, caller)
        if nxt is not None:
            return enter_route(s, tid, nxt, stack, ev)
    return None


def next_location(
    s: Session, tid: uuid.UUID, lot: Row, step: Row, *, branch: bool, rework: bool
) -> tuple[Row | None, list[Row], list[Row]]:
    """计算批次的下一位置。

    Args:
        s: 数据库会话。
        tid: 租户 id。
        lot: 批次。
        step: 当前工步。
        branch: 是否走分支。
        rework: 是否进入返工路线。

    Returns:
        ``(下一工步或 None（路线结束）, 新的路线栈, 事件列表)``。

    Raises:
        HTTPException: 请求分支 / 返工但工步未配置（422）。
    """
    stack: list[Row] = list(lot.get("route_stack") or [])
    ev: list[Row] = []
    if rework:
        if not step["rework_route_id"]:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": ec.REWORK_ROUTE_MISSING,
                    "message": "this step has no rework route",
                    "route_step_id": str(step["id"]),
                    "step_seq": step.get("seq"),
                },
            )
        steps = route_steps(s, tid, step["rework_route_id"])
        if not steps:
            raise http_422(
                [
                    fe(
                        "rework",
                        ec.REWORK_ROUTE_EMPTY,
                        "rework: rework route has no steps",
                    )
                ]
            )
        rt = one(s, tid, "route", step["rework_route_id"])
        stack.append(
            {
                "kind": "rework",
                "route_id": str(step["route_id"]),
                "step_id": str(step["id"]),
                "return": step["rework_return"] or "same_step",
            }
        )
        ev.append({"action": "rework", "route": rt and rt["code"], "step": step})
        return enter_route(s, tid, steps[0], stack, ev), stack, ev
    if branch:
        if step["branch_to_seq"] is None:
            raise http_422(
                [fe("branch", ec.BRANCH_NONE, "branch: this step has no branch")]
            )
        tgt = next(
            (
                x
                for x in route_steps(s, tid, step["route_id"])
                if x["seq"] == step["branch_to_seq"]
            ),
            None,
        )
        if tgt is None:
            raise http_422(
                [
                    fe(
                        "branch",
                        ec.BRANCH_TARGET_MISSING,
                        f"branch: target seq {step['branch_to_seq']} not found",
                        target=step["branch_to_seq"],
                    )
                ]
            )
        ev.append(
            {
                "action": "branch",
                "condition": step["branch_condition"],
                "to_seq": tgt["seq"],
                "step": step,
            }
        )
        return enter_route(s, tid, tgt, stack, ev), stack, ev
    nxt = step_after(s, tid, step)
    if nxt is not None:
        return enter_route(s, tid, nxt, stack, ev), stack, ev
    return pop_route(s, tid, stack, ev), stack, ev
