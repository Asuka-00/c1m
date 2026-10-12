"""上传文件回收。

当平台配置值 / 默认值或租户覆盖值中的图片 / 文件项指向 ``/api/v1/files/<id>`` 时文件即被引用。
租户文件只能被该租户的覆盖值引用；平台文件可被平台值或任意租户覆盖值引用。租户覆盖值在
RLS 下逐个租户读取。

- ``release_values``：值被替换 / 删除 / 重置后调用，旧文件无人引用即删除。
- ``cleanup_unreferenced``：定期清理（scripts/cleanup_files.py 或 POST /files/cleanup）
  从未保存进配置且超过宽限期的文件。
"""

import logging
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlmodel import Session, col, select

from app.core.config import settings
from app.core.tenant import set_tenant
from app.platform.config.models import ConfigItem, TenantConfigValue
from app.platform.files.models import UploadedFile
from app.platform.tenants.models import Tenant

logger = logging.getLogger(__name__)

FILE_PREFIX = f"{settings.API_V1_STR}/files/"
FILE_TYPES = ("image", "file")


def upload_dir() -> Path:
    """上传目录（相对路径基于 backend/），不存在时创建。"""
    p = Path(settings.UPLOAD_DIR)
    if not p.is_absolute():
        p = Path(__file__).resolve().parents[3] / p  # backend/<UPLOAD_DIR>
    p.mkdir(parents=True, exist_ok=True)
    return p


def file_id(value: Any) -> uuid.UUID | None:
    """从 ``/api/v1/files/<id>`` 形式的值中提取文件 id，否则 None。"""
    if isinstance(value, str) and value.startswith(FILE_PREFIX):
        try:
            return uuid.UUID(value.removeprefix(FILE_PREFIX))
        except ValueError:
            return None
    return None


def _file_items(session: Session) -> list[ConfigItem]:
    return list(
        session.exec(
            select(ConfigItem).where(col(ConfigItem.value_type).in_(FILE_TYPES))
        ).all()
    )


def referenced_ids(session: Session, tenant_ids: Iterable[uuid.UUID]) -> set[uuid.UUID]:
    """平台配置值与给定租户覆盖值引用的文件 id。注意：会切换会话的 RLS 租户，调用方需恢复。"""
    items = _file_items(session)
    refs = {
        fid for i in items for v in (i.value, i.default_value) if (fid := file_id(v))
    }
    item_ids = [i.id for i in items]
    for tid in tenant_ids:
        set_tenant(session, tid)
        rows = session.exec(
            select(TenantConfigValue.value).where(
                TenantConfigValue.tenant_id == tid,
                col(TenantConfigValue.item_id).in_(item_ids),
            )
        ).all()
        refs |= {fid for v in rows if (fid := file_id(v))}
    return refs


def _all_tenant_ids(session: Session) -> list[uuid.UUID]:
    return list(session.exec(select(Tenant.id)).all())


def _delete(session: Session, f: UploadedFile) -> None:
    (upload_dir() / f.stored_name).unlink(missing_ok=True)
    session.delete(f)


def release_values(
    session: Session, old_values: Iterable[Any], restore_tenant: uuid.UUID | None
) -> int:
    """删除旧配置值引用、现已无人引用的文件（配置变更提交后调用）。

    Returns:
        删除的文件数。
    """
    files = [
        f
        for v in old_values
        if (fid := file_id(v)) and (f := session.get(UploadedFile, fid))
    ]
    deleted = 0
    for f in {f.id: f for f in files}.values():
        scope = [f.tenant_id] if f.tenant_id else _all_tenant_ids(session)
        if f.id not in referenced_ids(session, scope):
            _delete(session, f)
            deleted += 1
    session.commit()
    set_tenant(session, restore_tenant)
    return deleted


def cleanup_unreferenced(
    session: Session,
    grace: timedelta = timedelta(hours=24),
    tenant_id: uuid.UUID | None = None,
    dry_run: bool = False,
) -> list[UploadedFile]:
    """删除超过宽限期且未被引用的文件。

    Args:
        session: 数据库会话。
        grace: 宽限期（新上传但尚未保存到配置的文件不删）。
        tenant_id: 仅清理某租户的文件；None 为全部。
        dry_run: 只返回不删除。

    Returns:
        被（将被）删除的文件。
    """
    cutoff = datetime.now(UTC) - grace
    stmt = select(UploadedFile).where(col(UploadedFile.created_at) < cutoff)
    if tenant_id:
        stmt = stmt.where(UploadedFile.tenant_id == tenant_id)
    candidates = list(session.exec(stmt).all())
    if not candidates:
        return []
    refs = referenced_ids(
        session, [tenant_id] if tenant_id else _all_tenant_ids(session)
    )
    victims = [f for f in candidates if f.id not in refs]
    if not dry_run:
        for f in victims:
            _delete(session, f)
        session.commit()
    set_tenant(session, None)
    logger.info(
        "file cleanup: %d unreferenced file(s)%s",
        len(victims),
        " (dry run)" if dry_run else "",
    )
    return victims
