import uuid

from sqlmodel import SQLModel


class FileUploadPublic(SQLModel):
    id: uuid.UUID
    url: str
    filename: str
    content_type: str
    size: int
    tenant_id: uuid.UUID | None = None
