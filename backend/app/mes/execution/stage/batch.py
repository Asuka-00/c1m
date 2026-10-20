"""批量作业：同一设备上多个批次一起 Track In / Track Out。"""

import uuid
from typing import Any

from fastapi import HTTPException
from sqlmodel import Session

from app.core import error_codes as ec
from app.core.db import engine
from app.core.spec.errors import coded, fe, http_422
from app.core.tenant import set_tenant
from app.mes.common.query import find, one
from app.mes.execution.checks import service as ck
from app.mes.execution.stage.constants import NEXT_STAGE
from app.mes.execution.stage.dispatch import queue
from app.mes.execution.stage.stages import run_stage

Row = dict[str, Any]
MAX_BATCH = 25


def batch_stage(s: Session, tid: uuid.UUID, stage: str, body: Row, user: Any) -> Row:
    """批量执行 Track In / Track Out（全部批次执行成功才提交）。

    全部批次在同一个数据库事务中逐批执行（含全部校验、检查规则、Hold / Q-Time 处置）；
    任一批次失败（校验错误、检查阻断、Q-Time 超时转 Hold 等）则整批回滚，
    返回 409 并按批次给出结果。

    Args:
        s: 数据库会话。
        tid: 租户 id。
        stage: ``track_in`` / ``track_out``。
        body: ``{lot_ids, ...阶段载荷}``（设备 / 配方 / 腔体对全部批次生效）。
        user: 操作人。

    Returns:
        ``{items: [{lot_id, code, ok, results}]}``。

    Raises:
        HTTPException: 批次数量或状态不符（422）；批次不存在（404）；
            任一批次失败（409，detail.code = batch_blocked，``items`` 为逐批结果）。
    """
    ids = list(dict.fromkeys(str(i) for i in body.get("lot_ids") or []))
    if not 2 <= len(ids) <= MAX_BATCH:
        raise http_422(
            [
                fe(
                    "lot_ids",
                    ec.BATCH_SIZE,
                    f"lot_ids: select 2–{MAX_BATCH} lots",
                    min=2,
                    max=MAX_BATCH,
                )
            ]
        )
    lots = [one(s, tid, "lot", uuid.UUID(i)) for i in ids]
    if not all(lots):
        raise coded(404, ec.RECORD_NOT_FOUND, "Record not found")
    rows: list[Row] = [x for x in lots if x]
    bad = [x["code"] for x in rows if NEXT_STAGE.get(x["lot_status"]) != stage]
    if bad:
        raise http_422(
            [
                fe(
                    "lot_ids",
                    ec.BATCH_NOT_READY,
                    f"lot_ids: not ready for {stage}: {', '.join(bad)}",
                    stage=stage,
                    lots=", ".join(bad),
                )
            ]
        )
    shared = {k: v for k, v in body.items() if k not in ("lot_ids", "carrier_id")}
    shared["batch"] = rows
    items: list[Row] = []
    # 整批一个外层事务：各阶段内部的 commit / rollback 只作用于保存点
    # （join_transaction_mode="create_savepoint"），由这里统一提交或回滚
    with engine.connect() as c:
        txn = c.begin()
        bs = Session(bind=c, join_transaction_mode="create_savepoint")
        set_tenant(bs, tid)
        try:
            items = [_run_one(bs, tid, x, stage, shared, user) for x in rows]
            if all(i["ok"] for i in items):
                bs.commit()
                txn.commit()
                return {"items": items}
        finally:
            bs.close()
            if txn.is_active:
                txn.rollback()
    for i in items:
        if i["ok"]:
            i.update(
                ok=False,
                error={
                    "code": ec.BATCH_ROLLED_BACK,
                    "message": "not executed: another lot in the batch failed",
                },
            )
    raise HTTPException(
        status_code=409, detail={"code": ec.BATCH_BLOCKED, "items": items}
    )


def _run_one(
    s: Session, tid: uuid.UUID, lot: Row, stage: str, body: Row, user: Any
) -> Row:
    """批量作业中执行一个批次；失败时撤销该批次未提交到保存点的改动（整批随后统一回滚）。"""
    item: Row = {"lot_id": str(lot["id"]), "code": lot["code"]}
    try:
        out = run_stage(s, tid, lot["id"], stage, body, user)
    except ck.CheckBlocked as ex:
        s.rollback()
        return {**item, "ok": False, "results": ex.results}
    except HTTPException as ex:
        s.rollback()
        return {**item, "ok": False, "error": ex.detail}
    if out.get("qtime"):  # Q-Time 超时已转 Hold，批次未执行本阶段
        return {
            **item,
            "ok": False,
            "results": out["results"],
            "error": {
                "code": ec.BATCH_QTIME,
                "message": f"Q-Time exceeded: {out['qtime']}",
            },
        }
    return {**item, "ok": True, "results": out["results"]}


def batch_candidates(
    s: Session, tid: uuid.UUID, stage: str, equipment_id: uuid.UUID
) -> Row:
    """批量作业候选：该设备上可 Track In（已进站）/ Track Out（运行中）的批次，及可选腔体与配方。"""
    eq = one(s, tid, "equipment", equipment_id)
    if not eq:
        raise coded(404, ec.RECORD_NOT_FOUND, "Record not found")
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
