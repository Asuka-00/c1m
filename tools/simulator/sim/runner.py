"""场景执行器：解析编码 -> 调接口 -> 断言 -> 生成报告。"""

from __future__ import annotations

import copy
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from sim.adapters import B11_STEPS, MODES, STEP_ADAPTERS, Adapter, Call, default_adapters, fill
from sim.client import Client, Resp
from sim.ids import SeqCounter, event_id
from sim.safety import redact
from sim.scenario import Scenario, Step

PASSED, FAILED, SKIPPED, ERROR = "passed", "failed", "skipped", "error"


class Skip(Exception):
    pass


class StepFailed(Exception):
    pass


def utcnow(offset_s: float = 0) -> str:
    t = datetime.now(timezone.utc) + timedelta(seconds=offset_s)
    return t.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _data(resp: Resp) -> Any:
    return resp.body.get("data", resp.body) if isinstance(resp.body, dict) else resp.body


def check_expect(resp: Resp, expect: dict | None, default_status: int = 200) -> list[str]:
    """返回不满足的断言列表（空表示通过）。"""
    expect = expect or {}
    errs: list[str] = []
    want = expect.get("status", default_status)
    if resp.status != want:
        errs.append(f"HTTP {resp.status} != 期望 {want}（code={resp.code}）")
    if "code" in expect and resp.code != expect["code"]:
        errs.append(f"code {resp.code!r} != 期望 {expect['code']!r}")
    # D65：422 明细第一条的 loc / type，例如 unknown_field 的 [body, 字段]、查询参数的 [query, 参数]
    # message：任一条明细的 msg 含该文本（字符串 / 列表 detail 都可用）
    if "message" in expect and not any(expect["message"] in str(e.get("msg") or "") for e in resp.errors):
        errs.append(f"错误信息里没有 {expect['message']!r}（实际 {[e.get('msg') for e in resp.errors]}）"[:300])
    if "loc" in expect or "type" in expect:
        first = resp.errors[0] if resp.errors else {}
        if not resp.detail_is_list:
            errs.append(
                f"detail 不是列表：{resp.body.get('detail') if isinstance(resp.body, dict) else resp.body!r}"[:200]
            )
        if "loc" in expect and first.get("loc") != expect["loc"]:
            errs.append(f"detail[0].loc {first.get('loc')!r} != 期望 {expect['loc']!r}")
        if "type" in expect and first.get("type") != expect["type"]:
            errs.append(f"detail[0].type {first.get('type')!r} != 期望 {expect['type']!r}")
    # data: 比较响应 data 里的字段，例如 D55 OQ-5 的 {cleared: false}
    want_data = expect.get("data") or {}
    if want_data:
        d = _data(resp)
        d = d if isinstance(d, dict) else {}
        for k, v in want_data.items():
            if d.get(k) != v:
                errs.append(f"data.{k} {d.get(k)!r} != 期望 {v!r}")
    # body: 比较整个响应体的字段，支持点号路径，例如 B9 清除的顶层 {cleared: false}、
    # B10 上报的 {"tool.life_state": warning, life_reached: true}
    for k, v in (expect.get("body") or {}).items():
        cur: Any = resp.body
        for part in str(k).split("."):
            cur = cur.get(part) if isinstance(cur, dict) else None
        if v == "$nonempty":  # 只要求非空（D59 补充前 state_skip_reason 是英文原文）
            if cur in (None, "", [], {}):
                errs.append(f"body.{k} {cur!r} 期望非空")
        elif cur != v:
            errs.append(f"body.{k} {cur!r} != 期望 {v!r}")
    chk = expect.get("check")
    if chk:
        want_type = chk.get("check_type")
        hits = [r for r in resp.check_results if want_type in (r.get("check_type"), r.get("code"), r.get("check"))]
        if not hits:
            got = [r.get("check_type") or r.get("code") for r in resp.check_results]
            errs.append(f"检查项里没有 {want_type!r}（实际 {got}）")
        else:
            if "min_count" in chk and len(hits) < int(chk["min_count"]):
                errs.append(f"检查项 {want_type} 只有 {len(hits)} 条，期望至少 {chk['min_count']} 条")
            bad = chk.get("not_message")
            if bad and any(bad in str(h.get("message") or "") for h in hits):
                errs.append(f"检查项 {want_type} 的 message 不应含 {bad!r}（实际 {[h.get('message') for h in hits]}）")
            # all: true = 每个字段每一条命中项都要满足；all: [字段...] = 只有这些字段要求每一条都满足，其余任一条满足
            # （P2-D3：规则项和内置项 result 都是 block；overridable=false 由内置硬拦截给出）
            every = chk.get("all")
            for k, v in chk.items():
                if k in ("check_type", "all", "not_message", "min_count"):
                    continue
                pick = all if every is True or (isinstance(every, list) and k in every) else any
                if not pick(h.get(k) == v for h in hits):
                    errs.append(f"检查项 {want_type} 的 {k} != {v!r}（实际 {[h.get(k) for h in hits]}）")
    return errs


def shape_422(resp: Resp) -> list[str]:
    """D65 补充（后端 1a7c0fb）：模拟器见到的每个 422 明细都必须带非空 code（没有专用码时 code = type）。
    detail 是列表时逐项检查；是对象时（如 D57 的 idempotency_key_reused）要求对象本身带 code。
    非列表 detail 本身不判失败，由 ``nonlist_422`` 记进报告（1a7c0fb 声明 detail 一律为列表）。"""
    if resp.status != 422:
        return []
    det = resp.body.get("detail") if isinstance(resp.body, dict) else None
    if isinstance(det, dict):
        return [] if det.get("code") else [f"422 detail 对象缺 code：{det!r}"[:200]]
    if not isinstance(det, list) or not det:
        return [f"422 的 detail 既不是列表也不是带 code 的对象：{det!r}"[:200]]
    bad = [x for x in det if not isinstance(x, dict) or not x.get("code")]
    if bad:
        return [f"422 明细缺 code：{bad!r}"[:200]]
    return []


# D65 补充 4：这些 422 的 detail 用对象 {code, message} 是认可的旧格式，不记 warn_422
LEGACY_OBJECT_422 = {"idempotency_key_reused"}


def nonlist_422(resp: Resp) -> str | None:
    det = resp.body.get("detail") if isinstance(resp.body, dict) else None
    if isinstance(det, dict) and det.get("code") in LEGACY_OBJECT_422:
        return None
    if resp.status == 422 and not isinstance(det, list):
        return f"422 detail 不是列表（{type(det).__name__}）：code={resp.code}"
    return None


class Runner:
    def __init__(
        self,
        client: Client,
        adapters: dict[str, Adapter] | None = None,
        paths: set[str] | None = None,
        stop_on_fail: bool = True,
        mode: str = "manual",
        svc: Client | None = None,
        strict_422: bool = True,
        xfail: bool = True,
    ) -> None:
        if mode not in MODES:
            raise ValueError(f"mode 只能是 {MODES}")
        self.mode = mode
        self.c = client
        self.svc = svc  # D65：只有 eap_service 的服务账号；None 时 B11 也用主账号
        self.strict_422 = strict_422
        # xfail=True：带 xfail 的步骤失败只记 xfail，不判场景失败；False（--strict-xfail / SIM_XFAIL=0）按普通步骤判
        self.xfail = xfail  # 1a7c0fb：模拟器见到的每个 422 都检查 detail 列表 + code
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
        for name in sc.required_adapters(self.mode):
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
            if st.args.get("pending"):  # 写好但先跳过的断言（等后端提交），不算失败
                entry.update(ok=None, pending=True, message=f"pending：{st.args['pending']}")
                rep.setdefault("pending", []).append(st.index)
                continue
            t0 = time.monotonic()
            try:
                self._step(sc, st, entry, seq, sent, saved)
                entry.setdefault("ok", True)  # 步骤自己记了 ok=None（如没有服务账号）时保留
                if st.args.get("xfail") and self.xfail:  # 预期失败的步骤通过了：后端已修，可去掉 xfail
                    entry["xpass"] = True
                    rep.setdefault("xpass", []).append(st.index)
            except Skip as e:
                entry.update(ok=None, message=str(e))
                rep.update(status=SKIPPED, reason=f"第 {st.index} 步前置条件不满足：{e}")
                break
            except StepFailed as e:
                if st.args.get("xfail") and self.xfail:  # 预期失败：后端下个提交前不算失败
                    entry.update(ok=None, xfail=True, message=f"xfail（{st.args['xfail']}）：{e}")
                    rep.setdefault("xfail", []).append(st.index)
                    continue
                entry.update(ok=False, message=str(e))
                rep["status"] = FAILED
                rep["reason"] = rep["reason"] or f"第 {st.index} 步：{e}"
                if self.stop_on_fail:
                    break
            finally:
                entry["elapsed_ms"] = int((time.monotonic() - t0) * 1000)
        rep["finished_at"] = utcnow()
        return rep

    def cli(self, call: Call) -> Client:
        """B11 事件走服务账号（有的话），其余走主账号。"""
        return self.svc if (self.svc is not None and self.is_b11(call)) else self.c

    def _send(self, entry: dict, call: Call, expect: dict | None) -> Resp:
        if self.svc is not None and self.is_b11(call):
            entry["account"] = "eap_service"
        r = self.cli(call).request(
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
        if call.idem:
            entry["idempotency_key"] = call.idem
        errs = check_expect(self.view(call, r), expect) + (shape_422(r) if self.strict_422 else [])
        if nonlist_422(r):
            entry["warn_422"] = nonlist_422(r)
        if errs:
            raise StepFailed("；".join(errs))
        return r

    def _ad(self, name: str) -> str:
        ad = self.adapters[name]
        p = ad.path or ad.resolve(self.paths)
        if not p and self.mode == "b11":  # b11 模式下手工路径只用来拼 payload，不真正调用
            p = ad.candidates[0]
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
        if k == "reuse":
            return self._reuse(a, entry, sent)
        if k == "expect_e10":
            return self._expect_e10(a, entry, saved)
        if k == "expect_alarm":
            return self._expect_alarm(a, entry, saved)
        if k == "seed_alarm_code":
            return self._seed_alarm_code(a, entry)
        if k == "expect_e10_history":
            return self._expect_e10_history(a, entry)
        if k == "tool_set":
            return self._tool_set(a, entry)
        if k == "expect_eap_read":
            return self._expect_eap_read(a, entry)
        if k == "expect_eap_envelope_extra":
            return self._expect_eap_envelope_extra(dict(a, run_id=sc.run_id), entry)
        if k == "expect_body_422":
            return self._expect_body_422(a, entry)
        if k == "expect_query_422":
            return self._expect_query_422(a, entry)
        if k == "expect_alarm_list":
            return self._expect_alarm_list(a, entry)
        if k in ("tool_reset", "tool_unmount", "tool_replace"):
            return self._tool_action(sc, st, entry)
        if k == "expect_tool_log":
            return self._expect_tool_log(a, entry)
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
            # time_offset_s：事件时间相对现在的偏移，D55 OQ-2 用 >300 秒测 422 time_in_future
            occurred = utcnow(float(a.get("time_offset_s", 0)))
            body = {"alid": str(a["alid"]), "external_event_id": ext, "set_at": occurred}
            if a.get("lots"):
                body["lot_ids"] = [self.rid("lot", x) for x in a["lots"]]
            call = Call("POST", fill(self._ad("alarm_set"), eq_id=eq_id), body, ext)
        elif k == "alarm_clear":
            body = {"external_event_id": ext, "cleared_at": utcnow(float(a.get("time_offset_s", 0)))}
            if a.get("alid") is not None:
                # B11 8294b63：按 (equipment_id, alid) 清除，没有 active 报警时 200 cleared=false、data=null
                body = {"equipment_id": eq_id, "alid": str(a["alid"]), **body}
                call = Call("POST", self._ad("alarm_clear_alid"), body, ext)
            else:
                aid = saved.get(str(a["alarm"]).lstrip("$"))
                if not aid:
                    raise StepFailed(f"alarm_clear 找不到保存的报警 {a.get('alarm')}")
                call = Call("POST", fill(self._ad("alarm_clear"), alarm_id=aid), body, ext)
                if self.mode == "b11":  # B11 只认 alid：用 save_as 时记下的 alid
                    alid = saved.get(str(a["alarm"]).lstrip("$") + "#alid")
                    if not alid:
                        raise StepFailed(f"b11 模式下 alarm_clear 需要 alid（{a['alarm']} 没记下 alid）")
                    call.body = {"alid": alid, **body}
        elif k == "tool_usage":
            body = {"delta": str(a["delta"]), "equipment_id": eq_id, "external_event_id": ext}
            if a.get("reason"):  # 负数调整必须带 reason_id（reason_code）
                body["reason_id"] = self.rid("reason_code", a["reason"])
            call = Call("POST", fill(self._ad("tool_usage"), tool_id=self.rid("tool", a["tool"])), body, ext)
        elif k == "tool_mount":
            body = {"equipment_id": eq_id, "comment": tag[:300]}
            if a.get("port"):
                body["port_code"] = a["port"]
            call = Call("POST", fill(self._ad("tool_mount"), tool_id=self.rid("tool", a["tool"])), body, ext)
        else:  # pragma: no cover - scenario.parse 已拦
            raise StepFailed(f"未知步骤 {k}")
        if self.mode == "b11" and k in B11_STEPS:
            call = self._to_b11(k, eq_id, ext, call)
        r = self._send(entry, call, a.get("expect"))
        sent[(eq, n)] = (call, r)
        if a.get("save_as") and isinstance(r.body, dict):
            d = self.view(call, r).body
            d = d.get("data", d) if isinstance(d, dict) else None
            saved[a["save_as"]] = d.get("id") if isinstance(d, dict) else None
            if k == "alarm_set":
                saved[a["save_as"] + "#alid"] = str(a["alid"])

    @staticmethod
    def is_b11(call: Call) -> bool:
        return isinstance(call.body, dict) and "event_type" in call.body and "payload" in call.body

    def view(self, call: Call, r: Resp) -> Resp:
        """B11 响应是 {data: 台账行, duplicate, result: 下层接口响应}。断言和 save_as 用 result
        （和手工接口同形），但 duplicate 取信封上的（重放时 result 原样是首次的）；台账行放在 event。"""
        if not self.is_b11(call) or not isinstance(r.body, dict) or "result" not in r.body:
            return r
        res = r.body.get("result")
        res = dict(res) if isinstance(res, dict) else {"data": res}
        res.update(duplicate=r.body.get("duplicate"), event=r.body.get("data"))
        return Resp(r.status, res, r.elapsed_ms)

    def _to_b11(self, kind: str, eq_id: str, ext: str, manual: Call) -> Call:
        """把手工接口调用改写成 B11（8294b63）的 EAP 入口事件。

        payload 是严格校验的：external_event_id、equipment_id 只放信封；tool_usage 把路径里的
        tool_id 放进 payload；alarm_clear 只发 alid（B11 不认 alarm_id）。"""
        payload = {k: v for k, v in (manual.body or {}).items() if k not in ("external_event_id", "equipment_id")}
        if kind == "tool_usage":
            payload["tool_id"] = manual.path.rstrip("/").split("/")[-2]
        if kind == "alarm_clear" and "alid" not in payload:
            raise StepFailed("B11 alarm_clear 必须带 alid")
        body = {
            "source": "simulator",  # D53-4 / D54
            "external_event_id": ext,
            "event_type": kind,
            "equipment_id": eq_id,
            "payload": payload,
        }
        return Call("POST", self._ad("eap_events"), body, None)

    def _tool_action(self, sc, st: Step, entry: dict) -> None:
        """B10 reset / unmount / replace：请求体严格（extra=forbid），不收 external_event_id，
        模拟器标识放 comment 和 Idempotency-Key 请求头。"""
        a, k = st.args, st.kind
        tid = self.rid("tool", a["tool"])
        idem = f"{sc.run_id}:{a['tool']}:{st.index}"
        body: dict[str, Any] = {"comment": f"sim_run_id={sc.run_id} step={st.index}"}
        if k == "tool_reset":
            body["reason_id"] = self.rid("reason_code", a["reason"])
        else:
            body["reason"] = a["reason"]
        if k == "tool_replace":
            body["new_tool_id"] = self.rid("tool", a["new_tool"])
        self._send(entry, Call("POST", fill(self._ad(k), tool_id=tid), body, idem), a.get("expect"))

    def _expect_tool_log(self, a: dict, entry: dict) -> None:
        """GET usage / mounts 履历：count 精确匹配，last 比较最新一条（newest first）。"""
        name = "tool_mounts" if a.get("log") == "mounts" else "tool_usage_log"
        r = self.c.get(fill(self._ad(name), tool_id=self.rid("tool", a["tool"])), page_size=200)
        entry.update(status=r.status, code=r.code)
        if r.status != 200:
            raise StepFailed(f"查 {a['tool']} 履历 HTTP {r.status}")
        b = r.body if isinstance(r.body, dict) else {}
        rows = b.get("data") or []
        entry["count"] = b.get("count", len(rows))
        if "count" in a and entry["count"] != a["count"]:
            raise StepFailed(f"{a['tool']} 履历条数={entry['count']}，期望 {a['count']}")
        for f, v in (a.get("last") or {}).items():
            got = rows[0].get(f) if rows else None
            if got != v:
                raise StepFailed(f"{a['tool']} 最新履历 {f}={got!r}，期望 {v!r}")

    def _e10_code(self, eq: str) -> str | None:
        board = self.c.get("/mes/eqp/board").body or {}
        rows = board.get("data", []) if isinstance(board, dict) else []
        cur = next((x for x in rows if x.get("code") == eq), {}).get("state") or {}
        return cur.get("code")

    def _expect_e10(self, a: dict, entry: dict, saved: dict) -> None:
        """state: 期望编码；save_as: 记下当前状态；same_as: $名，要求与记下的相同（报警不改 E10）。"""
        got = self._e10_code(a["eq"])
        entry["e10"] = got
        if "state" in a and got != a["state"]:
            raise StepFailed(f"{a['eq']} 当前 E10={got}，期望 {a['state']}")
        if a.get("same_as"):
            key = str(a["same_as"]).lstrip("$")
            if key not in saved:
                raise StepFailed(f"expect_e10 找不到保存的状态 {a['same_as']}")
            if got != saved[key]:
                raise StepFailed(f"{a['eq']} E10 从 {saved[key]} 变成了 {got}，期望不变")
        if a.get("save_as"):
            saved[a["save_as"]] = got

    def _expect_alarm(self, a: dict, entry: dict, saved: dict) -> None:
        """D55 OQ-3：报警记录（含 unregistered）和 mes_alarm_lot 关联的在制批。"""
        aid = saved.get(str(a["alarm"]).lstrip("$"))
        if not aid:
            raise StepFailed(f"expect_alarm 找不到保存的报警 {a['alarm']}")
        r = self.c.get(fill(self._ad("alarm_get"), alarm_id=aid))
        entry.update(status=r.status, code=r.code)
        if r.status != 200:
            raise StepFailed(f"查报警 {aid} HTTP {r.status}")
        d = _data(r) if isinstance(_data(r), dict) else {}
        for f in ("unregistered", "alarm_status", "alid", "source", "action", "state_changed", "state_skip_reason"):
            if f in a and d.get(f) != self.by_mode(a[f]):
                raise StepFailed(f"报警 {aid} 的 {f}={d.get(f)!r}，期望 {self.by_mode(a[f])!r}")
        if a.get("lots"):
            linked = d.get("lots") or d.get("lot_ids") or []
            keys = set()
            for x in linked:
                if isinstance(x, dict):
                    keys.update(str(x.get(f)) for f in ("lot_id", "id", "lot_code", "code") if x.get(f))
                else:
                    keys.add(str(x))
            for lot in a["lots"]:
                if lot not in keys and self.rid("lot", lot) not in keys:
                    raise StepFailed(f"报警 {aid} 没有关联在制批 {lot}（mes_alarm_lot）")

    def by_mode(self, v: Any) -> Any:
        """期望值可以按模式给：``{manual: manual, b11: simulator}``（D30 手工接口记 manual，B11 记事件来源）。"""
        if isinstance(v, dict) and set(v) and set(v) <= set(MODES):
            return v.get(self.mode)
        return v

    def _seed_alarm_code(self, a: dict, entry: dict) -> None:
        """D59 报警码种子：按 (设备, ALID) upsert 单台覆盖的报警码，联动只有 none / set_state + target_state。
        设备类型取自设备行（alarm_code.equipment_type 必填）。也用来测 D59 的 422 反例（expect 给 422）。"""
        eq = self.row("equipment", a["eq"])
        body: dict[str, Any] = {
            "alid": str(a["alid"]),
            "equipment_id": eq.get("id") or self.rid("equipment", a["eq"]),
            "equipment_type_id": eq.get("equipment_type_id"),
            "action": a["action"],
            "target_state": a.get("target_state"),
        }
        for f in ("severity", "text_zh", "text_en"):
            if a.get(f):
                body[f] = a[f]
        body.update(a.get("extra") or {})  # P2-D6 反例：带未知 / 只读字段（如 target_e10_state_id、migration_note）
        r = self.c.get(self._ad("crud").replace("{entity}", "alarm_code"), q=body["alid"], page_size=100)
        rows = (r.body or {}).get("data", []) if isinstance(r.body, dict) else []
        hit = [x for x in rows if x.get("alid") == body["alid"] and x.get("equipment_id") == body["equipment_id"]]
        if hit:
            call = Call("PATCH", fill(self._ad("crud_item"), entity="alarm_code", rid=hit[0]["id"]), body)
        else:
            call = Call("POST", self._ad("crud").replace("{entity}", "alarm_code"), body)
        self._send(entry, call, a.get("expect"))

    def _expect_e10_history(self, a: dict, entry: dict) -> None:
        """D58 补充：E10 履历最新一条的 trigger（manual/equipment/system）、source（事件来源）和目标状态。"""
        eq_id = self.rid("equipment", a["eq"])
        q = {k: self.by_mode(v) for k, v in (a.get("filter") or {}).items()}  # 如 ?trigger=equipment（f2d890c）
        r = self.c.get(
            self._ad("crud").replace("{entity}", "e10_history"),
            equipment_id=eq_id,
            sort_by="at",
            sort_order="desc",
            page_size=int(a.get("n", 1 if not q else 100)),
            **q,
        )
        rows = (r.body or {}).get("data", []) if isinstance(r.body, dict) else []
        entry.update(status=r.status, rows=len(rows))
        if r.status != 200 or not rows:
            raise StepFailed(f"{a['eq']} 查不到 E10 履历（HTTP {r.status}）")
        for f, v in q.items():  # 筛选结果每一条都要符合
            bad = [x.get(f) for x in rows if x.get(f) != v]
            if bad:
                raise StepFailed(f"{a['eq']} E10 履历按 {f}={v} 筛选，结果里有 {bad}")
        last = rows[0]
        entry["last"] = {k: last.get(k) for k in ("trigger", "source", "to_state_id", "comment")}
        for f, v in (a.get("last") or {}).items():
            want = self.by_mode(v)
            if f == "to":
                got, want = last.get("to_state_id"), self.rid("e10_state", want)
            else:
                got = last.get(f)
            if got != want:
                raise StepFailed(f"{a['eq']} 最新 E10 履历 {f}={got!r}，期望 {want!r}")

    def _expect_eap_read(self, a: dict, entry: dict) -> None:
        """D65 mes.eap:read_master：服务账号能列表 / 详情 equipment、alarm_code、e10_state；
        对它们新增、修改、导出 403；其他主数据（denied）读也 403。不发 DELETE（防止权限放错时真删数据）。"""
        if self.svc is None:
            entry.update(ok=None, message="没有 eap_service 账号（SIM_SVC_*），跳过")
            return
        base = self._ad("crud")
        got: dict[str, Any] = {}
        errs: list[str] = []
        for ent in a.get("entities") or ("equipment", "alarm_code", "e10_state"):
            path = base.replace("{entity}", ent)
            r = self.svc.get(path, page_size=5)
            rows = (r.body or {}).get("data", []) if isinstance(r.body, dict) else []
            got[ent] = {"list": r.status}
            if r.status != 200 or not rows:
                errs.append(f"{ent} 列表 HTTP {r.status}，{len(rows)} 条（期望 200 且非空）")
                continue
            rid = rows[0]["id"]
            item = fill(self._ad("crud_item"), entity=ent, rid=rid)
            d = self.svc.get(item)
            w1 = self.svc.request("POST", path, {})
            w2 = self.svc.request("PATCH", item, {})
            ex = self.svc.get(path + "/export")
            got[ent].update(detail=d.status, post=w1.status, patch=w2.status, export=ex.status)
            if d.status != 200:
                errs.append(f"{ent} 详情 HTTP {d.status}（期望 200）")
            for n, x in (("新增", w1), ("修改", w2), ("导出", ex)):
                if x.status != 403:
                    errs.append(f"{ent} {n} HTTP {x.status}（期望 403）")
        for p in a.get("allowed_paths") or ():  # 1a7c0fb：/mes/_meta 对 eap_service 开放
            r = self.svc.get(p)
            got[p] = r.status
            if r.status != 200:
                errs.append(f"{p} HTTP {r.status}（期望 200）")
        for ent in a.get("denied") or ():
            r = self.svc.get(base.replace("{entity}", ent), page_size=1)
            got[ent] = {"list": r.status}
            if r.status != 403:
                errs.append(f"{ent} 不在 read_master 里，列表应 403，实际 {r.status}")
        entry.update(account="eap_service", access=got)
        if errs:
            raise StepFailed("；".join(errs))

    def _expect_query_422(self, a: dict, entry: dict) -> None:
        """D65：查询参数校验错误 422，detail 是列表，loc 以 query 开头（给了 field 时等于 [query, field]）。"""
        path = a["path"]
        if "{entity}" in path:
            path = path.replace("{entity}", a["entity"])
        params = {}
        for k, v in (a.get("params") or {}).items():
            v = self.by_mode(v)
            if isinstance(v, str) and v.startswith("$eq:"):  # 设备编码 -> id
                v = self.rid("equipment", v[4:])
            params[k] = v
        r = self.c.get(path, **params)
        entry.update(path=path, status=r.status, code=r.code)
        det = r.body.get("detail") if isinstance(r.body, dict) else None
        entry["detail"] = det if isinstance(det, list) else str(det)[:200]
        if r.status != 422:
            raise StepFailed(f"{path} {a.get('params')} HTTP {r.status}（期望 422）")
        if not isinstance(det, list) or not det or not isinstance(det[0], dict):
            raise StepFailed(f"{path} 422 的 detail 不是列表：{str(det)[:150]}")
        loc = det[0].get("loc") or []
        want_loc = a.get("loc")
        if want_loc is not None:  # 显式 loc，如路径参数 [path, field]
            if list(loc) != list(want_loc):
                raise StepFailed(f"{path} 422 的 loc={loc}，期望 {want_loc}")
        else:
            if not loc or loc[0] != "query":
                raise StepFailed(f"{path} 422 的 loc={loc}，期望以 query 开头")
            if a.get("field") and list(loc) != ["query", a["field"]]:
                raise StepFailed(f"{path} 422 的 loc={loc}，期望 ['query', {a['field']!r}]")
        code = det[0].get("code")
        if a.get("code") and code != a["code"]:
            raise StepFailed(f"{path} 422 的 code={code!r}，期望 {a['code']!r}")
        if a.get("code_is_type") and code != det[0].get("type"):
            raise StepFailed(f"{path} 422 的 code={code!r} 应等于 type={det[0].get('type')!r}")
        errs = shape_422(r)
        if errs:
            raise StepFailed("；".join(errs))

    def _expect_alarm_list(self, a: dict, entry: dict) -> None:
        """D65：报警履历列表（GET /mes/eqp/alarms）每行顶层带 state_changed / state_skip_reason。
        rows 按 ALID 给期望值，取该 ALID 最新一行比较；每一行都必须有这两个键。"""
        r = self.c.get(self._ad("alarm_list"), equipment_id=self.rid("equipment", a["eq"]), page_size=100)
        rows = (r.body or {}).get("data", []) if isinstance(r.body, dict) else []
        entry.update(status=r.status, rows=len(rows))
        if r.status != 200:
            raise StepFailed(f"报警列表 HTTP {r.status}")
        miss = [x.get("alid") for x in rows if "state_changed" not in x or "state_skip_reason" not in x]
        if miss:
            raise StepFailed(f"报警列表这些行没有顶层 state_changed/state_skip_reason：{miss}")
        for alid, want in (a.get("rows") or {}).items():
            hit = [x for x in rows if x.get("alid") == str(alid)]
            if not hit:
                raise StepFailed(f"报警列表里没有 ALID {alid}")
            for f, v in want.items():
                if hit[0].get(f) != v:
                    raise StepFailed(f"报警列表 ALID {alid} 的 {f}={hit[0].get(f)!r}，期望 {v!r}")

    def _tool_set(self, a: dict, entry: dict) -> None:
        """改工具字段（测试准备）：P2-D3 用来造过期（expiry_date 相对天数如 -1）和不可用（tool_status）。"""
        fields: dict[str, Any] = {}
        for f, v in a["fields"].items():
            if f == "expiry_date" and isinstance(v, int):
                v = (datetime.now(timezone.utc).date() + timedelta(days=v)).isoformat()
            fields[f] = v
        call = Call("PATCH", fill(self._ad("crud_item"), entity="tool", rid=self.rid("tool", a["tool"])), fields)
        self._send(entry, call, a.get("expect"))

    def _precondition(self, a: dict) -> None:
        if a.get("eq"):
            row = self.row("equipment", a["eq"])
            if "qual_state" in a and (row.get("qual_state") or "ready") != a["qual_state"]:
                raise Skip(f"{a['eq']} qual_state={row.get('qual_state')}，场景要求 {a['qual_state']}")
            if "e10" in a:
                cur = self._e10_code(a["eq"])
                if cur != a["e10"]:
                    raise Skip(f"{a['eq']} 当前 E10={cur}，场景要求从 {a['e10']} 开始")
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
            r = self.cli(call).request(
                call.method, call.path, call.body, headers={"Idempotency-Key": call.idem} if call.idem else None
            )
            key = call.idem or (call.body or {}).get("external_event_id")
            item = {"seq": n, "external_event_id": key, "status": r.status, "code": r.code}
            entry["replayed"].append(item)
            first, r = self.view(call, first), self.view(call, r)
            mode = a.get("expect", "idempotent")
            if mode == "idempotent":
                if r.status != first.status:
                    raise StepFailed(f"重放 {key} HTTP {r.status} != 首次 {first.status}")
                fd = (first.body or {}).get("data") if isinstance(first.body, dict) else None
                rd = (r.body or {}).get("data") if isinstance(r.body, dict) else None
                if isinstance(fd, dict) and isinstance(rd, dict) and fd.get("id") != rd.get("id"):
                    raise StepFailed(f"重放 {key} 生成了新记录（{rd.get('id')}）")
                # P2-D8：重复上报返回和首次相同的字段（如 state_changed / state_skip_reason）
                for f in a.get("same_as_first") or []:
                    fv = first.body.get(f) if isinstance(first.body, dict) else None
                    rv = r.body.get(f) if isinstance(r.body, dict) else None
                    if fv != rv:
                        raise StepFailed(f"重放 {key} 的 {f}={rv!r}，首次是 {fv!r}")
                if a.get("body"):
                    errs = check_expect(r, {"status": r.status, "body": a["body"]})
                    if errs:
                        raise StepFailed("；".join(errs))
            elif isinstance(mode, dict):
                errs = check_expect(r, mode) + (shape_422(r) if self.strict_422 else [])
                if errs:
                    raise StepFailed("；".join(errs))

    def _expect_body_422(self, a: dict, entry: dict) -> None:
        """D65 补充 4（后端 56474fe）：请求体带未知字段 -> 422 unknown_field（loc [body, 字段]），且没有副作用。
        走主账号的手工接口。endpoint=e10：to 填设备当前状态（就算后端不拦也只会报原地迁移，不改状态）；
        endpoint=move_in/track_in：要 lot，前后比对批次行，确认没写入。"""
        ep = a.get("endpoint", "e10")
        extra = a.get("extra") or {"bogus": 1}
        field = next(iter(extra))
        eq_id = self.rid("equipment", a["eq"])
        if ep == "e10":
            path = fill(self._ad("e10"), eq_id=eq_id)
            body = {"to_state_id": self.rid("e10_state", a["to"]), **extra}
            before = None
        elif ep in ("move_in", "track_in"):
            path = fill(self._ad("stage"), lot_id=self.rid("lot", a["lot"]), stage=ep)
            body = {"equipment_id": eq_id, **extra}
            before = self.row("lot", a["lot"])
        else:
            raise StepFailed(f"expect_body_422 不支持 endpoint={ep}")
        want_code, want_loc = a.get("code", "unknown_field"), a.get("loc") or ["body", field]
        r = self.c.request("POST", path, body)
        entry.update(method="POST", path=path, request=redact(body), status=r.status, code=r.code)
        errs = shape_422(r) if self.strict_422 else []
        det = r.body.get("detail") if isinstance(r.body, dict) else None
        hit = (
            [x for x in det if isinstance(x, dict) and list(x.get("loc") or []) == want_loc]
            if isinstance(det, list)
            else []
        )
        if r.status != 422:
            errs.append(f"带未知字段 {field} 期望 422，实际 HTTP {r.status}")
        elif not hit or hit[0].get("code") != want_code:
            errs.append(f"期望 loc {want_loc} code {want_code}，实际 {det!r}"[:300])
        if before is not None:
            after = self.row("lot", a["lot"])
            if after != before:
                diff = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
                errs.append(f"未知字段请求被拒后批次 {a['lot']} 仍有变化：{diff}")
        if errs:
            raise StepFailed("；".join(errs))

    def _expect_eap_envelope_extra(self, a: dict, entry: dict) -> None:
        """D54 例外：/mes/eap/events 信封顶层多出的字段并进 payload，不报 422。用服务账号发一条按 ALID 清除
        （ALID 没有 active 报警 -> 200 cleared=false，无副作用），comment 放在顶层而不是 payload。"""
        if self.svc is None:
            entry.update(ok=None, message="没有服务账号（SIM_SVC_*），跳过")
            return
        ext = f"sim:{a.get('run_id', 'env')}:{a['eq']}:envx:{int(time.time() * 1000)}"
        body = {
            "source": "simulator",
            "external_event_id": ext,
            "event_type": "alarm_clear",
            "equipment_id": self.rid("equipment", a["eq"]),
            "payload": {"alid": str(a.get("alid", "1999"))},
            a.get("field", "comment"): a.get("value", "sim envelope extra"),
        }
        path = self._ad("eap_events")
        r = self.svc.request("POST", path, body)
        entry.update(
            method="POST", path=path, request=redact(body), status=r.status, code=r.code, account="eap_service"
        )
        if r.status == 422 or r.status >= 400:
            raise StepFailed(
                f"信封顶层多带 {a.get('field', 'comment')} 应被接受，实际 HTTP {r.status} {r.body!r}"[:300]
            )
        v = self.view(Call("POST", path, body), r).body or {}
        if "cleared" in a and v.get("cleared") != a["cleared"]:
            raise StepFailed(f"cleared={v.get('cleared')!r}，期望 {a['cleared']!r}")

    def _reuse(self, a: dict, entry: dict, sent) -> None:
        """D57 反例：同一个 key（manual 是 Idempotency-Key，b11 是 external_event_id）换请求内容重发，
        默认期望 422 idempotency_key_reused。change 里的字段改到请求体（b11 改到 payload）；
        ``to`` 是 E10 状态编码的简写，会解析成 to_state_id。是否没写入由后面的 expect_* 步骤验证。"""
        eq, n = a["eq"], int(a["seq"])
        if (eq, n) not in sent:
            raise StepFailed(f"没有 {eq} 序号 {n} 的已发送事件可改内容重发")
        call, _ = sent[(eq, n)]
        body = copy.deepcopy(call.body)
        target = body["payload"] if self.is_b11(call) else body
        for f, v in (a.get("change") or {}).items():
            if f == "to":
                target["to_state_id"] = self.rid("e10_state", v)
            else:
                target[f] = str(v) if f == "delta" else v
        if body == call.body:
            raise StepFailed("reuse 的 change 没有改变请求内容")
        new = Call(call.method, call.path, body, call.idem)
        self._send(entry, new, a.get("expect") or {"status": 422, "code": "idempotency_key_reused"})


__all__ = ["Runner", "check_expect", "STEP_ADAPTERS", "PASSED", "FAILED", "SKIPPED", "ERROR"]
