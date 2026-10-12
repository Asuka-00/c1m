"""Model aggregator: importing this registers every table on SQLModel.metadata
(used by Alembic and by code that needs all relationships configured)."""

from sqlmodel import SQLModel

import app.mes.specs  # noqa: F401
import app.mes.validators  # noqa: F401
import app.mes.wo  # noqa: F401
from app.platform.config import models as _config  # noqa: F401
from app.platform.files import models as _files  # noqa: F401
from app.platform.menus import models as _menus  # noqa: F401
from app.platform.rbac import models as _rbac  # noqa: F401
from app.platform.tenants import models as _tenants  # noqa: F401
from app.platform.users import models as _users  # noqa: F401

__all__ = ["SQLModel"]
