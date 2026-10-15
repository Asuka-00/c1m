"""撤销单位转换（P2，D41 / D42 推迟项；bom.md Q4）。

只能撤销尚未被后续作业动过的转换，规则：

- 所有子批仍是 waiting、未 Hold，履历里除 ``transform`` 外没有任何记录，也没有再分出
  下游批次（谱系里不是母批）；否则 409 ``transform_undo_blocked``，``lots`` 列出原因；
- 所有母批仍是 converted（没被别的操作动过）。

撤销在一个事务里完成：删除子批（及条单元、履历、谱系）、unit_origin、转换输出 / 输入
（坐标图引用随之释放）；转换记录本身保留（D54-2），写 ``undone_at`` / ``undone_by`` /
``undo_reason``，追溯时看得到「曾转换、已撤销」；已撤销的再撤返回 409
``transform_undo_blocked``（``lots`` 为空）。母批恢复到转换前状态（取转换时写的履历
``from_status``），晶圆 converted → waiting；载具不恢复（D54-3），履历 details 里写
``carrier_restored=false``；母批写履历 ``transform_undo``（details 留下转换快照），母批和
子批都写审计。删除时若撞上未预料的外键引用，整体回滚并返回 409。
"""

import uuid
from typing import Any

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.core.spec.audit import audit
from app.core.spec.base import conn, now
from app.core.spec.engine import TABLES
from app.core.spec.serialize import serialize
from app.mes.common.rows import _upd
from app.mes.execution.stages import LOT
from app.mes.lot.service import history, lock_lots

Row = dict[str, Any]


def _blocked(message: str, lots: list[Row], reason: str) -> HTTPException:
    """409 ``transform_undo_blocked``。

    ``reason``（D58）：``already_undone``（lots 为空）或 ``lots_blocked``（lots 逐批给出原因）。
    """
    return HTTPException(
        status_code=409,
        detail={
            "code": "transform_undo_blocked",
            "reason": reason,
            "message": message,
            "lots": lots,
        },
    )


def _referenced(s: Session, children: list[Row]) -> list[Row]:
    """子批被其他记录引用（外键 RESTRICT）时，逐批列出引用它的表（``reason=referenced``）。

    从 PG 目录找出所有引用 ``mes_lot.id`` 的外键列，再按子批 id 计数；转换本身会删的表跳过。
    """
    own = {
        "mes_lot",
        "mes_lot_history",
        "mes_lot_genealogy",
        "mes_unit_origin",
        "mes_unit_transform_output",
        "mes_unit_transform_input",
        "mes_wafer",
        "mes_audit_log",
    }
    fks = (
        conn(s)
        .execute(
            sa.text(
                """
            SELECT cl.relname AS tbl, att.attname AS col
            FROM pg_constraint c
            JOIN pg_class cl ON cl.oid = c.conrelid
            JOIN pg_class ref ON ref.oid = c.confrelid
            JOIN pg_attribute att ON att.attrelid = c.conrelid AND att.attnum = ANY (c.conkey)
            WHERE c.contype = 'f' AND ref.relname = 'mes_lot' AND c.confdeltype <> 'c'
            """
            )
        )
        .all()
    )
    out: list[Row] = []
    for c in children:
        tables = sorted(
            {
                r.tbl
                for r in fks
                if r.tbl not in own
                and conn(s)
                .execute(
                    sa.text(f'SELECT 1 FROM "{r.tbl}" WHERE "{r.col}" = :i LIMIT 1'),
                    {"i": c["id"]},
                )
                .first()
            }
        )
        if tables:
            out.append(
                {
                    "lot_id": str(c["id"]),
                    "lot_code": c["code"],
                    "reason": "referenced",
                    "tables": tables,
                }
            )
    return out


def _rows(s: Session, tid: uuid.UUID, ent: str, **eq: Any) -> list[Row]:
    t = TABLES[ent]
    q = sa.select(t).where(t.c.tenant_id == tid)
    for k, v in eq.items():
        q = q.where(t.c[k] == v)
    return [dict(r) for r in conn(s).execute(q).mappings().all()]


def undo(
    s: Session, tid: uuid.UUID, transform_id: uuid.UUID, body: Row, user: Any
) -> Row:
    """撤销一次单位转换（含 B8 按 bin 拆批），返回恢复后的母批与被删除的子批编码。"""
    tt = TABLES["unit_transform"]
    found = (
        conn(s)
        .execute(
            sa.select(tt)
            .where(tt.c.tenant_id == tid, tt.c.id == transform_id)
            .with_for_update()
        )
        .mappings()
        .first()
    )
    if not found:
        raise HTTPException(status_code=404, detail="Record not found")
    tr = dict(found)
    if tr.get("undone_at") is not None:
        raise _blocked("transform already undone", [], "already_undone")
    ins = _rows(s, tid, "unit_transform_input", unit_transform_id=transform_id)
    outs = _rows(s, tid, "unit_transform_output", unit_transform_id=transform_id)
    parent_ids = list(dict.fromkeys(x["lot_id"] for x in ins))
    child_ids = [x["lot_id"] for x in outs]
    locked = lock_lots(s, tid, [*parent_ids, *child_ids])
    parents = [locked[i] for i in parent_ids]
    children = [locked[i] for i in child_ids]
    # 子批：未动过
    h, g = TABLES["lot_history"], TABLES["lot_genealogy"]
    acted = set(
        conn(s)
        .execute(
            sa.select(h.c.lot_id).where(
                h.c.tenant_id == tid,
                h.c.lot_id.in_(child_ids),
                h.c.action != "transform",
            )
        )
        .scalars()
    )
    split = set(
        conn(s)
        .execute(
            sa.select(g.c.parent_lot_id).where(
                g.c.tenant_id == tid, g.c.parent_lot_id.in_(child_ids)
            )
        )
        .scalars()
    )
    bad: list[Row] = []
    for c in children:
        why = (
            "lot_status"
            if c["lot_status"] != "waiting"
            else "on_hold"
            if c["on_hold"]
            else "has_transactions"
            if c["id"] in acted
            else "has_descendants"
            if c["id"] in split
            else None
        )
        if why:
            bad.append({"lot_id": str(c["id"]), "lot_code": c["code"], "reason": why})
    for p in parents:
        if p["lot_status"] != "converted":
            bad.append(
                {
                    "lot_id": str(p["id"]),
                    "lot_code": p["code"],
                    "reason": "parent_status",
                }
            )
    if bad:
        raise _blocked(
            "transform cannot be undone: lots already processed", bad, "lots_blocked"
        )
    # 母批转换前状态：转换时写的 input 履历
    before: dict[Any, str] = {}
    for r in conn(s).execute(
        sa.select(h.c.lot_id, h.c.from_status, h.c.details).where(
            h.c.tenant_id == tid,
            h.c.lot_id.in_(parent_ids),
            h.c.action == "transform",
        )
    ):
        if (r.details or {}).get("transform_id") == str(transform_id):
            before[r.lot_id] = r.from_status or "waiting"
    at = now()
    snapshot = {
        "transform_id": str(transform_id),
        "transform_type": tr["transform_type"],
        "transform_at": tr["at"],
        "children": [c["code"] for c in children],
        "inputs": [
            {
                "wafer_id": str(x["wafer_id"]) if x["wafer_id"] else None,
                "substrate_map_id": str(x["substrate_map_id"])
                if x["substrate_map_id"]
                else None,
                "good_source": x["good_source"],
                "good_qty": x["good_qty"],
            }
            for x in ins
        ],
        # D54-3：撤销不恢复载具，P3 再评估
        "carrier_restored": False,
        "note": "carrier not restored|载具未恢复|キャリアは復元されません",
    }
    reason = body.get("comment")
    if body.get("reason_id"):
        rc = TABLES["reason_code"]
        code = (
            conn(s)
            .execute(
                sa.select(rc.c.code).where(
                    rc.c.tenant_id == tid, rc.c.id == body["reason_id"]
                )
            )
            .scalar()
        )
        if code:
            reason = f"{code}: {reason}" if reason else code
    try:
        for c in children:
            audit(s, tid, LOT, "transform_undo", c, user, {"lot": (c["code"], None)})
        uo = TABLES["unit_origin"]
        conn(s).execute(
            sa.delete(uo).where(
                uo.c.tenant_id == tid, uo.c.unit_transform_id == transform_id
            )
        )
        for ent in ("unit_transform_output", "unit_transform_input"):
            t = TABLES[ent]
            conn(s).execute(
                sa.delete(t).where(
                    t.c.tenant_id == tid, t.c.unit_transform_id == transform_id
                )
            )
        conn(s).execute(
            sa.delete(g).where(
                g.c.tenant_id == tid,
                g.c.child_lot_id.in_(child_ids),
                g.c.relation == "transform",
            )
        )
        lt = TABLES["lot"]
        if child_ids:
            conn(s).execute(
                sa.delete(lt).where(lt.c.tenant_id == tid, lt.c.id.in_(child_ids))
            )
        conn(s).execute(
            sa.update(tt)
            .where(tt.c.tenant_id == tid, tt.c.id == transform_id)
            .values(
                undone_at=at,
                undone_by=getattr(user, "username", None) or str(user.id),
                undo_reason=(reason or "")[:300] or None,
                updated_at=at,
            )
        )
        wt = TABLES["wafer"]
        for p in parents:
            old = before.get(p["id"], "waiting")
            conn(s).execute(
                sa.update(wt)
                .where(
                    wt.c.tenant_id == tid,
                    wt.c.lot_id == p["id"],
                    wt.c.wafer_status == "converted",
                )
                .values(wafer_status="waiting", updated_at=at)
            )
            _upd(s, tid, "lot", p["id"], user, lot_status=old, completed_at=None)
            p.update(lot_status=old)
            history(
                s,
                tid,
                p,
                "transform_undo",
                user,
                from_status="converted",
                reason_id=body.get("reason_id"),
                comment=body.get("comment"),
                details=snapshot,
            )
            audit(
                s,
                tid,
                LOT,
                "transform_undo",
                p,
                user,
                {"lot_status": ("converted", old)},
            )
        s.flush()
    except IntegrityError:
        s.rollback()
        # 之前 lots 为空：只回滚不定位。现在查出是哪个子批被哪张表引用（D58）
        refs = _referenced(s, children)
        s.rollback()
        raise _blocked(
            "transform cannot be undone: child lots are referenced by other records",
            refs
            or [
                {"lot_id": str(c["id"]), "lot_code": c["code"], "reason": "referenced"}
                for c in children
            ],
            "lots_blocked",
        ) from None
    s.commit()
    lt = TABLES["lot"]
    rows = [
        dict(r)
        for r in conn(s)
        .execute(sa.select(lt).where(lt.c.tenant_id == tid, lt.c.id.in_(parent_ids)))
        .mappings()
    ]
    return {
        "transform_id": str(transform_id),
        "transform_type": tr["transform_type"],
        "parents": serialize(s, tid, LOT, rows),
        "removed_children": [c["code"] for c in children],
        "undone_at": at.isoformat().replace("+00:00", "Z"),
        "undone_by": getattr(user, "username", None) or str(user.id),
        "undo_reason": (reason or "")[:300] or None,
        "carrier_restored": False,
    }
