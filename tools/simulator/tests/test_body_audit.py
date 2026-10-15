"""D65 补充 4 审计：模拟器发出的每个请求体只含后端 56474fe 请求模型声明的字段（未知字段一律 422）。
E10In / StageIn 也已 forbid；/mes/eap/events 信封例外（D54 顶层并进 payload）。
字段表照抄 eap/be-517 的 pydantic 模型 / 实体规格；故意的反例步骤（seed_alarm_code extra、expect_body_422）除外。"""

import glob
import re

import pytest
from fake import FakeClient

from sim.runner import Runner
from sim.scenario import load

ALLOWED = [  # (方法, 路径正则, 字段集合)
    ("POST", r"/mes/eqp/[^/]+/e10$", {"to_state_id", "reason_id", "comment"}),  # E10In
    (
        "POST",
        r"/mes/exec/lots/[^/]+/(move_in|track_in|track_out)$",
        {
            "equipment_id",
            "recipe_id",
            "eqp_recipe",
            "reticle_id",
            "carrier_id",
            "tool_ids",
            "chamber_ids",
            "material_lot_ids",
            "dc",
            "scrap",
            "rework_units",
            "branch",
            "rework",
            "override",
            "override_reason",
        },
    ),  # StageIn
    (
        "POST",
        r"/mes/eqp/[^/]+/mount$",
        {"port_code", "material_lot_id", "material_lot_code", "mounted_at", "external_event_id", "comment"},
    ),  # MountIn
    ("POST", r"/mes/eqp/mount/[^/]+/unmount$", {"unmounted_at"}),  # UnmountIn
    (
        "POST",
        r"/mes/eqp/alarms/clear$",
        {"equipment_id", "alid", "cleared_at", "occurred_at", "comment", "external_event_id"},
    ),  # AlarmClearByAlidIn
    ("POST", r"/mes/eqp/alarms/[^/]+/clear$", {"cleared_at", "occurred_at", "comment", "external_event_id"}),
    (
        "POST",
        r"/mes/eqp/[^/]+/alarms$",
        {"alid", "alarm_text", "alcd_raw", "set_at", "occurred_at", "lot_ids", "raw", "comment", "external_event_id"},
    ),  # AlarmSetIn
    (
        "POST",
        r"/mes/eqp/tools/[^/]+/usage$",
        {"delta", "equipment_id", "lot_id", "occurred_at", "reason_id", "comment", "external_event_id"},
    ),  # UsageIn
    ("POST", r"/mes/eqp/tools/[^/]+/mount$", {"equipment_id", "sub_unit_id", "port_code", "mounted_at", "comment"}),
    ("POST", r"/mes/eqp/tools/[^/]+/unmount$", {"reason", "unmounted_at", "comment"}),
    ("POST", r"/mes/eqp/tools/[^/]+/replace$", {"new_tool_id", "reason", "comment"}),
    ("POST", r"/mes/eqp/tools/[^/]+/reset$", {"reason_id", "comment"}),
    ("POST", r"/mes/eap/events$", {"source", "external_event_id", "event_type", "equipment_id", "payload"}),
    (
        "(POST|PATCH)",
        r"/mes/alarm_code(/[^/]+)?$",
        {
            "equipment_type_id",
            "equipment_id",
            "alid",
            "alcd_category",
            "severity",
            "text_en",
            "text_zh",
            "text_ja",
            "category",
            "action",
            "target_state",
        },
    ),  # alarm/specs.py（通用 CRUD）
    ("PATCH", r"/mes/tool/[^/]+$", {"tool_status", "expiry_date"}),  # 场景只改这两个（tool 规格里都有）
]
PAYLOADS = {  # execution/eap.py，_P extra=forbid
    "state": {"to_state_id", "reason_id", "event_at", "comment"},
    "alarm_set": {"alid", "alarm_text", "alcd_raw", "set_at", "lot_ids", "raw", "comment"},
    "alarm_clear": {"alid", "cleared_at", "comment"},
    "tool_usage": {"tool_id", "delta", "lot_id", "occurred_at", "reason_id", "comment"},
}
ENVELOPE = {"source", "external_event_id", "event_type", "equipment_id", "payload"}
NEGATIVE = {"target_e10_state_id", "migration_note", "bogus"}  # 场景里故意的未知 / 只读字段反例


def allowed(method, path):
    for m, p, f in ALLOWED:
        if re.fullmatch(m, method) and re.search(p, path):
            return f
    return None


@pytest.mark.parametrize("mode", ["manual", "b11"])
@pytest.mark.parametrize("f", sorted(glob.glob("scenarios/*.yaml")))
def test_bodies_have_no_extra_fields(f, mode):
    c = FakeClient(qual="wait_qual" if "wait-qual" in f else "ready")
    Runner(c, mode=mode, svc=c if mode == "b11" else None).run(load(f))
    for method, path, body, _h, _q in c.calls:
        if method not in ("POST", "PATCH") or not isinstance(body, dict) or path.startswith("/login"):
            continue
        ok = allowed(method, path)
        if ok is None and body == {}:
            continue  # D65 服务账号写权限探测（空体，期望 403）
        assert ok is not None, f"{method} {path} 没有登记请求模型"
        extra = set(body) - ok - NEGATIVE
        if path.endswith("/mes/eap/events"):
            extra = set()  # 信封例外（D54），见下
        assert not extra, f"{method} {path} 多余字段 {extra}"
        if path.endswith("/mes/eap/events"):  # D54：顶层多余字段并进 payload，按合并后的 payload 审计
            merged = {**{k: v for k, v in body.items() if k not in ENVELOPE}, **body["payload"]}
            pe = set(merged) - PAYLOADS[body["event_type"]] - NEGATIVE
            assert not pe, f"B11 {body['event_type']} payload 多余字段 {pe}"
