"""打标模板表规格（P3-B1，D79-1/2、D89）。

- ``mes_marking_template``：code（≤64，租户内唯一）、name（接口限 ≤128）、description（≤300）、
  product / customer（D61「产品+客户」绑定）、creator（起草人用户名，接口输出为 created_by）。
- ``mes_marking_template_version``：version 从 1 递增；status draft|approved|retired（D89 补充一：
  无 pending）；lines JSON 字符串数组；drafter / approved_by / approved_at / retired_at。
  每个模板至多一条 draft、至多一条 approved（部分唯一索引）。
两张表都是内部实体：不走通用 CRUD，只经 ``/mes/marking-template`` 专用接口读写（D81 + key）。
"""

from app.core.spec.engine import ENUMS, Entity, F, register

ENUMS["marking_template_status"] = [
    ("draft", "Draft|草稿|下書き"),
    ("approved", "Approved|已批准|承認済み"),
    ("retired", "Retired|已停用|廃止"),
]

register(
    Entity(
        "marking_template",
        "marking",
        "Marking template|打标模板|マーキングテンプレート",
        [
            F("product", "ref", "Product|产品|製品", ref="product", required=True),
            F("customer", "ref", "Customer|客户|顧客", ref="customer", required=True),
            F("creator", "str", "Created by|创建人|作成者", max_length=255),
        ],
        phase=6,
        # D89 补充二：code 租户内唯一；产品 + 客户租户内只有一个模板（版本挂在其下）
        unique=[("code",), ("product", "customer")],
        internal=True,
        menu=False,
        icon="Stamp",
    ),
    Entity(
        "marking_template_version",
        "marking",
        "Marking template version|打标模板版本|マーキングテンプレート版",
        [
            F(
                "template",
                "ref",
                "Template|模板|テンプレート",
                ref="marking_template",
                required=True,
            ),
            F("version", "int", "Version|版本|版", required=True),
            F(
                "status",
                "enum",
                "Status|状态|状態",
                enum="marking_template_status",
                required=True,
            ),
            F("lines", "json", "Lines|行|行"),
            F("drafter", "str", "Drafted by|起草人|起案者", max_length=255),
            F("approved_by", "str", "Approved by|批准人|承認者", max_length=255),
            F("approved_at", "datetime", "Approved at|批准时间|承認日時"),
            F("retired_at", "datetime", "Retired at|停用时间|廃止日時"),
        ],
        phase=6,
        has_code=False,
        internal=True,
        menu=False,
        sort_default="version",
        label_field="version",
        unique=[("template", "version")],
        partial_unique=[
            (
                "uq_mes_marking_template_version_open",
                ("template",),
                "status = 'draft'",
            ),
            (
                "uq_mes_marking_template_version_approved",
                ("template",),
                "status = 'approved'",
            ),
        ],
    ),
)
