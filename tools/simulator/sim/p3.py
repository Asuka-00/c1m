"""P3 打标 / 光罩步骤执行器（P3-E2：marking-report.yaml、reticle-report.yaml）。

接口路径与字段按 eap/p3 的 p3-e2-marking-prereview.md、p3-e2-reticle-prereview.md 与 decisions D78–D82：

- 光罩手工写接口 ``POST /mes/reticle/{rid}/<动作>``（D80 补充一/二共 14 个），都带 ``Idempotency-Key``
  （步骤写 ``idem``；``no_idem: true`` 时不带，测 422 missing）。
- 打标 ``POST /mes/marking``（建主记录）、``/{id}/prints``、``/{id}/inspect``、``/{id}/void``，
  ``GET /mes/marking/config``。
- EAP 上报（``reticle_report`` / ``marking_report``）走 ``POST /mes/eap/events`` 信封，event_type 为
  ``reticle_mount|reticle_unmount|reticle_usage`` / ``marking``（G4：P3 不开，后端没有这个 event_type 时记「未实现」）。

接口还不存在（openapi 里没有、或 404 ``{"detail": "Not Found"}`` 路由不存在、405）时抛 :class:`Unimplemented`，
runner 记该步「未实现」，不算失败。

取值（参数与 expect 里的字符串）：
``$now±N[smh]`` 相对时间（sim.reticle.resolve_relative）；``$名.字段`` save_as 记下的数据；``$ext.名`` 该步的
external_event_id；``$cfg.字段``；``$issued`` / ``$issued.批次`` 系统发号；``$marking.批次|名`` 主记录 id；
``$print_seq_N[.字段]`` 当前批次第 N 次打印；``$reason.编码``、``$eq.编码``、``$lot.编码`` 主数据 id。
匹配器：``$nonempty``（非空）、``$utc_z``（UTC 带 Z 的时间串）。
"""

from __future__ import annotations

import copy
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sim.adapters import Call, fill
from sim.client import Resp
from sim.ids import event_id
from sim.marking import pattern_allowed
from sim.reticle import resolve_relative

if TYPE_CHECKING:  # pragma: no cover
    from sim.runner import Runner


class Unimplemented(Exception):
    """后端还没有这个接口：报「未实现」，不算失败。"""


UTC_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")

# 光罩手工写步骤 -> (适配器, 请求体构造)
RETICLE_REASON = {"reticle_hold", "reticle_restore", "reticle_life_reset", "reticle_scrap"}
RETICLE_COMMENT = {
    "reticle_release",
    "reticle_clean_start",
    "reticle_clean_complete",
    "reticle_repair_complete",
    "reticle_inspect_start",
}
RETICLE_WRITE = (
    RETICLE_REASON
    | RETICLE_COMMENT
    | {"reticle_mount", "reticle_unmount", "reticle_adjust", "reticle_incident", "reticle_inspection"}
)
RETICLE_ADAPTER = {k: k for k in RETICLE_WRITE} | {"reticle_adjust": "reticle_usage_manual"}

MARKING_STEPS = {
    "marking_create",
    "marking_print",
    "marking_inspect",
    "marking_void",
    "marking_config",
    "marking_report",
    "marking_replay",
    "marking_template_ready",
    "marking_template",
    "lot_scrap",
    "expect_marking",
    "expect_marking_prints",
    "expect_marking_inspections",
    "expect_marking_events",
    "expect_marking_list",
    "expect_marking_trace",
    "pack_lot",
    "label_print",
}
RETICLE_STEPS = RETICLE_WRITE | {
    "reticle_report",
    "reticle_replay",
    "expect_reticle",
    "expect_reticle_history",
    "expect_reticle_events",
}
P3_EXEC_STEPS = MARKING_STEPS | RETICLE_STEPS


TEMPLATE_ROUTE = {
    "create": ("POST", "marking_template"),
    "update": ("PATCH", "marking_template_item"),
    "new_version": ("POST", "marking_template_version"),
    "approve": ("POST", "marking_template_approve"),
    "preview": ("POST", "marking_template_preview"),
    "get": ("GET", "marking_template_item"),
    "validate": ("POST", "marking_template_validate"),
}


def template_call(a: dict, resolve: Any, path: Any, idem: Any) -> Call:
    """组模板请求：写接口带 ``{run_id}:{idem}``（no_idem 测缺失），只读 POST 一律不带 key。"""
    from sim.scenario import TEMPLATE_WRITE

    method, adapter = TEMPLATE_ROUTE[a["action"]]
    # 附注二：预览 / 校验路径不带 {id}，template_id 或 lines 放请求体
    tid = resolve(a["template"]) if a.get("template") and a["action"] not in ("preview", "validate") else ""
    body = None if a["action"] == "get" else resolve(a.get("body") or {})
    key = idem(a) if a["action"] in TEMPLATE_WRITE else None
    return Call(method, path(adapter, id=str(tid)), body, key)


def check_results(resp: Resp, want: list[dict]) -> list[str]:
    """D79 补充七（04:28 更正）：check_blocked 的 results[] 每项含 check_type、result、ctx（沿用现有字段名）；
    按 check_type 找项，字段按子集匹配。"""
    d = detail(resp)
    rows = d.get("results") if isinstance(d, dict) else None
    if not isinstance(rows, list):
        return [f"detail.results 不是列表：{rows!r}"[:200]]
    errs = []
    for r in rows:
        miss = [k for k in ("check_type", "result", "ctx") if not isinstance(r, dict) or k not in r]
        if miss:
            errs.append(f"results 项缺 {miss}：{r!r}"[:200])
    for w in want:
        hit = [r for r in rows if isinstance(r, dict) and r.get("check_type") == w.get("check_type")]
        if not hit:
            errs.append(f"results 里没有 check_type={w.get('check_type')!r}")
            continue
        ctx = hit[0].get("ctx") if isinstance(hit[0].get("ctx"), dict) else {}
        for k in w.get("absent_ctx") or []:
            if k in ctx:
                errs.append(f"results[{w['check_type']}].ctx 不应带 {k}")
        body = {k: v for k, v in w.items() if k != "absent_ctx"}
        if not match(hit[0], body):
            errs.append(f"results[{w['check_type']}] {hit[0]!r} != 期望 {body!r}"[:300])
    return errs


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- 匹配
def match(got: Any, want: Any) -> bool:
    """期望值匹配：映射按子集、列表逐项（长度相同），``$nonempty`` / ``$utc_z`` 匹配器，数值按 Decimal。"""
    from sim.runner import same

    if want == "$nonempty":
        return got not in (None, "", [], {})
    if want == "$utc_z":
        return isinstance(got, str) and UTC_Z.match(got) is not None
    if isinstance(want, dict):
        return isinstance(got, dict) and all(match(dig(got, k), v) for k, v in want.items())
    if isinstance(want, list):
        if not isinstance(got, list) or len(got) != len(want):
            return False
        return all(match(g, w) for g, w in zip(got, want, strict=True))
    return same(got, want)


def dig(obj: Any, path: str) -> Any:
    """点号路径取值；键本身含点时（如 ``lot.marked``）先整键取。缺失返回 None。"""
    if isinstance(obj, dict) and path in obj:
        return obj[path]
    cur = obj
    for part in str(path).split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):  # 列表下标（data.versions.0.status）
            cur = cur[int(part)]
        else:
            return None
    return cur


def has_key(obj: Any, path: str) -> bool:
    cur = obj
    for part in str(path).split("."):
        if not isinstance(cur, dict) or part not in cur:
            return False
        cur = cur[part]
    return True


def detail(resp: Resp) -> Any:
    return resp.body.get("detail") if isinstance(resp.body, dict) else None


def resp_ctx(resp: Resp) -> dict:
    d = detail(resp)
    if isinstance(d, dict):
        c = d.get("ctx")
        return c if isinstance(c, dict) else {}
    if isinstance(d, list) and d and isinstance(d[0], dict) and isinstance(d[0].get("ctx"), dict):
        return d[0]["ctx"]
    return {}


def check_p3_expect(resp: Resp, expect: dict | None) -> list[str]:
    """在 runner.check_expect 之上补 P3 用到的断言：ctx、absent_ctx、overridable、errors（逐条）、absent、
    匹配器形式的 body。"""
    expect = expect or {}
    errs: list[str] = []
    if "ctx" in expect:
        c = resp_ctx(resp)
        for k, v in expect["ctx"].items():
            if not match(c.get(k), v):
                errs.append(f"ctx.{k} {c.get(k)!r} != 期望 {v!r}")
    for k in expect.get("absent_ctx") or []:
        if k in resp_ctx(resp):
            errs.append(f"ctx 不应带 {k}（实际 {resp_ctx(resp).get(k)!r}）")
    if "overridable" in expect:
        d = detail(resp)
        got = None
        if isinstance(d, dict):
            got = d.get("overridable", resp_ctx(resp).get("overridable"))
            if got is None:  # check_blocked 的 results[]
                hits = [r for r in (d.get("results") or []) if isinstance(r, dict) and "overridable" in r]
                got = hits[0]["overridable"] if hits else None
        if got != expect["overridable"]:
            errs.append(f"overridable {got!r} != 期望 {expect['overridable']!r}")
    if "errors" in expect:
        got = resp.errors
        want = expect["errors"]
        if not resp.detail_is_list:
            errs.append(f"detail 不是列表：{detail(resp)!r}"[:200])
        elif len(got) != len(want) or not all(match(g, w) for g, w in zip(got, want, strict=True)):
            slim = [{k: g.get(k) for k in ("type", "loc", "ctx")} for g in got]
            errs.append(f"errors {slim!r} != 期望 {want!r}"[:400])
    if "results" in expect:
        errs += check_results(resp, expect["results"])
    # D86 补充二：replayed true → 头 Idempotent-Replayed: true；false → 不带该头（首次执行 / 4xx 重发）
    if "replayed" in expect:
        rep = (resp.headers or {}).get("idempotent-replayed")
        if expect["replayed"] is True and rep != "true":
            errs.append(f"应带 Idempotent-Replayed: true，实际 {rep!r}")
        if expect["replayed"] is False and rep is not None:
            errs.append(f"不应带 Idempotent-Replayed，实际 {rep!r}")
    for k in expect.get("absent") or []:
        b = resp.body if isinstance(resp.body, dict) else {}
        if has_key(b, k) or has_key(b.get("data"), k):
            errs.append(f"响应不应带 {k}")
    return errs


INACTIVE_UNIT = ("scrapped", "converted")


def active_units(unit_rows: list[dict]) -> list[dict]:
    """在批、未报废 / 未转换的片，按 slot、code 排序（同后端 lots.units）。"""
    act = [u for u in unit_rows if (u.get("wafer_status") or u.get("status")) not in INACTIVE_UNIT]
    return sorted(act, key=lambda u: (u.get("slot") or 0, str(u.get("code") or "")))


def scrap_body(lot: dict, unit_rows: list[dict], a: dict, reason_id: str | None, comment: str) -> dict:
    """组 adjust kind=scrap 的请求体：晶圆 / 单元级带 unit_ids，数量级带 qty。"""
    body: dict[str, Any] = {"kind": "scrap", "reason_id": reason_id, "comment": comment}
    if a.get("override"):  # qty_adjust_limit 等可放行卡控（409 check_blocked, overridable）
        body.update(override=True, override_reason=a.get("override_reason") or comment)
    if (lot.get("tracking_level") or "wafer") == "quantity":
        qty = a.get("qty", lot.get("qty"))
        body["qty"] = int(Decimal(str(qty))) if qty is not None else None
        return body
    act = active_units(unit_rows)
    want = a.get("units", "all")
    if want == "all" or want is None:
        picked = act
    elif isinstance(want, int):
        picked = act[:want]
    else:
        codes = [str(x) for x in want]
        by_code = {str(u.get("code")): u for u in act}
        picked = [by_code[c] for c in codes if c in by_code]
    body["unit_ids"] = [u["id"] for u in picked]
    return body


def route_missing(resp: Resp) -> bool:
    """FastAPI 路由不存在：404 {"detail": "Not Found"}；或 405。业务 404（带 code 的对象）不算。"""
    if resp.status == 405:
        return True
    return resp.status == 404 and isinstance(resp.body, dict) and resp.body.get("detail") == "Not Found"


def event_type_rejected(resp: Resp) -> bool:
    """B11 入口不认识 event_type（P3 不开光罩/打标事件，G4）。"""
    if resp.status != 422:
        return False
    for e in resp.errors:
        loc = e.get("loc") or []
        if isinstance(loc, list) and "event_type" in loc:
            return True
    return False


# ---------------------------------------------------------------- 执行器
class P3Exec:
    """挂在 Runner 上，一个场景一个实例（状态：save_as、发号、主记录 id 等）。"""

    def __init__(self, runner: Runner, run_id: str) -> None:
        self.r = runner
        self.run_id = run_id
        self.saved: dict[str, Any] = {}  # save_as -> data（映射）
        self.calls: dict[str, tuple[Call, str]] = {}  # save_as -> (请求, 步骤类型)
        self.ext: dict[str, str] = {}  # save_as -> external_event_id
        self.cfg: dict[str, Any] = {}
        self.issued: dict[str, str] = {}  # 批次 -> 系统发号 trace_code
        self.marking: dict[str, str] = {}  # 批次 / save_as -> 主记录 id（批次键始终指向最新未作废那条）
        self.unimpl: set[str] = set()  # 未实现步骤的 save_as
        self.lot: str | None = None  # 当前步骤的批次（$issued、$print_seq_N 用）
        self.ghost: dict[str, str] = {}  # 不存在编码（*NOT-EXIST*）-> 随机 uuid

    # ---- 编码 -> id
    def id_of(self, entity: str, code: str) -> str:
        if "NOT-EXIST" in str(code):
            return self.ghost.setdefault(code, str(uuid.uuid4()))
        return self.r.rid(entity, code)

    def path(self, adapter: str, **kw: str) -> str:
        ad = self.r.adapters[adapter]
        p = ad.path or ad.resolve(self.r.paths)
        if not p:
            raise Unimplemented(ad.skip_reason())
        # 通用 CRUD 兜底（/mes/{entity}/{rid}、/mes/{entity}）：详情按 reticle / marking，事件按 audit_log
        ent = {"reticle_get": "reticle", "marking_get": "marking"}.get(adapter, "audit_log")
        rid = kw.get("reticle_id") or kw.get("marking_id") or ""
        return fill(p, **{"entity": ent, "rid": rid, **kw})

    # ---- 取值
    def resolve(self, v: Any) -> Any:
        if isinstance(v, dict):
            return {k: self.resolve(x) for k, x in v.items()}
        if isinstance(v, list):
            return [self.resolve(x) for x in v]
        if not isinstance(v, str) or not v.startswith("$") or v in ("$nonempty", "$utc_z"):
            return v
        if v.startswith("$now"):
            out = resolve_relative(v, now_utc())
            if out == v and v == "$now":
                out = resolve_relative("$now+0s", now_utc())
            return out
        if v == "$missing_uuid":  # 不存在的 id（测 404 及 D81 里排在 404 前的 422）
            return "00000000-0000-0000-0000-00000000dead"
        name, _, rest = v[1:].partition(".")
        if name == "ext":
            return self._need(self.ext, rest, v)
        if name == "cfg":
            return self._need(self.cfg, rest, v)
        if name == "issued":
            return self._need(self.issued, rest or (self.lot or ""), v)
        if name == "marking":
            return self._need(self.marking, rest, v)
        if name in ("reason", "eq", "lot", "product", "customer"):
            ent = {"reason": "reason_code", "eq": "equipment", "lot": "lot"}.get(name, name)
            return self.id_of(ent, rest)
        m = re.fullmatch(r"print_seq_(\d+)", name)
        if m:
            row = self._print_row(int(m.group(1)))
            return row.get(rest) if rest else row.get("id")
        if name in self.saved:
            d = self.saved[name]
            return dig(d, rest) if rest else (d.get("id") if isinstance(d, dict) else d)
        if name in self.unimpl:
            raise Unimplemented(f"{v} 来自未实现的步骤")
        return v  # 不认识的 $ 串原样（例如 P2 写法），交给后端

    def b2_missing(self) -> bool:
        """后端还没有打标接口（P3-B2）：依赖打标数据的取值和断言一律记未实现。"""
        ad = self.r.adapters["marking_create"]
        return not (ad.path or ad.resolve(self.r.paths))

    def _need(self, table: dict, key: str, v: str) -> Any:
        if key in table:
            return table[key]
        if key in self.unimpl or (table is not self.ext and table is not self.cfg and self.b2_missing()):
            raise Unimplemented(f"{v} 依赖打标接口（P3-B2 未实现）")
        if table is self.cfg and self.b2_missing():
            raise Unimplemented(f"{v} 来自未实现的步骤")
        from sim.runner import StepFailed

        raise StepFailed(f"取不到 {v}（前面没有记下）")

    def _print_row(self, seq: int) -> dict:
        from sim.runner import StepFailed

        mid = self._mid(self.lot)
        r = self.r.c.get(self.path("marking_prints", marking_id=mid), page_size=200)
        rows = self._rows(r)
        hit = [x for x in rows if x.get("seq") == seq]
        if not hit:
            raise StepFailed(f"批次 {self.lot} 没有 seq={seq} 的打印")
        return hit[0]

    def _mid(self, ref: str | None) -> str:
        if ref is None:
            from sim.runner import StepFailed

            raise StepFailed("缺少批次")
        if ref in self.marking:
            return self.marking[ref]
        if "NOT-EXIST" in ref:
            return self.id_of("marking", ref)
        if ref in self.unimpl:
            raise Unimplemented(f"主记录 {ref} 来自未实现的步骤")
        # 场景之外已有的主记录：按批次查未作废那条
        r = self.r.c.get(self.path("marking_list", marking_id=""), lot_id=self.id_of("lot", ref), page_size=50)
        rows = [x for x in self._rows(r) if not x.get("voided")]
        if not rows:
            from sim.runner import StepFailed

            raise StepFailed(f"批次 {ref} 没有主记录")
        self.marking[ref] = rows[0]["id"]
        return self.marking[ref]

    @staticmethod
    def _rows(r: Resp) -> list[dict]:
        if route_missing(r):
            raise Unimplemented(f"GET 接口不存在（HTTP {r.status}）")
        b = r.body
        rows = b.get("data", b) if isinstance(b, dict) else b
        return [x for x in rows if isinstance(x, dict)] if isinstance(rows, list) else []

    # ---- 发送
    def send(
        self, entry: dict, call: Call, expect: dict | None, kind: str, save_as: str | None = None, flat: bool = False
    ) -> Resp:
        from sim.runner import StepFailed, check_expect, nonlist_422, shape_422

        expect = self.resolve(expect or {})  # 先解析，取不到就不发请求
        cli = self.r.cli(call)
        hdr = {"Idempotency-Key": call.idem} if call.idem else None
        r = cli.request(call.method, call.path, call.body, headers=hdr)
        from sim.safety import redact

        entry.update(method=call.method, path=call.path, request=redact(call.body), status=r.status, code=r.code)
        if call.idem:
            entry["idempotency_key"] = call.idem
        b11_off = self.r.is_b11(call) and (event_type_rejected(r) or (r.status == 403 and self.r.svc is None))
        if route_missing(r) or b11_off:
            if save_as:
                self.unimpl.add(save_as)
            raise Unimplemented(f"{call.method} {call.path} 后端未实现（HTTP {r.status}）")
        view = self.r.view(call, r)
        if flat and isinstance(view.body, dict) and isinstance(view.body.get("data"), dict):
            # config 响应：{data: {...}} 与平铺两种都认，body 断言按平铺后的字段
            view = Resp(view.status, {**view.body["data"], **view.body}, view.elapsed_ms)
        errs = check_expect(view, expect) + check_p3_expect(view, expect)
        if self.r.strict_422:
            errs += shape_422(r)
        if nonlist_422(r):
            entry["warn_422"] = nonlist_422(r)
        if save_as:
            self.calls[save_as] = (call, kind)
            d = view.body.get("data", view.body) if isinstance(view.body, dict) else None
            self.saved[save_as] = d if isinstance(d, dict) else {}
        if errs:
            from sim.safety import redact_detail

            # 失败时把完整 detail（loc/type/msg/ctx…）记进报告，凭据类键遮掉
            entry["response_detail"] = redact_detail(detail(r))
            raise StepFailed("；".join(errs))
        return r

    # ---- 入口
    def step(self, kind: str, a: dict, entry: dict) -> None:
        a = dict(a)
        self.lot = a.get("lot") or self.lot
        # needs: [save_as, ...]：依赖的步骤未实现（如 EAP 光罩 event_type D67 未开）时本步也记未实现，不算失败
        need = a.pop("needs", None) or []
        miss = [n for n in ([need] if isinstance(need, str) else need) if n in self.unimpl]
        if miss:
            raise Unimplemented(f"依赖未实现的步骤 {', '.join(miss)}")
        handler = getattr(self, "_" + kind, None)
        if handler is None:  # pragma: no cover
            raise Unimplemented(f"{kind} 没有执行器")
        handler(a, entry)

    # ================================================= 光罩
    def _reticle_write(self, kind: str, a: dict, entry: dict) -> None:
        rid = self.id_of("reticle", a["reticle"])
        body: dict[str, Any] = {}
        if kind == "reticle_mount":
            body["equipment_id"] = self.id_of("equipment", a["eq"])
            if a.get("slot") is not None:
                body["slot_code"] = a["slot"]
            if "mounted_at" in a:
                body["mounted_at"] = self.resolve(a["mounted_at"])
        elif kind == "reticle_unmount":
            if "unmounted_at" in a:
                body["unmounted_at"] = self.resolve(a["unmounted_at"])
        elif kind == "reticle_adjust":
            body["delta"] = str(a["delta"])
            if a.get("reason"):
                body["reason_id"] = self.id_of("reason_code", a["reason"])
        elif kind == "reticle_incident":
            body["kind"] = a.get("kind", "other")
            if a.get("eq"):
                body["equipment_id"] = self.id_of("equipment", a["eq"])
            if "occurred_at" in a:
                body["occurred_at"] = self.resolve(a["occurred_at"])
        elif kind == "reticle_inspection":
            body.update(kind=a.get("kind", "other"), result=a.get("result", "pass"))
        elif kind in RETICLE_REASON:
            body["reason"] = str(a.get("reason") or "sim")
        if a.get("comment") is not None:
            body["comment"] = a["comment"]
        body.update(self.resolve(a.get("extra") or {}))
        action = kind.removeprefix("reticle_")
        idem = None if a.get("no_idem") else f"{self.run_id}:{a['idem']}"
        call = Call("POST", self.path(RETICLE_ADAPTER[kind], reticle_id=rid), body, idem)
        entry["reticle"] = a["reticle"]
        entry["action"] = action
        self.send(entry, call, a.get("expect"), kind, a.get("save_as"))

    def __getattr__(self, name: str) -> Any:
        k = name[1:]
        if name.startswith("_reticle_") and k in RETICLE_WRITE:
            return lambda a, entry: self._reticle_write(k, a, entry)
        raise AttributeError(name)

    def _envelope(self, a: dict, event_type: str, payload: dict) -> Call:
        eq_id = self.id_of("equipment", a["eq"])
        ext = event_id(self.run_id, a["eq"], int(a["seq"]))
        body = {
            "source": "simulator",
            "external_event_id": ext,
            "event_type": event_type,
            "equipment_id": eq_id,
            "payload": payload,
        }
        body.update(self.resolve(a.get("extra") or {}))
        if a.get("save_as"):
            self.ext[a["save_as"]] = ext
        return Call("POST", self.path("eap_events"), body, None)

    def _reticle_report(self, a: dict, entry: dict) -> None:
        payload = {"reticle_id": self.id_of("reticle", a["reticle"]), **self.resolve(a.get("payload") or {})}
        call = self._envelope(a, f"reticle_{a['kind']}", payload)
        entry.update(external_event_id=call.body["external_event_id"], reticle=a["reticle"])
        self.send(entry, call, a.get("expect"), "reticle_report", a.get("save_as"))

    def _replay(self, a: dict, entry: dict, kind: str) -> None:
        of = a["of"]
        if of in self.unimpl or of not in self.calls:
            raise Unimplemented(f"{kind} 引用的 {of} 未实现或未发送")
        call, _ = self.calls[of]
        call = copy.deepcopy(call)
        if a.get("change"):
            target = call.body["payload"] if self.r.is_b11(call) else call.body
            target.update(self.resolve(a["change"]))
        self.send(entry, call, a.get("expect"), kind)

    def _reticle_replay(self, a: dict, entry: dict) -> None:
        self._replay(a, entry, "reticle_replay")

    def _marking_replay(self, a: dict, entry: dict) -> None:
        self._replay(a, entry, "marking_replay")

    def _get(self, path: str, **params: Any) -> Resp:
        r = self.r.c.get(path, **params)
        if route_missing(r):
            raise Unimplemented(f"GET {path} 后端未实现")
        return r

    def _fail_if(self, errs: list[str]) -> None:
        if errs:
            from sim.runner import StepFailed

            raise StepFailed("；".join(errs))

    def _fields(self, row: Any, fields: dict, label: str) -> list[str]:
        out = []
        for k, v in self.resolve(fields or {}).items():
            got = dig(row, k)
            if not match(got, v):
                out.append(f"{label}.{k} {got!r} != 期望 {v!r}")
        return out

    def _expect_reticle(self, a: dict, entry: dict) -> None:
        rid = self.id_of("reticle", a["reticle"])
        r = self._get(self.path("reticle_get", reticle_id=rid))
        row = r.body.get("data", r.body) if isinstance(r.body, dict) else {}
        entry["status"] = r.status
        self._fail_if(([f"HTTP {r.status}"] if r.status != 200 else []) + self._fields(row, a.get("fields"), "reticle"))

    def _expect_reticle_history(self, a: dict, entry: dict) -> None:
        rid = self.id_of("reticle", a["reticle"])
        r = self._get(self.path("reticle_history", reticle_id=rid), page_size=200)
        rows = self._rows(r)  # 后端按时间倒序
        errs: list[str] = []
        for typ, n in (a.get("count_of") or {}).items():
            got = sum(1 for x in rows if x.get("type") == typ)
            if got != int(n):
                errs.append(f"履历 {typ} {got} 条 != 期望 {n}")
        if a.get("latest_of"):
            hit = [x for x in rows if x.get("type") == a["latest_of"]]
            if not hit:
                errs.append(f"履历里没有 {a['latest_of']}")
            else:
                errs += self._fields(hit[0], a.get("fields"), a["latest_of"])
                if a.get("save_as"):
                    self.saved[a["save_as"]] = hit[0]
        self._fail_if(errs)

    def _events(self, entity_type: str, record_id: str) -> list[dict]:
        # audit_log page_size 上限 100（超过 422 会被当成空列表，f9e9dda 联调发现）
        r = self._get(self.path("reticle_events"), entity_type=entity_type, record_id=record_id, page_size=100)
        if r.status != 200:
            self._fail_if([f"GET 事件列表 HTTP {r.status}：{str(r.body)[:200]}"])
        rows = self._rows(r)
        out = []
        for x in rows:
            ch = x.get("changes") if isinstance(x.get("changes"), dict) else {}
            pl = ch.get("payload", ch)
            if isinstance(pl, list) and len(pl) == 2:  # audit changes 是 [旧, 新]，取新值
                pl = pl[1]
            out.append({**x, "event": x.get("action"), "payload": pl if isinstance(pl, dict) else {}})
        out.sort(key=lambda x: str(x.get("created_at") or x.get("at") or ""), reverse=True)
        return out

    def _check_events(self, rows: list[dict], a: dict, after_ts: str | None = None) -> list[str]:
        errs: list[str] = []
        if after_ts:
            rows = [x for x in rows if str(x.get("created_at") or "") > after_ts]
        for ev, n in (a.get("count") or {}).items():
            got = sum(1 for x in rows if x["event"] == ev)
            if got != int(n):
                errs.append(f"事件 {ev} {got} 条 != 期望 {n}")
        if a.get("latest"):
            want = dict(a["latest"])
            ev = want.pop("event", None)
            hit = [x for x in rows if ev is None or x["event"] == ev]
            errs += [f"没有事件 {ev}"] if not hit else self._fields(hit[0], want, f"事件 {ev}")
        for ev, want in (a.get("latest_of") or {}).items():
            hit = [x for x in rows if x["event"] == ev]
            errs += [f"没有事件 {ev}"] if not hit else self._fields(hit[0], want, f"事件 {ev}")
        for ev, keys in (a.get("payload_absent") or {}).items():
            hit = [x for x in rows if x["event"] == ev]
            if hit:
                errs += [f"事件 {ev} payload 不应带 {k}" for k in keys if has_key(hit[0]["payload"], k)]
        if a.get("audit_has") and not any(x["event"] == a["audit_has"] for x in rows):
            errs.append(f"audit 里没有 {a['audit_has']}")
        for ev, n in (a.get("audit_count") or {}).items():
            got = sum(1 for x in rows if x["event"] == ev)
            if got != int(n):
                errs.append(f"audit {ev} {got} 条 != 期望 {n}")
        return errs

    def _absent_after(self, rows: list[dict], a: dict, pivot_ts: str | None) -> list[str]:
        if pivot_ts is None:
            return []
        later = [x for x in rows if str(x.get("created_at") or "") > pivot_ts and x["event"] in (a.get("events") or [])]
        return [f"{pivot_ts} 之后不应有 {[x['event'] for x in later]}"] if later else []

    def _expect_reticle_events(self, a: dict, entry: dict) -> None:
        rows = self._events("reticle", self.id_of("reticle", a["reticle"]))
        errs = self._check_events(rows, a)
        if a.get("absent_after"):
            ev = a["absent_after"].get("event")
            piv = [x for x in rows if x["event"] == ev]
            errs += [f"没有事件 {ev}"] if not piv else self._absent_after(rows, a, str(piv[0].get("created_at")))
        self._fail_if(errs)

    # ================================================= 打标
    def _marking_config(self, a: dict, entry: dict) -> None:
        p = self.path("marking_config")
        if a.get("set"):
            idem = None if a.get("no_idem") else (f"{self.run_id}:{a['idem']}" if a.get("idem") else None)
            call = Call("PATCH", p, self.resolve(a["set"]), idem)
        else:
            call = Call("GET", p)
        r = self.send(entry, call, a.get("expect"), "marking_config", a.get("save_as"), flat=True)
        d = r.body.get("data", r.body) if isinstance(r.body, dict) else {}
        if call.method == "GET" and r.status == 200 and isinstance(d, dict):
            if a.get("save_as") == "cfg" or not self.cfg:
                self.cfg = dict(d)
            if a.get("pattern_allowed") is not None:
                ok = pattern_allowed(d.get("trace_code_pattern"))
                self._fail_if(
                    []
                    if ok == a["pattern_allowed"]
                    else [f"config pattern {d.get('trace_code_pattern')!r} 白名单判断 {ok} != {a['pattern_allowed']}"]
                )

    def _idem(self, a: dict, suffix: str = "") -> str | None:
        return None if a.get("no_idem") else f"{self.run_id}:{a.get('idem') or 'x'}{suffix}"

    def _marking_create(self, a: dict, entry: dict) -> None:
        body = {"lot_id": self.id_of("lot", a["lot"]), **self.resolve(a.get("extra") or {})}
        call = Call("POST", self.path("marking_create"), body, self._idem(a))
        save = a.get("save_as") or f"#create:{a['lot']}:{entry.get('step')}"
        r = self.send(entry, call, a.get("expect"), "marking_create", save)
        d = r.body.get("data") if isinstance(r.body, dict) else None
        if r.status in (200, 201) and isinstance(d, dict) and d.get("id"):
            self.marking[a["lot"]] = d["id"]
            if a.get("save_as"):
                self.marking[a["save_as"]] = d["id"]
            if d.get("trace_code"):
                self.issued[a["lot"]] = d["trace_code"]

    def _body_from(self, a: dict, keys: dict[str, str]) -> dict:
        body: dict[str, Any] = {}
        for src, dst in keys.items():
            if src in a:
                body[dst] = self.resolve(a[src])
        if "reason" in a:
            body["reason_id"] = self.id_of("reason_code", a["reason"])
        body.update(self.resolve(a.get("extra") or {}))
        for k in a.get("omit") or []:
            body.pop(k, None)
        return body

    def _marking_print(self, a: dict, entry: dict) -> None:
        mid = self._mid(a["lot"])
        body = self._body_from(a, {"trace_code": "trace_code", "comment": "comment"})
        if a.get("eq"):
            body["equipment_id"] = self.id_of("equipment", a["eq"])
        call = Call("POST", self.path("marking_print", marking_id=mid), body, self._idem(a))
        self._as(a, entry, call, "marking_print")

    def _as(self, a: dict, entry: dict, call: Call, kind: str, flat: bool = False) -> None:
        """``as: <角色>``：用 SIM_AS_<角色>_TOKEN（或 _USER/_PASSWORD）账号发；没配时该步记 skip。"""
        role = a.get("as")
        if role:
            cli = self.r.role_client(role)
            if cli is None:
                entry.update(ok=None, message=f"没有 SIM_AS_{role.upper()}_* 账号，跳过权限断言")
                return
            saved_c, self.r.c = self.r.c, cli
            try:
                self.send(entry, call, a.get("expect"), kind, a.get("save_as"), flat=flat)
            finally:
                self.r.c = saved_c
            entry["account"] = role
            return
        self.send(entry, call, a.get("expect"), kind, a.get("save_as"), flat=flat)

    def _marking_inspect(self, a: dict, entry: dict) -> None:
        mid = self._mid(a["lot"])
        body = self._body_from(a, {"result": "result", "read_code": "read_code", "comment": "comment"})
        call = Call("POST", self.path("marking_inspect", marking_id=mid), body, self._idem(a))
        self.send(entry, call, a.get("expect"), "marking_inspect", a.get("save_as"))

    # ---- P3-B3 草稿：出货标签与打标一致（P2-B2 /mes/pack、/mes/label/{pack_id}/print）
    def _pack_lot(self, a: dict, entry: dict) -> None:
        """建包装并装入批次：POST /mes/pack（code）→ POST /mes/pack/{id}/pack（lot_id）。"""
        call = Call("POST", self.path("pack_create"), {"code": a["pack"], **self.resolve(a.get("extra") or {})}, self._idem(a))
        r = self.send(entry, call, None, "pack_lot")
        d = (r.body or {}).get("data", r.body) if isinstance(r.body, dict) else {}
        pid = d.get("id") if isinstance(d, dict) else None
        if not pid:
            self._fail_if([f"建包装 {a['pack']} 没拿到 id"])
        self.saved[f"pack:{a['pack']}"] = pid
        body = {"lot_id": self.id_of("lot", a["lot"])}
        call = Call("POST", self.path("pack_pack", pack_id=pid), body, self._idem(a, "-in"))
        self.send(entry, call, a.get("expect"), "pack_lot", a.get("save_as"))

    def _label_print(self, a: dict, entry: dict) -> None:
        pid = self.saved.get(f"pack:{a['pack']}") or self.id_of("pack", a["pack"])
        call = Call("POST", self.path("label_print", pack_id=pid), self.resolve(a.get("body") or {}), self._idem(a))
        self._as(a, entry, call, "label_print")

    def _marking_void(self, a: dict, entry: dict) -> None:
        self.path("marking_void", marking_id="x")  # 先确认接口在，再查原因码
        mid = self._mid(a["marking"])
        body = self._body_from(a, {"comment": "comment"})
        call = Call("POST", self.path("marking_void", marking_id=mid), body, self._idem(a))
        # $marking.<批次> 作废后仍指向这条（场景用它断言旧记录），重新建主记录后才改指新记录
        self._as(a, entry, call, "marking_void")

    def _marking_report(self, a: dict, entry: dict) -> None:
        payload = {"lot_id": self.id_of("lot", a["lot"]), "kind": a["kind"], **self.resolve(a.get("payload") or {})}
        call = self._envelope(a, "marking", payload)
        entry.update(external_event_id=call.body["external_event_id"])
        self.send(entry, call, a.get("expect"), "marking_report", a.get("save_as"))

    def _marking_template_ready(self, a: dict, entry: dict) -> None:
        # B1 模板与产品绑定接口还没定稿：两条路径都在时才执行；否则记未实现
        self.path("marking_template")
        self.path("marking_template_approve", id="x")
        entry.update(ok=None, message="B1 模板接口已出现，绑定方式待按 openapi 补执行（不算失败）")

    def _marking_template(self, a: dict, entry: dict) -> None:
        """模板接口（P3-B1）。D79 补充七：create / update / new_version / approve 带 Idempotency-Key，
        preview / validate 是只读 POST、不带 key。``as:`` 换账号（测 self_approval 等）。"""
        call = template_call(a, self.resolve, self.path, self._idem)
        # 附注二：预览 {template_id, lines}、校验 {valid, unknown_placeholders}，{data: …} 与平铺都认
        self._as(a, entry, call, "marking_template", flat=a["action"] in ("preview", "validate"))

    def _lot_scrap(self, a: dict, entry: dict) -> None:
        """批次报废（POST /mes/exec/lots/{id}/adjust kind=scrap）。

        后端 adjust.py：晶圆级 / 单元级批次按 ``unit_ids``（本批次内、未报废的片），只有数量级批次按 ``qty``。
        执行器先查批次的 tracking_level；非数量级时从 ``GET /mes/wafer?lot_id=`` 取在批的片号。
        场景参数 ``units``：省略 / ``all`` = 剩下的全部；整数 N = 按 slot 顺序前 N 片；列表 = 指定片号（code）。
        数量级批次 ``qty`` 省略时 = 批次当前数量。
        """
        lid = self.id_of("lot", a["lot"])
        row = self.r.row("lot", a["lot"])
        row = row if isinstance(row, dict) else {}
        unit_rows: list[dict] = []
        if (row.get("tracking_level") or "wafer") != "quantity":
            r = self.r.c.get("/mes/wafer", lot_id=lid, page_size=100)
            if r.status != 200:
                self._fail_if([f"查 {a['lot']} 的片号 GET /mes/wafer HTTP {r.status}"])
            unit_rows = self._rows(r)
        reason_id = self.id_of("reason_code", a["reason"]) if a.get("reason") else None
        body = scrap_body(row, unit_rows, a, reason_id, a.get("comment") or f"sim {self.run_id}")
        entry["tracking_level"] = row.get("tracking_level")
        call = Call("POST", self.path("lot_adjust", lot_id=lid), body, f"{self.run_id}:scrap:{a['lot']}")
        self.send(entry, call, a.get("expect"), "lot_scrap", a.get("save_as"))
        if a.get("save_as"):
            self.saved[a["save_as"]] = {"at": now_iso(), **(self.saved.get(a["save_as"]) or {})}

    def _expect_marking(self, a: dict, entry: dict) -> None:
        ref = a.get("marking")
        mid = self.resolve(ref) if ref else self._mid(a["lot"])
        r = self._get(self.path("marking_get", marking_id=mid))
        row = r.body.get("data", r.body) if isinstance(r.body, dict) else {}
        errs = [f"HTTP {r.status}"] if r.status != 200 else []
        if "voided" in a and dig(row, "voided") != a["voided"]:
            errs.append(f"voided {dig(row, 'voided')!r} != 期望 {a['voided']!r}")
        self._fail_if(errs + self._fields(row, a.get("fields"), "marking"))

    def _sublist(self, adapter: str, a: dict) -> list[dict]:
        mid = self._mid(a["lot"])
        return self._rows(self._get(self.path(adapter, marking_id=mid), page_size=200))

    def _expect_marking_prints(self, a: dict, entry: dict) -> None:
        rows = sorted(self._sublist("marking_prints", a), key=lambda x: x.get("seq") or 0)
        errs = self._count_last(rows, a, "prints")
        if "seqs" in a and [x.get("seq") for x in rows] != a["seqs"]:
            errs.append(f"seq {[x.get('seq') for x in rows]} != 期望 {a['seqs']}")
        self._fail_if(errs)

    def _expect_marking_inspections(self, a: dict, entry: dict) -> None:
        rows = self._sublist("marking_inspections", a)
        rows.sort(key=lambda x: str(x.get("inspected_at") or x.get("created_at") or ""))
        self._fail_if(self._count_last(rows, a, "inspections"))

    def _count_last(self, rows: list[dict], a: dict, label: str) -> list[str]:
        errs = []
        if "count" in a and len(rows) != int(a["count"]):
            errs.append(f"{label} {len(rows)} 条 != 期望 {a['count']}")
        if a.get("last"):
            errs += [f"{label} 为空"] if not rows else self._fields(rows[-1], a["last"], f"{label}[-1]")
        return errs

    def _expect_marking_events(self, a: dict, entry: dict) -> None:
        if self.b2_missing():
            raise Unimplemented("打标领域事件依赖 P3-B2")
        rows = self._events("lot", self.id_of("lot", a["lot"]))
        after = None
        if a.get("after"):
            after = self._pivot(a["after"])
        errs = self._check_events(rows, a, after)
        if a.get("absent_after"):
            errs += self._absent_after(rows, a, self._pivot(a["absent_after"]))
        self._fail_if(errs)

    def _pivot(self, name: str) -> str | None:
        d = self.saved.get(name) or {}
        if name in self.unimpl:
            raise Unimplemented(f"{name} 来自未实现的步骤")
        return d.get("at") or d.get("created_at") or d.get("printed_at") or d.get("inspected_at") or d.get("voided_at")

    def _expect_marking_list(self, a: dict, entry: dict) -> None:
        params = {"lot_id": self.id_of("lot", a["lot"]), "page_size": 200}
        for k in ("marked_at_from", "marked_at_to"):
            if k in a:
                params[k] = self.resolve(a[k])
        rows = self._rows(self._get(self.path("marking_list"), **params))
        self._fail_if([] if len(rows) == int(a["count"]) else [f"列表 {len(rows)} 条 != 期望 {a['count']}"])

    def _expect_marking_trace(self, a: dict, entry: dict) -> None:
        params: dict[str, Any] = {"kind": "trace_code", "code": self.resolve(a["code"])}
        if a.get("include_voided"):
            params["include_voided"] = "true"
        if a.get("expect") or a.get("as"):
            # B3 草稿：权限 / 跨租户（as: other_tenant，无凭据记 skip）/ 422 断言，走 send 统一检查
            from urllib.parse import urlencode

            call = Call("GET", self.path("marking_trace") + "?" + urlencode(params))
            self._as(a, entry, call, "expect_marking_trace")
            return
        rows = self._rows(self._get(self.path("marking_trace"), **params))
        errs = [] if len(rows) == int(a.get("count", len(rows))) else [f"追溯 {len(rows)} 条 != 期望 {a['count']}"]
        if a.get("first"):
            errs += ["追溯为空"] if not rows else self._fields(rows[0], a["first"], "trace[0]")
        self._fail_if(errs)


def now_iso() -> str:
    return now_utc().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
