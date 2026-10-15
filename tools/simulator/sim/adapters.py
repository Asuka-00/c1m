"""事件 -> MES 接口的适配层（可插拔）。

每个适配器声明它需要的接口路径（可有多个候选，取后端 openapi 里第一个存在的）。
后端没有这些接口时（例如 B9 报警、B10 耗材计数还没做），场景整体标记为 skipped，而不是失败。

按 D30，手工接口不传 ``source``；模拟器标识放在 ``external_event_id``（支持的接口）、
``Idempotency-Key`` 请求头和 comment 里，数据在 MES 里记为 manual（D54）。

``--mode b11``：E10 状态、报警、清除、耗材计数改发到 D54 的 EAP 写入入口 ``POST /mes/eap/events``
（P2-B11，后端 8294b63），带 ``source=simulator`` 和 ``external_event_id``，幂等键
(tenant, source, external_event_id)。只有 ``eap_service`` 角色的服务账号能调（其他账号 403）。
默认仍是 manual。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Call:
    method: str
    path: str
    body: Any = None
    idem: str | None = None


def _norm(path: str) -> str:
    import re

    return re.sub(r"\{[^}]+\}", "{}", path)


@dataclass
class Adapter:
    name: str
    candidates: list[str]  # openapi 路径模板，按优先级
    card: str = ""  # 依赖的后端卡（用于 skipped 说明）
    path: str | None = field(default=None)

    def resolve(self, paths: set[str]) -> str | None:
        """按路径形状匹配：路径参数名不同（后端 ``{rid}``、我们 ``{reticle_id}``）也算同一条接口；返回我们的模板。"""
        norm = {_norm(p) for p in paths}
        self.path = next((p for p in self.candidates if p in paths or _norm(p) in norm), None)
        return self.path

    def skip_reason(self) -> str:
        dep = f"（依赖 {self.card}）" if self.card else ""
        return f"后端没有 {self.name} 接口{dep}，尝试过：{', '.join(self.candidates)}"


def default_adapters() -> dict[str, Adapter]:
    return {
        "e10": Adapter("设备状态变化", ["/mes/eqp/{eq_id}/e10"]),
        "stage": Adapter("开工/出站", ["/mes/exec/lots/{lot_id}/{stage}"]),
        "mount": Adapter("上料", ["/mes/eqp/{eq_id}/mount"]),
        "unmount": Adapter("卸料", ["/mes/eqp/mount/{mount_id}/unmount"]),
        "holds": Adapter("Hold 查询", ["/mes/exec/holds"]),
        # 通用 CRUD：报警码种子（D59）、E10 履历（D58 trigger）、工具字段（P2-D3 过期/不可用）
        "crud": Adapter("通用列表/新增", ["/mes/{entity}"]),
        "crud_item": Adapter("通用修改", ["/mes/{entity}/{rid}"]),
        # B9（0a74f8a）：/mes/eqp 下的报警接口。B9 没有按 ALID 清除的接口，清除只能按报警 id。
        "alarm_set": Adapter("报警上报", ["/mes/eqp/{eq_id}/alarms"], card="B9"),
        "alarm_clear": Adapter("报警清除", ["/mes/eqp/alarms/{alarm_id}/clear"], card="B9"),
        # B11（8294b63）新增的手工接口：按设备 + ALID 清除
        "alarm_clear_alid": Adapter("按 ALID 清除报警", ["/mes/eqp/alarms/clear"], card="B11"),
        # D55 OQ-3：查报警记录及关联在制批（mes_alarm_lot -> data.lots）
        "alarm_get": Adapter("报警记录查询", ["/mes/eqp/alarms/{alarm_id}"], card="B9"),
        "alarm_list": Adapter("报警履历列表", ["/mes/eqp/alarms"], card="B9"),
        # D54：EAP 写入入口，仅 --mode b11 使用
        "eap_events": Adapter("EAP 事件入口", ["/mes/eap/events"], card="B11"),
        # B10（d27b700）：/mes/eqp/tools/{tool_id}/...
        "tool_usage": Adapter("耗材计数", ["/mes/eqp/tools/{tool_id}/usage"], card="B10"),
        "tool_reset": Adapter("耗材计数重置", ["/mes/eqp/tools/{tool_id}/reset"], card="B10"),
        "tool_mount": Adapter("工具上机", ["/mes/eqp/tools/{tool_id}/mount"], card="B10"),
        "tool_unmount": Adapter("工具下机", ["/mes/eqp/tools/{tool_id}/unmount"], card="B10"),
        "tool_replace": Adapter("工具更换", ["/mes/eqp/tools/{tool_id}/replace"], card="B10"),
        # GET 与上报同一路径模板
        "tool_usage_log": Adapter("耗材用量履历", ["/mes/eqp/tools/{tool_id}/usage"], card="B10"),
        "tool_mounts": Adapter("工具上下机履历", ["/mes/eqp/tools/{tool_id}/mounts"], card="B10"),
        # P3-B4（光罩，未实现）：E1 草案 v0.6 的接口，草稿场景用；路径在后端落地后以 openapi 为准
        "reticle_mount": Adapter("光罩挂载", ["/mes/reticle/{reticle_id}/mount"], card="P3-B4"),
        "reticle_incident": Adapter("光罩事故录入", ["/mes/reticle/{reticle_id}/incident"], card="P3-B4"),
        "reticle_get": Adapter("光罩详情", ["/mes/reticle/{reticle_id}", "/mes/{entity}/{rid}"], card="P3-B4"),
        # 335db8a：领域事件记在 audit_log（D71），GET /mes/audit_log?entity_type=reticle&record_id=…
        "reticle_events": Adapter("光罩领域事件（audit_log）", ["/mes/audit_log", "/mes/{entity}"], card="P3-B4"),
        "reticle_history": Adapter("光罩履历", ["/mes/reticle/{reticle_id}/history"], card="P3-B4"),
        # E1 v0.7 §3.2 / §5（D67）：动作接口与人工调整计数
        "reticle_usage_manual": Adapter("光罩计数人工调整", ["/mes/reticle/{reticle_id}/usage"], card="P3-B4"),
        "reticle_hold": Adapter("光罩 Hold", ["/mes/reticle/{reticle_id}/hold"], card="P3-B4"),
        "reticle_release": Adapter("光罩解除 Hold", ["/mes/reticle/{reticle_id}/release"], card="P3-B4"),
        "reticle_restore": Adapter("光罩人工恢复", ["/mes/reticle/{reticle_id}/restore"], card="P3-B4"),
        "reticle_scrap": Adapter("光罩报废", ["/mes/reticle/{reticle_id}/scrap"], card="P3-B4"),
        "reticle_unmount": Adapter("光罩卸载", ["/mes/reticle/{reticle_id}/unmount"], card="P3-B4"),
        "reticle_inspection": Adapter("光罩检查录入", ["/mes/reticle/{reticle_id}/inspection"], card="P3-B4"),
        "reticle_life_reset": Adapter("光罩寿命重置", ["/mes/reticle/{reticle_id}/life-reset"], card="P3-B4"),
        # D80 补充二：_flow 路由 4 个，同样 Idempotency-Key 必填（共 14 个）
        "reticle_clean_start": Adapter("光罩开始清洗", ["/mes/reticle/{reticle_id}/clean-start"], card="P3-B4"),
        "reticle_clean_complete": Adapter("光罩清洗完成", ["/mes/reticle/{reticle_id}/clean-complete"], card="P3-B4"),
        "reticle_repair_complete": Adapter("光罩维修完成", ["/mes/reticle/{reticle_id}/repair-complete"], card="P3-B4"),
        "reticle_inspect_start": Adapter("光罩开始检查", ["/mes/reticle/{reticle_id}/inspect-start"], card="P3-B4"),
        # D80+补充一：10 个写接口（usage/incident/inspection/mount/unmount/hold/release/restore/life-reset/scrap）
        #   Idempotency-Key 必填，缺失 422 missing loc [header, Idempotency-Key]；重放按 D57
        # P3-B8（D70，未实现）：报警码 track_in_action 配置。路径为提议（通用 CRUD PATCH 或专用接口），B8 落地后核对
        # D70 补充：改配置走通用 CRUD PATCH /mes/alarm_code/{rid}；非法值 422 enum（ctx.expected=[off,warn,block]）；
        #   设备类型层传 null 422，单台设备覆盖层传 null = 清空改为继承；eap_service 不能改（403）
        "alarm_track_in_action": Adapter("报警码进站动作配置", ["/mes/alarm_code/{rid}"], card="P3-B8"),
        "alarm_code_get": Adapter("报警码详情", ["/mes/alarm_code/{rid}"], card="P3-B8"),
        # D70 补充：删除仍被单台行引用的类型行 409 referenced（通用 CRUD DELETE），B8 落地后核对
        # P3-B6（D74 + D85 + 补充一，未实现）：operator_qual 通用 CRUD 写接口必须带 key；履历 GET .../{qual_id}/history
        "operator_qual": Adapter("人员资质写接口", ["/mes/exec/operator-qual"], card="P3-B6"),
        "operator_qual_history": Adapter("人员资质履历", ["/mes/exec/operator-qual/{qual_id}/history"], card="P3-B6"),
        "alarm_code_delete": Adapter("报警码删除", ["/mes/alarm_code/{rid}"], card="P3-B8"),
        # P3-B2（打标，未实现，D78/D79）：主记录 + mes_marking_print（每次打印一行，seq 后端分配）
        #   + mes_marking_inspection。
        # D79-3：POST /mes/marking 只建主记录；所有打印（含首打）走 POST /mes/marking/{id}/prints，EAP 上报同一套逻辑。
        # 打印/检验列表 GET 路径与 EAP kind=print|inspection 是本组提议，D78 补充二定为后端先按提议实现
        "marking_create": Adapter("打标主记录创建", ["/mes/marking"], card="P3-B2"),
        "marking_print": Adapter(
            "打印（首打/重打，新增 print 行）", ["/mes/marking/{marking_id}/prints"], card="P3-B2"
        ),
        # D79-6：筛选 marked_at_from / marked_at_to（D77 半开区间）
        "marking_list": Adapter("打标记录列表", ["/mes/marking"], card="P3-B2"),
        # D79-5/6 + 补充 1：追溯 GET /mes/exec/trace?kind=trace_code&code=，权限 mes.exec:read；
        #   默认不含已作废，include_voided=true 才含
        "marking_trace": Adapter("追溯（kind=trace_code）", ["/mes/exec/trace"], card="P3-B3"),
        # P3-B3（未实现）：出货标签生成时比对打标内容，不一致 409 label_marking_mismatch（D78 补充一 2）
        #   包装 / 标签接口是 P2-B2：/mes/pack、/mes/pack/{id}/pack、/mes/label/{pack_id}/print
        "pack_create": Adapter("包装创建", ["/mes/pack"], card="P2-B2"),
        "pack_pack": Adapter("包装装入批次", ["/mes/pack/{pack_id}/pack"], card="P2-B2"),
        "label_print": Adapter("出货标签打印", ["/mes/label/{pack_id}/print"], card="P3-B3"),
        "marking_inspect": Adapter(
            "打标检验（新增 inspection 行）", ["/mes/marking/{marking_id}/inspect"], card="P3-B2"
        ),
        "marking_preview": Adapter("打标预览", ["/mes/marking/preview"], card="P3-B2"),
        "marking_get": Adapter("打标记录", ["/mes/marking/{marking_id}"], card="P3-B2"),
        "marking_prints": Adapter("打印履历 mes_marking_print", ["/mes/marking/{marking_id}/prints"], card="P3-B2"),
        "marking_inspections": Adapter(
            "检验履历 mes_marking_inspection", ["/mes/marking/{marking_id}/inspections"], card="P3-B2"
        ),
        "marking_events": Adapter("打标领域事件（audit_log）", ["/mes/audit_log", "/mes/{entity}"], card="P3-B2"),
        # D78 补充二 3：作废（必填 reason_id + comment，reason_type=marking_void，不可恢复）
        "marking_void": Adapter("打标记录作废", ["/mes/marking/{marking_id}/void"], card="P3-B2"),
        # D78 补充三 6：trace_code 生效配置（trace_code_max_length / trace_code_pattern），权限 mes.marking:exec
        "marking_config": Adapter("打标配置", ["/mes/marking/config"], card="P3-B2"),
        # P3-B1 模板（D79-1/2）：建模板 + 审批；产品绑定已批准模板 = 要求打标（D79 补充 5）
        "marking_template": Adapter("打标模板", ["/mes/marking-template"], card="P3-B1"),
        "marking_template_approve": Adapter("打标模板审批", ["/mes/marking-template/{id}/approve"], card="P3-B1"),
        # D79 补充七：模板写接口（创建 / 编辑 / 新版本 / 审批）必须带 Idempotency-Key；预览、校验是只读 POST，不带
        "marking_template_item": Adapter("打标模板编辑", ["/mes/marking-template/{id}"], card="P3-B1"),
        "marking_template_version": Adapter("打标模板新版本", ["/mes/marking-template/{id}/versions"], card="P3-B1"),
        "marking_template_preview": Adapter("打标模板预览（只读）", ["/mes/marking-template/preview"], card="P3-B1"),
        "marking_template_validate": Adapter("打标模板校验（只读）", ["/mes/marking-template/validate"], card="P3-B1"),
        # 批次整批报废：P1 数量调整 kind=scrap 报废到 0 → lot_status=scrapped（后端确认 adjust.py:128）
        "lot_adjust": Adapter("批次数量调整（报废）", ["/mes/exec/lots/{lot_id}/adjust"], card="P1"),
    }


# 每种场景步骤需要哪些适配器
STEP_ADAPTERS: dict[str, list[str]] = {
    "state": ["e10"],
    "track_in": ["stage"],
    "move_in": ["stage"],
    "track_out": ["stage"],
    "mount": ["mount"],
    "unmount": ["unmount"],
    "expect_hold": ["holds"],
    "alarm_set": ["alarm_set"],
    "alarm_clear": ["alarm_clear"],
    "tool_usage": ["tool_usage"],
    "tool_reset": ["tool_reset"],
    "tool_mount": ["tool_mount"],
    "tool_unmount": ["tool_unmount"],
    "tool_replace": ["tool_replace"],
    "expect_tool_log": ["tool_usage_log"],
    "expect_alarm": ["alarm_get"],
    "expect_e10": [],
    "seed_alarm_code": ["crud", "crud_item"],
    "expect_e10_history": ["crud"],
    "tool_set": ["crud_item"],
    "expect_eap_read": ["crud", "crud_item"],
    "expect_query_422": [],
    "expect_datetime_eq_match": [],
    "reticle_crud": [],
    "expect_reticle_life_state": [],
    "expect_body_422": ["e10"],  # move_in/track_in 时见 step_adapters
    "expect_eap_envelope_extra": ["eap_events"],
    "expect_alarm_list": ["alarm_list"],
    "replay": [],
    # P3 草稿步骤（P3-B4 前不执行）
    "reticle_mount": ["reticle_mount"],
    "reticle_usage": ["eap_events"],  # 以后 B11 event_type=reticle_usage（P3 不实现）
    "reticle_incident": ["reticle_incident"],
    "expect_reticle": ["reticle_get"],
    "expect_reticle_history": ["reticle_history"],
    "expect_reticle_events": ["reticle_events"],
    "expect_effective_track_in_action": ["alarm_code_get"],
    "delete_alarm_code": ["alarm_code_delete"],
    "reticle_adjust": ["reticle_usage_manual"],
    "reticle_hold": ["reticle_hold"],
    "reticle_release": ["reticle_release"],
    "reticle_restore": ["reticle_restore"],
    "reticle_scrap": ["reticle_scrap"],
    "reticle_unmount": ["reticle_unmount"],
    "reticle_inspection": ["reticle_inspection"],
    "reticle_life_reset": ["reticle_life_reset"],
    "reticle_clean_start": ["reticle_clean_start"],
    "reticle_clean_complete": ["reticle_clean_complete"],
    "reticle_repair_complete": ["reticle_repair_complete"],
    "reticle_inspect_start": ["reticle_inspect_start"],
    "set_track_in_action": ["alarm_track_in_action"],
    "expect_alarm_code": ["alarm_code_get"],
    # P3-E2 光罩预审：以后 B11 event_type=reticle_mount/reticle_unmount/reticle_usage（D67：P3 不开）
    "reticle_report": ["eap_events"],
    "reticle_replay": [],  # 重发 save_as 记下的草稿请求：同路径、同请求体、同 Idempotency-Key（或同 external_event_id）
    # P3-B2 打标草稿步骤（B2 前不执行）
    "marking_report": ["eap_events"],  # 以后 B11 event_type=marking；按批次未作废主记录定位，无则 409 no_active_marking
    "marking_create": ["marking_preview", "marking_create"],
    "marking_print": ["marking_print"],  # seq=1 首打；seq>1 重打必填 reason + comment
    "expect_marking_list": ["marking_list"],
    "expect_marking_trace": ["marking_trace"],
    "pack_lot": ["pack_create", "pack_pack"],
    "label_print": ["label_print"],
    "marking_inspect": ["marking_inspect"],
    "marking_void": ["marking_void"],
    "lot_scrap": ["lot_adjust"],
    "marking_config": ["marking_config"],
    "marking_template_ready": ["marking_template", "marking_template_approve"],
    "marking_template": ["marking_template"],
    "expect_marking": ["marking_get"],
    "expect_marking_prints": ["marking_prints"],
    "expect_marking_inspections": ["marking_inspections"],
    "expect_marking_events": ["marking_events"],
    "marking_replay": [],  # 同 reticle_replay：同路径、同请求体、同 Idempotency-Key / external_event_id
    "operator_qual": ["operator_qual"],
    "operator_qual_replay": [],
    "expect_operator_qual_history": ["operator_qual_history"],
    "expect_operator_qual_events": ["operator_qual_history"],
    "reuse": [],
    "precondition": [],
}


# --mode b11 时这些步骤改走 eap_events（其余步骤不变）
B11_STEPS = {"state", "alarm_set", "alarm_clear", "tool_usage"}
MODES = ("manual", "b11")


def step_adapters(kind: str, args: dict | None = None, mode: str = "manual") -> list[str]:
    if mode == "b11" and kind in B11_STEPS:
        return ["eap_events"]
    if kind == "expect_body_422" and args and args.get("endpoint") in ("move_in", "track_in"):
        return ["stage"]
    if kind == "alarm_clear" and args and args.get("alid") is not None:
        return ["alarm_clear_alid"]
    if kind == "expect_tool_log" and args and args.get("log") == "mounts":
        return ["tool_mounts"]
    return STEP_ADAPTERS[kind]


def fill(template: str, **kw: str) -> str:
    out = template
    for k, v in kw.items():
        out = out.replace("{" + k + "}", str(v))
    if "{" in out:
        raise ValueError(f"路径参数没填全：{out}")
    return out
