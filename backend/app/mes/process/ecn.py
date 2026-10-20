"""工程变更（ECN）：发布、按生效时间生效、在制批次版本规则。

生效时：激活新版本（同编码旧版本失效），并把引用旧版本的主数据
（产品流程绑定、Q-Time 规则、检查绑定、工步资源、参数规格、设备能力等）改指新版本；
流程变更的工步引用按工步序号映射。

在制规则（仅流程变更）：
- ``keep_old``：在制批次与未完工单沿用旧版本；
- ``switch_new``：未完工单改用新版本；等待中的顶层批次按序号切换到新版本对应工步，
  已进站 / 加工中或位于子流程的批次保持旧版本（结果中列出）。
旧版本仍在使用（``keep_old``，或有批次保持旧版本）时，工步级配置（检查绑定、Q-Time 规则）
复制一份给新版本，旧版本保留原配置；否则直接改指。预约 Hold 按批次处理：只随切换到新版本的批次改指。
配方变更：后续 Track In 使用新版本，已进站批次按其参数快照完成。
"""

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlmodel import Session

from app.core import error_codes as ec
from app.core.spec.audit import audit
from app.core.spec.base import conn, now
from app.core.spec.engine import ENTITIES, TABLES, Entity, F
from app.core.spec.errors import MesError, coded, fe
from app.core.spec.validate import validator
from app.core.spec.write import set_status
from app.mes.common.query import find, one

Row = dict[str, Any]
#: 不随变更改指的实体（批次 / 工单 / 预约 Hold 由在制规则处理，变更单本身记录目标版本）
SKIP = {"lot", "work_order", "change_order", "lot_recipe_run", "future_hold"}
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
        raise coded(
            409,
            ec.VERSION_INACTIVE,
            f"{code} version {row['version']} is inactive",
            entity=code,
            version=row["version"],
        )
    if row["status"] == "draft":
        set_status(s, tid, ENTITIES[code], row["id"], "active", user)


def apply(s: Session, tid: uuid.UUID, co: Row, user: Any) -> Row:
    """执行变更（调用方提交）：激活新版本、改指引用、处理在制，返回执行结果。"""
    kind = co["change_type"]
    new = one(s, tid, kind, co[f"{kind}_id"])
    if not new:
        raise coded(422, ec.ECN_TARGET_NOT_FOUND, f"{kind} not found", entity=kind)
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
        if co["wip_rule"] == "switch_new":
            _switch_wip(s, tid, ids, steps, new, user, res)
        else:
            res["kept"] = [
                x["code"]
                for o in olds
                for x in find(s, tid, "lot", route_id=o["id"])
                if x["lot_status"] in ("waiting", "moved_in", "running", "tracked_out")
            ]
        # 配置只从被替换的现行版本（无则取最高旧版本）转给新版本；更早版本的配置
        # 只服务于仍在其上的批次，保持不动（否则多个旧版本会同时改指到同一工步）
        src = next((o for o in olds if o["status"] == "active"), None) or max(
            olds, key=lambda o: o["version"], default=None
        )
        src_ids = {src["id"]: new["id"]} if src else {}
        src_steps = _step_map(s, tid, [src], new) if src else {}
        skip = SKIP | {"route_step"}
        if co["wip_rule"] != "switch_new" or res["kept"]:
            # 旧版本仍在使用：工步级配置复制给新版本，旧版本保留原配置
            res["copied"] = _copy_step_config(s, tid, src_ids, src_steps, new, user)
            skip |= set(_step_config())
        res["refs"] = _repoint(s, tid, "route", src_ids, skip) + _repoint(
            s, tid, "route_step", src_steps, skip
        )
    return res


def _step_config() -> dict[str, list[F]]:
    """引用工步的配置实体及其工步引用字段（批次 / 履历等只读记录与 SKIP 除外）。"""
    out: dict[str, list[F]] = {}
    for e in ENTITIES.values():
        if e.code in SKIP | {"route_step"} or e.readonly or e.code not in TABLES:
            continue
        fs = [
            f
            for f in e.all_fields
            if f.type == "ref" and f.ref == "route_step" and not f.cascade
        ]
        if fs:
            out[e.code] = fs
    return out


def _copy_code(s: Session, tid: uuid.UUID, t: sa.Table, code: str, ver: int) -> str:
    """复制行的新编码：``<原编码>-V<新版本号>``（超长时截短原编码，重复时追加序号）。"""
    size = getattr(t.c.code.type, "length", None) or 64
    for i in range(1, 100):
        tail = f"-V{ver}" if i == 1 else f"-V{ver}-{i}"
        cand = code[: size - len(tail)] + tail
        hit = conn(s).execute(
            sa.select(t.c.id).where(t.c.tenant_id == tid, t.c.code == cand)
        )
        if hit.first() is None:
            return cand
    raise coded(
        409,
        ec.COPY_CODE_CONFLICT,
        f"cannot derive a unique code from {code}",
        code=code,
    )


def _copy_step_config(
    s: Session,
    tid: uuid.UUID,
    routes: dict[Any, Any],
    steps: dict[Any, Any],
    new: Row,
    user: Any,
) -> int:
    """把引用旧版本工步的配置行复制一份，改指新版本对应工步（及流程），返回复制行数。

    新版本中找不到对应工步（按序号）的配置不复制。
    """
    n = 0
    uid = getattr(user, "id", None)
    for code, fs in _step_config().items():
        e, t = ENTITIES[code], TABLES[code]
        cols = [t.c[f.column] for f in fs]
        rows = (
            conn(s)
            .execute(
                sa.select(t).where(
                    t.c.tenant_id == tid, sa.or_(*(c.in_(list(steps)) for c in cols))
                )
            )
            .mappings()
            .all()
        )
        for r in rows:
            if any(r[c.name] is not None and r[c.name] not in steps for c in cols):
                continue
            vals = {
                **r,
                "id": uuid.uuid4(),
                "created_at": now(),
                "updated_at": now(),
                "created_by": uid,
                "updated_by": uid,
            }
            for f in e.all_fields:
                if f.type != "ref" or f.cascade or vals.get(f.column) is None:
                    continue
                if f.ref == "route_step":
                    vals[f.column] = steps[vals[f.column]]
                elif f.ref == "route":
                    vals[f.column] = routes.get(vals[f.column], vals[f.column])
            if _exists(s, tid, e, t, vals):
                continue
            if e.has_code:
                vals["code"] = _copy_code(s, tid, t, r["code"], new["version"])
            conn(s).execute(sa.insert(t).values(**vals))
            n += 1
    return n


def _exists(s: Session, tid: uuid.UUID, e: Entity, t: sa.Table, vals: Row) -> bool:
    """新版本上是否已有等同配置：按实体唯一键比较，无唯一键时按全部引用字段比较。"""
    keys = (
        [list(u) for u in e.unique]
        if e.unique
        else [[f.name for f in e.all_fields if f.type == "ref"]]
    )
    for names in keys:
        cols = [t.c[fd.column] for n in names if (fd := e.field(n))]
        q = sa.select(t.c.id).where(
            t.c.tenant_id == tid,
            *(c.is_(None) if vals[c.name] is None else c == vals[c.name] for c in cols),
        )
        if conn(s).execute(q).first() is not None:
            return True
    return False


def _switch_wip(
    s: Session,
    tid: uuid.UUID,
    ids: dict[Any, Any],
    steps: dict[Any, Any],
    new: Row,
    user: Any,
    res: Row,
) -> None:
    wt, lt, fh_t = TABLES["work_order"], TABLES["lot"], TABLES["future_hold"]
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
            # 该批次待触发的预约 Hold 随批次改指新版本对应工步
            for fh in find(s, tid, "future_hold", lot_id=x["id"], fh_status="active"):
                if fh["route_step_id"] in steps:
                    conn(s).execute(
                        sa.update(fh_t)
                        .where(fh_t.c.id == fh["id"])
                        .values(
                            route_step_id=steps[fh["route_step_id"]], updated_at=now()
                        )
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
        raise coded(404, ec.CHANGE_ORDER_NOT_FOUND, "change order not found")
    if co["ecn_status"] != "draft":
        raise coded(
            409,
            ec.ECN_STATUS,
            f"change order is {co['ecn_status']}",
            status=co["ecn_status"],
        )
    _set(s, tid, co, user, ecn_status="released")
    if not co["effective_at"] or co["effective_at"] <= now():
        _apply_one(s, tid, co, user)
    s.commit()
    return one(s, tid, "change_order", cid) or {}


def cancel(s: Session, tid: uuid.UUID, cid: Any, user: Any) -> Row:
    """取消未生效的变更单。"""
    co = one(s, tid, "change_order", cid)
    if not co:
        raise coded(404, ec.CHANGE_ORDER_NOT_FOUND, "change order not found")
    if co["ecn_status"] not in ("draft", "released"):
        raise coded(
            409,
            ec.ECN_STATUS,
            f"change order is {co['ecn_status']}",
            status=co["ecn_status"],
        )
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
        raise MesError(
            [
                fe(
                    "ecn_status",
                    ec.ECN_NOT_EDITABLE,
                    "only draft change orders can be edited",
                )
            ]
        )
    kind = row.get("change_type")
    other = "recipe" if kind == "route" else "route"
    if row.get(f"{other}_id"):
        raise MesError(
            [
                fe(
                    other,
                    ec.ECN_FIELD_UNUSED,
                    f"{other}: not used for a {kind} change",
                    entity=other,
                    kind=kind,
                )
            ]
        )


@validator("change_order:delete")
def _co_delete(
    _s: Session, _t: uuid.UUID, _e: Entity, row: Row, _o: Row | None
) -> None:
    if row["ecn_status"] not in ("draft", "cancelled"):
        raise MesError(
            [
                fe(
                    "ecn_status",
                    ec.ECN_NOT_DELETABLE,
                    "only draft or cancelled orders can be deleted",
                )
            ]
        )
