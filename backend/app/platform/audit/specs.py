from app.core.spec.engine import Entity, F, register

register(
    Entity(
        "audit_log",
        "common",
        "Audit log|审计日志|監査ログ",
        [
            F("entity_type", "enum", "Entity|实体|エンティティ", enum="entity_type"),
            F("action", "enum", "Action|操作|操作", enum="audit_action"),
            F(
                "record_id",
                "str",
                "Record id|记录 ID|レコード ID",
                max_length=36,
                list=False,
                filter=False,
            ),
            F(
                "record_code",
                "str",
                "Record|记录|レコード",
                max_length=200,
                search=True,
            ),
            F("changes", "json", "Changes|变更内容|変更内容"),
            F("user_email", "str", "User|用户|ユーザー", max_length=255, search=True),
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
