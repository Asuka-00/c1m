"""P2-B11 / D57：mes_eap_event（EAP 事件台账）与 mes_idempotency_key（Idempotency-Key 存档）

- mes_eap_event：uq_mes_eap_event_0 (tenant, source, external_event_id)，存 request_hash 与首次
  处理结果，重放原样返回；内容不同 422 idempotency_key_reused（D54-1 / D57）。
- mes_idempotency_key：uq_mes_idempotency_key_0 (tenant, endpoint, idem_key)，保留 24 小时（D57）。
均启用 RLS。升级 / 降级均可重复执行。

Revision ID: 0028_eap_events_idempotency
Revises: 0027_transform_undone
"""

import sqlalchemy as sa
from alembic import op

from app.core.migrate import disable_rls, enable_rls

revision = "0028_eap_events_idempotency"
down_revision = "0027_transform_undone"
branch_labels = None
depends_on = None

EVT, IDEM = "mes_eap_event", "mes_idempotency_key"
S, DT, J = sa.String, sa.DateTime(timezone=True), sa.JSON


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _sys() -> list[sa.Column]:
    return [
        sa.Column("attrs", J(), nullable=True),
        sa.Column("created_at", DT, nullable=True),
        sa.Column("updated_at", DT, nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
    ]


def _create(name: str, *items: object, unique: tuple[str, ...], refs: tuple[str, ...] = ()) -> None:
    op.create_table(
        name,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        *items,
        *_sys(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", *unique, name=f"uq_{name}_0",
            postgresql_nulls_not_distinct=True,
        ),
    )
    for c in ("tenant_id", *refs):
        op.create_index(op.f(f"ix_{name}_{c}"), name, [c], unique=False)
    enable_rls(op, [name])


def upgrade():
    have = _tables()
    if EVT not in have:
        _create(
            EVT,
            sa.Column("source", S(40), nullable=False),
            sa.Column("external_event_id", S(128), nullable=False),
            sa.Column("event_type", S(40), nullable=False),
            sa.Column("equipment_id", sa.Uuid(), nullable=True),
            sa.ForeignKeyConstraint(
                ["equipment_id"], ["mes_equipment.id"], ondelete="RESTRICT"
            ),
            sa.Column("payload", J(), nullable=True),
            sa.Column("request_hash", S(64), nullable=True),
            sa.Column("result", J(), nullable=True),
            sa.Column("username", S(255), nullable=True),
            sa.Column("received_at", DT, nullable=True),
            unique=("source", "external_event_id"),
            refs=("equipment_id",),
        )
    if IDEM not in have:
        _create(
            IDEM,
            sa.Column("endpoint", S(200), nullable=False),
            sa.Column("idem_key", S(128), nullable=False),
            sa.Column("request_hash", S(64), nullable=False),
            sa.Column("status_code", sa.Integer(), nullable=False),
            sa.Column("response", J(), nullable=True),
            sa.Column("username", S(255), nullable=True),
            unique=("endpoint", "idem_key"),
        )


def downgrade():
    have = _tables()
    for name in (IDEM, EVT):
        if name in have:
            disable_rls(op, [name])
            op.drop_table(name)
