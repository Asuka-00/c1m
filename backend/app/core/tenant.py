"""Tenant session context: sets `app.current_tenant` for Postgres RLS."""

import uuid
from typing import Any

from sqlalchemy import event, text
from sqlmodel import Session
from sqlmodel.sql.expression import SelectOfScalar


# ---------- Postgres RLS context ----------
# The tenant id lives in session.info; every transaction the Session begins gets
# `set_config('app.current_tenant', <id>, true)` (== SET LOCAL), so it survives commits
# within a request and never leaks to the next user of a pooled connection.
@event.listens_for(Session, "after_begin")
def _set_tenant_on_begin(session: Session, _txn: Any, connection: Any) -> None:
    tid = session.info.get("tenant_id")
    if tid is not None:
        connection.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(tid)}
        )


def set_tenant(session: Session, tenant_id: uuid.UUID | None) -> None:
    session.info["tenant_id"] = tenant_id
    if session.in_transaction():
        # raw SQL on the session's current connection (sqlmodel's exec() is for selects)
        session.connection().execute(
            text("SELECT set_config('app.current_tenant', :t, true)"),
            {"t": str(tenant_id) if tenant_id else ""},
        )


def tenant_scoped[T](
    stmt: SelectOfScalar[T], model: Any, tenant_id: uuid.UUID
) -> SelectOfScalar[T]:
    """App-layer filter: add `WHERE model.tenant_id = :tenant` (RLS is the backstop)."""
    return stmt.where(model.tenant_id == tenant_id)
