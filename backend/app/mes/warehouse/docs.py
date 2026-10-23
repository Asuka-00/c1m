"""仓储单据（领料单 / 出货单 / 来料接收单）共用的状态流转与草稿保护。

状态机（动作：从 → 到）::

    confirm   draft -> confirmed   （确认：校验并过账，由各单据的 ``post`` 实现）
    cancel    draft -> cancelled

只有草稿可以修改 / 删除，明细同理；状态字段统一为 ``issue_status``。
"""

import uuid
from collections.abc import Callable
from typing import Any

import sqlalchemy as sa
from sqlmodel import Session

from app.core import error_codes as ec
from app.core.models import actor_name
from app.core.spec.audit import audit
from app.core.spec.base import conn, now
from app.core.spec.engine import ENTITIES, TABLES, Entity
from app.core.spec.errors import MesError, fe, http_422
from app.core.spec.query import get_row
from app.core.spec.validate import validator
from app.mes.common.query import find, one
from app.mes.common.rows import _upd

Row = dict[str, Any]
TRANSITIONS: dict[str, tuple[set[str], str]] = {
    "confirm": ({"draft"}, "confirmed"),
    "cancel": ({"draft"}, "cancelled"),
}
#: 过账：``post(session, tenant_id, 单据, 明细, user)``，校验失败抛 422
Post = Callable[[Session, uuid.UUID, Row, list[Row], Any], None]


def draft_error() -> MesError:
    """只有草稿可修改的统一错误。"""
    return MesError(
        [
            fe(
                "issue_status",
                ec.ISSUE_EDIT_DRAFT_ONLY,
                "issue_status: only draft documents can be changed or deleted",
            )
        ]
    )


def guard_drafts(header: str, line: str) -> None:
    """登记草稿保护校验器：单据与明细只有草稿状态下可改 / 删。

    Args:
        header: 单据实体编码。
        line: 明细实体编码（其引用单据的字段名为 ``header``）。
    """

    def _parent_draft(s: Session, tid: uuid.UUID, row: Row) -> None:
        doc = one(s, tid, header, row.get(f"{header}_id"))
        if not doc or doc["issue_status"] != "draft":
            raise draft_error()

    @validator(header)
    def _edit(
        _s: Session, _t: uuid.UUID, _e: Entity, _row: Row, old: Row | None
    ) -> None:
        if old and old["issue_status"] != "draft":
            raise draft_error()

    @validator(f"{header}:delete")
    def _delete(
        _s: Session, _t: uuid.UUID, _e: Entity, row: Row, _o: Row | None
    ) -> None:
        if row["issue_status"] != "draft":
            raise draft_error()

    @validator(line)
    def _line(s: Session, tid: uuid.UUID, _e: Entity, row: Row, _o: Row | None) -> None:
        _parent_draft(s, tid, row)

    @validator(f"{line}:delete")
    def _line_delete(
        s: Session, tid: uuid.UUID, _e: Entity, row: Row, _o: Row | None
    ) -> None:
        _parent_draft(s, tid, row)


def transition(
    s: Session,
    tid: uuid.UUID,
    header: str,
    line: str,
    doc_id: uuid.UUID,
    action: str,
    user: Any,
    post: Post,
) -> Row:
    """执行单据状态迁移（confirm / cancel）。

    Args:
        s: 数据库会话。
        tid: 租户 id。
        header: 单据实体编码。
        line: 明细实体编码。
        doc_id: 单据 id。
        action: 动作。
        user: 操作人。
        post: 确认时的过账函数。

    Returns:
        更新后的单据。

    Raises:
        HTTPException: 非法动作 / 状态、没有明细或过账校验失败（422）；单据不存在（404）。
    """
    if action not in TRANSITIONS:
        raise http_422(
            [
                fe(
                    "action",
                    ec.ACTION_INVALID,
                    f"action: must be one of {', '.join(TRANSITIONS)}",
                    actions=", ".join(TRANSITIONS),
                )
            ]
        )
    ent, t = ENTITIES[header], TABLES[header]
    r = (
        conn(s)
        .execute(
            sa.select(t).where(t.c.tenant_id == tid, t.c.id == doc_id).with_for_update()
        )
        .mappings()
        .first()
    )
    doc = dict(r) if r else get_row(s, ent, tid, doc_id)  # 404
    allowed, to = TRANSITIONS[action]
    if doc["issue_status"] not in allowed:
        raise http_422(
            [
                fe(
                    "issue_status",
                    ec.ISSUE_TRANSITION,
                    f"issue_status: cannot {action} a {doc['issue_status']} document",
                    action=action,
                    status=doc["issue_status"],
                )
            ]
        )
    vals: Row = {"issue_status": to}
    if action == "confirm":
        lines = find(s, tid, line, order="created_at", **{f"{header}_id": doc["id"]})
        if not lines:
            raise http_422(
                [fe("lines", ec.ISSUE_LINES_REQUIRED, "lines: add at least one line")]
            )
        post(s, tid, doc, lines, user)
        vals.update(confirmed_at=now(), confirmed_by=actor_name(user))
    _upd(s, tid, header, doc["id"], user, **vals)
    new = get_row(s, ent, tid, doc["id"])
    audit(s, tid, ent, action, new, user, {"issue_status": (doc["issue_status"], to)})
    s.commit()
    return new
