"""清理历史自动创建的个人工作区租户（一次性运维脚本）。

用法::

    python -m app.cleanup_personal_tenants           # 仅列出（演练）
    python -m app.cleanup_personal_tenants --apply   # 删除可安全删除的租户

判定“明确为自动创建的个人工作区”须同时满足：
- 名称为 ``<名字>'s workspace``，slug 为 ``<名字（或邮箱本地部分）slug>-<6位十六进制>``；
- ``<名字>`` 等于该租户某个 owner 的用户名或邮箱。

仅当所有租户作用域表（含 ``tenant_id`` 列）中除结构性表（租户角色、成员）外均无数据时才删除；
有数据的租户只列出不删除。平台操作日志不随租户删除（无外键，保留留痕）。
"""

import logging
import re
import sys
from typing import Any

from sqlalchemy import text

from app.core.db import admin_engine

#: （随租户创建而生成，不算业务数据）；platform_audit 为平台留痕
logger = logging.getLogger(__name__)

#: 结构性表
STRUCTURAL = {"role", "tenant_member", "platform_audit"}
SUFFIX = "'s workspace"


def _slug(value: str) -> str:
    """与旧版个人工作区 slug 生成规则一致。"""
    return (re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "t")[:40]


def find_candidates(conn: Any) -> list[dict[str, Any]]:
    """返回所有个人工作区候选及其业务数据计数。"""
    tables = [
        r[0]
        for r in conn.execute(
            text(
                "SELECT table_name FROM information_schema.columns "
                "WHERE table_schema='public' AND column_name='tenant_id' ORDER BY 1"
            )
        )
    ]
    out = []
    for tid, name, slug in conn.execute(
        text(
            "SELECT id, name, slug FROM tenant WHERE name LIKE :p ORDER BY created_at"
        ),
        {"p": f"%{SUFFIX}"},
    ):
        who = name[: -len(SUFFIX)]
        bases = {_slug(who), _slug(who.split("@")[0])}
        if not any(re.fullmatch(re.escape(b) + r"-[0-9a-f]{6}", slug) for b in bases):
            continue
        owners = conn.execute(
            text(
                'SELECT u.username, u.email FROM tenant_member m JOIN "user" u '
                "ON u.id = m.user_id JOIN member_role mr ON mr.member_id = m.id "
                "JOIN role r ON r.id = mr.role_id AND r.name = 'owner' "
                "WHERE m.tenant_id = :t"
            ),
            {"t": tid},
        ).all()
        if not any(who in (u, e) for u, e in owners):
            continue
        data = {}
        for t in tables:
            if t in STRUCTURAL:
                continue
            n = conn.execute(
                text(f'SELECT count(*) FROM "{t}" WHERE tenant_id = :t'), {"t": tid}
            ).scalar()
            if n:
                data[t] = n
        members = conn.execute(
            text("SELECT count(*) FROM tenant_member WHERE tenant_id = :t"), {"t": tid}
        ).scalar()
        out.append(
            {"id": tid, "name": name, "slug": slug, "members": members, "data": data}
        )
    return out


def cleanup(conn: Any, apply: bool) -> dict[str, list[str]]:
    """列出（并在 ``apply`` 时删除）可安全删除的个人工作区。

    Returns:
        ``deleted``（或演练时将删除）、``kept``（有业务数据）与 ``orphans``（无租户的非超级用户）。
    """
    res: dict[str, list[str]] = {"deleted": [], "kept": [], "orphans": []}
    for c in find_candidates(conn):
        if c["data"]:
            logger.info("KEEP (has data) %s | %s | %s", c["slug"], c["name"], c["data"])
            res["kept"].append(c["slug"])
            continue
        logger.info(
            "%s %s | %s | members=%s",
            "DELETE" if apply else "WOULD DELETE",
            c["slug"],
            c["name"],
            c["members"],
        )
        res["deleted"].append(c["slug"])
        if apply:
            conn.execute(text("DELETE FROM tenant WHERE id = :t"), {"t": c["id"]})
    res["orphans"] = [
        r[0]
        for r in conn.execute(
            text(
                'SELECT username FROM "user" u WHERE NOT is_superuser AND NOT EXISTS '
                "(SELECT 1 FROM tenant_member m WHERE m.user_id = u.id) ORDER BY 1"
            )
        )
    ]
    logger.info("non-superusers without tenant: %s", res["orphans"])
    return res


def main(apply: bool) -> None:
    """命令行入口：在管理连接（绕过 RLS）上执行清理。"""
    with admin_engine.begin() as conn:
        cleanup(conn, apply)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main("--apply" in sys.argv)
