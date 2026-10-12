"""上传文件数据模型（归属平台或租户）。"""

import uuid
from datetime import datetime

from sqlmodel import Field, SQLModel

from app.core.models import get_datetime_utc


class UploadedFile(SQLModel, table=True):
    """Metadata of an uploaded file. tenant_id NULL = platform-owned.
    Bytes live on disk under settings.UPLOAD_DIR/<id><ext>; served publicly by id
    (branding images must load on the sign-in page)."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    tenant_id: uuid.UUID | None = Field(
        default=None, foreign_key="tenant.id", ondelete="CASCADE", index=True
    )
    uploaded_by: uuid.UUID | None = Field(
        default=None, foreign_key="user.id", ondelete="SET NULL"
    )
    filename: str = Field(max_length=255)
    stored_name: str = Field(max_length=64)
    content_type: str = Field(max_length=100)
    size: int
    created_at: datetime | None = Field(default_factory=get_datetime_utc)
