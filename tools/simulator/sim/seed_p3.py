"""P3 场景种子数据（marking-report / reticle-report），只给模拟器场景用。

只走后端接口（通用 CRUD + 工单下达/开批 + 进站），按编码先查后建，可重复跑（幂等）。
只允许对设备集成环境 app_it_eap 操作：目标必须是 127.0.0.1:8013（env.sh 里 8013 对应 app_it_eap），
端口还要在 SIM_ALLOWED_PORTS 里，并且显式设置 ``SIM_SEED_DB=app_it_eap`` 确认。凭据同 ``sim run``（运行时注入）。

建的数据：
- 设备类型 ET-LITHO / ET-MARKER，设备 EAP-LT01、EAP-MK01（初始 E10 取租户 is_initial 状态，一般是 SBY）
- 光罩 R-SIM-03 … R-SIM-12（available）
- 原因码 R-MKREPRINT（marking_reprint）、R-MKVOID（marking_void）、R-scrap（scrap）——后端没有这些 reason_type 时记未建
- 打标批次：工序 OP-MK、路线 RT-MK、产品 P-MK / P-NOMK、批次规则 MK{SEQ}；MK0001–MK0004 属 P-MK、MK0009 属 P-NOMK，
  开批后 move_in + track_in 到 EAP-MK01（场景从出站开始）
打标模板绑定（B1）不在这里做，由场景 ``marking_template_ready`` 负责。
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlparse

from sim.client import Client

SEED_PORT = 8013
SEED_DB = "app_it_eap"
RETICLES = [f"R-SIM-{i:02d}" for i in range(3, 13)]
REASONS = [("R-MKREPRINT", "marking_reprint"), ("R-MKVOID", "marking_void"), ("R-scrap", "scrap")]


class SeedRefused(SystemExit):
    pass


def guard(target: str) -> None:
    if urlparse(target).port != SEED_PORT:
        raise SeedRefused(f"种子脚本只对 {SEED_DB}（127.0.0.1:{SEED_PORT}）操作，拒绝 {target}")
    if os.environ.get("SIM_SEED_DB") != SEED_DB:
        raise SeedRefused(f"请设置 SIM_SEED_DB={SEED_DB} 确认目标库")


class Seeder:
    def __init__(self, c: Client) -> None:
        self.c = c
        self.log: list[str] = []

    def find(self, ent: str, code: str) -> dict | None:
        r = self.c.get(f"/mes/{ent}", code=code, page_size=50)
        rows = r.body.get("data", []) if isinstance(r.body, dict) else []
        hit = [x for x in rows if isinstance(x, dict) and x.get("code") == code]
        return hit[0] if hit else None

    def ensure(self, ent: str, code: str, body: dict[str, Any]) -> dict | None:
        row = self.find(ent, code)
        if row:
            self.log.append(f"有  {ent} {code}")
            return row
        # D87 补充一：光罩主数据通用 CRUD 写入必须带 Idempotency-Key（每个对象唯一）
        hdr = {"Idempotency-Key": f"seed-p3:{ent}:{code}"} if ent == "reticle" else None
        r = self.c.request("POST", f"/mes/{ent}", {"code": code, **body}, headers=hdr)
        if r.status in (200, 201) and isinstance(r.body, dict):
            self.log.append(f"建  {ent} {code}")
            return r.body.get("data", r.body)
        self.log.append(f"未建 {ent} {code}：HTTP {r.status} {str(r.body)[:200]}")
        return None

    def first(self, ent: str, **q: Any) -> dict | None:
        r = self.c.get(f"/mes/{ent}", page_size=1, **q)
        rows = r.body.get("data", []) if isinstance(r.body, dict) else []
        return rows[0] if rows else None

    def post(self, path: str, body: Any = None, idem: str | None = None) -> Any:
        r = self.c.post(path, body or {}, idem=idem)
        if r.status not in (200, 201):
            self.log.append(f"失败 POST {path}：HTTP {r.status} {str(r.body)[:200]}")
            return None
        return r.body.get("data", r.body) if isinstance(r.body, dict) else r.body

    def run(self) -> list[str]:
        wc = self.first("workcenter")
        area = self.first("area")
        eqs = {}
        for code, et in (("EAP-LT01", "ET-LITHO"), ("EAP-MK01", "ET-MARKER")):
            t = self.ensure("equipment_type", et, {"name": et, "category": "process"})
            body = {"name": code, "equipment_type_id": (t or {}).get("id")}
            if wc:
                body["workcenter_id"] = wc["id"]
            eqs[code] = self.ensure("equipment", code, body)
        for code in RETICLES:
            self.ensure("reticle", code, {"name": code, "max_shots": 250})
        for code, rt in REASONS:
            self.ensure("reason_code", code, {"name": code, "reason_type": rt})
        self.lots(eqs.get("EAP-MK01"), area)
        return self.log

    def lots(self, eq: dict | None, area: dict | None) -> None:
        want = ["MK0001", "MK0002", "MK0003", "MK0004", "MK0009"]
        if all(self.find("lot", x) for x in want):
            self.log.append("有  lot MK0001–MK0004、MK0009")
            if eq:
                self.back_to_sby(eq)
            return
        if not (eq and area):
            self.log.append("未建 打标批次：缺 EAP-MK01 或 area")
            return
        op = self.ensure("operation", "OP-MK", {"name": "marking", "area_id": area["id"]})
        if not op:
            return
        self.c.request("POST", "/mes/equipment_capability", {"equipment_id": eq["id"], "operation_id": op["id"]})
        rt = self.find("route", "RT-MK")
        if not rt:
            rt = self.ensure("route", "RT-MK", {"name": "marking route"})
            if not rt:
                return
            self.c.request("POST", "/mes/route_step", {"route_id": rt["id"], "seq": 10, "operation_id": op["id"]})
            self.post(f"/mes/route/{rt['id']}/status", {"status": "active"})
        rule = self.ensure("code_rule", "MK-LOT", {"name": "mk lot", "target": "lot", "pattern": "MK{SEQ}"})
        base_lt = self.first("lot_type")
        lt_body = {"name": "marking lots", "lot_id_rule_id": (rule or {}).get("id")}
        if base_lt:
            for k in ("default_priority_id", "wafer_id_rule_id"):
                if base_lt.get(k):
                    lt_body[k] = base_lt[k]
        lt = self.ensure("lot_type", "LT-MK", lt_body)
        if not lt:
            return
        prods = {}
        tmpl = self.first("product") or {}  # 必填上下文（uom / family / tech_node）照租户已有产品
        ctx = {k: tmpl[k] for k in ("uom_id", "family_id", "tech_node_id") if tmpl.get(k)}
        for code in ("P-MK", "P-NOMK"):
            p = self.find("product", code)
            if not p:
                p = self.ensure("product", code, {"name": code, **ctx})
                if not p:
                    return
                self.c.request("POST", "/mes/product_route", {"product_id": p["id"], "route_id": rt["id"]})
                self.post(f"/mes/product/{p['id']}/status", {"status": "active"})
            prods[code] = p
        # MK{SEQ} 顺序发号：P-MK 开 8 批（MK0001–MK0008），P-NOMK 开 1 批（MK0009）
        for code, n in (("P-MK", 8), ("P-NOMK", 1)):
            wo_body = {"product_id": prods[code]["id"], "lot_type_id": lt["id"], "planned_qty": 100}
            wo = self.post("/mes/work_order", wo_body)
            if not wo:
                return
            self.post(f"/mes/work-order/{wo['id']}/transition", {"action": "release"})
            started = self.post(f"/mes/work-order/{wo['id']}/start", {"lots": [{"qty": 1} for _ in range(n)]}) or []
            for lot in started if isinstance(started, list) else []:
                for stage in ("move_in", "track_in"):
                    key = f"seed:{lot['id']}:{stage}"
                    self.post(f"/mes/exec/lots/{lot['id']}/{stage}", {"equipment_id": eq["id"]}, idem=key)
                self.log.append(f"建  lot {lot.get('code')}（{code}，已进站 EAP-MK01）")
        self.back_to_sby(eq)

    def back_to_sby(self, eq: dict) -> None:
        """进站的自动规则会把设备切到 PRD；场景前提要求 SBY，种子最后切回。"""
        sby = self.find("e10_state", "SBY")
        if sby:
            self.post(
                f"/mes/eqp/{eq['id']}/e10",
                {"to_state_id": sby["id"], "comment": "seed-p3"},
                idem=f"seed:sby:{eq['id']}",
            )
