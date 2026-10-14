"""BOM 服务（D28，bom.md v1.1）：生效 / 作废、复制为新版本、两级树、开批锁定版本。

- 同一产品同时只有一个 active（部分唯一索引兜底）；新版本生效时旧 active 变 superseded。
- 生效前校验：至少一条明细；展开深度 ≤ ``MAX_BOM_DEPTH`` 且无循环引用（含引用了本产品的
  上层 BOM）。
- 开批锁定当时生效的版本；没有时锁空，开关 ``bom_required``（检查规则，默认关）打开时拒绝。
"""

import uuid
from typing import Any

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.core.models import actor_name
from app.core.spec.audit import audit
from app.core.spec.base import conn, now
from app.core.spec.engine import ENTITIES, TABLES, Entity
from app.core.spec.errors import http_422
from app.core.spec.serialize import serialize
from app.core.spec.validate import validator
from app.mes.common.query import find, one
from app.mes.common.rows import _ins
from app.mes.product.bom_specs import MAX_BOM_DEPTH
from app.mes.product.bom_validators import next_version

Row = dict[str, Any]
# 检查规则类型：开批必须有生效 BOM（无规则或严重度 off 时关闭）
REQUIRE_CHECK = "bom_required"


def _bom(s: Session, tid: uuid.UUID, bom_id: Any, lock: bool = False) -> Row:
    t = TABLES["bom"]
    q = sa.select(t).where(t.c.tenant_id == tid, t.c.id == bom_id)
    if lock:
        q = q.with_for_update()
    r = conn(s).execute(q).mappings().first()
    if not r:
        raise HTTPException(status_code=404, detail="Record not found")
    return dict(r)


def active_bom(s: Session, tid: uuid.UUID, product_id: Any) -> Row | None:
    """产品当前生效的 BOM，没有时 None。"""
    if product_id is None:
        return None
    rows = find(s, tid, "bom", product_id=product_id, status="active")
    return rows[0] if rows else None


def bom_brief(s: Session, tid: uuid.UUID, bom_id: Any) -> Row | None:
    """``{id, version, status, product}``，用于报错与履历。"""
    b = one(s, tid, "bom", bom_id) if bom_id else None
    if not b:
        return None
    p = one(s, tid, "product", b["product_id"])
    return {
        "id": str(b["id"]),
        "version": b["version"],
        "status": b["status"],
        "product": p and p["code"],
    }


def _lines(s: Session, tid: uuid.UUID, bom_id: Any) -> list[Row]:
    return find(s, tid, "bom_line", order="line_no", bom_id=bom_id)


# ---------------- depth / cycle ----------------
def _depth(
    s: Session,
    tid: uuid.UUID,
    product_id: Any,
    override: dict[Any, Any],
    path: tuple[Any, ...],
) -> int:
    """从 ``product_id`` 展开的 BOM 层数（无 BOM 为 0）。``override`` 指定某产品用哪个 BOM。

    Raises:
        HTTPException: 循环引用（422）。
    """
    if product_id in path:
        codes = [_pcode(s, tid, p) for p in (*path, product_id)]
        raise http_422([("bom", f"bom: circular reference {' → '.join(codes)}")])
    if product_id in override:
        bom_id = override[product_id]
    else:
        act = active_bom(s, tid, product_id)
        bom_id = act and act["id"]
    if not bom_id:
        return 0
    kids = [
        ln["component_product_id"]
        for ln in _lines(s, tid, bom_id)
        if ln["component_type"] == "product" and ln["component_product_id"]
    ]
    sub = [_depth(s, tid, k, override, (*path, product_id)) for k in kids]
    return 1 + max(sub, default=0)


def _pcode(s: Session, tid: uuid.UUID, product_id: Any) -> str:
    p = one(s, tid, "product", product_id)
    return f"{p['code']} v{p['version']}" if p else str(product_id)


def _users_of(s: Session, tid: uuid.UUID, product_id: Any) -> set[Any]:
    """引用了该产品作半成品的 active BOM 所属产品（递归向上）。"""
    b, ln = TABLES["bom"], TABLES["bom_line"]
    out: set[Any] = set()
    todo = [product_id]
    while todo and len(out) < 1000:
        cur = todo.pop()
        for pid in (
            conn(s)
            .execute(
                sa.select(b.c.product_id)
                .join(ln, ln.c.bom_id == b.c.id)
                .where(
                    b.c.tenant_id == tid,
                    b.c.status == "active",
                    ln.c.component_product_id == cur,
                )
            )
            .scalars()
        ):
            if pid not in out and pid != product_id:
                out.add(pid)
                todo.append(pid)
    return out


def check_structure(s: Session, tid: uuid.UUID, bom: Row) -> None:
    """生效前校验：深度 ≤ MAX_BOM_DEPTH、无循环（本产品及引用它的上层产品）。

    Raises:
        HTTPException: 超深或循环（422）。
    """
    override = {bom["product_id"]: bom["id"]}
    for pid in [bom["product_id"], *_users_of(s, tid, bom["product_id"])]:
        d = _depth(s, tid, pid, override, ())
        if d > MAX_BOM_DEPTH:
            raise http_422(
                [
                    (
                        "bom",
                        f"bom: {_pcode(s, tid, pid)} would expand to {d} levels "
                        f"(max {MAX_BOM_DEPTH})",
                    )
                ]
            )


# ---------------- lifecycle ----------------
def activate(s: Session, tid: uuid.UUID, bom_id: uuid.UUID, user: Any) -> Row:
    """草稿 → 生效：记确认人 / 时间，旧 active 版本改为 superseded。

    Raises:
        HTTPException: 非草稿（409）；无明细、超深或循环（422）。
    """
    head = _bom(s, tid, bom_id)
    # 同产品的全部 BOM 行加锁，串行化并发生效
    t = TABLES["bom"]
    conn(s).execute(
        sa.select(t.c.id)
        .where(t.c.tenant_id == tid, t.c.product_id == head["product_id"])
        .with_for_update()
    ).all()
    bom = _bom(s, tid, bom_id)
    if bom["status"] != "draft":
        raise HTTPException(
            status_code=409,
            detail=f"BOM v{bom['version']} is {bom['status']}; only drafts can be activated",
        )
    if not _lines(s, tid, bom_id):
        raise http_422([("bom_line", "bom_line: a BOM needs at least one line")])
    check_structure(s, tid, bom)
    at = now()
    old = active_bom(s, tid, bom["product_id"])
    c = conn(s)
    try:
        with s.begin_nested():
            if old:
                c.execute(
                    sa.update(t)
                    .where(t.c.id == old["id"])
                    .values(
                        status="superseded",
                        updated_at=at,
                        updated_by=getattr(user, "id", None),
                    )
                )
                audit(
                    s,
                    tid,
                    ENTITIES["bom"],
                    "status",
                    old,
                    user,
                    {"status": ("active", "superseded")},
                )
            c.execute(
                sa.update(t)
                .where(t.c.id == bom_id)
                .values(
                    status="active",
                    effective_at=at,
                    confirmed_by=actor_name(user),
                    confirmed_at=at,
                    updated_at=at,
                    updated_by=getattr(user, "id", None),
                )
            )
    except IntegrityError as ex:  # 并发生效被部分唯一索引拦下
        raise HTTPException(
            status_code=409, detail="another BOM version was activated concurrently"
        ) from ex
    new = _bom(s, tid, bom_id)
    audit(
        s,
        tid,
        ENTITIES["bom"],
        "activate",
        new,
        user,
        {
            "status": ("draft", "active"),
            "superseded": (None, old and old["version"]),
        },
    )
    s.commit()
    return new


def void(s: Session, tid: uuid.UUID, bom_id: uuid.UUID, user: Any) -> Row:
    """草稿或生效版本 → 作废。已锁定该版本的批次不受影响。

    Raises:
        HTTPException: 已替代 / 已作废（409）。
    """
    bom = _bom(s, tid, bom_id, lock=True)
    if bom["status"] not in ("draft", "active"):
        raise HTTPException(
            status_code=409, detail=f"BOM v{bom['version']} is already {bom['status']}"
        )
    t = TABLES["bom"]
    conn(s).execute(
        sa.update(t)
        .where(t.c.id == bom_id)
        .values(status="void", updated_at=now(), updated_by=getattr(user, "id", None))
    )
    new = _bom(s, tid, bom_id)
    audit(
        s, tid, ENTITIES["bom"], "void", new, user, {"status": (bom["status"], "void")}
    )
    s.commit()
    return new


_SKIP = {"id", "tenant_id", "created_at", "updated_at", "created_by", "updated_by"}


def _clone(
    s: Session, tid: uuid.UUID, src: Row, product_id: Any, user: Any
) -> uuid.UUID:
    """把 ``src`` 复制为 ``product_id`` 的下一个草稿版本（含明细与替代料），返回新 id。"""
    t = TABLES["bom"]
    # 目标产品加锁，避免并发复制拿到同一版本号
    conn(s).execute(
        sa.select(t.c.id)
        .where(t.c.tenant_id == tid, t.c.product_id == product_id)
        .with_for_update()
    ).all()
    nid = _ins(
        s,
        tid,
        "bom",
        user,
        product_id=product_id,
        version=next_version(s, tid, product_id),
        status="draft",
        copied_from_id=src["id"],
        description=src["description"],
        attrs=src["attrs"],
    )
    for ln in _lines(s, tid, src["id"]):
        lid = _ins(
            s,
            tid,
            "bom_line",
            user,
            **{k: v for k, v in ln.items() if k not in _SKIP and k != "bom_id"},
            bom_id=nid,
        )
        for sub in find(s, tid, "bom_line_substitute", bom_line_id=ln["id"]):
            _ins(
                s,
                tid,
                "bom_line_substitute",
                user,
                **{
                    k: v
                    for k, v in sub.items()
                    if k not in _SKIP and k != "bom_line_id"
                },
                bom_line_id=lid,
            )
    return nid


def copy(s: Session, tid: uuid.UUID, bom_id: uuid.UUID, user: Any) -> Row:
    """复制为同产品的下一个草稿版本（含明细与替代料）。"""
    src = _bom(s, tid, bom_id)
    new = _bom(s, tid, _clone(s, tid, src, src["product_id"], user))
    audit(
        s,
        tid,
        ENTITIES["bom"],
        "copy",
        new,
        user,
        {"version": (src["version"], new["version"])},
    )
    s.commit()
    return new


@validator("product:new_version")
def _product_new_version(
    s: Session, tid: uuid.UUID, _e: Entity, new: Row, old: Row | None
) -> None:
    """产品出新版本：把旧版本当前生效的 BOM 复制成新版本下的草稿（bom.md §11）。"""
    src = old and active_bom(s, tid, old["id"])
    if not src or not old:
        return
    actor = new.get("_user")
    nb = _bom(s, tid, _clone(s, tid, src, new["id"], actor))
    audit(
        s,
        tid,
        ENTITIES["bom"],
        "copy",
        nb,
        actor,
        {
            "copied_from": (
                None,
                f"{old.get('code')} v{old.get('version')} BOM v{src['version']}",
            )
        },
    )


# ---------------- tree ----------------
def _node(s: Session, tid: uuid.UUID, bom: Row | None, level: int) -> Row:
    if not bom:
        return {"bom": None, "lines": []}
    lines = _lines(s, tid, bom["id"])
    subs = {
        ln["id"]: serialize(
            s,
            tid,
            ENTITIES["bom_line_substitute"],
            find(s, tid, "bom_line_substitute", order="priority", bom_line_id=ln["id"]),
        )
        for ln in lines
    }
    out = []
    for ln, js in zip(
        lines, serialize(s, tid, ENTITIES["bom_line"], lines), strict=True
    ):
        js["substitutes"] = subs[ln["id"]]
        js["child"] = None
        if ln["component_type"] == "product" and level < MAX_BOM_DEPTH:
            act = active_bom(s, tid, ln["component_product_id"])
            js["child"] = _node(s, tid, act, level + 1)
        out.append(js)
    return {
        "bom": serialize(s, tid, ENTITIES["bom"], [bom])[0],
        "level": level,
        "lines": out,
    }


def tree(s: Session, tid: uuid.UUID, product_id: Any = None, bom_id: Any = None) -> Row:
    """两级树：指定版本（``bom_id``）或产品当前生效版本；半成品行展开它的生效版本（只读）。

    Raises:
        HTTPException: 两个参数都没给（422）或 BOM 不存在（404）。
    """
    if bom_id:
        bom: Row | None = _bom(s, tid, bom_id)
    elif product_id:
        bom = active_bom(s, tid, product_id)
    else:
        raise http_422([("product_id", "product_id or bom_id: required")])
    return _node(s, tid, bom, 1)


# ---------------- lots ----------------
def required(s: Session, tid: uuid.UUID) -> str:
    """开关档位（D1）：``off`` 不检查 / ``warn`` 放行并提示 / ``block`` 拒绝开批。

    取 ``bom_required`` 检查规则的第一条有效规则的严重度；没有规则视为 ``off``。
    """
    for r in find(
        s, tid, "check_rule", order="code", check_type=REQUIRE_CHECK, is_active=True
    ):
        return "block" if r["severity"] == "block" else str(r["severity"] or "off")
    return "off"


def lock_for_start(s: Session, tid: uuid.UUID, product_id: Any) -> Row | None:
    """开批时取当前生效版本（加共享锁，防止开批过程中被替代）。

    Raises:
        HTTPException: 开关为 block 且产品没有生效 BOM（422）；warn / off 放行，由调用方
            返回 ``no_active_bom`` 提示。
    """
    t = TABLES["bom"]
    r = (
        conn(s)
        .execute(
            sa.select(t)
            .where(
                t.c.tenant_id == tid,
                t.c.product_id == product_id,
                t.c.status == "active",
            )
            .with_for_update(read=True)
        )
        .mappings()
        .first()
    )
    if r is None and required(s, tid) == "block":
        raise http_422(
            [("bom", f"bom: {_pcode(s, tid, product_id)} has no active BOM")]
        )
    return dict(r) if r else None


def version_label(s: Session, tid: uuid.UUID, bom_id: Any) -> str:
    """报错用：``v3`` 或 ``none``。"""
    b = one(s, tid, "bom", bom_id) if bom_id else None
    return f"v{b['version']}" if b else "none"
