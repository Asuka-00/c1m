"""工程变更（ECN）：发布、按生效时间生效、在制批次版本规则。

生效时：激活新版本（同编码旧版本失效），并把引用旧版本的主数据
（产品流程绑定、Q-Time 规则、检查绑定、工步资源、参数规格、设备能力等）改指新版本；
流程变更的工步引用按工步序号映射。

在制规则（仅流程变更）：
- ``keep_old``：在制批次与未完工单沿用旧版本；
- ``switch_new``：未完工单改用新版本；等待中的顶层批次按序号切换到新版本对应工步，
  已进站 / 加工中或位于子流程的批次保持旧版本（结果中列出）。
配方变更：后续 Track In 使用新版本，已进站批次按其参数快照完成。
"""

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from fastapi import HTTPException
from sqlmodel import Session

from app.core.spec.audit import audit
from app.core.spec.base import conn, now
from app.core.spec.engine import ENTITIES, TABLES, Entity
from app.core.spec.errors import MesError, err_422
from app.core.spec.validate import validator
from app.core.spec.write import set_status
from app.mes.common.query import find, one

Row = dict[str, Any]
#: 不随变更改指的实体（批次 / 工单由在制规则处理，变更单本身记录目标版本）
SKIP = {"lot", "work_order", "change_order", "lot_recipe_run"}
OPEN_WO = ("draft", "released", "in_progress", "on_hold")


def _repoint(
    s: Session, tid: uuid.UUID, target: str, ids: dict[Any, Any], skip: set[str]
) -> int:
    """把非级联引用 ``target`` 的字段从旧 id 改为新 id，返回改动行数。"""
    n = 0
    for e in ENTITIES.values():
        if e.code in skip or e.readonly or e.code not in TABLES:
            continue
        t = TABLES[e.code]
        for f in e.all_fields:
            if f.type != "ref" or f.ref != target or f.cascade:
                continue
            col = t.c[f.column]
            for old, new in ids.items():
                n += (
                    conn(s)
                    .execute(
                        sa.update(t)
                        .where(t.c.tenant_id == tid, col == old)
                        .values({f.column: new, "updated_at": now()})
                    )
                    .rowcount
                )
    return n


def _step_map(s: Session, tid: uuid.UUID, olds: list[Row], new: Row) -> dict[Any, Any]:
    """旧版本工步 id -> 新版本同序号工步 id。"""
    by_seq = {x["seq"]: x["id"] for x in find(s, tid, "route_step", route_id=new["id"])}
    out = {}
    for o in olds:
        for x in find(s, tid, "route_step", route_id=o["id"]):
            if x["seq"] in by_seq:
                out[x["id"]] = by_seq[x["seq"]]
    return out


def _activate(s: Session, tid: uuid.UUID, code: str, row: Row, user: Any) -> None:
    if row["status"] == "inactive":
        raise HTTPException(409, f"{code} version {row['version']} is inactive")
    if row["status"] == "draft":
        set_status(s, tid, ENTITIES[code], row["id"], "active", user)


def apply(s: Session, tid: uuid.UUID, co: Row, user: Any) -> Row:
    """执行变更（调用方提交）：激活新版本、改指引用、处理在制，返回执行结果。"""
    kind = co["change_type"]
    new = one(s, tid, kind, co[f"{kind}_id"])
    if not new:
        raise err_422(
            ["body", f"{kind}_id"],
            f"{kind} not found",
            "ref_not_found",
            {"entity": kind},
        )
    olds = [
        r
        for r in find(s, tid, kind)
        if r["code"] == new["code"] and r["id"] != new["id"]
    ]
    _activate(s, tid, kind, new, user)
    ids = {o["id"]: new["id"] for o in olds}
    res: Row = {"version": new["version"], "switched": [], "kept": []}
    if kind == "recipe":
        res["refs"] = _repoint(s, tid, "recipe", ids, SKIP)
    else:
        steps = _step_map(s, tid, olds, new)
        res["refs"] = _repoint(s, tid, "route", ids, SKIP) + _repoint(
            s, tid, "route_step", steps, SKIP | {"route_step"}
        )
        if co["wip_rule"] == "switch_new":
            _switch_wip(s, tid, ids, steps, new, user, res)
        else:
            res["kept"] = [
                x["code"]
                for o in olds
                for x in find(s, tid, "lot", route_id=o["id"])
                if x["lot_status"] in ("waiting", "moved_in", "running", "tracked_out")
            ]
    return res


def _switch_wip(
    s: Session,
    tid: uuid.UUID,
    ids: dict[Any, Any],
    steps: dict[Any, Any],
    new: Row,
    user: Any,
    res: Row,
) -> None:
    wt, lt = TABLES["work_order"], TABLES["lot"]
    for old in ids:
        conn(s).execute(
            sa.update(wt)
            .where(
                wt.c.tenant_id == tid,
                wt.c.route_id == old,
                wt.c.wo_status.in_(OPEN_WO),
            )
            .values(route_id=new["id"], route_version=new["version"], updated_at=now())
        )
        for x in find(s, tid, "lot", route_id=old):
            if x["lot_status"] not in ("waiting", "moved_in", "running", "tracked_out"):
                continue
            to = steps.get(x["current_step_id"])
            if x["lot_status"] != "waiting" or x["route_stack"] or not to:
                res["kept"].append(x["code"])
                continue
            conn(s).execute(
                sa.update(lt)
                .where(lt.c.id == x["id"])
                .values(route_id=new["id"], current_step_id=to, updated_at=now())
            )
            audit(
                s,
                tid,
                ENTITIES["lot"],
                "update",
                x,
                user,
                {"route_id": (str(old), str(new["id"]))},
            )
            res["switched"].append(x["code"])


def release(s: Session, tid: uuid.UUID, cid: Any, user: Any) -> Row:
    """发布变更单：生效时间已到（或未填）立即生效，否则待定时扫描生效。"""
    co = one(s, tid, "change_order", cid)
    if not co:
        raise HTTPException(404, "change order not found")
    if co["ecn_status"] != "draft":
        raise HTTPException(409, f"change order is {co['ecn_status']}")
    _set(s, tid, co, user, ecn_status="released")
    if not co["effective_at"] or co["effective_at"] <= now():
        _apply_one(s, tid, co, user)
    s.commit()
    return one(s, tid, "change_order", cid) or {}


def cancel(s: Session, tid: uuid.UUID, cid: Any, user: Any) -> Row:
    """取消未生效的变更单。"""
    co = one(s, tid, "change_order", cid)
    if not co:
        raise HTTPException(404, "change order not found")
    if co["ecn_status"] not in ("draft", "released"):
        raise HTTPException(409, f"change order is {co['ecn_status']}")
    _set(s, tid, co, user, ecn_status="cancelled")
    s.commit()
    return one(s, tid, "change_order", cid) or {}


def _set(s: Session, tid: uuid.UUID, co: Row, user: Any, **vals: Any) -> None:
    t = TABLES["change_order"]
    conn(s).execute(
        sa.update(t).where(t.c.id == co["id"]).values(**vals, updated_at=now())
    )
    audit(
        s,
        tid,
        ENTITIES["change_order"],
        "update",
        co,
        user,
        {k: (str(co.get(k)), str(v)) for k, v in vals.items() if k != "result"},
    )


def _apply_one(s: Session, tid: uuid.UUID, co: Row, user: Any) -> None:
    res = apply(s, tid, co, user)
    _set(s, tid, co, user, ecn_status="applied", applied_at=now(), result=res)


def apply_due(s: Session, tid: uuid.UUID, at: datetime | None = None) -> int:
    """定时扫描：生效时间已到的已发布变更单逐个生效，返回生效数。"""
    at = at or now()
    n = 0
    for co in find(s, tid, "change_order", order="effective_at", ecn_status="released"):
        if co["effective_at"] and co["effective_at"] <= at:
            _apply_one(s, tid, co, None)
            n += 1
    return n


@validator("change_order")
def _co_save(_s: Session, _t: uuid.UUID, _e: Entity, row: Row, old: Row | None) -> None:
    """已发布的变更单不可修改；目标版本须与变更对象一致。"""
    if old and old["ecn_status"] != "draft":
        raise MesError([("ecn_status", "only draft change orders can be edited")])
    kind = row.get("change_type")
    other = "recipe" if kind == "route" else "route"
    if row.get(f"{other}_id"):
        raise MesError([(other, f"{other}: not used for a {kind} change")])


@validator("change_order:delete")
def _co_delete(
    _s: Session, _t: uuid.UUID, _e: Entity, row: Row, _o: Row | None
) -> None:
    if row["ecn_status"] not in ("draft", "cancelled"):
        raise MesError(
            [("ecn_status", "only draft or cancelled orders can be deleted")]
        )
