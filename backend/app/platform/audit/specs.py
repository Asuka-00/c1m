"""审计日志实体规格（由 app.core.spec.audit 写入）。"""

from app.core.spec.engine import Entity, F, register

register(
    Entity(
        "audit_log",
        "common",
        "Audit log",
        [
            F("entity_type", "enum", "Entity", enum="entity_type"),
            F("action", "enum", "Action", enum="audit_action"),
            F(
                "record_id",
                "str",
                "Record id",
                max_length=36,
                list=False,
                filter=False,
            ),
            F(
                "record_code",
                "str",
                "Record",
                max_length=200,
                search=True,
            ),
            F("changes", "json", "Changes"),
            F(
                "username",
                "str",
                "User",
                max_length=255,
                search=True,
                filter=True,
            ),
        ],
        phase=1,
        has_code=False,
        readonly=True,
        icon="History",
        order=4,
        sort_default="created_at",
        label_field="record_code",
    ),
)
