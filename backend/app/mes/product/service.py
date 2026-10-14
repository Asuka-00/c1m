"""产品模块对外服务面（跨模块只从这里导入）：BOM 查询与开批锁定。"""

from app.mes.product.bom import (
    active_bom,
    bom_brief,
    lock_for_start,
    version_label,
)

__all__ = ["active_bom", "bom_brief", "lock_for_start", "version_label"]
