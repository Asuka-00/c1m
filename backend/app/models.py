"""Model aggregator: importing this registers every table on SQLModel.metadata
(used by Alembic and by code that needs all relationships configured)."""

from sqlmodel import SQLModel

from app.core import registry
from app.platform.config import models as _config  # noqa: F401
from app.platform.files import models as _files  # noqa: F401
from app.platform.menus import models as _menus  # noqa: F401
from app.platform.rbac import models as _rbac  # noqa: F401
from app.platform.tenants import models as _tenants  # noqa: F401
from app.platform.users import models as _users  # noqa: F401

# MES / platform spec entities + CRUD validators, in module order
registry.load()

__all__ = ["SQLModel"]
