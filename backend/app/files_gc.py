"""Uploaded-file garbage collection.

A file is *referenced* when a platform config value/default or a tenant override
of an image/file item points at ``/api/v1/files/<id>``. Ownership limits where a
reference can live (see config routes): a tenant file only in that tenant's
overrides (or nowhere else), a platform file in platform values or ANY tenant's
overrides. Tenant overrides are read under RLS, one tenant at a time.

- ``release_values``: called after a value is replaced/removed/reset; deletes the
  old files right away when nothing references them any more.
- ``cleanup_unreferenced``: periodic sweep (scripts/cleanup_files.py or
  POST /files/cleanup) for files never saved into config, older than a grace
  period so in-progress uploads survive.
"""

import logging
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlmodel import Session, col, select

from app.core.config import settings
from app.models import ConfigItem, Tenant, TenantConfigValue, UploadedFile
from app.tenancy import set_tenant

logger = logging.getLogger(__name__)

FILE_PREFIX = f"{settings.API_V1_STR}/files/"
FILE_TYPES = ("image", "file")


def upload_dir() -> Path:
    p = Path(settings.UPLOAD_DIR)
    if not p.is_absolute():
        p = Path(__file__).resolve().parents[1] / p  # backend/<UPLOAD_DIR>
    p.mkdir(parents=True, exist_ok=True)
    return p


def file_id(value: Any) -> uuid.UUID | None:
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
    """Ids referenced by platform values and by the given tenants' overrides.
    Changes the session's RLS tenant; callers restore it."""
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
    """Delete files formerly referenced by `old_values` that are now unreferenced.
    Call after the config change is committed."""
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
    """Remove unreferenced files older than `grace` (optionally only one tenant's)."""
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
