"""通用 CRUD 的“受控写”实体（D74 / D81）：写接口必须带 Idempotency-Key，可放行附加字段。

由业务模块登记（如 ``operator_qual``），通用路由按此执行 D81 顺序：
403 → 缺 key 422 → 请求体 422（含附加字段）→ 幂等重放 → 404 → ``after_404``（如 422
holder_approval）→ 409 → 写入。附加字段经 ``extra_var`` 传给写入钩子。
"""

import uuid
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from sqlmodel import Session

Row = dict[str, Any]


@dataclass(frozen=True)
class KeyedWrite:
    """受控写实体的回调集合。"""

    #: 取出并校验请求体附加字段（body 阶段，不读目标行）：fn(s, tid, method, body, user)
    extras: Callable[[Session, uuid.UUID, str, Row, Any], Row]
    #: 查到目标行之后（POST 为请求体）、409 之前的校验：fn(extra, row)
    after_404: Callable[[Row, Row], None]
    #: 删除前校验（如有履历 409 referenced）：fn(s, tid, rid)
    before_delete: Callable[[Session, uuid.UUID, uuid.UUID], None]
    #: 附加字段的上下文变量（写入钩子读取）
    extra_var: ContextVar[Row | None]


KEYED: dict[str, KeyedWrite] = {}

#: 实体元数据的租户级附加项（``GET /mes/_meta``）：fn(s, tid) -> dict（如 D64 warn_days）
META_HOOKS: dict[str, Callable[[Session, uuid.UUID], Row]] = {}
