"""P3 执行器单测用的 mock HTTP 服务（真实 socket，127.0.0.1 随机端口）。

只模拟 D78–D82 里模拟器会用到的形状：光罩 14 个写接口（Idempotency-Key 必填、D57 重放、补录时间边界）、
履历、audit_log、``/mes/eap/events`` 光罩上报、打标主记录/打印/检验/作废/config。``enabled`` 控制哪些路由存在，
不存在的返回 FastAPI 风格 404 ``{"detail": "Not Found"}``。
"""

from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

API = "/api/v1"
RETICLE_ACTIONS = [
    "mount",
    "unmount",
    "usage",
    "incident",
    "inspection",
    "hold",
    "release",
    "restore",
    "life-reset",
    "scrap",
    "clean-start",
    "clean-complete",
    "repair-complete",
    "inspect-start",
]
RETICLE_PATHS = {f"/mes/reticle/{{reticle_id}}/{x}" for x in RETICLE_ACTIONS} | {
    "/mes/reticle/{reticle_id}",
    "/mes/reticle/{reticle_id}/history",
    "/mes/audit_log",
    "/mes/eap/events",
}
MARKING_PATHS = {
    "/mes/marking",
    "/mes/marking/config",
    "/mes/marking/{marking_id}",
    "/mes/marking/{marking_id}/prints",
    "/mes/marking/{marking_id}/inspect",
    "/mes/marking/{marking_id}/inspections",
    "/mes/marking/{marking_id}/void",
}
BASE = {"/mes/{entity}", "/mes/{entity}/{rid}", "/mes/exec/lots/{lot_id}/{stage}"}


def z(t: datetime) -> str:
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def parse_t(v):
    return datetime.fromisoformat(v.replace("Z", "+00:00"))


def err(loc, typ, ctx=None):
    e = {"loc": loc, "type": typ, "code": typ, "msg": typ}
    if ctx:
        e["ctx"] = ctx
    return e


class State:
    def __init__(self, enabled: set[str]):
        self.enabled = enabled
        self.lock = threading.Lock()
        self.requests: list[dict] = []
        self.codes = {
            ("equipment", "EAP-LT01"): "eq-lt01",
            ("equipment", "EAP-MK01"): "eq-mk01",
            ("lot", "MK0001"): "lot-mk1",
            ("reason_code", "R-MKREPRINT"): "rs-rep",
        }
        self.reticles: dict[str, dict] = {}
        for code in ("R-SIM-03", "R-SIM-04", "R-SIM-07"):
            rid = str(uuid.uuid4())
            self.codes[("reticle", code)] = rid
            self.reticles[rid] = {
                "id": rid,
                "code": code,
                "status_code": "available",
                "shot_count": "0",
                "mount_count": 0,
            }
        self.history: dict[str, list[dict]] = {}
        self.audit: list[dict] = []
        self.idem: dict[str, tuple[str, int, dict]] = {}
        self.ext: dict[str, tuple[str, dict]] = {}
        self.markings: dict[str, dict] = {}
        self.prints: dict[str, list[dict]] = {}
        self.inspections: dict[str, list[dict]] = {}
        self.cfg = {"trace_code_max_length": 32, "trace_code_pattern": "^[A-Z0-9-]+$"}

    def paths(self):
        return sorted(API + p for p in self.enabled)


def make_handler(st: State):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):  # 安静
            pass

        def _send(self, status, body):
            raw = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            self._do("GET")

        def do_POST(self):
            self._do("POST")

        def do_PATCH(self):
            self._do("PATCH")

        def _do(self, method):
            u = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n)) if n else None
            key = self.headers.get("Idempotency-Key")
            path = u.path.removeprefix(API)
            with st.lock:
                st.requests.append({"method": method, "path": path, "body": body, "idem": key, "query": q})
                status, out = route(st, method, path, q, body, key)
            self._send(status, out)

    return H


def has(st, tpl):
    return tpl in st.enabled


def route(st: State, method, path, q, body, key):
    if path == "/openapi.json":
        return 200, {"paths": {p: {} for p in st.paths()}}
    m = re.fullmatch(r"/mes/reticle/([^/]+)/([a-z-]+)", path)
    if m and method == "POST" and has(st, f"/mes/reticle/{{reticle_id}}/{m.group(2)}"):
        return reticle_write(st, m.group(1), m.group(2), body or {}, key)
    if m and m.group(2) == "history" and has(st, "/mes/reticle/{reticle_id}/history"):
        rid = m.group(1)
        rows = sorted(st.history.get(rid, []), key=lambda x: x["at"], reverse=True)
        return 200, {"data": rows, "count": len(rows)}
    m = re.fullmatch(r"/mes/reticle/([^/]+)", path)
    if m and method == "GET" and m.group(1) in st.reticles:
        return 200, st.reticles[m.group(1)]
    if path == "/mes/audit_log" and has(st, "/mes/audit_log"):
        rows = [a for a in st.audit if a["record_id"] == q.get("record_id")]
        return 200, {"data": rows}
    if path == "/mes/eap/events" and has(st, "/mes/eap/events") and method == "POST":
        return eap_event(st, body)
    if path.startswith("/mes/marking") and any(p.startswith("/mes/marking") for p in st.enabled):
        return marking(st, method, path, q, body or {}, key)
    m = re.fullmatch(r"/mes/([a-z_]+)", path)
    if m and method == "GET":
        code = q.get("code")
        rid = st.codes.get((m.group(1), code))
        return 200, {"data": [{"id": rid, "code": code}] if rid else []}
    return 404, {"detail": "Not Found"}


def idem_wrap(st, scope, key, body, fn, ok=200):
    """D57 + D81：缺 key 422（先于一切）；同 key 同体返回原状态与原记录；换体 422 reused。"""
    if not key:
        return 422, {"detail": [err(["header", "Idempotency-Key"], "missing")]}
    sig = json.dumps(body, sort_keys=True)
    k = f"{scope}:{key}"
    if k in st.idem:
        s0, code0, out0 = st.idem[k]
        if s0 != sig:
            return 422, {"detail": {"code": "idempotency_key_reused", "message": "reused"}}
        return code0, out0
    code, out = fn()
    if code < 500:
        st.idem[k] = (sig, code, out)
    return code, out


def time_errs(body, field, now):
    v = body.get(field)
    if v is None:
        return []
    t = parse_t(v)
    if t.tzinfo is None:
        return [err(["body", field], "timezone_required")]
    if t - now > timedelta(minutes=5):
        return [err(["body", field], "value_error", {"reason": "future_time"})]
    return []


def audit(st, rid, action, payload):
    st.audit.append(
        {
            "record_id": rid,
            "action": action,
            "changes": {"payload": payload},
            "created_at": z(datetime.now(timezone.utc)),
        }
    )


def reticle_write(st, rid, action, body, key):
    now = datetime.now(timezone.utc)
    if not key:
        return 422, {"detail": [err(["header", "Idempotency-Key"], "missing")]}
    field = {"mount": "mounted_at", "unmount": "unmounted_at", "incident": "occurred_at"}.get(action)
    e = time_errs(body, field, now) if field else []
    if action == "usage" and "." in str(body.get("delta", "")) and len(str(body["delta"]).split(".")[1]) > 6:
        e.append(err(["body", "delta"], "value_error", {"max_places": 6}))
    if e:
        return 422, {"detail": e}

    def do():
        r = st.reticles.get(rid)
        if r is None:
            return 404, {"detail": {"code": "not_found", "message": "reticle"}}
        hist = st.history.setdefault(rid, [])
        if action == "mount":
            t = parse_t(body["mounted_at"]) if body.get("mounted_at") else now
            last = max((parse_t(h["at"]) for h in hist), default=None)
            if last and t < last:
                return 409, {"detail": {"code": "time_out_of_order", "message": "x"}}
            if r["status_code"] == "in_use":
                return 409, {"detail": {"code": "already_mounted", "message": "x"}}
            row = {
                "id": str(uuid.uuid4()),
                "type": "mount",
                "at": z(t),
                "mounted_at": z(t),
                "unmounted_at": None,
                "slot_code": body.get("slot_code"),
                "source": "manual",
                "external_event_id": None,
            }
            hist.append(row)
            r.update(status_code="in_use", mount_count=r["mount_count"] + 1)
            audit(st, rid, "reticle.mounted", {"source": "manual", "external_event_id": None})
            return 200, {"data": row}
        if action == "unmount":
            open_ = [h for h in hist if h["type"] == "mount" and h["unmounted_at"] is None]
            if not open_:
                return 409, {"detail": {"code": "invalid_transition", "message": "x"}}
            t = parse_t(body["unmounted_at"]) if body.get("unmounted_at") else now
            if t < parse_t(open_[0]["mounted_at"]):
                return 409, {"detail": {"code": "time_out_of_order", "message": "x"}}
            open_[0]["unmounted_at"] = z(t)
            r["status_code"] = "available"
            audit(st, rid, "reticle.unmounted", {"source": "manual", "external_event_id": None})
            return 200, {"data": open_[0]}
        if action == "usage":
            if r["status_code"] == "scrapped":
                return 409, {"detail": {"code": "invalid_transition", "message": "x"}}
            r["shot_count"] = str(int(r["shot_count"]) + int(body["delta"]))
            return 200, {"data": {"shot_count": r["shot_count"]}}
        if action == "scrap":
            r["status_code"] = "scrapped"
            return 200, {"data": r}
        return 200, {"data": r}

    return idem_wrap(st, f"reticle/{rid}/{action}", key, body, do)


def eap_event(st, body):
    et = body.get("event_type")
    if et not in ("reticle_mount", "reticle_usage", "reticle_unmount"):
        return 422, {"detail": [err(["body", "event_type"], "enum")]}
    ext = body["external_event_id"]
    sig = json.dumps(body, sort_keys=True)
    if ext in st.ext:
        if st.ext[ext][0] != sig:
            return 422, {"detail": {"code": "idempotency_key_reused", "message": "x"}}
        return 200, {"data": {}, "duplicate": True, "result": st.ext[ext][1]}
    rid = body["payload"]["reticle_id"]
    r = st.reticles[rid]
    if et == "reticle_mount":
        row = {
            "type": "mount",
            "at": z(datetime.now(timezone.utc)),
            "unmounted_at": None,
            "source": "simulator",
            "external_event_id": ext,
            "slot_code": body["payload"].get("slot_code"),
        }
        st.history.setdefault(rid, []).append(row)
        r.update(status_code="in_use", mount_count=r["mount_count"] + 1)
        audit(st, rid, "reticle.mounted", {"source": "simulator", "external_event_id": ext})
        res = {"data": row}
    else:
        r["shot_count"] = str(int(r["shot_count"]) + int(body["payload"].get("delta", "0")))
        res = {"data": r}
    st.ext[ext] = (sig, res)
    return 200, {"data": {}, "duplicate": False, "result": res}


def marking(st, method, path, q, body, key):
    if path == "/mes/marking/config":
        if method == "GET":
            return 200, {"data": dict(st.cfg)}
        return 422, {"detail": [err(["body", "trace_code_pattern"], "value_error", {"reason": "pattern_unsupported"})]}
    if path == "/mes/marking" and method == "POST":

        def do():
            mid = str(uuid.uuid4())
            rec = {
                "id": mid,
                "lot_id": body["lot_id"],
                "voided": False,
                "latest_inspection_status": "pending",
                "reprint_count": 0,
                "trace_code": f"TC-{len(st.markings) + 1:04d}",
            }
            st.markings[mid] = rec
            return 200, {"data": rec}

        return idem_wrap(st, "marking", key, body, do)
    m = re.fullmatch(r"/mes/marking/([^/]+)(?:/([a-z]+))?", path)
    if not m or m.group(1) not in st.markings:
        return 404, {"detail": {"code": "not_found", "message": "marking"}}
    mid, sub = m.groups()
    rec = st.markings[mid]
    if sub is None:
        return 200, {"data": rec}
    if sub == "prints" and method == "GET":
        return 200, {"data": st.prints.get(mid, [])}
    if sub == "inspections" and method == "GET":
        return 200, {"data": st.inspections.get(mid, [])}
    if sub == "prints":
        if not key:
            return 422, {"detail": [err(["header", "Idempotency-Key"], "missing")]}
        tc = body.get("trace_code")
        if tc is not None:
            e = []
            if len(tc) > st.cfg["trace_code_max_length"]:
                e.append(
                    err(
                        ["body", "trace_code"],
                        "value_error",
                        {"reason": "max_length", "max_length": st.cfg["trace_code_max_length"]},
                    )
                )
            if not re.fullmatch(st.cfg["trace_code_pattern"], tc):
                e.append(
                    err(
                        ["body", "trace_code"],
                        "value_error",
                        {"reason": "pattern", "pattern": st.cfg["trace_code_pattern"]},
                    )
                )
            if e:
                return 422, {"detail": e}

        def do():
            ps = st.prints.setdefault(mid, [])
            if ps and not (body.get("reason_id") and body.get("comment")):
                return 422, {"detail": [err(["body", "reason_id"], "missing")]}
            p = {
                "id": str(uuid.uuid4()),
                "seq": len(ps) + 1,
                "printed_at": z(datetime.now(timezone.utc)),
                "source": "manual",
            }
            ps.append(p)
            rec.update(reprint_count=len(ps) - 1, latest_inspection_status="pending")
            return 200, {"data": {**rec, "seq": p["seq"], "source": "manual"}}

        return idem_wrap(st, f"prints/{mid}", key, body, do)
    if sub == "inspect":
        if not key:
            return 422, {"detail": [err(["header", "Idempotency-Key"], "missing")]}
        if body.get("read_code") in (None, ""):
            return 422, {"detail": [err(["body", "read_code"], "missing")]}

        def do():
            p = st.prints[mid][-1]
            res = body["result"]
            ov = body["read_code"] != rec["trace_code"]
            if ov:
                res = "fail"
            row = {
                "id": str(uuid.uuid4()),
                "print_id": p["id"],
                "seq": p["seq"],
                "result": res,
                "read_code": body["read_code"],
                "result_overridden": ov,
            }
            st.inspections.setdefault(mid, []).append(row)
            rec["latest_inspection_status"] = res
            return 200, {"data": row}

        return idem_wrap(st, f"insp/{mid}", key, body, do)
    return 404, {"detail": "Not Found"}


class MockServer:
    def __init__(self, enabled: set[str] | None = None):
        self.state = State(BASE | (RETICLE_PATHS | MARKING_PATHS if enabled is None else enabled))
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.state))
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.t = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self):
        self.t.start()
        return self

    def __exit__(self, *a):
        self.httpd.shutdown()
        self.httpd.server_close()
