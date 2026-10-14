"""事件 -> MES 接口的适配层（可插拔）。

每个适配器声明它需要的接口路径（可有多个候选，取后端 openapi 里第一个存在的）。
后端没有这些接口时（例如 B9 报警、B10 耗材计数还没做），场景整体标记为 skipped，而不是失败。

按 D30，手工接口不传 ``source``；模拟器标识放在 ``external_event_id``（支持的接口）、
``Idempotency-Key`` 请求头和 comment 里，数据在 MES 里记为 manual（D54）。

D54 的 EAP 写入入口 ``POST /mes/eap/events``（P2-B11）落地后，可用 ``--mode b11`` 切过去：
E10 状态、报警、清除、耗材计数都发到这个入口，带 ``source=simulator`` 和 ``external_event_id``。
这是占位实现，默认关闭（mode=manual）；请求体形状等 B11 契约定稿后再对齐。
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


@dataclass
class Adapter:
    name: str
    candidates: list[str]  # openapi 路径模板，按优先级
    card: str = ""  # 依赖的后端卡（用于 skipped 说明）
    path: str | None = field(default=None)

    def resolve(self, paths: set[str]) -> str | None:
        self.path = next((p for p in self.candidates if p in paths), None)
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
        # B9（0a74f8a）：/mes/eqp 下的报警接口。B9 没有按 ALID 清除的接口，清除只能按报警 id。
        "alarm_set": Adapter("报警上报", ["/mes/eqp/{eq_id}/alarms"], card="B9"),
        "alarm_clear": Adapter("报警清除", ["/mes/eqp/alarms/{alarm_id}/clear"], card="B9"),
        # D55 OQ-3：查报警记录及关联在制批（mes_alarm_lot -> data.lots）
        "alarm_get": Adapter("报警记录查询", ["/mes/eqp/alarms/{alarm_id}"], card="B9"),
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
    "replay": [],
    "precondition": [],
}


# --mode b11 时这些步骤改走 eap_events（其余步骤不变）
B11_STEPS = {"state", "alarm_set", "alarm_clear", "tool_usage"}
MODES = ("manual", "b11")


def step_adapters(kind: str, args: dict | None = None, mode: str = "manual") -> list[str]:
    if mode == "b11" and kind in B11_STEPS:
        return ["eap_events"]
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
