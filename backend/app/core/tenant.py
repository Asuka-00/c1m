"""租户会话上下文：为 Postgres RLS 设置 ``app.current_tenant``。"""

import uuid
from typing import Any

from sqlalchemy import event, text
from sqlmodel import Session
from sqlmodel.sql.expression import SelectOfScalar


# ---------- Postgres RLS context ----------
# 租户 id 保存在 session.info；会话开启的每个事务都会执行
# `set_config('app.current_tenant', <id>, true)`（即 SET LOCAL），因此在同一请求内跨提交保持，
# 且不会泄漏给连接池中该连接的下一个使用者。
@event.listens_for(Session, "after_begin")
def _set_tenant_on_begin(session: Session, _txn: Any, connection: Any) -> None:
    tid = session.info.get("tenant_id")
    if tid is not None:
        connection.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(tid)}
        )


def set_tenant(session: Session, tenant_id: uuid.UUID | None) -> None:
    """设置会话的当前租户（写入 ``session.info``，事务开始时下发到 Postgres）。

    Args:
        session: 数据库会话。
        tenant_id: 租户 id；None 表示清除（RLS 下将看不到任何租户数据）。
    """
    session.info["tenant_id"] = tenant_id
    if session.in_transaction():
        # 在会话当前连接上执行原生 SQL（sqlmodel 的 exec() 用于查询）
        session.connection().execute(
            text("SELECT set_config('app.current_tenant', :t, true)"),
            {"t": str(tenant_id) if tenant_id else ""},
        )


def tenant_scoped[T](
    stmt: SelectOfScalar[T], model: Any, tenant_id: uuid.UUID
) -> SelectOfScalar[T]:
    """应用层租户过滤：追加 ``WHERE model.tenant_id = :tenant``（RLS 为兜底）。

    Args:
        stmt: 查询。
        model: 带 ``tenant_id`` 列的模型。
        tenant_id: 租户 id。

    Returns:
        追加过滤后的查询。
    """
    return stmt.where(model.tenant_id == tenant_id)
