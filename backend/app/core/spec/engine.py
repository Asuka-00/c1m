"""声明式实体规格 → SQLAlchemy 表（带 tenant_id，受 RLS 保护）。"""

from dataclasses import dataclass, field
from typing import Any, Literal

import sqlalchemy as sa
from sqlmodel import SQLModel

FieldType = Literal[
    "str",
    "text",
    "int",
    "float",
    "bool",
    "enum",
    "ref",
    "date",
    "time",
    "datetime",
    "json",
]
STATUSES = ("draft", "active", "inactive")
# 版本化主数据：允许的状态迁移
STATUS_TRANSITIONS = {
    "draft": {"active", "inactive"},
    "active": {"inactive"},
    "inactive": {"active"},
}

# 规格权限模块：编码 -> (英文标签, 排序)，以及额外
# 权限编码；二者都由各模块的 module.py 通过
# app.core.registry.register() 填充
MODULES: dict[str, tuple[str, int]] = {}
EXTRA_PERMISSIONS: dict[str, str] = {}


def perm(module: str, action: Literal["read", "write"]) -> str:
    """实体权限编码。

    Args:
        module: 权限模块编码。
        action: ``read`` / ``write``。

    Returns:
        ``mes.<module>:<action>``。
    """
    return f"mes.{module}:{action}"


@dataclass
class F:
    """字段规格。

    Attributes:
        name: 字段名（引用字段为目标名，列名为 ``<name>_id``）。
        type: 类型（str / text / int / float / bool / enum / ref / date / time / datetime / json）。
        label: 英文标签（数据库种子 / 接口兜底用；各语言显示文案在前端语言包 ``mes.field.*``）。
        required: 是否必填。
        ref: 引用的实体编码。
        enum: 枚举名（见 ENUMS）。
    """

    name: str
    type: FieldType = "str"
    label: str | None = None  # 英文标签；None 表示使用共享的 FIELD_LABELS
    required: bool = False
    enum: str | None = None  # ENUMS 的 key
    ref: str | None = None  # 目标实体编码
    cascade: bool = False  # 引用：随被引用行一起删除（子表行）
    max_length: int = 100
    search: bool = False  # 参与 ?q= 关键字搜索
    list: bool = True  # 显示为表格列
    default: Any = None
    filter: bool | None = None  # 下拉筛选；默认 enum/bool/ref 字段
    help: str | None = None
    # 条件必填：{其他字段: (取值...)}；"*" 表示任意非空值
    required_when: dict[str, tuple[Any, ...]] | None = None
    # 仅在 required_when 条件满足时显示于表单（如卡控绑定的范围字段）
    only_when_required: bool = False
    default_from: str | None = None  # 为空时复制该同级字段（如 code）
    auto: bool = False  # 为空时由后端生成（如编码规则）
    system: bool = False  # 仅由后端设置，从不取自请求载荷
    depends: str | None = None  # 引用选项按此同级引用过滤（目标上同名字段）
    ref_filter: dict[str, str] | None = None  # 引用选项的固定筛选（如只列待入库批次）

    @property
    def column(self) -> str:
        """数据库列名（引用字段为 ``<name>_id``）。"""
        return f"{self.name}_id" if self.type == "ref" else self.name

    @property
    def filterable(self) -> bool:
        """是否可作为列表筛选条件。"""
        if self.filter is not None:
            return self.filter
        return self.type in ("enum", "bool", "ref")


@dataclass
class Entity:
    """实体规格。

    Attributes:
        code: 实体编码（表名 ``mes_<code>``）。
        module: 所属权限模块。
        label: 英文标签（显示文案在前端语言包 ``mes.entity.*``）。
        fields: 字段规格。
        versioned: 是否版本化（draft/active/inactive，激活后锁定）。
        tree: 是否树形（parent 自引用）。
        parent: 子表所属的父实体（随父级版本锁定与复制）。
        internal: 内部实体（不暴露通用 API / 菜单）。
    """

    code: str  # API 名，如 "equipment_type"
    module: str
    label: str  # 英文标签
    fields: list[F]
    phase: int
    path: str | None = None  # URL 段；默认把 code 中的 '_' 换成 '-'
    has_code: bool = True  # `code` + `name` 列（code 唯一）
    tree: bool = False  # 自引用 `parent_id`
    versioned: bool = False  # `version` + `status`（draft/active/inactive）
    unique: list[tuple[str, ...]] = field(default_factory=list)  # 业务唯一键
    parent: str | None = None  # 作为该引用字段的子表（在详情抽屉中显示）
    children: list[str] = field(default_factory=list)  # 子实体编码
    readonly: bool = False  # 如审计日志
    internal: bool = False  # 不暴露 API / 菜单
    icon: str = "Box"
    order: int = 0
    label_field: str = "code"
    label_ref: str | None = None  # 在标签后追加该引用的编码（如 工步 -> 工序）
    sort_default: str = "code"
    parent_required_when: dict[str, tuple[Any, ...]] | None = None
    has_name: bool = True
    code_label: str | None = None
    code_auto: bool = False  # code 为空时按编码规则生成
    perm_module: str | None = None  # 使用其他模块的权限
    menu: bool = True  # 独立菜单项（False：从其他页面进入）

    @property
    def pmod(self) -> str:
        """用于权限判断的模块（子表继承父实体）。"""
        return self.perm_module or self.module

    @property
    def table_name(self) -> str:
        """数据库表名。"""
        return f"mes_{self.code}"

    @property
    def url(self) -> str:
        """API 路径段（下划线转连字符）。"""
        return self.path or self.code.replace("_", "-")

    def field(self, name: str) -> F | None:
        """按名称查找字段，不存在返回 None。"""
        return next((f for f in self.all_fields if f.name == name), None)

    @property
    def all_fields(self) -> list[F]:
        """声明字段 + 隐式可编辑字段（如 status、attrs），按显示顺序。"""
        out: list[F] = []
        if self.has_code:
            out.append(
                F(
                    "code",
                    label=self.code_label,
                    required=True,
                    search=True,
                    max_length=64,
                    auto=self.code_auto,
                )
            )
            if self.has_name:
                out.append(F("name", required=True, search=True, max_length=200))
        if self.tree:
            out.append(
                F(
                    "parent",
                    "ref",
                    ref=self.code,
                    cascade=True,
                    required_when=self.parent_required_when,
                )
            )
        out += self.fields
        if self.has_code:
            out.append(F("description", "text", list=False, search=True))
        return out

    @property
    def natural_key(self) -> tuple[str, ...]:
        """业务唯一键字段（如 code[, version]），用于导入匹配与去重。"""
        if self.unique:
            return self.unique[0]
        return ("code", "version") if self.versioned else ("code",)


ENTITIES: dict[str, Entity] = {}
ENUMS: dict[str, list[tuple[str, str]]] = {}
FIELD_LABELS: dict[str, str] = {}
TABLES: dict[str, sa.Table] = {}


def _sa_type(f: F) -> Any:
    match f.type:
        case "str" | "enum":
            return sa.String(f.max_length if f.type == "str" else 40)
        case "text":
            return sa.Text()
        case "int":
            return sa.Integer()
        case "float":
            return sa.Float()
        case "bool":
            return sa.Boolean()
        case "date":
            return sa.Date()
        case "time":
            return sa.Time()
        case "datetime":
            return sa.DateTime(timezone=True)
        case "json":
            return sa.JSON()
        case "ref":
            return sa.Uuid()


def build_table(e: Entity) -> sa.Table:
    """根据实体规格构建 SQLAlchemy 表（系统列、外键、唯一约束、索引）。"""
    cols: list[Any] = [
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Uuid(),
            sa.ForeignKey("tenant.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
    ]
    for f in e.all_fields:
        if f.type == "ref":
            target = ENTITIES[f.ref or ""].table_name
            cols.append(
                sa.Column(
                    f.column,
                    sa.Uuid(),
                    sa.ForeignKey(
                        f"{target}.id",
                        ondelete="CASCADE" if f.cascade else "RESTRICT",
                    ),
                    nullable=not f.required,
                    index=True,
                )
            )
        else:
            cols.append(sa.Column(f.column, _sa_type(f), nullable=not f.required))
    if e.versioned:
        cols += [
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        ]
    cols += [
        sa.Column("attrs", sa.JSON(), nullable=True),  # 自定义属性
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
    ]
    keys = list(e.unique) or ([e.natural_key] if e.has_code else [])
    for i, key in enumerate(keys):
        colnames = [(fld.column if (fld := e.field(k)) else k) for k in key]
        cols.append(
            sa.UniqueConstraint(
                "tenant_id",
                *colnames,
                name=f"uq_{e.table_name}_{i}",
                postgresql_nulls_not_distinct=True,  # 唯一键中的可选部分
            )
        )
    return sa.Table(e.table_name, SQLModel.metadata, *cols)


def register(*entities: Entity) -> None:
    """注册实体规格（建表在 :func:`build_all` 中统一进行）。"""
    for e in entities:
        assert e.code not in ENTITIES, e.code
        assert e.module in MODULES, e.module
        ENTITIES[e.code] = e


def build_all() -> None:
    """为所有已注册且尚未建表的实体构建表。"""
    for e in ENTITIES.values():
        if e.code not in TABLES:
            for f in e.all_fields:
                assert f.label or f.name in FIELD_LABELS, f"{e.code}.{f.name}: label"
                assert f.type != "enum" or f.enum in ENUMS, f"{e.code}.{f.name}: enum"
                assert f.type != "ref" or f.ref in ENTITIES, f"{e.code}.{f.name}: ref"
            TABLES[e.code] = build_table(e)


def label_of(f: F) -> str:
    """字段的英文标签（缺省时取全局字段标签）。"""
    return f.label or FIELD_LABELS[f.name]
