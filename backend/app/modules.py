"""组合根：功能模块的有序清单。

顺序即规格注册顺序（决定表/菜单/实体类型的顺序）与路由挂载顺序
（路由另按 ``router_priority`` 稳定排序）。新增模块需在此按依赖顺序导入其 ``module.py``。
"""

from app.mes.common import module as _mes_common  # noqa: F401
from app.mes.equipment import module as _mes_equipment  # noqa: F401
from app.mes.execution import module as _mes_execution  # noqa: F401
from app.mes.factory import module as _mes_factory  # noqa: F401
from app.mes.lot import module as _mes_lot  # noqa: F401
from app.mes.planning import module as _mes_planning  # noqa: F401
from app.mes.process import module as _mes_process  # noqa: F401
from app.mes.product import module as _mes_product  # noqa: F401
from app.mes.quality import module as _mes_quality  # noqa: F401
from app.mes.warehouse import module as _mes_warehouse  # noqa: F401
from app.platform.audit import module as _audit  # noqa: F401
from app.platform.auth import module as _auth  # noqa: F401
from app.platform.config import module as _config  # noqa: F401
from app.platform.files import module as _files  # noqa: F401
from app.platform.menus import module as _menus  # noqa: F401
from app.platform.rbac import module as _rbac  # noqa: F401
from app.platform.tenants import module as _tenants  # noqa: F401
from app.platform.users import module as _users  # noqa: F401
