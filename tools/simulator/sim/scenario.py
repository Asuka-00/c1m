"""YAML 场景解析与校验。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from sim.adapters import STEP_ADAPTERS, step_adapters

EQ_STEPS = {
    "state",
    "track_in",
    "move_in",
    "track_out",
    "mount",
    "alarm_set",
    "alarm_clear",
    "tool_usage",
    "tool_mount",
    "expect_e10",
    "seed_alarm_code",
    "expect_e10_history",
}


class ScenarioError(ValueError):
    pass


@dataclass
class Step:
    kind: str
    args: dict[str, Any]
    index: int

    @property
    def eq(self) -> str | None:
        return self.args.get("eq")


@dataclass
class Scenario:
    run_id: str
    name: str
    target: str | None
    steps: list[Step]
    equipment: list[dict] = field(default_factory=list)
    description: str = ""
    path: str | None = None

    def required_adapters(self, mode: str = "manual") -> list[str]:
        seen: list[str] = []
        for s in self.steps:
            for a in step_adapters(s.kind, s.args, mode):
                if a not in seen:
                    seen.append(a)
        return seen


def parse(data: dict, path: str | None = None) -> Scenario:
    if not isinstance(data, dict):
        raise ScenarioError("场景必须是 YAML 映射")
    run_id = str(data.get("run_id") or "").strip()
    if not run_id or ":" in run_id:
        raise ScenarioError("run_id 必填且不能含冒号")
    raw = data.get("steps")
    if not isinstance(raw, list) or not raw:
        raise ScenarioError("steps 必须是非空列表")
    steps: list[Step] = []
    for i, item in enumerate(raw, 1):
        if not isinstance(item, dict):
            raise ScenarioError(f"第 {i} 步必须是映射")
        item = dict(item)
        item.pop("at", None)  # 预留：时间偏移，模式 A 顺序执行
        item.pop("name", None)
        kinds = [k for k in item if k in STEP_ADAPTERS]
        if len(kinds) != 1:
            raise ScenarioError(f"第 {i} 步要恰好一个动作，可选：{sorted(STEP_ADAPTERS)}")
        k = kinds[0]
        args = item[k] or {}
        if not isinstance(args, dict):
            raise ScenarioError(f"第 {i} 步 {k} 的参数必须是映射")
        if k in EQ_STEPS and not args.get("eq"):
            raise ScenarioError(f"第 {i} 步 {k} 缺少 eq")
        if k == "alarm_clear" and bool(args.get("alarm")) == (args.get("alid") is not None):
            raise ScenarioError(f"第 {i} 步 alarm_clear 要二选一：alarm: $名（按报警 id）或 alid（按设备 + ALID）")
        if k == "reuse" and (not args.get("eq") or not args.get("seq") or not args.get("change")):
            raise ScenarioError(f"第 {i} 步 reuse 需要 eq、seq 和 change")
        if k.startswith("tool_") or k == "expect_tool_log":
            if not args.get("tool"):
                raise ScenarioError(f"第 {i} 步 {k} 缺少 tool")
        if k == "tool_reset" and not args.get("reason"):
            raise ScenarioError(f"第 {i} 步 tool_reset 缺少 reason（reason_code 编码）")
        if k in ("tool_unmount", "tool_replace") and not args.get("reason"):
            raise ScenarioError(f"第 {i} 步 {k} 缺少 reason（life_end/broken/pm/swap/other）")
        if k == "tool_replace" and not args.get("new_tool"):
            raise ScenarioError(f"第 {i} 步 tool_replace 缺少 new_tool")
        if k == "seed_alarm_code":
            if not args.get("alid") or args.get("action") not in ("none", "set_state"):
                raise ScenarioError(f"第 {i} 步 seed_alarm_code 需要 alid，action 只能是 none/set_state（D59）")
        if k == "expect_query_422" and not args.get("path"):
            raise ScenarioError(f"第 {i} 步 expect_query_422 需要 path")
        if k == "expect_alarm_list" and not args.get("eq"):
            raise ScenarioError(f"第 {i} 步 expect_alarm_list 缺少 eq")
        if k == "tool_set" and not isinstance(args.get("fields"), dict):
            raise ScenarioError(f"第 {i} 步 tool_set 需要 fields 映射")
        if k == "expect_alarm" and not args.get("alarm"):
            raise ScenarioError(f"第 {i} 步 expect_alarm 缺少 alarm")
        steps.append(Step(k, args, i))
    return Scenario(
        run_id=run_id,
        name=str(data.get("name") or run_id),
        target=data.get("target"),
        steps=steps,
        equipment=data.get("equipment") or [],
        description=str(data.get("description") or ""),
        path=path,
    )


def load(path: str | Path) -> Scenario:
    p = Path(path)
    with p.open(encoding="utf-8") as f:
        return parse(yaml.safe_load(f), str(p))
