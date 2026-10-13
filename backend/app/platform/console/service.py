"""平台控制台服务：登录日志与平台操作审计的写入。"""

import uuid
from typing import Any

from sqlmodel import Session

from app.core.models import actor_name
from app.platform.console.models import LoginLog, PlatformAudit
from app.platform.users.models import User


def record_platform_audit(
    session: Session,
    actor: User,
    action: str,
    target_type: str,
    target_id: Any = None,
    tenant_id: uuid.UUID | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    """记录一条平台操作日志（调用方负责提交事务）。

    Args:
        session: 数据库会话。
        actor: 操作人（超级用户）。
        action: 动作，如 ``tenant.create``、``tenant.enter``、``audit.cross_tenant_read``。
        target_type: 目标类型，如 ``tenant``。
        target_id: 目标 id。
        tenant_id: 涉及的租户。
        detail: 附加信息。
    """
    session.add(
        PlatformAudit(
            actor_id=actor.id,
            actor_email=actor_name(actor) or "",
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id is not None else None,
            tenant_id=tenant_id,
            detail=detail,
        )
    )


def record_login(
    session: Session,
    email: str,
    user: User | None,
    success: bool,
    reason: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> None:
    """记录一次登录尝试并立即提交（失败的登录也要留痕）。"""
    session.add(
        LoginLog(
            email=email[:255],
            user_id=user.id if user else None,
            success=success,
            reason=reason,
            ip=ip,
            user_agent=(user_agent or "")[:500] or None,
        )
    )
    session.commit()
