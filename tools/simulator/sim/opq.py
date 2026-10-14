# ruff: noqa: E501
"""opq-01：P3-B6 人员资质（D74/D81/D85 补充二~四/D86/D88）直连执行器。

YAML 草稿 scenarios/p3-draft/operator-qual.yaml 是契约说明；通用 DSL 还没有 operator_qual 步骤，
这里按草稿逐条执行。写走通用 CRUD /mes/operator-qual，读履历 /mes/exec/operator-qual/{id}/history，
事件读 /mes/audit_log（entity_type=operator_qual）。每次运行 key 带 run 前缀；跑前必须先 reset。
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import date, timedelta
from typing import Any

from sim.client import Client, Resp

Q = "/mes/operator-qual"


class Opq:
    def __init__(self, c: Client, run: str, lead: str) -> None:
        self.c, self.run, self.lead = c, run, lead
        self.steps: list[dict] = []
        self.n = 0

    # ---------- 基础 ----------
    def rows(self, r: Resp) -> list[dict]:
        b = r.body
        if isinstance(b, dict):
            b = b.get("data", b.get("rows", b))
        return b if isinstance(b, list) else []

    def req(self, m: str, p: str, body: Any = None, key: str | None = "auto", **params: Any) -> Resp:
        h = None
        if key == "auto":
            self.n += 1
            key = f"{self.run}:k{self.n}"
        if key:
            h = {"Idempotency-Key": key}
        return self.c.request(m, p, body, params=params or None, headers=h)

    def step(self, name: str, fn, xfail: str | None = None) -> Any:
        e: dict = {"i": len(self.steps) + 1, "step": name}
        try:
            out = fn(e)
            if xfail:
                e.update(result="xpass", note=f"xfail 已通过：{xfail}")
            else:
                e["result"] = "pass"
            self.steps.append(e)
            return out
        except AssertionError as ex:
            e.update(result="xfail" if xfail else "fail", error=str(ex)[:600])
            if xfail:
                e["xfail"] = xfail
        except Exception as ex:  # noqa: BLE001
            e.update(result="fail", error=f"{type(ex).__name__}: {ex}"[:600])
        self.steps.append(e)
        return None

    @staticmethod
    def rec(e: dict, m: str, p: str, r: Resp, body: Any = None) -> None:
        e.update(req=f"{m} {re.sub(r'[0-9a-f-]{36}', '{id}', p)}", status=r.status,
                 resp=json.dumps(r.body, ensure_ascii=False)[:500] if r.status >= 300 else None,
                 replayed=r.headers.get("idempotent-replayed"))
        if body is not None:
            e["body"] = json.dumps(body, ensure_ascii=False)[:300]

    @staticmethod
    def det(r: Resp) -> Any:
        return r.body.get("detail") if isinstance(r.body, dict) else None

    def err422(self, r: Resp, typ: str, loc: list, ctx: dict | None = None) -> None:
        assert r.status == 422, f"HTTP {r.status}（期望 422）：{r.body}"
        d = self.det(r)
        assert isinstance(d, list) and d, f"detail 不是数组：{d}"
        hit = [x for x in d if x.get("loc") == loc]
        assert hit, f"没有 loc={loc} 的错误项：{d}"
        assert hit[0].get("type") == typ, f"type={hit[0].get('type')} 期望 {typ}"
        for k, v in (ctx or {}).items():
            got = (hit[0].get("ctx") or {}).get(k)
            assert got == v, f"ctx.{k}={got!r} 期望 {v!r}"

    def hist(self, qid: str) -> list[dict]:
        r = self.c.get(f"/mes/exec/operator-qual/{qid}/history", limit=200)
        assert r.status == 200, f"history HTTP {r.status} {r.body}"
        return self.rows(r)

    def events(self, qid: str) -> list[dict]:
        r = self.c.get("/mes/audit_log", entity_type="operator_qual", record_id=qid, page_size=100)
        assert r.status == 200, f"audit_log HTTP {r.status}"
        out = [x.get("action") for x in sorted(self.rows(r), key=lambda x: str(x.get("created_at")), reverse=True)]
        return [a for a in out if str(a).startswith("operator_qual.")]

    def latest(self, qid: str, action: str, **want: Any) -> None:
        h = self.hist(qid)
        assert h, "履历为空"
        top = h[0]
        for k in ("comment", "reason_id", "approved_by"):
            assert k in top, f"履历行缺列 {k}：{list(top)}"
        assert top.get("action") == action, f"最新履历 action={top.get('action')} 期望 {action}"
        for k, v in want.items():
            assert top.get(k) == v, f"履历 {k}={top.get(k)!r} 期望 {v!r}"

    # ---------- 场景 ----------
    def run_all(self) -> list[dict]:
        c = self.c
        today = date.today()
        d = lambda n: (today + timedelta(days=n)).isoformat()  # noqa: E731
        me = (c.get("/users/me").body or {}).get("username")
        ctx: dict[str, Any] = {}

        def prep(e):
            area = self.rows(c.get("/mes/area", page_size=1))[0]
            op = self.rows(c.get("/mes/operation", code="OP-MK", page_size=5))
            assert op, "没有 OP-MK（先跑 reset/seed-p3）"
            eq = [x for x in self.rows(c.get("/mes/equipment", code="EAP-MK01", page_size=5)) if x["code"] == "EAP-MK01"][0]
            rs = self.rows(c.get("/mes/reason_code", reason_type="operator_qual", page_size=50))
            rs = [x for x in rs if x.get("reason_type") == "operator_qual" and x.get("is_active") is not False]
            if not rs:  # app_it_eap 不跑 initial_data，原因表本环境自建一行（类别 operator_qual）
                r = self.req("POST", "/mes/reason_code", {"code": "OPQ-SIM", "name": "资质变更（模拟器）", "reason_type": "operator_qual"}, key=None)
                self.rec(e, "POST", "/mes/reason_code", r)
                assert r.status in (200, 201), f"建原因码失败 {r.status} {r.body}"
                rs = [r.body.get("data", r.body)]
            ctx.update(op=op[0], eq=eq, reason=rs[0]["id"], area=area)
            # 本库无 demo 卡控：自建 operator_qualified 规则（block）→ 方案 → 绑定 track_in / 工序 OP-MK（reset 后消失）
            def mk(ent, body):
                r = self.req("POST", f"/mes/{ent}", body, key=None)
                assert r.status in (200, 201), f"建 {ent} 失败 {r.status} {r.body}"
                return r.body.get("data", r.body)
            rule = mk("check_rule", {"code": "CR-QUAL-SIM", "name": "operator qualified (sim)", "check_type": "operator_qualified", "severity": "block", "params": {}})
            plan = mk("check_plan", {"code": "CP-QUAL-SIM", "name": "qual (sim)"})
            mk("check_plan_item", {"check_plan_id": plan["id"], "check_rule_id": rule["id"], "seq": 10})
            mk("check_binding", {"check_plan_id": plan["id"], "trigger": "track_in", "scope": "operation", "operation_id": op[0]["id"]})
            e["note"] = f"me={me} lead={self.lead} reason={rs[0].get('code')} op=OP-MK eq=EAP-MK01"
        self.step("准备：OP-MK / EAP-MK01 / 原因码（operator_qual）", prep)
        if "reason" not in ctx:
            return self.steps
        op, et, R = ctx["op"]["id"], ctx["eq"]["equipment_type_id"], ctx["reason"]
        MISSING = str(uuid.uuid4())
        pr = self.req("PATCH", f"{Q}/{MISSING}", {"expires_on": d(60), "reason_id": R, "comment": "probe", "approved_by": self.lead})
        lead_ok = pr.status == 404
        NOLEAD = "由 QA 覆盖"  # D88 补充一：8012 上 QA 覆盖，8013 不建额外账号
        orig_step = self.step

        def gated(name, fn, xfail=None, need_lead=False):
            if need_lead and not lead_ok:
                self.steps.append({"i": len(self.steps) + 1, "step": name, "result": "skip", "note": NOLEAD})
                return None
            return orig_step(name, fn, xfail)
        self.step = gated  # type: ignore[assignment]

        def grant(e):
            b = {"username": me, "operation_id": op, "equipment_type_id": et, "expires_on": d(-1), "is_active": True}
            r = self.req("POST", Q, b)
            self.rec(e, "POST", Q, r, b)
            assert r.status == 200, f"授予 HTTP {r.status}（期望 200）：{r.body}"
            assert "idempotent-replayed" not in r.headers, "首次执行带了 Idempotent-Replayed"
            ctx["q"] = (r.body.get("data", r.body))["id"]
        self.step("授予（无 reason/approved_by，昨天到期的种子）→ 200", grant)
        if "q" not in ctx:
            return self.steps
        q = ctx["q"]
        qp = f"{Q}/{q}"
        self.step("履历 granted（comment/reason_id/approved_by 为 null）",
                  lambda e: self.latest(q, "granted", comment=None, reason_id=None, approved_by=None))

        def ev(name, none=()):
            def f(e):
                evs = self.events(q)
                e["events"] = evs[:6]
                assert evs and evs[0] == name, f"最新事件 {evs[:1]} 期望 {name}"
                for x in none:
                    assert x not in evs, f"不应有事件 {x}"
            return f
        self.step("事件 operator_qual.granted", ev("operator_qual.granted"))

        # 过期 → 进站 409 check_blocked
        def track_in(e):
            prods = self.rows(c.get("/mes/product", code="P-MK", page_size=5))
            lt = self.rows(c.get("/mes/lot_type", code="LT-MK", page_size=5))
            assert prods and lt, "缺 P-MK / LT-MK"
            wo = self.req("POST", "/mes/work_order", {"product_id": prods[0]["id"], "lot_type_id": lt[0]["id"], "planned_qty": 1}, key=f"{self.run}:wo")
            wid = wo.body.get("data", wo.body)["id"]
            self.req("POST", f"/mes/work-order/{wid}/transition", {"action": "release"}, key=f"{self.run}:rel")
            st = self.req("POST", f"/mes/work-order/{wid}/start", {"lots": [{"qty": 1}]}, key=f"{self.run}:start")
            lots = st.body if isinstance(st.body, list) else st.body.get("data", [])
            lot = lots[0]["id"]
            mi = self.req("POST", f"/mes/exec/lots/{lot}/move_in", {"equipment_id": ctx["eq"]["id"]}, key=f"{self.run}:mi")
            assert mi.status == 200, f"move_in HTTP {mi.status} {mi.body}"
            p = f"/mes/exec/lots/{lot}/track_in"
            r = self.req("POST", p, {"equipment_id": ctx["eq"]["id"]}, key=f"{self.run}:ti")
            self.rec(e, "POST", p, r)
            assert r.status == 409 and r.code == "check_blocked", f"HTTP {r.status} code={r.code}"
            hit = [x for x in r.check_results if x.get("check_type") == "operator_qualified"]
            assert hit, f"results 里没有 operator_qualified：{r.check_results}"
            x = hit[0]
            assert x.get("result") == "block", f"result={x.get('result')}"
            assert x.get("overridable") is False, f"overridable={x.get('overridable')}"
            cx = x.get("ctx") or (x.get("data") or {}).get("ctx") or {}
            assert cx.get("qual_id") == q, f"ctx.qual_id={cx.get('qual_id')}"
            assert cx.get("expires_on") == d(-1) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(cx.get("expires_on"))), f"ctx.expires_on={cx.get('expires_on')}"
            assert self.det(r).get("overridable") is False
        self.step("过期资质进站 → 409 check_blocked operator_qualified ctx{qual_id,expires_on}", track_in)

        def still_active(e):
            r = c.get(qp)
            row = r.body.get("data", r.body)
            assert row.get("is_active") is True, f"is_active={row.get('is_active')}（过期不应自动停用）"
        self.step("过期不自动停用（GET is_active=true）", still_active)

        # 缺 key
        for m, b in (("POST", {"username": me, "operation_id": op}), ("PATCH", {"certified_on": d(-5)}), ("DELETE", None)):
            p = Q if m == "POST" else qp
            def f(e, m=m, b=b, p=p):
                r = self.req(m, p, b, key=None)
                self.rec(e, m, p, r, b)
                self.err422(r, "missing", ["header", "Idempotency-Key"])
            self.step(f"{m} 缺 key → 422 missing", f)
        self.step("只读账号 403（由 QA 覆盖）", lambda e: e.update(result_override="skip", note="由 QA 覆盖"))

        def chk(name, m, p, b, typ, loc, ctxw=None, status=422, code=None, need_lead=False):
            def f(e):
                r = self.req(m, p, b)
                self.rec(e, m, p, r, b)
                if status == 422:
                    self.err422(r, typ, loc, ctxw)
                else:
                    assert r.status == status, f"HTTP {r.status} 期望 {status}：{r.body}"
                    e["detail_fmt"] = json.dumps(self.det(r), ensure_ascii=False)
            self.step(name, f, need_lead=need_lead)
        mp = f"{Q}/{MISSING}"
        chk("冲突字段（不存在 id）→ 422 conflicting_fields 先于 404", "PATCH", mp,
            {"is_active": False, "expires_on": d(60), "reason_id": R, "comment": "x", "approved_by": self.lead},
            "value_error", ["body", "is_active"], {"reason": "conflicting_fields", "fields": ["is_active", "expires_on"]})
        chk("自批（不存在 id）→ 422 self_approval 先于 404", "PATCH", mp,
            {"expires_on": d(60), "reason_id": R, "comment": "延期", "approved_by": me}, "value_error", ["body", "approved_by"], {"reason": "self_approval"})
        chk("不存在 id 合法延期 → 404", "PATCH", mp,
            {"expires_on": d(60), "reason_id": R, "comment": "延期", "approved_by": self.lead}, None, None, status=404, code="not_found", need_lead=True)
        chk("comment 超 300 → 422 max_length", "PATCH", qp,
            {"expires_on": d(60), "reason_id": R, "comment": "x" * 301, "approved_by": self.lead}, "value_error", ["body", "comment"], {"reason": "max_length"})
        chk("reason_id 非 operator_qual → 422 invalid_reason", "PATCH", qp,
            {"expires_on": d(60), "reason_id": str(uuid.uuid4()), "comment": "延期", "approved_by": self.lead}, "value_error", ["body", "reason_id"], {"reason": "invalid_reason"})
        chk("approved_by 非本租户 → 422 user_not_found", "PATCH", qp,
            {"expires_on": d(60), "reason_id": R, "comment": "延期", "approved_by": "nobody-sim-xyz"}, "value_error", ["body", "approved_by"], {"reason": "user_not_found"})
        for miss in ("reason_id", "comment", "approved_by"):
            b = {"expires_on": d(60), "reason_id": R, "comment": "延期", "approved_by": self.lead}
            b.pop(miss)
            chk(f"延期缺 {miss} → 422 missing", "PATCH", qp, b, "missing", ["body", miss])

        # holder_approval：另一条资质（持有人 = lead），批准人 = 持有人 → 404 之后的 422
        def grant2(e):
            b = {"username": self.lead, "operation_id": op, "equipment_type_id": et, "expires_on": d(10)}
            r = self.req("POST", Q, b)
            self.rec(e, "POST", Q, r, b)
            assert r.status == 200, f"HTTP {r.status} {r.body}"
            ctx["q2"] = r.body.get("data", r.body)["id"]
        self.step("授予第二条（持有人 = lead）", grant2, need_lead=True)
        if "q2" in ctx:
            chk("批准人 = 持有人 → 422 holder_approval", "PATCH", f"{Q}/{ctx['q2']}",
                {"expires_on": d(60), "reason_id": R, "comment": "延期", "approved_by": self.lead}, "value_error", ["body", "approved_by"], {"reason": "holder_approval"}, need_lead=True)

        # 延期 renewed + 回放 + reused
        rk = f"{self.run}:renew"
        rb = {"expires_on": d(60), "reason_id": R, "comment": "复训通过", "approved_by": self.lead}

        def renew(e):
            r = self.req("PATCH", qp, rb, key=rk)
            self.rec(e, "PATCH", qp, r, rb)
            assert r.status == 200, f"HTTP {r.status} {r.body}"
            assert "idempotent-replayed" not in r.headers, "首次执行带了 Idempotent-Replayed"
            ctx["renew"] = r.body
        self.step("延后 → 200，首次无回放头", renew, need_lead=True)
        self.step("履历 renewed（comment/reason_id/approved_by）", lambda e: self.latest(q, "renewed", comment="复训通过", reason_id=R, approved_by=self.lead), need_lead=True)
        self.step("事件 operator_qual.renewed", ev("operator_qual.renewed"), need_lead=True)

        def replay(e):
            r = self.req("PATCH", qp, rb, key=rk)
            self.rec(e, "PATCH", qp, r, rb)
            assert r.status == 200 and r.headers.get("idempotent-replayed") == "true", f"HTTP {r.status} 头={r.headers.get('idempotent-replayed')}"
            assert r.body == ctx.get("renew"), "回放响应体与首次不同"
            n = sum(1 for x in self.hist(q) if x.get("action") == "renewed")
            assert n == 1, f"回放后 renewed 履历 {n} 条"
        self.step("同 key 同体回放 → 原响应 + Idempotent-Replayed: true，履历不增", replay, need_lead=True)

        def reused(e):
            b = {**rb, "comment": "改了"}
            r = self.req("PATCH", qp, b, key=rk)
            self.rec(e, "PATCH", qp, r, b)
            dt = self.det(r)
            assert r.status == 422 and isinstance(dt, dict) and dt.get("code") == "idempotency_key_reused" and "ctx" not in dt and dt.get("message"), f"HTTP {r.status} detail={dt}"
        self.step("同 key 换体 → 422 detail 对象 {code: idempotency_key_reused, message}，无 ctx", reused, need_lead=True)

        def shorten(e):
            b0 = {"expires_on": d(30), "reason_id": R, "comment": "缩短"}
            r0 = self.req("PATCH", qp, b0)
            self.rec(e, "PATCH", qp, r0, b0)
            self.err422(r0, "missing", ["body", "approved_by"])
            b = {**b0, "approved_by": self.lead}
            r = self.req("PATCH", qp, b)
            assert r.status == 200, f"HTTP {r.status} {r.body}"
        self.step("提前（D88）：缺批准人 422 missing；带批准人 200", shorten, need_lead=True)
        self.step("履历 changed（D88）", lambda e: self.latest(q, "changed", comment="缩短", reason_id=R, approved_by=self.lead), need_lead=True)
        self.step("事件 operator_qual.changed", ev("operator_qual.changed"), need_lead=True)

        chk("停用缺 reason_id → 422 missing", "PATCH", qp, {"is_active": False, "comment": "离岗"}, "missing", ["body", "reason_id"])
        chk("停用缺 comment → 422 missing", "PATCH", qp, {"is_active": False, "reason_id": R}, "missing", ["body", "comment"])

        dk, db = f"{self.run}:deact", {"is_active": False, "reason_id": R, "comment": "离岗"}

        def deact(e):
            r = self.req("PATCH", qp, db, key=dk)
            self.rec(e, "PATCH", qp, r, db)
            assert r.status == 200, f"HTTP {r.status} {r.body}"
            assert "idempotent-replayed" not in r.headers, "首次执行带了 Idempotent-Replayed"
            ctx["deact"] = r.body
        self.step("停用 → 200，首次无回放头", deact)

        def dreplay(e):
            r = self.req("PATCH", qp, db, key=dk)
            self.rec(e, "PATCH", qp, r, db)
            assert r.status == 200 and r.headers.get("idempotent-replayed") == "true", f"HTTP {r.status} 头={r.headers.get('idempotent-replayed')}"
            assert r.body == ctx.get("deact"), "回放响应体与首次不同"
            n = sum(1 for x in self.hist(q) if x.get("action") == "deactivated")
            assert n == 1, f"回放后 deactivated 履历 {n} 条"
        self.step("停用同 key 同体回放 → 原响应 + Idempotent-Replayed: true，履历不增", dreplay)

        def dreused(e):
            b = {**db, "comment": "改了"}
            r = self.req("PATCH", qp, b, key=dk)
            self.rec(e, "PATCH", qp, r, b)
            dt = self.det(r)
            assert r.status == 422 and isinstance(dt, dict) and dt.get("code") == "idempotency_key_reused" and "ctx" not in dt and dt.get("message"), f"HTTP {r.status} detail={dt}"
        self.step("停用同 key 换体 → 422 detail 对象 {code: idempotency_key_reused, message}，无 ctx", dreused)
        self.step("履历 deactivated", lambda e: self.latest(q, "deactivated", comment="离岗", reason_id=R, approved_by=None))
        self.step("事件 operator_qual.deactivated", ev("operator_qual.deactivated"))

        def deact_again(e):
            nh, ne = len(self.hist(q)), len(self.events(q))
            r = self.req("PATCH", qp, {**db, "comment": "再停用"})
            self.rec(e, "PATCH", qp, r, db)
            assert r.status == 200, f"HTTP {r.status} {r.body}"
            assert len(self.hist(q)) == nh, "已停用再停用不应写履历"
            assert len(self.events(q)) == ne, "已停用再停用不应发事件"
        self.step("已停用再停用（D88 补充二）→ 200，履历条数不变、无事件", deact_again)

        def ab65(e):
            b = {"expires_on": d(60), "reason_id": R, "comment": "延期", "approved_by": "a" * 65}
            r = self.req("PATCH", qp, b)
            self.rec(e, "PATCH", qp, r, b)
            self.err422(r, "value_error", ["body", "approved_by"], {"reason": "user_not_found"})
        self.step("approved_by 65 字符（D88 补充二）→ 422 user_not_found（无单独 max_length）", ab65)

        def react(e):
            b = {"is_active": True, "reason_id": R, "comment": "返岗"}
            r = self.req("PATCH", qp, b)
            self.rec(e, "PATCH", qp, r, b)
            assert r.status == 200, f"HTTP {r.status} {r.body}"
        self.step("恢复 → 200", react)
        self.step("履历 reactivated", lambda e: self.latest(q, "reactivated", comment="返岗", reason_id=R))
        self.step("恢复不发事件（最新仍 deactivated，无 reactivated）", ev("operator_qual.deactivated", none=("operator_qual.reactivated",)))

        # 删除：恒 409 referenced（顶层 ref_type/ref_count）
        def del409(e, key, target=qp, status=409):
            r = self.req("DELETE", target, None, key=key)
            self.rec(e, "DELETE", target, r)
            assert "idempotent-replayed" not in r.headers, "4xx 不应带回放头"
            if status == 404:
                assert r.status == 404, f"HTTP {r.status} {r.body}"
                e["detail_fmt"] = json.dumps(self.det(r), ensure_ascii=False)
                return
            dt = self.det(r)
            assert r.status == 409 and r.code == "referenced", f"HTTP {r.status} {r.body}"
            assert dt.get("ref_type") == "operator_qual_log", f"ref_type={dt.get('ref_type')}"
            assert isinstance(dt.get("ref_count"), int) and dt["ref_count"] >= 1, f"ref_count={dt.get('ref_count')}"
            assert "tables" not in dt, "不应带 tables[]"
        x0, x1 = f"{self.run}:x0", f"{self.run}:x1"
        self.step("删除不存在 → 404", lambda e: del409(e, x0, mp, 404))
        self.step("删除 → 409 referenced 顶层 ref_type/ref_count", lambda e: del409(e, x1))
        self.step("同 key 同目标重发 → 仍 409，无回放头（4xx 不缓存）", lambda e: del409(e, x1))
        self.step("同 key 换不存在目标 → 404（不是 reused）", lambda e: del409(e, x1, mp, 404))
        self.step("404 用过的 key 换到存在目标 → 409", lambda e: del409(e, x0))
        self.step("删除不改数据（GET is_active=true）", still_active)

        def overview(e, z):
            h = self.hist(q)
            acts = [x.get("action") for x in h]
            e["actions"] = acts
            want = ["reactivated", "deactivated", "changed", "renewed", "granted"] if lead_ok else ["reactivated", "deactivated", "granted"]
            assert acts == want, f"履历 {acts} 期望 {want}"
            for x in h:
                if z:
                    assert str(x.get("at", "")).endswith("Z"), f"at 不带 Z：{x.get('at')}"
                for k in ("comment", "reason_id", "approved_by"):
                    assert k in x
        self.step("履历总览：倒序、三列齐全", lambda e: overview(e, False))
        self.step("履历 at 为 UTC 带 Z（D88-3）", lambda e: overview(e, True), xfail="D88-3 小提交未落地")

        def expiring(e):
            r = c.get("/mes/exec/operator-qual/expiring", days=0)
            self.err422(r, "value_error", ["query", "days"], {"min": 1, "max": 365})
            r = c.get("/mes/exec/operator-qual/expiring", days=365)
            assert r.status == 200, f"HTTP {r.status}"
            r = c.get(f"/mes/exec/operator-qual/{q}/history", limit=201)
            assert r.status == 422, f"limit=201 HTTP {r.status}"
            r = c.get(f"/mes/exec/operator-qual/{MISSING}/history")
            assert r.status == 404, f"不存在资质履历 HTTP {r.status}"
        self.step("expiring days 越界 422 ctx{min,max}；history limit>200 422；不存在 404", expiring)

        def meta(e):
            m = c.get("/mes/_meta").body
            ent = [x for x in m.get("entities", []) if x.get("code") == "operator_qual"]
            assert ent and ent[0].get("warn_days") == 30, f"_meta warn_days={ent and ent[0].get('warn_days')}"
        self.step("/mes/_meta operator_qual.warn_days = 30（无 qual_expiry_notice 规则时默认）", meta)

        for s in self.steps:
            if s.pop("result_override", None):
                s["result"] = "skip"
        return self.steps
