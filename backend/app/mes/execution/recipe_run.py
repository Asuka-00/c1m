"""配方执行记录：Track In 时快照配方版本与参数，Track Out 时关闭。"""

import uuid
from typing import Any

from sqlmodel import Session

from app.core.models import actor_name
from app.core.spec.base import now
from app.mes.common.query import find, one
from app.mes.common.rows import _ins, _upd
from app.mes.execution.checks.registry import Ctx

Row = dict[str, Any]


def _specs(ctx: Ctx) -> list[Row]:
    """当前工序 / 配方 / 产品适用的参数规格（空字段视为通配）。"""
    keys = {
        "operation_id": ctx.op and ctx.op["id"],
        "recipe_id": ctx.recipe and ctx.recipe["id"],
        "product_id": ctx.lot["product_id"],
    }
    out = []
    for p in find(ctx.s, ctx.tid, "param_spec", order="code"):
        if all(p[k] is None or p[k] == v for k, v in keys.items()):
            uom = one(ctx.s, ctx.tid, "uom", p["uom_id"])
            out.append(
                {
                    "code": p["code"],
                    "name": p["name"],
                    "target": p["target"],
                    "lsl": p["lsl"],
                    "usl": p["usl"],
                    "uom": uom and uom["code"],
                }
            )
    return out


def open_run(ctx: Ctx, user: Any) -> uuid.UUID | None:
    """Track In：写一条配方执行记录（配方版本、参数与适用规格的快照）。

    无设备且无配方时不记录。
    """
    eq, rc = ctx.equipment, ctx.recipe
    if not eq and not rc:
        return None
    return _ins(
        ctx.s,
        ctx.tid,
        "lot_recipe_run",
        user,
        lot_id=ctx.lot["id"],
        route_step_id=ctx.step["id"],
        operation_id=ctx.op and ctx.op["id"],
        equipment_id=eq and eq["id"],
        recipe_id=rc and rc["id"],
        recipe_version=rc and rc["version"],
        eqp_recipe=ctx.eqp_recipe,
        chambers=", ".join(c["code"] for c in ctx.chambers) or None,
        params=(rc and rc["body"]) or {},
        param_specs=_specs(ctx),
        qty=ctx.lot["qty"],
        track_in_at=now(),
        username=actor_name(user),
    )


def close_run(s: Session, tid: uuid.UUID, lot: Row, user: Any) -> None:
    """Track Out：关闭该批次最近一条未结束的配方执行记录。"""
    runs = [
        r
        for r in find(s, tid, "lot_recipe_run", lot_id=lot["id"])
        if r["track_out_at"] is None
    ]
    if runs:
        last = max(runs, key=lambda r: r["track_in_at"])
        _upd(
            s,
            tid,
            "lot_recipe_run",
            last["id"],
            user,
            track_out_at=now(),
            qty=lot["qty"],
        )
