"""场景执行器：解析编码 -> 调接口 -> 断言 -> 生成报告。"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from sim.adapters import STEP_ADAPTERS, Adapter, Call, default_adapters, fill
from sim.client import Client, Resp
from sim.ids import SeqCounter, event_id
from sim.safety import redact
from sim.scenario import Scenario, Step

PASSED, FAILED, SKIPPED, ERROR = "passed", "failed", "skipped", "error"


class Skip(Exception):
    pass


class StepFailed(Exception):
    pass


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def check_expect(resp: Resp, expect: dict | None, default_status: int = 200) -> list[str]:
    """返回不满足的断言列表（空表示通过）。"""
    expect = expect or {}
    errs: list[str] = []
    want = expect.get("status", default_status)
    if resp.status != want:
        errs.append(f"HTTP {resp.status} != 期望 {want}（code={resp.code}）")
    if "code" in expect and resp.code != expect["code"]:
        errs.append(f"code {resp.code!r} != 期望 {expect['code']!r}")
    chk = expect.get("check")
    if chk:
        want_type = chk.get("check_type")
        hits = [r for r in resp.check_results if want_type in (r.get("check_type"), r.get("code"), r.get("check"))]
        if not hits:
            got = [r.get("check_type") or r.get("code") for r in resp.check_results]
            errs.append(f"检查项里没有 {want_type!r}（实际 {got}）")
        else:
            for k, v in chk.items():
                if k == "check_type":
                    continue
                if not any(h.get(k) == v for h in hits):
                    errs.append(f"检查项 {want_type} 的 {k} != {v!r}（实际 {[h.get(k) for h in hits]}）")
    return errs


class Runner:
    def __init__(
        self,
        client: Client,
        adapters: dict[str, Adapter] | None = None,
        paths: set[str] | None = None,
        stop_on_fail: bool = True,
    ) -> None:
        self.c = client
        self.adapters = adapters or default_adapters()
        self._paths = paths
        self.stop_on_fail = stop_on_fail
        self._ids: dict[tuple[str, str], str] = {}

    # ---- 能力探测 ----
    @property
    def paths(self) -> set[str]:
        if self._paths is None:
            self._paths = self.c.openapi_paths()
        return self._paths

    def missing(self, sc: Scenario) -> list[str]:
        out = []
        for name in sc.required_adapters():
            ad = self.adapters[name]
            if not ad.resolve(self.paths):
                out.append(ad.skip_reason())
        return out

    # ---- 编码 -> id ----
    def rid(self, entity: str, code: str) -> str:
        key = (entity, code)
        if key not in self._ids:
            r = self.c.get(f"/mes/{entity}", code=code, page_size=50)
            rows = (r.body or {}).get("data", []) if isinstance(r.body, dict) else []
            hit = [x for x in rows if x.get("code") == code]
            if r.status != 200 or not hit:
                raise StepFailed(f"找不到 {entity} 编码 {code}（HTTP {r.status}）")
            self._ids[key] = hit[0]["id"]
        return self._ids[key]

    def row(self, entity: str, code: str) -> dict:
        r = self.c.get(f"/mes/{entity}/{self.rid(entity, code)}")
        b = r.body if isinstance(r.body, dict) else {}
        return b.get("data", b)

    # ---- 执行 ----
    def run(self, sc: Scenario) -> dict[str, Any]:
        rep: dict[str, Any] = {
            "scenario": sc.name,
            "run_id": sc.run_id,
            "file": sc.path,
            "started_at": utcnow(),
            "status": PASSED,
            "reason": None,
            "steps": [],
        }
        miss = self.missing(sc)
        if miss:
            rep.update(status=SKIPPED, reason="；".join(miss))
            return rep
        seq = SeqCounter()
        sent: dict[tuple[str, int], tuple[Call, Resp]] = {}
        saved: dict[str, Any] = {}
        for st in sc.steps:
            entry: dict[str, Any] = {"step": st.index, "kind": st.kind, "eq": st.eq}
            rep["steps"].append(entry)
            t0 = time.monotonic()
            try:
                self._step(sc, st, entry, seq, sent, saved)
                entry["ok"] = True
            except Skip as e:
                entry.update(ok=None, message=str(e))
                rep.update(status=SKIPPED, reason=f"第 {st.index} 步前置条件不满足：{e}")
                break
            except StepFailed as e:
                entry.update(ok=False, message=str(e))
                rep["status"] = FAILED
                rep["reason"] = rep["reason"] or f"第 {st.index} 步：{e}"
                if self.stop_on_fail:
                    break
            finally:
                entry["elapsed_ms"] = int((time.monotonic() - t0) * 1000)
        rep["finished_at"] = utcnow()
        return rep

    def _send(self, entry: dict, call: Call, expect: dict | None) -> Resp:
        r = self.c.request(
            call.method,
            call.path,
            call.body,
            headers={"Idempotency-Key": call.idem} if call.idem else None,
        )
        entry.update(
            method=call.method,
            path=call.path,
            request=redact(call.body),
            status=r.status,
            code=r.code,
            http_ms=r.elapsed_ms,
        )
        errs = check_expect(r, expect)
        if errs:
            raise StepFailed("；".join(errs))
        return r

    def _ad(self, name: str) -> str:
        p = self.adapters[name].path or self.adapters[name].resolve(self.paths)
        assert p, name
        return p

    def _step(self, sc, st: Step, entry, seq: SeqCounter, sent, saved) -> None:
        a, k = st.args, st.kind
        if k == "precondition":
            return self._precondition(a)
        if k == "expect_hold":
            return self._expect_hold(a, entry)
        if k == "replay":
            return self._replay(a, entry, sent)
        if k == "unmount":
            mid = saved.get(str(a.get("mount", "")).lstrip("$"))
            if not mid:
                raise StepFailed(f"unmount 找不到保存的上料记录 {a.get('mount')}")
            call = Call("POST", fill(self._ad("unmount"), mount_id=mid), {})
            self._send(entry, call, a.get("expect"))
            return

        eq = st.eq
        n = seq.next(eq)
        ext = event_id(sc.run_id, eq, n)
        entry.update(seq=n, external_event_id=ext)
        eq_id = self.rid("equipment", eq)
        tag = f"sim_run_id={sc.run_id} ext={ext}"
        if k == "state":
            body = {"to_state_id": self.rid("e10_state", a["to"]), "comment": tag[:300]}
            if a.get("reason"):
                body["reason_id"] = self.rid("e10_reason", a["reason"])
            call = Call("POST", fill(self._ad("e10"), eq_id=eq_id), body, ext)
        elif k in ("track_in", "move_in", "track_out"):
            body = {"equipment_id": eq_id}
            if a.get("tools"):
                body["tool_ids"] = [self.rid("tool", t) for t in a["tools"]]
            if k == "track_out" and a.get("scrap"):
                body["scrap"] = a["scrap"]
            call = Call(
                "POST",
                fill(self._ad("stage"), lot_id=self.rid("lot", a["lot"]), stage=k),
                body,
                ext,
            )
        elif k == "mount":
            body = {
                "port_code": a["port"],
                "material_lot_code": a["material_lot"],
                "external_event_id": ext,
            }
            call = Call("POST", fill(self._ad("mount"), eq_id=eq_id), body, ext)
        elif k == "alarm_set":
            body = {"alid": str(a["alid"]), "external_event_id": ext, "occurred_at": utcnow()}
            if a.get("lots"):
                body["lot_ids"] = [self.rid("lot", x) for x in a["lots"]]
            call = Call("POST", fill(self._ad("alarm_set"), eq_id=eq_id), body, ext)
        elif k == "alarm_clear":
            aid = saved.get(str(a.get("alarm", "")).lstrip("$"))
            if not aid:
                raise StepFailed(f"alarm_clear 找不到保存的报警 {a.get('alarm')}")
            body = {"external_event_id": ext, "occurred_at": utcnow()}
            call = Call("POST", fill(self._ad("alarm_clear"), alarm_id=aid), body, ext)
        elif k == "tool_usage":
            body = {"delta": str(a["delta"]), "equipment_id": eq_id, "external_event_id": ext}
            call = Call("POST", fill(self._ad("tool_usage"), tool_id=self.rid("tool", a["tool"])), body, ext)
        else:  # pragma: no cover - scenario.parse 已拦
            raise StepFailed(f"未知步骤 {k}")
        r = self._send(entry, call, a.get("expect"))
        sent[(eq, n)] = (call, r)
        if a.get("save_as") and isinstance(r.body, dict):
            d = r.body.get("data", r.body)
            saved[a["save_as"]] = d.get("id") if isinstance(d, dict) else None

    def _precondition(self, a: dict) -> None:
        if a.get("eq"):
            row = self.row("equipment", a["eq"])
            if "qual_state" in a and (row.get("qual_state") or "ready") != a["qual_state"]:
                raise Skip(f"{a['eq']} qual_state={row.get('qual_state')}，场景要求 {a['qual_state']}")
            if "e10" in a:
                board = self.c.get("/mes/eqp/board").body or {}
                cur = next((x for x in board.get("data", []) if x.get("code") == a["eq"]), {}).get("state") or {}
                if cur.get("code") != a["e10"]:
                    raise Skip(f"{a['eq']} 当前 E10={cur.get('code')}，场景要求从 {a['e10']} 开始")
        if a.get("lot"):
            row = self.row("lot", a["lot"])
            if "lot_status" in a and row.get("lot_status") != a["lot_status"]:
                raise Skip(f"{a['lot']} lot_status={row.get('lot_status')}，场景要求 {a['lot_status']}")

    def _expect_hold(self, a: dict, entry: dict) -> None:
        r = self.c.get("/mes/exec/holds", q=a["lot"], source=a.get("source"), page_size=100)
        rows = (r.body or {}).get("data", []) if isinstance(r.body, dict) else []
        mine = [x for x in rows if a["lot"] in (x.get("lot_code"), x.get("code"), x.get("lot"))]
        entry.update(status=r.status, holds=len(mine))
        want = a.get("present", True)
        if bool(mine) != want:
            raise StepFailed(f"{a['lot']} active Hold 数={len(mine)}，期望{'有' if want else '无'}")
        if "count" in a and len(mine) != a["count"]:
            raise StepFailed(f"{a['lot']} active Hold 数={len(mine)}，期望 {a['count']}")

    def _replay(self, a: dict, entry: dict, sent) -> None:
        eq = a["eq"]
        lo = int(a.get("from_seq", a.get("seq", 1)))
        hi = int(a.get("to_seq", a.get("seq", lo)))
        entry["replayed"] = []
        for n in range(lo, hi + 1):
            if (eq, n) not in sent:
                raise StepFailed(f"没有 {eq} 序号 {n} 的已发送事件可重放")
            call, first = sent[(eq, n)]
            r = self.c.request(call.method, call.path, call.body, headers={"Idempotency-Key": call.idem})
            item = {"seq": n, "external_event_id": call.idem, "status": r.status, "code": r.code}
            entry["replayed"].append(item)
            mode = a.get("expect", "idempotent")
            if mode == "idempotent":
                if r.status != first.status:
                    raise StepFailed(f"重放 {call.idem} HTTP {r.status} != 首次 {first.status}")
                fd = (first.body or {}).get("data") if isinstance(first.body, dict) else None
                rd = (r.body or {}).get("data") if isinstance(r.body, dict) else None
                if isinstance(fd, dict) and isinstance(rd, dict) and fd.get("id") != rd.get("id"):
                    raise StepFailed(f"重放 {call.idem} 生成了新记录（{rd.get('id')}）")
            elif isinstance(mode, dict):
                errs = check_expect(r, mode)
                if errs:
                    raise StepFailed("；".join(errs))


__all__ = ["Runner", "check_expect", "STEP_ADAPTERS", "PASSED", "FAILED", "SKIPPED", "ERROR"]
