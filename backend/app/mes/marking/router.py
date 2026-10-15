"""打标模板接口（P3-B1，D79 / D81 / D89）。

- 写接口（创建 201、编辑 200、新版本 201、审批 200、停用 200）必须带 Idempotency-Key；
  顺序 403 → 缺 key 422 → 请求体 422（含 unknown_placeholder）→ 幂等重放 → 404 →
  404 后的 422（self_approval）→ 409（对象 {code, message}）。
- ``POST /preview`` / ``/validate``：只读、不要 key、200；template_id 与 lines 二选一。
"""

import uuid
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.core.deps import SessionDep
from app.core.schemas import StrictBody
from app.core.spec.errors import http_422
from app.mes.common import idempotency as idem
from app.mes.common.guard import need, perm_body, perm_key_body
from app.mes.marking import service as svc
from app.platform.auth.deps import CurrentTenant

router = APIRouter(prefix="/mes/marking-template", tags=["mes"])
READ = "mes.marking:read"
WRITE = "mes.marking_template:write"
APPROVE = "mes.marking_template:approve"

Key = Annotated[str | None, Header(alias=idem.HEADER, include_in_schema=False)]
KEY_PARAM: dict[str, Any] = {
    "name": idem.HEADER,
    "in": "header",
    "required": True,
    "schema": {"type": "string", "minLength": 1, "title": idem.HEADER},
    "description": "D79 supp.7 / D81: required; same key + same body replays the first response.",
}
KEYED: dict[str, Any] = {"openapi_extra": {"parameters": [KEY_PARAM]}}


# TODO(B1)：单行长度上限、lines 是否可为空均未规定
Lines = list[str]


class TemplateIn(StrictBody):
    code: str = Field(min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=300)
    product_id: uuid.UUID
    customer_id: uuid.UUID
    lines: Lines


class TemplatePatch(StrictBody):
    code: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=300)
    product_id: uuid.UUID | None = None
    customer_id: uuid.UUID | None = None
    lines: Lines | None = None


class SourceIn(StrictBody):
    template_id: uuid.UUID | None = None
    lines: Lines | None = None


def _lines(m: BaseModel | None) -> list[str] | None:
    v = getattr(m, "lines", None)
    return None if v is None else list(v)


def _write(
    session: Session,
    ctx: Any,
    endpoint: str,
    key: str | None,
    data: Any,
    fn: Callable[[], Any],
    status_code: int = 200,
) -> Any:
    def go() -> Any:
        out = fn()
        session.commit()
        return out

    return idem.run(
        session, ctx.id, ctx.user, endpoint, key, data, go, status_code=status_code
    )


def _exactly_one(b: SourceIn) -> None:
    if (b.template_id is None) == (b.lines is None):
        raise http_422(
            [
                (
                    "template_id",
                    "exactly one of template_id / lines is required",
                    "value_error",
                    {"reason": "exactly_one_of", "fields": ["template_id", "lines"]},
                )
            ]
        )


@router.post("/preview")
def preview(
    session: SessionDep,
    ctx: CurrentTenant,
    body: Annotated[SourceIn, Depends(perm_body(READ, SourceIn))],
) -> Any:
    """Read-only preview {template_id, lines}; template_id XOR lines (D79 supp.7 n.2/3)."""
    _exactly_one(body)
    return svc.preview(session, ctx.id, body.template_id, _lines(body))


@router.post("/validate")
def validate(
    session: SessionDep,
    ctx: CurrentTenant,
    body: Annotated[SourceIn, Depends(perm_body(READ, SourceIn))],
) -> Any:
    """Read-only check {valid, unknown_placeholders}; template_id XOR lines."""
    _exactly_one(body)
    return svc.validate_lines(session, ctx.id, body.template_id, _lines(body))


@router.get("")
def list_templates(
    session: SessionDep,
    ctx: CurrentTenant,
    q: str | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> Any:
    """Templates with their latest version (status / lines) and approved_version."""
    need(ctx, READ)
    return svc.list_templates(session, ctx.id, q, offset, limit)


@router.get("/{rid}")
def get_template(session: SessionDep, ctx: CurrentTenant, rid: uuid.UUID) -> Any:
    """Template detail with versions[] (newest first). Cross-tenant → 404."""
    need(ctx, READ)
    return {"data": svc.ser(session, ctx.id, svc.get(session, ctx.id, rid))}


@router.post("", status_code=201, **KEYED)
def create(
    session: SessionDep,
    ctx: CurrentTenant,
    body: Annotated[TemplateIn, Depends(perm_key_body(WRITE, TemplateIn))],
    idempotency_key: Key = None,
) -> Any:
    """Create template + v1 draft (201). 422 unknown_placeholder; 409 duplicate_code."""
    d = body.model_dump(mode="json")
    svc.check_placeholders(d["lines"])
    return _write(
        session,
        ctx,
        "POST /mes/marking-template",
        idempotency_key,
        d,
        lambda: svc.create(session, ctx.id, d, ctx.user),
        status_code=201,
    )


@router.patch("/{rid}", **KEYED)
def update(
    session: SessionDep,
    ctx: CurrentTenant,
    rid: uuid.UUID,
    body: Annotated[TemplatePatch, Depends(perm_key_body(WRITE, TemplatePatch))],
    idempotency_key: Key = None,
) -> Any:
    """Edit the draft (409 template_readonly when the latest version is not draft)."""
    d = body.model_dump(mode="json", exclude_unset=True)
    for k in ("code", "product_id", "customer_id", "lines"):
        if (
            k in d and d[k] is None
        ):  # TODO(B1)：PATCH 显式 null 的语义未规定，按不改处理
            d.pop(k)
    if d.get("lines") is not None:
        svc.check_placeholders(d["lines"])
    return _write(
        session,
        ctx,
        "PATCH /mes/marking-template/{rid}",
        idempotency_key,
        {"rid": rid, **d},
        lambda: svc.update(session, ctx.id, rid, d, ctx.user),
    )


@router.post("/{rid}/versions", status_code=201, **KEYED)
def new_version(
    session: SessionDep,
    ctx: CurrentTenant,
    rid: uuid.UUID,
    _b: Annotated[Any, Depends(perm_key_body(WRITE, StrictBody, optional=True))],
    idempotency_key: Key = None,
) -> Any:
    """Copy the latest version into a new draft (201); 409 draft_exists."""
    return _write(
        session,
        ctx,
        "POST /mes/marking-template/{rid}/versions",
        idempotency_key,
        {"rid": rid},
        lambda: svc.new_version(session, ctx.id, rid, ctx.user),
        status_code=201,
    )


@router.post("/{rid}/approve", **KEYED)
def approve(
    session: SessionDep,
    ctx: CurrentTenant,
    rid: uuid.UUID,
    _b: Annotated[Any, Depends(perm_key_body(APPROVE, StrictBody, optional=True))],
    idempotency_key: Key = None,
) -> Any:
    """Approve the open version; previous approved → retired. 422 self_approval; 409 invalid_transition."""
    return _write(
        session,
        ctx,
        "POST /mes/marking-template/{rid}/approve",
        idempotency_key,
        {"rid": rid},
        lambda: svc.approve(session, ctx.id, rid, ctx.user),
    )
