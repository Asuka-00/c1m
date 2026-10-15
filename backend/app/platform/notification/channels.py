"""通知渠道抽象：每个渠道实现 :class:`Channel` 并登记到 ``CHANNELS``。

目前只实现站内渠道 ``in_app``（写接收人行，前端轮询读取）；邮件等渠道后续按同一接口登记即可。
"""

import uuid
from typing import Protocol

from sqlalchemy.dialects.postgresql import insert
from sqlmodel import Session, SQLModel

from app.platform.notification.models import Notification


class Channel(Protocol):
    """通知渠道接口。"""

    code: str
    label: str

    def deliver(
        self, session: Session, note: Notification, user_ids: set[uuid.UUID]
    ) -> int:
        """把通知投递给用户，返回投递数量（在调用方事务内执行，不提交）。"""
        ...


class InAppChannel:
    """站内渠道：为每个接收人写一行未读记录（同一通知同一用户只写一次）。"""

    code = "in_app"
    label = "In-app|站内|アプリ内"

    def deliver(
        self, session: Session, note: Notification, user_ids: set[uuid.UUID]
    ) -> int:
        """写接收人行（冲突忽略）。"""
        if not user_ids:
            return 0
        t = SQLModel.metadata.tables["notification_recipient"]
        session.connection().execute(
            insert(t)
            .values(
                [
                    {
                        "id": uuid.uuid4(),
                        "tenant_id": note.tenant_id,
                        "notification_id": note.id,
                        "user_id": u,
                    }
                    for u in user_ids
                ]
            )
            .on_conflict_do_nothing(constraint="uq_notification_user")
        )
        return len(user_ids)


CHANNELS: dict[str, Channel] = {}


def register_channel(ch: Channel) -> None:
    """登记渠道（按 ``code`` 覆盖）。"""
    CHANNELS[ch.code] = ch


register_channel(InAppChannel())
