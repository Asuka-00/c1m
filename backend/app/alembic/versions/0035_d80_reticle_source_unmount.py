"""D80（G1 / G6）：光罩下机单独记事件行；source 加 CHECK。

- ``mes_reticle_mount_log`` 加 ``event_type``（mount / unmount，非空，存量回填 mount）和
  ``mount_log_id``（下机行指向上机行，自引用外键 RESTRICT）。下机行沿用
  (tenant_id, source, external_event_id) 部分唯一索引 ``uq_mes_reticle_mount_event`` 去重。
- ``source`` 列（挂载 / 计数 / 事故三张表）加 CHECK (manual, eap, simulator, system)：
  先统计不合规行，NULL → manual，其他非法值 → system，日志记行数，再加约束。
- 降级（QA P3-1）：先把下机行的时间 / 原因 / 计数补回对应上机行（上机行已有值不覆盖），
  把下机行整行暂存到 ``alembic_stash.d80_unmount_rows``（独立 schema，运行时角色无权访问）
  后删除，再删列；再次升级时若有暂存则原样恢复（id / source / 事件号不变）并删暂存表。
  从 0032 首次升级（无暂存）的结果与原来一致。

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
    _restore_unmount_rows(bind)


STASH = "alembic_stash.d80_unmount_rows"


def _restore_unmount_rows(bind) -> None:
    """升级：恢复降级时暂存的下机行（没有暂存表则什么都不做）。"""
    if not bind.execute(sa.text(f"SELECT to_regclass('{STASH}')")).scalar():
        return
    cols = [c["name"] for c in sa.inspect(bind).get_columns(MNT)]
    have = {
        c["name"]
        for c in sa.inspect(bind).get_columns("d80_unmount_rows", schema="alembic_stash")
    }
    lst = ", ".join(f'"{c}"' for c in cols if c in have)
    n = bind.execute(
        sa.text(
            f"INSERT INTO {MNT} ({lst}) SELECT {lst} FROM {STASH} s "
            f"WHERE NOT EXISTS (SELECT 1 FROM {MNT} m WHERE m.id = s.id)"
        )
    ).rowcount
    log.info("D80 restored %s unmount rows from %s", n, STASH)
    op.execute(f"DROP TABLE {STASH}")
    op.execute("DROP SCHEMA IF EXISTS alembic_stash")


def downgrade():
    bind = op.get_bind()
    for t in SRC_TABLES:
        op.execute(f"ALTER TABLE IF EXISTS {t} DROP CONSTRAINT IF EXISTS {_ck(t)}")
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns(MNT)} if insp.has_table(MNT) else set()
    if {"event_type", "mount_log_id"} <= cols:
        # 下机行的信息补回上机行（已有值不覆盖），整行暂存后删除，避免再升级时被回填成 mount
        op.execute(
            f"""UPDATE {MNT} m SET
                unmounted_at = COALESCE(m.unmounted_at, u.unmounted_at),
                unmount_reason = COALESCE(m.unmount_reason, u.unmount_reason),
                shots_at_unmount = COALESCE(m.shots_at_unmount, u.shots_at_unmount)
              FROM {MNT} u
             WHERE u.event_type = 'unmount' AND u.mount_log_id = m.id"""
        )
        op.execute("CREATE SCHEMA IF NOT EXISTS alembic_stash")
        op.execute("REVOKE ALL ON SCHEMA alembic_stash FROM PUBLIC")
        if bind.execute(sa.text(f"SELECT to_regclass('{STASH}')")).scalar():
            op.execute(
                f"INSERT INTO {STASH} SELECT * FROM {MNT} WHERE event_type = 'unmount'"
            )
        else:
            op.execute(
                f"CREATE TABLE {STASH} AS SELECT * FROM {MNT} WHERE event_type = 'unmount'"
            )
        n = bind.execute(
            sa.text(f"DELETE FROM {MNT} WHERE event_type = 'unmount'")
        ).rowcount
        log.info("D80 downgrade: %s unmount rows stashed in %s", n, STASH)
    op.execute(f"DROP INDEX IF EXISTS ix_{MNT}_mount_log_id")
    op.execute(f"ALTER TABLE IF EXISTS {MNT} DROP COLUMN IF EXISTS mount_log_id")
    op.execute(f"ALTER TABLE IF EXISTS {MNT} DROP COLUMN IF EXISTS event_type")
