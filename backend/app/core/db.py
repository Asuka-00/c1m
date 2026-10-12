"""数据库引擎：``engine``（运行时，受 RLS 约束）与 ``admin_engine``（owner，仅迁移/测试/维护）。"""

from sqlmodel import create_engine

from app.core.config import settings

engine = create_engine(str(settings.DATABASE_URL), pool_pre_ping=True)
# 特权引擎（表 owner）：仅用于迁移、测试初始化与维护
admin_engine = create_engine(settings.migration_database_url, pool_pre_ping=True)
