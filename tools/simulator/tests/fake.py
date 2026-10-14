"""内存假后端：只实现模拟器用到的接口形态。"""

from datetime import datetime, timedelta, timezone

from sim.client import Client, Resp


def _plus5min() -> str:
    t = datetime.now(timezone.utc) + timedelta(minutes=5)
    return t.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


BASE_PATHS = {
    "/mes/eqp/{eq_id}/e10",
    "/mes/exec/lots/{lot_id}/{stage}",
    "/mes/eqp/{eq_id}/mount",
    "/mes/eqp/mount/{mount_id}/unmount",
    "/mes/exec/holds",
    "/mes/{entity}",
    "/mes/{entity}/{rid}",
}
# 与后端 B9 0a74f8a / B10 d27b700 的路由一致
B9 = {
    "/mes/eqp/{eq_id}/alarms",
    "/mes/eqp/alarms/{alarm_id}/clear",
    "/mes/eqp/alarms",
    "/mes/eqp/alarms/{alarm_id}",
}
B10 = {
    "/mes/eqp/tools/{tool_id}/usage",
    "/mes/eqp/tools/{tool_id}/reset",
    "/mes/eqp/tools/{tool_id}/mount",
    "/mes/eqp/tools/{tool_id}/unmount",
    "/mes/eqp/tools/{tool_id}/replace",
    "/mes/eqp/tools/{tool_id}/mounts",
}
B11 = {"/mes/eap/events", "/mes/eqp/alarms/clear"}
REUSED = {"detail": {"code": "idempotency_key_reused", "message": "Idempotency-Key was already used"}}
REGISTERED_ALIDS = {"1001"}
# E10 迁移表（假后端）：UDT 只能回 SBY
TRANSITIONS = {"SBY": {"PRD", "UDT"}, "PRD": {"SBY", "UDT"}, "UDT": {"SBY"}}
STATE_IDS = {"PRD": "s-prd", "SBY": "s-sby", "UDT": "s-udt"}

IDS = {
    ("equipment", "EQ1"): "e-1",
    ("equipment", "EQ2"): "e-2",
    ("e10_state", "PRD"): "s-prd",
    ("e10_state", "SBY"): "s-sby",
    ("e10_state", "UDT"): "s-udt",
    ("lot", "L1"): "l-1",
    ("tool", "T1"): "t-1",
    # 随包场景用到的编码
    ("equipment", "EAP-DA01"): "e-da01",
    ("lot", "FX0001"): "l-fx1",
    ("lot", "FX0002"): "l-fx2",
    ("lot", "FX0003"): "l-fx3",
    ("tool", "T-SIM-01"): "t-sim",
    ("tool", "T2"): "t-2",
    ("reason_code", "REWORK"): "r-rw",
}


EAP_READ = {"equipment", "alarm_code", "e10_state"}  # D65 mes.eap:read_master


class SvcView(Client):
    """同一个假后端的另一个账号视图：只有 eap_service 角色（D65）。"""

    def __init__(self, fake):
        super().__init__("http://127.0.0.1:9", tenant="t", token="svc-token")
        self.fake = fake

    def openapi_paths(self):
        return self.fake.paths

    def request(self, method, path, json_body=None, params=None, headers=None, form=None):
        f = self.fake
        parts = path.split("/")
        ok = (
            (method == "POST" and path == "/mes/eap/events")
            or (method == "GET" and path == "/mes/_meta")
            or (method == "GET" and len(parts) in (3, 4) and parts[2] in EAP_READ and parts[-1] != "export")
        )
        if not ok:
            f.calls.append((method, path, json_body, headers, params, "svc"))
            return Resp(403, {"detail": "Not enough permissions"})
        saved, f.service = f.service, True
        try:
            return f.request(method, path, json_body, params, headers, form)
        finally:
            f.service = saved


def _with_code(r):
    """模拟后端 1a7c0fb 的全局 422 处理：列表明细补 code（没有就用 type）。"""
    if r.status == 422 and isinstance(r.body, dict) and isinstance(r.body.get("detail"), list):
        r.body["detail"] = [dict(x, code=x.get("code") or x.get("type") or "value_error") for x in r.body["detail"]]
    return r


class FakeClient(Client):
    def __init__(self, paths=None, qual="ready"):
        super().__init__("http://127.0.0.1:9", tenant="t", token="secret-token")
        self.paths = set(BASE_PATHS if paths is None else paths)
        self.calls = []
        self.qual = qual
        self.mounts = {}
        self.holds = 0
        self.alarms = {}
        self.alarm_rows = {}
        self.e10 = "SBY"
        self.e10_forbid_extra = True  # 56474fe：E10In / StageIn 未知字段 422；False 模拟 1a7c0fb
        self.stage_writes = 0
        self.usage = 0.0
        self.max_usage = 1000.0
        self.warn_ratio = 0.9
        self.usage_events = {}  # external_event_id -> 履历行
        self.usage_log = []  # newest first
        self.tool_mounts = {}  # tool_id -> 是否在机
        self.mount_log = []
        self.idem = {}  # (接口, key) -> (请求哈希, Resp)   D57
        self.events = {}  # (source, ext) -> (哈希, 台账行, result)   B11
        self.e10_writes = 0
        self.service = True  # 当前账号是否有 eap_service
        # D59 报警码：alid -> {action: none|set_state, target_state}；默认 1001 不联动（兼容旧用例）
        self.alarm_codes = {
            a: {"id": f"ac-{a}", "alid": a, "action": "none", "target_state": None} for a in REGISTERED_ALIDS
        }
        self.e10_hist = []  # 新的在前：{trigger, source, to_state_id}
        self.tool_status = "available"
        self.expiry = None  # ISO 日期
        self._src = "manual"

    def openapi_paths(self):
        return self.paths

    def request(self, method, path, json_body=None, params=None, headers=None, form=None):
        return _with_code(self._request(method, path, json_body, params, headers, form))

    def _request(self, method, path, json_body=None, params=None, headers=None, form=None):
        self.calls.append((method, path, json_body, headers, params))
        key = (headers or {}).get("Idempotency-Key")
        if method == "POST" and key and (path.endswith("/e10") or "/mes/exec/lots/" in path):
            ep = "e10" if path.endswith("/e10") else "stage"
            h = repr((path, sorted((json_body or {}).items())))
            if (ep, key) in self.idem:
                old_h, old = self.idem[(ep, key)]
                return old if old_h == h else Resp(422, REUSED)
            r = self._dispatch(method, path, json_body, params or {})
            if r.status < 400:
                self.idem[(ep, key)] = (h, r)
            return r
        return self._dispatch(method, path, json_body, params or {})

    def _b11(self, body):
        if not self.service:
            return Resp(403, {"detail": "Not enough permissions"})
        allowed = {
            "state": {"to_state_id", "reason_id", "event_at", "comment"},
            "alarm_set": {"alid", "set_at", "lot_ids", "alarm_text", "alcd_raw", "raw", "comment"},
            "alarm_clear": {"alid", "cleared_at", "comment"},
            "tool_usage": {"tool_id", "delta", "lot_id", "occurred_at", "reason_id", "comment"},
        }
        env = {"source", "external_event_id", "event_type", "equipment_id", "payload"}
        flat = {k: v for k, v in body.items() if k not in env}  # D54：信封顶层多余字段并进 payload
        both = sorted(set(flat) & set(body.get("payload") or {}))
        if both:
            return Resp(422, {"detail": [{"loc": ["body", k], "type": "duplicate_field"} for k in both]})
        typ, pl, eq = body["event_type"], {**flat, **(body.get("payload") or {})}, body["equipment_id"]
        k = (body["source"], body["external_event_id"])
        h = repr((typ, eq, sorted(pl.items())))
        if k in self.events:
            old_h, row, res = self.events[k]
            return Resp(422, REUSED) if old_h != h else Resp(200, {"data": row, "duplicate": True, "result": res})
        extra = set(pl) - allowed[typ]
        if extra:
            return Resp(422, {"detail": [{"loc": ["body", "payload", sorted(extra)[0]], "type": "extra_forbidden"}]})
        pl = dict(pl, external_event_id=body["external_event_id"])
        self._src = body["source"]
        try:
            return self._b11_inner(typ, pl, eq, k, h)
        finally:
            self._src = "manual"

    def _b11_inner(self, typ, pl, eq, k, h):
        if typ == "state":
            pl.pop("external_event_id")
            r = self._dispatch("POST", f"/mes/eqp/{eq}/e10", pl, {})
        elif typ == "alarm_set":
            r = self._dispatch("POST", f"/mes/eqp/{eq}/alarms", pl, {})
        elif typ == "alarm_clear":
            r = self._dispatch("POST", "/mes/eqp/alarms/clear", dict(pl, equipment_id=eq), {})
        else:
            tid = pl.pop("tool_id")
            r = self._dispatch("POST", f"/mes/eqp/tools/{tid}/usage", dict(pl, equipment_id=eq), {})
        if r.status >= 400:
            return r
        row = {"id": f"ev-{len(self.events) + 1}", "source": k[0], "external_event_id": k[1], "event_type": typ}
        self.events[k] = (h, row, r.body)
        return Resp(200, {"data": row, "duplicate": False, "result": r.body})

    def _hist(self, to, trigger):
        self.e10_hist.insert(
            0,
            {
                "id": f"h-{len(self.e10_hist) + 1}",
                "to_state_id": STATE_IDS[to],
                "trigger": trigger,
                "source": self._src,
            },
        )

    def _alarm_state(self, code):
        """D58/D59：报警码 set_state → 切 E10（trigger=equipment）；不允许时 200 + state_changed=false。"""
        if not code or code["action"] != "set_state":
            return {"state_changed": False, "state_skip_reason": None}
        ts = code["target_state"]
        if ts not in STATE_IDS:  # baf7b55：跳过原因改成代码
            return {"state_changed": False, "state_skip_reason": "unknown_state"}
        if ts == self.e10:
            return {"state_changed": False, "state_skip_reason": "already_in_state"}
        if ts not in TRANSITIONS.get(self.e10, set()):
            return {"state_changed": False, "state_skip_reason": "transition_not_allowed"}
        self.e10 = ts
        self._hist(ts, "equipment")
        return {"state_changed": True, "state_skip_reason": None}

    def _crud(self, method, path, body, params):
        parts = path.split("/")  # ['', 'mes', entity, rid?]
        ent = parts[2]
        if ent == "e10_history" and method == "GET":
            rows = self.e10_hist
            if params.get("trigger"):  # f2d890c：枚举 e10_history_trigger
                if params["trigger"] not in ("manual", "equipment", "system"):
                    return Resp(422, {"detail": [{"loc": ["query", "trigger"], "type": "value_error"}]})
                rows = [h for h in rows if h["trigger"] == params["trigger"]]
            return Resp(200, {"data": rows[: int(params.get("page_size", 20))], "count": len(rows)})
        if ent == "alarm_code":
            if method == "GET":
                rows = [dict(c, equipment_id="e-da01") for c in self.alarm_codes.values()]
                if params.get("q") is None:
                    return Resp(200, {"data": rows, "count": len(rows)})
                return Resp(200, {"data": [r for r in rows if r["alid"] == params.get("q")]})
            if "migration_note" in body:  # OQ-20 只读
                d = [{"loc": ["body", "migration_note"], "type": "read_only_field", "code": "read_only_field"}]
                return Resp(422, {"detail": d})
            known = {
                "alid",
                "equipment_id",
                "equipment_type_id",
                "action",
                "target_state",
                "severity",
                "text_zh",
                "text_en",
            }
            if set(body) - known:  # P2-D6 严格载荷
                k = sorted(set(body) - known)[0]  # D65：type/code unknown_field
                d = [
                    {"loc": ["body", k], "msg": f"{k}: unknown field", "type": "unknown_field", "code": "unknown_field"}
                ]
                return Resp(422, {"detail": d})
            act, ts = body.get("action") or "none", (body.get("target_state") or "").strip()
            if act == "set_state" and (not ts or ts not in STATE_IDS):
                return Resp(422, {"detail": [{"loc": ["body", "target_state"], "type": "value_error"}]})
            if act == "none" and ts:
                return Resp(422, {"detail": [{"loc": ["body", "target_state"], "type": "value_error"}]})
            row = {"id": f"ac-{body['alid']}", "alid": body["alid"], "action": act, "target_state": ts or None}
            self.alarm_codes[body["alid"]] = row
            return Resp(200, {"data": row})
        if ent == "tool" and method == "PATCH":
            if "tool_status" in body:
                self.tool_status = body["tool_status"]
            if "expiry_date" in body:
                self.expiry = body["expiry_date"]
            return Resp(200, {"data": {"id": parts[3], "tool_status": self.tool_status, "expiry_date": self.expiry}})
        return None

    def _tool_block(self):
        if self.tool_status not in ("available", "in_use"):
            return f"tool T-SIM-01 is {self.tool_status}"
        if self.usage >= self.max_usage:
            return f"tool T-SIM-01 reached its life ({self.usage:g}/{self.max_usage:g})"
        if self.expiry and self.expiry < datetime.now(timezone.utc).date().isoformat():
            return f"tool T-SIM-01 expired on {self.expiry}"
        return None

    def _dispatch(self, method, path, json_body, params):
        if method == "GET":  # D65：查询参数 422 的 loc 以 query 开头
            if params.get("sort_by") not in (None, "at", "code", "alid", "set_at"):
                return Resp(422, {"detail": [{"loc": ["query", "sort_by"], "msg": "sort_by", "type": "value_error"}]})
            for k, v in params.items():
                if v == "bogus":  # 非法枚举值
                    return Resp(422, {"detail": [{"loc": ["query", k], "msg": k, "type": "value_error"}]})
                if k.startswith("has_") and str(v).lower() not in ("true", "false", "1", "0"):
                    return Resp(422, {"detail": [{"loc": ["query", k], "msg": k, "type": "value_error"}]})
        if method == "GET" and "/distinct/" in path:
            f = path.split("/")[-1]
            if f not in ("code", "name"):
                d = [{"loc": ["path", "field"], "msg": f"{f} is not a text filter", "type": "not_text_filter"}]
                return Resp(422, {"detail": d})
            return Resp(200, {"data": []})
        if method == "GET" and path == "/mes/eqp/mount/at":
            if not str(params.get("at", "")).endswith(("Z", "+00:00", "+08:00")):
                d = [{"loc": ["query", "at"], "msg": "at: timezone required", "type": "timezone_required"}]
                return Resp(422, {"detail": d})
            return Resp(200, {"data": []})
        if method == "GET" and path == "/mes/_meta":
            return Resp(200, {"data": {}})
        if method == "GET" and path == "/mes/eqp/alarms" and params.get("status") not in (None, "active", "cleared"):
            d = [{"type": "literal_error", "loc": ["query", "status"], "msg": "Input should be 'active' or 'cleared'"}]
            return Resp(422, {"detail": d})
        if method == "GET" and path == "/mes/eqp/alarms":  # 报警履历列表，新的在前，顶层带联动结果
            rows = [
                {k: v for k, v in r.items() if not k.startswith("_")} for r in reversed(list(self.alarm_rows.values()))
            ]
            for r in rows:
                r.setdefault("state_changed", False)
                r.setdefault("state_skip_reason", None)
            return Resp(200, {"data": rows, "count": len(rows)})
        if method == "GET" and path.count("/") == 2 and not params.get("code"):
            ent = path.split("/")[2]
            if ent in EAP_READ and ent != "alarm_code":
                rows = [{"id": i, "code": c} for (e, c), i in IDS.items() if e == ent]
                return Resp(200, {"data": rows, "count": len(rows)})
        if method == "GET" and path.count("/") == 3 and path.split("/")[2] in ("e10_state", "alarm_code"):
            return Resp(200, {"data": {"id": path.split("/")[3]}})
        if (
            path.split("/")[2:3]
            and path.split("/")[2] in ("alarm_code", "e10_history", "tool")
            and path.count("/") <= 3
        ):
            r = self._crud(method, path, json_body or {}, params)
            if r is not None:
                return r
        if method == "GET" and path.count("/") == 2:  # /mes/{entity}
            ent = path.split("/")[2]
            rid = IDS.get((ent, params.get("code")))
            return Resp(200, {"data": [{"id": rid, "code": params["code"]}] if rid else []})
        if method == "GET" and path.startswith("/mes/equipment/"):
            return Resp(
                200, {"data": {"id": path.split("/")[-1], "qual_state": self.qual, "equipment_type_id": "et-1"}}
            )
        if method == "GET" and path.startswith("/mes/lot/"):
            return Resp(200, {"data": {"lot_status": "waiting", "stage_writes": self.stage_writes}})
        if path == "/mes/eqp/board":
            return Resp(200, {"data": [{"code": c, "state": {"code": self.e10}} for c in ("EQ1", "EAP-DA01")]})
        if path == "/mes/eap/events":
            return self._b11(json_body)
        if path == "/mes/eqp/alarms/clear":
            if set(json_body) - {"equipment_id", "alid", "cleared_at", "comment", "external_event_id"}:
                return Resp(422, {"detail": [{"loc": ["body", "source"], "type": "extra_forbidden"}]})
            act = [
                r for r in self.alarm_rows.values() if r["alid"] == json_body["alid"] and r["alarm_status"] == "active"
            ]
            if not act:
                return Resp(200, {"data": None, "duplicate": False, "cleared": False})
            act[0].update(alarm_status="cleared", clear_event_id=json_body.get("external_event_id"))
            return Resp(200, {"data": act[0], "duplicate": False, "cleared": True})
        if method == "GET" and path.startswith("/mes/eqp/alarms/"):
            row = self.alarm_rows.get(path.split("/")[-1])
            return Resp(200, {"data": row}) if row else Resp(404, {"detail": "Not Found"})
        if path.startswith("/mes/eqp/tools/"):
            return self._tools(method, path, json_body or {})
        if path == "/mes/exec/holds":
            return Resp(200, {"data": [{"lot_code": params.get("q") or "L1"}] * self.holds})
        if path.endswith("/e10"):
            extra = sorted(set(json_body) - {"to_state_id", "reason_id", "comment"})
            if extra and self.e10_forbid_extra:
                d = [{"loc": ["body", f], "msg": f"{f}: unknown field", "type": "unknown_field"} for f in extra]
                return Resp(422, {"detail": d})
            to = {"s-prd": "PRD", "s-sby": "SBY"}.get(json_body.get("to_state_id"), "UDT")
            if to not in TRANSITIONS[self.e10]:  # 迁移表（含不允许原地迁移）
                return Resp(422, {"detail": [{"loc": ["body", "to_state_id"], "type": "value_error"}]})
            self.e10_writes += 1
            frm, self.e10 = self.e10, to
            self._hist(to, "manual" if self._src == "manual" else "equipment")
            return Resp(200, {"data": {"id": f"log-{self.e10_writes}"}, "from": frm, "to": to})
        if "/mes/exec/lots/" in path and self.e10_forbid_extra:
            stage_ok = {
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
            }
            extra = sorted(set(json_body) - stage_ok)
            if extra:
                d = [{"loc": ["body", f], "msg": f"{f}: unknown field", "type": "unknown_field"} for f in extra]
                return Resp(422, {"detail": d})
        if "/mes/exec/lots/" in path:
            self.stage_writes += 1
        if path.endswith("/move_in") or path.endswith("/track_in"):
            # B10：tool_life 只在 track_in 判断，用量 >= 上限硬拦（overridable=false）；预警区间不拦
            blk = self._tool_block() if path.endswith("/track_in") and json_body.get("tool_ids") else None
            if blk:  # 517b0a0 P2-D3：内置硬拦截 + 绑定规则，两条都 block、同一 message
                # f2d890c：规则项也 overridable=false；c6b5907：顶层 overridable=false
                res = [{"check_type": "tool_life", "overridable": False, "result": "block", "message": blk}] * 2
                return Resp(409, {"detail": {"code": "check_blocked", "results": res, "overridable": False}})
            if path.endswith("/track_in") and self.e10 not in ("SBY", "PRD"):  # e10_available
                res = [{"check_type": "e10_available", "result": "fail"}]
                return Resp(409, {"detail": {"code": "check_blocked", "results": res}})
            if self.qual == "wait_qual":
                res = [{"check_type": "eqp_wait_qual", "overridable": False, "result": "block"}]
                return Resp(409, {"detail": {"code": "check_blocked", "results": res}})
            return Resp(200, {"data": {"id": "l-1"}})
        if path.endswith("/mount"):
            ext = json_body["external_event_id"]
            dup = ext in self.mounts
            self.mounts.setdefault(ext, f"m-{len(self.mounts) + 1}")
            return Resp(200, {"data": {"id": self.mounts[ext]}, "duplicate": dup})
        if path.endswith("/alarms"):
            if json_body["set_at"] > _plus5min():
                d = [{"loc": ["body", "set_at"], "type": "time_in_future", "code": "time_in_future"}]
                return Resp(422, {"detail": d})
            ext = json_body["external_event_id"]
            alid = json_body["alid"]
            if ext in self.alarms:  # D57：同事件号内容不同 → 422
                old = self.alarm_rows[self.alarms[ext]]
                if (
                    old["alid"] != alid
                    or old["_set_at"] != json_body["set_at"]
                    or not {x["lot_id"] for x in old["lots"]} >= set(json_body.get("lot_ids", []))
                ):
                    return Resp(422, REUSED)
            act = [r for r in self.alarm_rows.values() if r["alid"] == alid and r["alarm_status"] == "active"]
            if ext in self.alarms or act:
                aid = self.alarms.get(ext) or act[0]["id"]
                return Resp(
                    200,
                    {
                        "data": self.alarm_rows[aid],
                        "duplicate": True,
                        # P2-D8：重复上报返回原记录的联动结果
                        "state_changed": self.alarm_rows[aid].get("state_changed", False),
                        "state_skip_reason": self.alarm_rows[aid].get("state_skip_reason"),
                    },
                )
            aid = self.alarms[ext] = f"a-{len(self.alarms) + 1}"
            code = self.alarm_codes.get(alid)
            unreg = code is None
            self.alarm_rows[aid] = {
                "id": aid,
                "alid": alid,
                "alarm_status": "active",
                "unregistered": unreg,
                "clear_event_id": None,
                "source": self._src,
                "action": code and code["action"],
                "_set_at": json_body["set_at"],
                "lots": [{"lot_id": x} for x in json_body.get("lot_ids", [])],
            }
            # D58：报警只记录、关联批次，不 Hold；只有报警码 set_state 才切 E10
            st = self._alarm_state(code)
            self.alarm_rows[aid].update(e10_change=st, **st)  # baf7b55：履历也带 state_changed / state_skip_reason
            return Resp(200, {"data": self.alarm_rows[aid], "duplicate": False, **st})
        if path.endswith("/clear"):
            row = self.alarm_rows.get(path.split("/")[-2])
            if not row:
                return Resp(404, {"detail": "alarm not found"})
            ext = json_body.get("external_event_id")
            if row["alarm_status"] == "cleared":
                dup = bool(ext) and row["clear_event_id"] == ext
                return Resp(200, {"data": row, "duplicate": dup, "cleared": False})
            row.update(alarm_status="cleared", clear_event_id=ext)
            return Resp(200, {"data": row, "duplicate": False, "cleared": True})
        if path.endswith("/unmount"):
            return Resp(200, {"data": {"id": path.split("/")[-2]}})
        return Resp(404, {"detail": "Not Found"})

    def _tool_brief(self):
        st = "pending_maintenance" if self.usage >= self.max_usage else "available"
        life = (
            "reached"
            if self.usage >= self.max_usage
            else ("warning" if self.usage >= self.max_usage * self.warn_ratio else "ok")
        )
        n = lambda v: f"{v:g}"  # noqa: E731  十进制字符串（D50）
        return {
            "usage_count": n(self.usage),
            "max_usage": n(self.max_usage),
            "life_state": life,
            "tool_status": st,
            "warn_ratio": n(self.warn_ratio),
            "effective_max_usage": n(self.max_usage),  # 23c502d
            "effective_warn_ratio": n(self.warn_ratio),
        }

    def _tools(self, method, path, body):
        parts = path.split("/")  # ['', 'mes', 'eqp', 'tools', id, action]
        tid, act = parts[4], parts[5]
        extra = set(body) - {
            "usage": {"delta", "equipment_id", "lot_id", "occurred_at", "reason_id", "comment", "external_event_id"},
            "reset": {"reason_id", "comment"},
            "mount": {"equipment_id", "sub_unit_id", "port_code", "mounted_at", "comment"},
            "unmount": {"reason", "unmounted_at", "comment"},
            "replace": {"new_tool_id", "reason", "comment"},
        }.get(act, set())
        if method == "POST" and extra:  # extra=forbid
            return Resp(422, {"detail": [{"loc": ["body", sorted(extra)[0]], "type": "extra_forbidden"}]})
        if method == "GET":
            rows = self.usage_log if act == "usage" else [m for m in self.mount_log if m["tool_id"] == tid]
            return Resp(200, {"data": rows, "count": len(rows)})
        if act == "usage":
            ext = body.get("external_event_id")
            if ext and ext in self.usage_events:
                if self.usage_events[ext]["delta"] != body["delta"]:  # D57：同事件号内容不同
                    return Resp(422, REUSED)
                return Resp(
                    200,
                    {
                        "data": self.usage_events[ext],
                        "tool": self._tool_brief(),
                        "duplicate": True,
                        "life_reached": False,
                    },
                )
            d = float(body["delta"])
            if d < 0 and not body.get("reason_id"):
                return Resp(422, {"detail": [{"loc": ["body", "reason_id"], "code": "reason_required"}]})
            before = self.usage
            self.usage += d
            row = {
                "id": f"u-{len(self.usage_log) + 1}",
                "kind": "report" if d > 0 else "adjust",
                "delta": body["delta"],
                "count_after": f"{self.usage:g}",
            }
            self.usage_log.insert(0, row)
            if ext:
                self.usage_events[ext] = row
            reached = before < self.max_usage <= self.usage
            return Resp(200, {"data": row, "tool": self._tool_brief(), "duplicate": False, "life_reached": reached})
        if act == "reset":
            n = len(self.usage_log) + 1
            row = {"id": f"u-{n}", "kind": "reset", "delta": f"{-self.usage:g}", "count_after": "0"}
            self.usage = 0.0
            self.usage_log.insert(0, row)
            return Resp(200, {"data": row, "tool": self._tool_brief()})
        if act == "mount":
            if self.tool_mounts.get(tid):
                return Resp(409, {"detail": {"code": "tool_already_mounted"}})
            self.tool_mounts[tid] = True
            row = {
                "id": f"tm-{len(self.mount_log) + 1}",
                "tool_id": tid,
                "port_code": body.get("port_code"),
                "unmounted_at": None,
                "unmount_reason": None,
            }
            self.mount_log.insert(0, row)
            return Resp(200, {"data": row, "tool": {"equipment_id": body["equipment_id"]}})
        if act in ("unmount", "replace"):
            if not self.tool_mounts.get(tid):
                return Resp(409, {"detail": {"code": "tool_not_mounted"}})
            self.tool_mounts[tid] = False
            cur = next(m for m in self.mount_log if m["tool_id"] == tid and m["unmounted_at"] is None)
            cur.update(unmounted_at="2026-10-14T00:00:00Z", unmount_reason=body["reason"])
            if act == "unmount":
                return Resp(200, {"data": cur})
            new = body["new_tool_id"]
            self.tool_mounts[new] = True
            row = {
                "id": f"tm-{len(self.mount_log) + 1}",
                "tool_id": new,
                "port_code": cur["port_code"],
                "unmounted_at": None,
                "unmount_reason": None,
            }
            self.mount_log.insert(0, row)
            cur["replaced_by_tool_id"] = new
            return Resp(200, {"unmounted": cur, "mounted": row, "new_tool": {"id": new}})
        return Resp(404, {"detail": "Not Found"})
