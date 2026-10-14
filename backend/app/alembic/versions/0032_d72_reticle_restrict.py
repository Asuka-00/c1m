"""D72：5 张光罩履历表 reticle_id 外键改 ON DELETE RESTRICT（原 CASCADE）。

有履历时删除光罩返回 409 ``referenced``（接口层先查，外键兜底）；不删就 scrap。
适用关系表 mes_reticle_applicability 仍为 CASCADE。定点列已是 numeric(18,6)，不改类型。

Revision ID: 0032_d72_reticle_restrict
Revises: 0031_d71_reticle_inspection
"""

import sqlalchemy as sa
from alembic import op

revision = "0032_d72_reticle_restrict"
down_revision = "0031_d71_reticle_inspection"
branch_labels = None
depends_on = None

RT = "mes_reticle"
TABLES = (
    "mes_reticle_incident",
    "mes_reticle_mount_log",
    "mes_reticle_usage",
    "mes_reticle_inspection",
    "mes_reticle_status_log",
)


def _set(ondelete: str) -> None:
    insp = sa.inspect(op.get_bind())
    have = set(insp.get_table_names())
    for t in TABLES:
        if t not in have:
            continue
        for fk in insp.get_foreign_keys(t):
            if fk["referred_table"] == RT and fk["constrained_columns"] == [
                "reticle_id"
            ]:
                op.drop_constraint(str(fk["name"]), t, type_="foreignkey")
        op.create_foreign_key(
            f"{t}_reticle_id_fkey", t, RT, ["reticle_id"], ["id"], ondelete=ondelete
        )


def upgrade():
    _set("RESTRICT")


def downgrade():
    _set("CASCADE")
