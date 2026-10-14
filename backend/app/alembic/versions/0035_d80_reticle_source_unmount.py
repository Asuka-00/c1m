"""D80（G1 / G6）：光罩下机单独记事件行；source 加 CHECK。

- ``mes_reticle_mount_log`` 加 ``event_type``（mount / unmount，非空，存量回填 mount）和
  ``mount_log_id``（下机行指向上机行，自引用外键 RESTRICT）。下机行沿用
  (tenant_id, source, external_event_id) 部分唯一索引 ``uq_mes_reticle_mount_event`` 去重。
- ``source`` 列（挂载 / 计数 / 事故三张表）加 CHECK (manual, eap, simulator, system)：
  先统计不合规行，NULL → manual，其他非法值 → system，日志记行数，再加约束。

编号说明：0033（D74 资质履历）、0034（B8 track_in_action）已为 B6 / B8 预留但尚未提交，
本迁移暂接在 0032 之后；B6 / B8 落地时把本文件 down_revision 改为 0034（P3 未发布，可重排）。

Revision ID: 0035_d80_reticle_source_unmount
Revises: 0032_d72_reticle_restrict
"""

import logging

import sqlalchemy as sa
from alembic import op

revision = "0035_d80_reticle_source_unmount"
down_revision = "0032_d72_reticle_restrict"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")

MNT = "mes_reticle_mount_log"
SRC_TABLES = ("mes_reticle_mount_log", "mes_reticle_usage", "mes_reticle_incident")
ALLOWED = ("manual", "eap", "simulator", "system")
_IN = ", ".join(f"'{x}'" for x in ALLOWED)


def _ck(t: str) -> str:
    return f"ck_{t}_source"


def upgrade():
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns(MNT)}
    if "event_type" not in cols:
        op.add_column(MNT, sa.Column("event_type", sa.String(40), nullable=True))
        op.execute(f"UPDATE {MNT} SET event_type = 'mount' WHERE event_type IS NULL")
        op.alter_column(MNT, "event_type", nullable=False)
    if "mount_log_id" not in cols:
        op.add_column(MNT, sa.Column("mount_log_id", sa.Uuid(), nullable=True))
        op.create_foreign_key(
            f"{MNT}_mount_log_id_fkey", MNT, MNT, ["mount_log_id"], ["id"],
            ondelete="RESTRICT",
        )
        op.create_index(f"ix_{MNT}_mount_log_id", MNT, ["mount_log_id"])
    bind = op.get_bind()
    for t in SRC_TABLES:
        n_null = bind.execute(
            sa.text(f"SELECT count(*) FROM {t} WHERE source IS NULL")
        ).scalar()
        n_bad = bind.execute(
            sa.text(
                f"SELECT count(*) FROM {t} WHERE source IS NOT NULL AND source NOT IN ({_IN})"
            )
        ).scalar()
        log.info(
            "D80 %s.source: %s NULL -> manual, %s invalid -> system", t, n_null, n_bad
        )
        if n_null:
            op.execute(f"UPDATE {t} SET source = 'manual' WHERE source IS NULL")
        if n_bad:
            op.execute(f"UPDATE {t} SET source = 'system' WHERE source NOT IN ({_IN})")
        have = {c["name"] for c in sa.inspect(bind).get_check_constraints(t)}
        if _ck(t) not in have:  # 可重跑（迁移往返测试）
            op.create_check_constraint(_ck(t), t, f"source IN ({_IN})")


def downgrade():
    for t in SRC_TABLES:
        op.execute(f"ALTER TABLE IF EXISTS {t} DROP CONSTRAINT IF EXISTS {_ck(t)}")
    op.execute(f"DROP INDEX IF EXISTS ix_{MNT}_mount_log_id")
    op.execute(f"ALTER TABLE IF EXISTS {MNT} DROP COLUMN IF EXISTS mount_log_id")
    op.execute(f"ALTER TABLE IF EXISTS {MNT} DROP COLUMN IF EXISTS event_type")
