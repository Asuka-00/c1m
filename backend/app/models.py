"""模型聚合：导入本模块即把所有表注册到 ``SQLModel.metadata``。

供 Alembic（autogenerate / check）与需要完整关系配置的代码使用；同时调用
``registry.load()`` 按模块顺序加载 MES 规格与 CRUD 校验器并构建规格表。
"""

from sqlmodel import SQLModel

from app.core import registry
from app.platform.config import models as _config  # noqa: F401
from app.platform.files import models as _files  # noqa: F401
from app.platform.menus import models as _menus  # noqa: F401
from app.platform.notification import models as _notification  # noqa: F401
from app.platform.rbac import models as _rbac  # noqa: F401
from app.platform.tenants import models as _tenants  # noqa: F401
from app.platform.users import models as _users  # noqa: F401

# 按模块顺序加载 MES / 平台规格实体与 CRUD 校验器
registry.load()

__all__ = ["SQLModel"]
