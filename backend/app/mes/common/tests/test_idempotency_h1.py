"""H-1（D57/D72）：Idempotency-Key 并发安全。

业务写入用另一个 endpoint 下的 mes_idempotency_key 行当“业务记录”计数（租户表、受 RLS）。
"""

import threading
import time
import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from sqlmodel import Session

from app.core.db import admin_engine, engine
from app.core.tenant import set_tenant
from app.mes.common import idempotency as idem
from app.mes.common.rows import _ins

EP = "POST /test/h1"


@pytest.fixture()
def tid() -> uuid.UUID:
    with admin_engine.begin() as c:
        t = c.execute(sa.text("SELECT id FROM tenant ORDER BY created_at LIMIT 1"))
        return t.scalar_one()


def _sess(tid: uuid.UUID) -> Session:
    s = Session(engine)
    set_tenant(s, tid)
    return s


def _count(tag: str) -> int:
    with admin_engine.begin() as c:
        return int(
            c.execute(
                sa.text("SELECT count(*) FROM mes_idempotency_key WHERE endpoint=:e"),
                {"e": tag},
            ).scalar_one()
        )


def _biz(s: Session, tid: uuid.UUID, tag: str, sleep: float = 0.0) -> Any:
    def fn() -> Any:
        _ins(
            s,
            tid,
            idem.ENT,
            None,
            endpoint=tag,
            idem_key=uuid.uuid4().hex,
            request_hash="x",
            status_code=1,
        )
        s.commit()  # 业务代码自己的 commit 只作用于 SAVEPOINT
        if sleep:
            time.sleep(sleep)
        return {"ok": True, "tag": tag}

    return fn


def _call(tid: uuid.UUID, key: str, body: Any, fn_factory: Any) -> Any:
    with _sess(tid) as s:
        try:
            r = idem.run(s, tid, None, EP, key, body, fn_factory(s))
        except HTTPException as ex:
            return ex.status_code, ex.detail
        if isinstance(r, JSONResponse):
            return r.status_code, r.body
        return 200, r


def test_h1_concurrent_same_key_applied_once(tid: uuid.UUID) -> None:
    tag, key = f"biz-{uuid.uuid4().hex}", uuid.uuid4().hex
    barrier = threading.Barrier(10)
    out: list[Any] = []

    def worker() -> None:
        barrier.wait()
        out.append(_call(tid, key, {"a": 1}, lambda s: _biz(s, tid, tag, 0.3)))

    ts = [threading.Thread(target=worker) for _ in range(10)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert _count(tag) == 1
    codes = sorted(c for c, _ in out)
    assert set(codes) <= {200, 409} and codes.count(200) >= 1
    assert all(d["code"] == "idempotency_in_progress" for c, d in out if c == 409)
    # 完成后同 key 重放首个响应，不再写入
    c, body = _call(tid, key, {"a": 1}, lambda s: _biz(s, tid, tag))
    assert c == 200 and b'"tag"' in body and _count(tag) == 1


def test_h1_in_progress_409(tid: uuid.UUID) -> None:
    tag, key = f"biz-{uuid.uuid4().hex}", uuid.uuid4().hex
    started = threading.Event()

    def slow(s: Session) -> Any:
        inner = _biz(s, tid, tag)

        def fn() -> Any:
            r = inner()
            started.set()
            time.sleep(1.0)
            return r

        return fn

    th = threading.Thread(target=lambda: _call(tid, key, {"a": 1}, slow))
    th.start()
    assert started.wait(10)
    c, d = _call(tid, key, {"a": 1}, lambda s: _biz(s, tid, tag))
    th.join()
    assert c == 409 and d["code"] == "idempotency_in_progress"
    assert _count(tag) == 1


def test_h1_different_body_422(tid: uuid.UUID) -> None:
    tag, key = f"biz-{uuid.uuid4().hex}", uuid.uuid4().hex
    assert _call(tid, key, {"a": 1}, lambda s: _biz(s, tid, tag))[0] == 200
    c, d = _call(tid, key, {"a": 2}, lambda s: _biz(s, tid, tag))
    assert c == 422 and d["code"] == "idempotency_key_reused"
    assert _count(tag) == 1


def test_h1_rollback_then_retry_succeeds(tid: uuid.UUID) -> None:
    tag, key = f"biz-{uuid.uuid4().hex}", uuid.uuid4().hex

    def failing(s: Session) -> Any:
        inner = _biz(s, tid, tag)

        def fn() -> Any:
            inner()  # 业务已 commit（SAVEPOINT），随后失败 → 整体回滚
            raise HTTPException(status_code=409, detail={"code": "boom"})

        return fn

    c, d = _call(tid, key, {"a": 1}, failing)
    assert c == 409 and d["code"] == "boom"
    assert _count(tag) == 0
    with admin_engine.begin() as cn:
        n = cn.execute(
            sa.text("SELECT count(*) FROM mes_idempotency_key WHERE idem_key=:k"),
            {"k": key},
        ).scalar_one()
    assert n == 0  # 占位随回滚消失
    assert _call(tid, key, {"a": 1}, lambda s: _biz(s, tid, tag))[0] == 200
    assert _count(tag) == 1
