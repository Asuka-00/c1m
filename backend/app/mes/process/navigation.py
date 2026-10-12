"""Route navigation: step order, sub-route enter/return, next location."""

import uuid
from typing import Any

from sqlmodel import Session

from app.core.spec.errors import http_422
from app.mes.common.query import find, one

Row = dict[str, Any]


# ---------------- route navigation ----------------
def route_steps(s: Session, tid: uuid.UUID, route_id: Any) -> list[Row]:
    return find(s, tid, "route_step", order="seq", route_id=route_id)


def step_after(s: Session, tid: uuid.UUID, step: Row) -> Row | None:
    return next(
        (x for x in route_steps(s, tid, step["route_id"]) if x["seq"] > step["seq"]),
        None,
    )


def enter_route(
    s: Session, tid: uuid.UUID, step: Row | None, stack: list[Row], ev: list[Row]
) -> Row | None:
    """Descend into sub-routes until an operation step is reached."""
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
    """Leave the current sub/rework route (end reached)."""
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
    stack: list[Row] = list(lot.get("route_stack") or [])
    ev: list[Row] = []
    if rework:
        if not step["rework_route_id"]:
            raise http_422([("rework", "rework: this step has no rework route")])
        steps = route_steps(s, tid, step["rework_route_id"])
        if not steps:
            raise http_422([("rework", "rework: rework route has no steps")])
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
            raise http_422([("branch", "branch: this step has no branch")])
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
                [("branch", f"branch: target seq {step['branch_to_seq']} not found")]
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
