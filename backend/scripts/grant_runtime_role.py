"""D83 补救：0036 运行时角色不存在而跳过授权后，DBA 建好角色再执行本脚本。

只执行 0036 同一组幂等 GRANT / 默认权限语句（迁移角色连接）；不建角色、不改密码。
用法：``python scripts/grant_runtime_role.py``（读取与 alembic 相同的配置）。
"""

import importlib.util
import pathlib
import sys

import sqlalchemy as sa

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402

_P = (
    pathlib.Path(__file__).resolve().parents[1]
    / "app/alembic/versions/0036_d83_runtime_role_grants.py"
)


def main() -> int:
    spec = importlib.util.spec_from_file_location("m0036", _P)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    eng = sa.create_engine(settings.migration_database_url)
    with eng.begin() as c:
        role = m.runtime_role(c)
        if not role:
            sys.stdout.write(
                "runtime role missing or same as migration role: nothing granted" + "\n"
            )
            return 1
        db = str(c.execute(sa.text("SELECT current_database()")).scalar())
        for stmt in m.grant_statements(role, db, m.migration_role(c)):
            c.execute(sa.text(stmt))
    sys.stdout.write(f"granted runtime role {role!r} on {db}" + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
