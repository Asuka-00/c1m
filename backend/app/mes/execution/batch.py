"""批量作业：同一设备上多个批次一起 Track In / Track Out。"""

import uuid
from typing import Any

from fastapi import HTTPException
from sqlmodel import Session

from app.core.spec.errors import http_422
from app.mes.common.query import find, one
from app.mes.execution.checks import service as ck
from app.mes.execution.constants import NEXT_STAGE
from app.mes.execution.context import build_ctx
from app.mes.execution.dispatch import queue
from app.mes.execution.stages import run_stage

Row = dict[str, Any]
MAX_BATCH = 25


def batch_stage(s: Session, tid: uuid.UUID, stage: str, body: Row, user: Any) -> Row:
    """批量执行 Track In / Track Out。

    先对全部批次预检（阶段一致 + 检查规则），任一阻断则整体不执行（409，按批次返回结果）；
    预检通过后逐批执行，单批失败不影响其他批次。

    Args:
        s: 数据库会话。
        tid: 租户 id。
        stage: ``track_in`` / ``track_out``。
        body: ``{lot_ids, ...阶段载荷}``（设备 / 配方 / 腔体对全部批次生效）。
        user: 操作人。

    Returns:
        ``{items: [{lot_id, code, ok, results | error}]}``。
    """
    ids = list(dict.fromkeys(str(i) for i in body.get("lot_ids") or []))
    if not 2 <= len(ids) <= MAX_BATCH:
        raise http_422([("lot_ids", f"lot_ids: select 2–{MAX_BATCH} lots")])
    lots = [one(s, tid, "lot", uuid.UUID(i)) for i in ids]
    if not all(lots):
        raise HTTPException(status_code=404, detail="Record not found")
    rows: list[Row] = [x for x in lots if x]
    bad = [x["code"] for x in rows if NEXT_STAGE.get(x["lot_status"]) != stage]
    if bad:
        raise http_422(
            [("lot_ids", f"lot_ids: not ready for {stage}: {', '.join(bad)}")]
        )
    shared = {k: v for k, v in body.items() if k not in ("lot_ids", "carrier_id")}
    # 预检：任一批次存在阻断则整体不执行
    pre: list[Row] = []
    for x in rows:
        ctx = build_ctx(s, tid, x, stage, shared)
        ctx.batch = rows
        res = ck.run(ctx)
        pre.append({"lot_id": str(x["id"]), "code": x["code"], "results": res})
    if not body.get("override") and any(
        r["result"] == "block" for p in pre for r in p["results"]
    ):
        raise HTTPException(
            status_code=409, detail={"code": "batch_blocked", "items": pre}
        )
    items: list[Row] = []
    for x in rows:
        try:
            out = run_stage(s, tid, x["id"], stage, {**shared, "batch": rows}, user)
            items.append(
                {
                    "lot_id": str(x["id"]),
                    "code": x["code"],
                    "ok": True,
                    "results": out["results"],
                }
            )
        except HTTPException as ex:
            s.rollback()
            items.append(
                {
                    "lot_id": str(x["id"]),
                    "code": x["code"],
                    "ok": False,
                    "error": ex.detail,
                }
            )
    return {"items": items}


def batch_candidates(
    s: Session, tid: uuid.UUID, stage: str, equipment_id: uuid.UUID
) -> Row:
    """批量作业候选：该设备上可 Track In（已进站）/ Track Out（运行中）的批次，及可选腔体与配方。"""
    eq = one(s, tid, "equipment", equipment_id)
    if not eq:
        raise HTTPException(status_code=404, detail="Record not found")
    status = "moved_in" if stage == "track_in" else "running"
    lots = [
        r
        for r in queue(s, tid, lot_status=status)
        if r["equipment_id"] == str(eq["id"]) and not r["on_hold"]
    ]
    rids = {
        x["recipe_id"]
        for sid in {r["step_id"] for r in lots if r["step_id"]}
        for x in find(s, tid, "step_resource", route_step_id=uuid.UUID(sid))
        if x["recipe_id"]
    }
    recipes = [r for r in (one(s, tid, "recipe", i) for i in rids) if r]
    return {
        "lots": lots,
        "chambers": [
            {"id": str(c["id"]), "code": c["code"], "name": c["name"]}
            | _state(s, tid, c)
            for c in ck.chambers_of(s, tid, eq)
        ],
        "recipes": [
            {
                "id": str(r["id"]),
                "code": r["code"],
                "name": r["name"],
                "version": r["version"],
            }
            for r in sorted(recipes, key=lambda r: r["code"])
        ],
    }


def _state(s: Session, tid: uuid.UUID, eq: Row) -> Row:
    st = ck.e10_current(s, tid, eq)
    return {
        "state": st and st["code"],
        "category": st and st["e10_category"],
        "color": st and st["color"],
    }
