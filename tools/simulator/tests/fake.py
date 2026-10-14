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
}
B9 = {
    "/mes/eqp/{eq_id}/alarms",
    "/mes/eqp/alarms/{alarm_id}/clear",
    "/mes/eqp/{eq_id}/alarms/clear",
    "/mes/eqp/alarms/{alarm_id}",
}
B10 = {"/mes/eqp/tools/{tool_id}/usage"}
B11 = {"/mes/eap/events"}
REGISTERED_ALIDS = {"1001"}

IDS = {
    ("equipment", "EQ1"): "e-1",
    ("equipment", "EQ2"): "e-2",
    ("e10_state", "PRD"): "s-prd",
    ("e10_state", "SBY"): "s-sby",
    ("lot", "L1"): "l-1",
    ("tool", "T1"): "t-1",
    # 随包场景用到的编码
    ("equipment", "EAP-DA01"): "e-da01",
    ("lot", "FX0001"): "l-fx1",
    ("lot", "FX0002"): "l-fx2",
    ("tool", "T-SIM-01"): "t-sim",
}


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
        self.usage = 0.0
        self.max_usage = 1000.0
        self.warn_ratio = 0.9

    def openapi_paths(self):
        return self.paths

    def request(self, method, path, json_body=None, params=None, headers=None, form=None):
        self.calls.append((method, path, json_body, headers, params))
        params = params or {}
        if method == "GET" and path.count("/") == 2:  # /mes/{entity}
            ent = path.split("/")[2]
            rid = IDS.get((ent, params.get("code")))
            return Resp(200, {"data": [{"id": rid, "code": params["code"]}] if rid else []})
        if method == "GET" and path.startswith("/mes/equipment/"):
            return Resp(200, {"data": {"qual_state": self.qual}})
        if method == "GET" and path.startswith("/mes/lot/"):
            return Resp(200, {"data": {"lot_status": "waiting"}})
        if path == "/mes/eqp/board":
            return Resp(200, {"data": [{"code": c, "state": {"code": self.e10}} for c in ("EQ1", "EAP-DA01")]})
        if path == "/mes/eap/events":
            return Resp(200, {"data": {"id": "ev-" + json_body["external_event_id"]}})
        if method == "GET" and path.startswith("/mes/eqp/alarms/"):
            row = self.alarm_rows.get(path.split("/")[-1])
            return Resp(200, {"data": row}) if row else Resp(404, {"detail": "Not Found"})
        if path.endswith("/alarms/clear"):
            active = [r for r in self.alarm_rows.values() if r["alid"] == json_body["alid"] and r["state"] == "active"]
            for r in active:
                r["state"] = "cleared"
            return Resp(200, {"data": {"cleared": bool(active)}})
        if path.endswith("/usage"):
            self.usage += float(json_body["delta"])
            return Resp(200, {"data": {"usage_count": str(self.usage)}})
        if path == "/mes/exec/holds":
            return Resp(200, {"data": [{"lot_code": params.get("q") or "L1"}] * self.holds})
        if path.endswith("/e10"):
            return Resp(200, {"data": {"id": "log"}})
        if path.endswith("/move_in"):
            if json_body.get("tool_ids") and self.usage >= self.max_usage * self.warn_ratio:
                hard = self.usage >= self.max_usage
                res = [{"check_type": "tool_life", "overridable": not hard, "result": "fail"}]
                return Resp(409, {"detail": {"code": "check_blocked", "results": res}})
            if self.qual == "wait_qual":
                res = [{"check_type": "eqp_wait_qual", "overridable": False, "result": "fail"}]
                return Resp(409, {"detail": {"code": "check_blocked", "results": res}})
            return Resp(200, {"data": {"id": "l-1"}})
        if path.endswith("/mount"):
            ext = json_body["external_event_id"]
            dup = ext in self.mounts
            self.mounts.setdefault(ext, f"m-{len(self.mounts) + 1}")
            return Resp(200, {"data": {"id": self.mounts[ext]}, "duplicate": dup})
        if path.endswith("/alarms"):
            if json_body["occurred_at"] > _plus5min():
                return Resp(422, {"detail": {"code": "time_in_future"}})
            ext = json_body["external_event_id"]
            if ext not in self.alarms:
                aid = self.alarms[ext] = f"a-{len(self.alarms) + 1}"
                unreg = json_body["alid"] not in REGISTERED_ALIDS
                self.alarm_rows[aid] = {
                    "id": aid,
                    "alid": json_body["alid"],
                    "state": "active",
                    "unregistered": unreg,
                    "lots": [{"lot_id": x} for x in json_body.get("lot_ids", [])],
                }
                if not unreg:
                    self.holds += 1
                    self.e10 = "UDT"
            return Resp(200, {"data": {"id": self.alarms[ext]}})
        if path.endswith("/clear"):
            aid = path.split("/")[-2]
            if aid in self.alarm_rows:
                self.alarm_rows[aid]["state"] = "cleared"
            return Resp(200, {"data": {"id": aid, "cleared": True}})
        if path.endswith("/unmount"):
            return Resp(200, {"data": {"id": path.split("/")[-2]}})
        return Resp(404, {"detail": "Not Found"})
