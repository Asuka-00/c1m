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
        "alarm_set": Adapter(
            "报警上报",
            ["/mes/eqp/{eq_id}/alarms", "/mes/equipment/{eq_id}/alarms"],
            card="B9",
        ),
        "alarm_clear": Adapter(
            "报警清除",
            ["/mes/eqp/alarms/{alarm_id}/clear", "/mes/alarms/{alarm_id}/clear"],
            card="B9",
        ),
        # D55 OQ-5：按 ALID 清除（可能没有 active 报警 -> 200 cleared=false）
        "alarm_clear_alid": Adapter(
            "按 ALID 清除报警",
            ["/mes/eqp/{eq_id}/alarms/clear", "/mes/equipment/{eq_id}/alarms/clear"],
            card="B9",
        ),
        # D55 OQ-3：查报警记录及关联在制批（mes_alarm_lot）
        "alarm_get": Adapter(
            "报警记录查询",
            ["/mes/eqp/alarms/{alarm_id}", "/mes/alarms/{alarm_id}"],
            card="B9",
        ),
        # D54：EAP 写入入口，仅 --mode b11 使用
        "eap_events": Adapter("EAP 事件入口", ["/mes/eap/events"], card="B11"),
        "tool_usage": Adapter(
            "耗材计数",
            ["/mes/eqp/tools/{tool_id}/usage", "/mes/tools/{tool_id}/usage"],
            card="B10",
        ),
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
    if kind == "alarm_clear" and args and "alid" in args and "alarm" not in args:
        return ["alarm_clear_alid"]
    return STEP_ADAPTERS[kind]


def fill(template: str, **kw: str) -> str:
    out = template
    for k, v in kw.items():
        out = out.replace("{" + k + "}", str(v))
    if "{" in out:
        raise ValueError(f"路径参数没填全：{out}")
    return out
