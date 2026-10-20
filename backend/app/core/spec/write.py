"""通用写操作：新增 / 更新 / 删除、状态迁移、版本化。"""

import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.core import error_codes as ec
from app.core.spec.audit import audit, diff
from app.core.spec.base import Row, conn, now, table
from app.core.spec.engine import (
    ENTITIES,
    STATUS_TRANSITIONS,
    STATUSES,
    Entity,
)
from app.core.spec.errors import MesError, coded, fe, http_422, integrity
from app.core.spec.query import get_row
from app.core.spec.validate import VALIDATORS, check_editable, locking_parent, validate


# ---------------- writes ----------------
def create_row(
    session: Session,
    tenant_id: uuid.UUID,
    e: Entity,
    data: Row,
    user: Any,
    *,
    commit: bool = True,
) -> Row:
    """新增一行（校验 → 插入 → 审计）。

    Args:
        session: 数据库会话。
        tenant_id: 租户 id。
        e: 实体规格。
        data: 载荷。
        user: 操作人。
        commit: 是否提交事务。

    Returns:
        序列化后的新行。
    """
    if e.readonly:
        raise coded(405, ec.READ_ONLY_ENTITY, "Read-only entity")
    values = validate(session, tenant_id, e, data, None)
    lp = locking_parent(session, tenant_id, e, values)
    if lp and lp[1]["status"] != "draft":
        raise coded(
            409,
            ec.PARENT_NOT_DRAFT,
            f"Parent {lp[0].code} is not a draft",
            entity=lp[0].code,
        )
    rid = uuid.uuid4()
    values.update(
        id=rid,
        tenant_id=tenant_id,
        created_at=now(),
        updated_at=now(),
        created_by=getattr(user, "id", None),
        updated_by=getattr(user, "id", None),
    )
    if e.versioned:
        values["version"] = (
            int(data["version"])
            if data.get("version")
            else _next_version(session, tenant_id, e, values.get("code"))
        )
        values["status"] = "draft"
    try:
        with session.begin_nested():
            conn(session).execute(sa.insert(table(e)).values(**values))
    except IntegrityError as ex:
        raise integrity(ex) from ex
    row = get_row(session, e, tenant_id, rid)
    audit(
        session,
        tenant_id,
        e,
        "create",
        row,
        user,
        diff(None, {k: v for k, v in row.items() if k != "tenant_id"}),
    )
    if commit:
        session.commit()
    return row


def update_row(
    session: Session,
    tenant_id: uuid.UUID,
    e: Entity,
    rid: uuid.UUID,
    data: Row,
    user: Any,
    *,
    commit: bool = True,
    action: str = "update",
) -> Row:
    """更新一行（锁定检查 → 校验 → 更新 → 审计差异）。

    Args:
        session: 数据库会话。
        tenant_id: 租户 id。
        e: 实体规格。
        rid: 行 id。
        data: 部分载荷。
        user: 操作人。
        commit: 是否提交事务。
        action: 审计动作名。

    Returns:
        序列化后的行。
    """
    old = get_row(session, e, tenant_id, rid)
    check_editable(session, tenant_id, e, old)
    values = validate(session, tenant_id, e, data, old)
    if not values:
        return old
    values.update(updated_at=now(), updated_by=getattr(user, "id", None))
    t = table(e)
    try:
        with session.begin_nested():
            conn(session).execute(
                sa.update(t)
                .where(t.c.id == rid, t.c.tenant_id == tenant_id)
                .values(**values)
            )
    except IntegrityError as ex:
        raise integrity(ex) from ex
    new = get_row(session, e, tenant_id, rid)
    audit(
        session, tenant_id, e, action, new, user, diff(old, {k: new[k] for k in values})
    )
    if commit:
        session.commit()
    return new


def delete_row(
    session: Session, tenant_id: uuid.UUID, e: Entity, rid: uuid.UUID, user: Any
) -> None:
    """删除一行（锁定检查 → 删除前校验 → 删除 → 审计）。

    Raises:
        HTTPException: 被引用或已锁定时（409）。
    """
    old = get_row(session, e, tenant_id, rid)
    check_editable(session, tenant_id, e, old)
    for fn in VALIDATORS.get(f"{e.code}:delete", []):
        try:
            fn(session, tenant_id, e, old, old)
        except MesError as ex:
            raise http_422(ex.errors) from ex
    t = table(e)
    try:
        with session.begin_nested():
            conn(session).execute(
                sa.delete(t).where(t.c.id == rid, t.c.tenant_id == tenant_id)
            )
    except IntegrityError as ex:
        raise integrity(ex) from ex
    audit(session, tenant_id, e, "delete", old, user)
    session.commit()


def _next_version(session: Session, tenant_id: uuid.UUID, e: Entity, code: Any) -> int:
    t = table(e)
    cur = (
        conn(session)
        .execute(
            sa.select(sa.func.max(t.c.version)).where(
                t.c.tenant_id == tenant_id, t.c.code == code
            )
        )
        .scalar()
    )
    return int(cur or 0) + 1


def set_status(
    session: Session,
    tenant_id: uuid.UUID,
    e: Entity,
    rid: uuid.UUID,
    status: str,
    user: Any,
) -> Row:
    """切换版本化数据状态（按 STATUS_TRANSITIONS）。

    激活时运行 ``<code>:activate`` 校验器，并把同编码的其他 active 版本置为 inactive。

    Raises:
        HTTPException: 非法状态迁移（409）或激活校验失败（422）。
    """
    if not e.versioned:
        raise coded(404, ec.ENTITY_IS_NOT_VERSIONED, "Entity is not versioned")
    if status not in STATUSES:
        raise http_422(
            [
                fe(
                    "status",
                    ec.STATUS_INVALID,
                    f"status must be one of: {', '.join(STATUSES)}",
                    allowed=", ".join(STATUSES),
                )
            ]
        )
    old = get_row(session, e, tenant_id, rid)
    if status not in STATUS_TRANSITIONS[old["status"]]:
        raise coded(
            409,
            ec.STATUS_TRANSITION,
            f"Cannot change status from {old['status']} to {status}",
            src=old["status"],
            to=status,
        )
    t = table(e)
    c = conn(session)
    if status == "active":
        for fn in VALIDATORS.get(f"{e.code}:activate", []):
            try:
                fn(session, tenant_id, e, old, old)
            except MesError as ex:
                raise http_422(ex.errors) from ex
        # 激活新版本即锁定该版本（之后只能新建版本修改），旧 active 版本转为 inactive
        # 同一编码仅允许一个 active 版本
        for r in c.execute(
            sa.select(t.c.id, t.c.version).where(
                t.c.tenant_id == tenant_id,
                t.c.code == old["code"],
                t.c.status == "active",
                t.c.id != rid,
            )
        ).mappings():
            c.execute(
                sa.update(t)
                .where(t.c.id == r["id"])
                .values(status="inactive", updated_at=now())
            )
            audit(
                session,
                tenant_id,
                e,
                "status",
                {**old, "id": r["id"], "version": r["version"]},
                user,
                {"status": ("active", "inactive")},
            )
    c.execute(
        sa.update(t)
        .where(t.c.id == rid)
        .values(status=status, updated_at=now(), updated_by=getattr(user, "id", None))
    )
    new = get_row(session, e, tenant_id, rid)
    audit(
        session, tenant_id, e, "status", new, user, {"status": (old["status"], status)}
    )
    session.commit()
    return new


def _copy_children(
    session: Session,
    tenant_id: uuid.UUID,
    e: Entity,
    old_id: Any,
    new_id: Any,
    user: Any,
) -> None:
    c = conn(session)
    for ce in ENTITIES.values():
        for f in ce.all_fields:
            if f.type == "ref" and f.cascade and f.ref == e.code and f.name != "parent":
                ct = table(ce)
                for r in c.execute(
                    sa.select(ct).where(
                        ct.c.tenant_id == tenant_id, ct.c[f.column] == old_id
                    )
                ).mappings():
                    nid = uuid.uuid4()
                    vals = {
                        **dict(r),
                        "id": nid,
                        f.column: new_id,
                        "created_at": now(),
                        "updated_at": now(),
                        "created_by": getattr(user, "id", None),
                    }
                    c.execute(sa.insert(ct).values(**vals))
                    _copy_children(session, tenant_id, ce, r["id"], nid, user)


def new_version(
    session: Session, tenant_id: uuid.UUID, e: Entity, rid: uuid.UUID, user: Any
) -> Row:
    """复制某版本（含子表行）为下一个 draft 版本。"""
    if not e.versioned:
        raise coded(404, ec.ENTITY_IS_NOT_VERSIONED, "Entity is not versioned")
    old = get_row(session, e, tenant_id, rid)
    nid = uuid.uuid4()
    vals = {
        **old,
        "id": nid,
        "version": _next_version(session, tenant_id, e, old["code"]),
        "status": "draft",
        "created_at": now(),
        "updated_at": now(),
        "created_by": getattr(user, "id", None),
        "updated_by": getattr(user, "id", None),
    }
    conn(session).execute(sa.insert(table(e)).values(**vals))
    _copy_children(session, tenant_id, e, rid, nid, user)
    new = get_row(session, e, tenant_id, nid)
    audit(
        session,
        tenant_id,
        e,
        "new_version",
        new,
        user,
        {"version": (old["version"], new["version"])},
    )
    session.commit()
    return new
