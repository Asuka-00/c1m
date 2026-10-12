import uuid
from datetime import datetime

from pydantic import EmailStr
from sqlmodel import Field, Relationship, SQLModel

from app.core.models import get_datetime_utc
from app.platform.rbac.models import Role, UserRole

# Shared properties
# login name (alternative to email); no '@' so it can't be confused with an email
USERNAME_RE = r"^[A-Za-z0-9_.-]{3,50}$"


class UserBase(SQLModel):
    email: EmailStr = Field(unique=True, index=True, max_length=255)
    username: str | None = Field(default=None, unique=True, index=True, max_length=50)
    is_active: bool = True
    is_superuser: bool = False
    full_name: str | None = Field(default=None, max_length=255)


# Database model, database table inferred from class name
class User(UserBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    hashed_password: str
    created_at: datetime | None = Field(default_factory=get_datetime_utc)
    roles: list[Role] = Relationship(back_populates="users", link_model=UserRole)
