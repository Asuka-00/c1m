"""Idempotency-Key（D57，#IK01）。

作用域 (tenant, endpoint, key)，保留 24 小时：

- 同 key、规范化请求体哈希相同 → 原样返回首次的状态码与响应，不校验、不写履历；
- 同 key、哈希不同 → 422 ``idempotency_key_reused``，不写入；
- 只存档成功（2xx）的响应；失败的请求什么都不写，修正后可用同一个 key 重发；
- 超过 24 小时的存档视为不存在（复用时覆盖）；
- 同 key 的原请求仍在处理中 → 409 ``idempotency_in_progress``（H-1）。

并发安全（H-1）：先在外层事务里拿 (tenant, endpoint, key) 的事务级咨询锁（拿不到 →
409），再 ``INSERT … ON CONFLICT DO NOTHING`` 占位；业务写入跑在同一连接的 SAVEPOINT
里（业务代码里的 ``commit()`` / ``rollback()`` 只作用于 SAVEPOINT），最后把响应写回占位行，
占位、业务写入、存档一起提交。失败则整个外层事务回滚，占位随之消失，同 key 可重试。

请求体哈希 = sha256(按键排序的紧凑 JSON)，路径参数并入请求体一起算。
"""

import hashlib
import json
import uuid
from collections.abc import Callable
from datetime import timedelta
from types import SimpleNamespace
from typing import Any

import sqlalchemy as sa
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import Session

from app.core.models import actor_name
from app.core.spec.base import now
from app.core.spec.engine import TABLES
from app.mes.common.rows import _sys

RETENTION = timedelta(hours=24)
ENT = "idempotency_key"
HEADER = "Idempotency-Key"


def body_hash(body: Any) -> str:
    """规范化请求体哈希（D57）。"""
    raw = json.dumps(
        jsonable_encoder(body), sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def reused() -> HTTPException:
    """422 ``idempotency_key_reused``（D57）。"""
    return HTTPException(
        status_code=422,
        detail={
            "code": "idempotency_key_reused",
            "message": "Idempotency-Key was already used with a different request body",
        },
    )


def in_progress() -> HTTPException:
    """409 ``idempotency_in_progress``：同 key 的原请求尚未完成（H-1）。"""
    return HTTPException(
        status_code=409,
        detail={
            "code": "idempotency_in_progress",
            "message": "A request with this Idempotency-Key is still in progress",
        },
    )


def _lock_id(tid: uuid.UUID, endpoint: str, key: str) -> int:
    d = hashlib.sha256(f"idem|{tid}|{endpoint}|{key}".encode()).digest()
    return int.from_bytes(d[:8], "big", signed=True)


def _find(
    c: sa.Connection, tid: uuid.UUID, endpoint: str, key: str
) -> dict[str, Any] | None:
    t = TABLES[ENT]
    r = (
        c.execute(
            sa.select(t).where(
                t.c.tenant_id == tid, t.c.endpoint == endpoint, t.c.idem_key == key
            )
        )
        .mappings()
        .first()
    )
    return dict(r) if r else None


def _replay(row: dict[str, Any], h: str) -> JSONResponse:
    if row["request_hash"] != h:
        raise reused()
    if not row["status_code"]:  # 占位未完成（理论上锁已挡住，兜底）
        raise in_progress()
    return JSONResponse(
        status_code=row["status_code"],
        content=row["response"],
        headers={"Idempotent-Replayed": "true"},
    )


def _reserve(
    c: sa.Connection,
    tid: uuid.UUID,
    user: SimpleNamespace,
    endpoint: str,
    key: str,
    h: str,
) -> JSONResponse | None:
    """占位；已有未过期存档时返回重放响应（或抛 422 / 409）。"""
    t = TABLES[ENT]
    at = now()
    if not c.execute(
        sa.select(sa.func.pg_try_advisory_xact_lock(_lock_id(tid, endpoint, key)))
    ).scalar():
        raise in_progress()
    res = c.execute(
        pg_insert(t)
        .values(
            id=uuid.uuid4(),
            tenant_id=tid,
            **_sys(user, at),
            endpoint=endpoint,
            idem_key=key,
            request_hash=h,
            status_code=0,
            response=None,
            username=user.name,
        )
        .on_conflict_do_nothing()
        .returning(t.c.id)
    )
    if res.first() is not None:
        return None
    row = _find(c, tid, endpoint, key)
    if row is None:  # 冲突的不是本 key（不应发生）
        raise in_progress()
    if row["created_at"] and row["created_at"] >= at - RETENTION:
        return _replay(row, h)
    # 过期存档：原地改成本次的占位
    c.execute(
        sa.update(t)
        .where(t.c.id == row["id"])
        .values(
            **_sys(user, at),
            request_hash=h,
            status_code=0,
            response=None,
            username=user.name,
        )
    )
    return None


def run(
    s: Session,
    tid: uuid.UUID,
    user: Any,
    endpoint: str,
    key: str | None,
    body: Any,
    fn: Callable[[], Any],
    status_code: int = 200,
) -> Any:
    """带 Idempotency-Key 时占位后执行 ``fn``（同一事务提交）；没有 key 直接执行 ``fn``。"""
    key = (key or "").strip()[:128] or None
    if not key:
        return fn()
    h = body_hash(body)
    # 先取出操作人（提交后 ORM 对象过期，刷新会把会话绑回引擎连接）
    actor = SimpleNamespace(id=getattr(user, "id", None), name=actor_name(user))
    s.commit()  # 结束会话里已有的（只读）事务，下面切到外层事务的连接上
    bind = s.bind
    eng = s.get_bind().engine
    mode = s.join_transaction_mode
    t = TABLES[ENT]
    with eng.connect() as c:
        outer = c.begin()
        try:
            c.execute(
                sa.text("SELECT set_config('app.current_tenant', :t, true)"),
                {"t": str(tid)},
            )
            replay = _reserve(c, tid, actor, endpoint, key, h)
            if replay is not None:
                outer.commit()
                return replay
            s.bind = c
            s.join_transaction_mode = "create_savepoint"
            try:
                result = fn()  # 业务里的 commit/rollback 只作用于 SAVEPOINT
                s.commit()
            except BaseException:
                if s.in_transaction():
                    s.rollback()
                raise
            finally:
                s.bind = bind
                s.join_transaction_mode = mode
            enc = jsonable_encoder(result)
            c.execute(
                sa.update(t)
                .where(
                    t.c.tenant_id == tid, t.c.endpoint == endpoint, t.c.idem_key == key
                )
                .values(status_code=status_code, response=enc, updated_at=now())
            )
            outer.commit()
        except BaseException:
            if outer.is_active:
                outer.rollback()
            raise
    return enc
