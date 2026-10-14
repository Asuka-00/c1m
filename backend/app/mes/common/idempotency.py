"""Idempotency-Key（D57，#IK01）。

作用域 (tenant, endpoint, key)，保留 24 小时：

- 同 key、规范化请求体哈希相同 → 原样返回首次的状态码与响应，不校验、不写履历；
- 同 key、哈希不同 → 422 ``idempotency_key_reused``，不写入；
- 只存档成功（2xx）的响应；失败的请求什么都不写，修正后可用同一个 key 重发；
- 超过 24 小时的存档视为不存在（复用时覆盖）。

请求体哈希 = sha256(按键排序的紧凑 JSON)，路径参数并入请求体一起算。
回放成功时响应头带 ``Idempotent-Replayed: true``（D86 补充二），首次执行不带。

D88-2：通用 CRUD（``/mes/{entity}``）中以下实体的新建 / 编辑 / 删除**必须**带
Idempotency-Key（缺失 422 missing，D81 顺序），登记在 :data:`keyed_write.KEYED`：
``reticle``（D87）、``alarm_code``（D84 Q6，随 B8 落地）、``operator_qual``（D74）。
其它实体的通用 CRUD 不要求 key。
"""

import hashlib
import json
import uuid
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import sqlalchemy as sa
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.core.models import actor_name
from app.core.spec.base import conn, now
from app.core.spec.engine import TABLES
from app.mes.common.rows import _ins

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


def _find(s: Session, tid: uuid.UUID, endpoint: str, key: str) -> dict[str, Any] | None:
    t = TABLES[ENT]
    r = (
        conn(s)
        .execute(
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
    return JSONResponse(
        status_code=row["status_code"],
        content=row["response"],
        headers={"Idempotent-Replayed": "true"},
    )


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
    """带 Idempotency-Key 时先查存档；没有 key 直接执行 ``fn``。"""
    key = (key or "").strip()[:128] or None
    if not key:
        return fn()
    h = body_hash(body)
    row = _find(s, tid, endpoint, key)
    t = TABLES[ENT]
    if row:
        if row["created_at"] and row["created_at"] >= now() - RETENTION:
            s.commit()
            return _replay(row, h)
        conn(s).execute(sa.delete(t).where(t.c.id == row["id"]))
        s.commit()
    result = fn()  # 失败（HTTPException）直接抛出，不存档
    enc = jsonable_encoder(result)
    try:
        with s.begin_nested():
            _ins(
                s,
                tid,
                ENT,
                user,
                endpoint=endpoint,
                idem_key=key,
                request_hash=h,
                status_code=status_code,
                response=enc,
                username=actor_name(user),
            )
    except IntegrityError:
        s.rollback()
        dup = _find(s, tid, endpoint, key)
        if dup:
            return _replay(dup, h)
        raise
    s.commit()
    return enc
