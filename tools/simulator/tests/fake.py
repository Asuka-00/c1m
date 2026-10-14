"""内存假后端：只实现模拟器用到的接口形态。"""

from sim.client import Client, Resp

BASE_PATHS = {
    "/mes/eqp/{eq_id}/e10",
    "/mes/exec/lots/{lot_id}/{stage}",
    "/mes/eqp/{eq_id}/mount",
    "/mes/eqp/mount/{mount_id}/unmount",
    "/mes/exec/holds",
}
B9 = {"/mes/eqp/{eq_id}/alarms", "/mes/eqp/alarms/{alarm_id}/clear"}
B10 = {"/mes/eqp/tools/{tool_id}/usage"}

IDS = {
    ("equipment", "EQ1"): "e-1",
    ("equipment", "EQ2"): "e-2",
    ("e10_state", "PRD"): "s-prd",
    ("e10_state", "SBY"): "s-sby",
    ("lot", "L1"): "l-1",
    ("tool", "T1"): "t-1",
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
        if path == "/mes/exec/holds":
            return Resp(200, {"data": [{"lot_code": "L1"}] * self.holds})
        if path.endswith("/e10"):
            return Resp(200, {"data": {"id": "log"}})
        if path.endswith("/move_in"):
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
            ext = json_body["external_event_id"]
            if ext not in self.alarms:
                self.alarms[ext] = f"a-{len(self.alarms) + 1}"
                self.holds += 1
            return Resp(200, {"data": {"id": self.alarms[ext]}})
        if path.endswith("/clear") or path.endswith("/unmount"):
            return Resp(200, {"data": {"id": path.split("/")[-2]}})
        return Resp(404, {"detail": "Not Found"})
