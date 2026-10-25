"""演示业务巡检：通过 HTTP 接口走一遍泛半导体前后道业务，补充演示数据并验证各功能可用。

    python scripts/demo_tour.py [--base http://localhost:8000/api/v1]

须在后端环境中运行（直接为默认租户的超级管理员签发 3 小时令牌）。主数据按编码幂等：已存在则复用，
新建的带 ``attrs._demo`` 标记（``scripts/mes_demo.py remove`` 可清除）；工单、批次、单据每次运行都新建。

流程：来料接收与 IQC → BOM 生效与工单锁定 → 领料 → 机台上料 → CP 测试（晶圆图、DC、SPC 判异自动 Hold）
→ Wafer Bank 入库 → 领用到封装工单 → 划片 / 固晶 / 切单自动单元转换 → 成品入库 → 出货 → NCR / MRB
→ 停机记录 → 追溯、报表、看板与全部实体列表。最后逐项输出结果，任一项失败时返回 1。
"""

import argparse
import random
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx

DEMO = {"_demo": True}
RUN = datetime.now().strftime("%m%d%H%M%S")
RESULTS: list[tuple[str, bool, str]] = []
Row = dict[str, Any]


class Api:
    """带令牌与租户头的接口客户端，以及规格实体的查找 / 幂等创建。"""

    def __init__(self, base: str, token: str, tenant_id: str) -> None:
        self.c = httpx.Client(
            base_url=base,
            headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_id},
            timeout=300,
            trust_env=False,
        )

    def call(self, method: str, path: str, body: Any = None, **params: Any) -> Any:
        r = self.c.request(method, path, json=body, params=params or None)
        if r.status_code >= 400:
            raise RuntimeError(f"{method} {path} → {r.status_code} {r.text[:500]}")
        return r.json() if "json" in r.headers.get("content-type", "") else r.content

    def get(self, path: str, **params: Any) -> Any:
        return self.call("GET", path, **params)

    def post(self, path: str, body: Any = None) -> Any:
        return self.call("POST", path, body if body is not None else {})

    @staticmethod
    def url(ent: str) -> str:
        return "/mes/" + ent.replace("_", "-")

    def rows(self, ent: str, **filters: Any) -> list[Row]:
        return self.get(self.url(ent), page_size=100, **filters)["data"]  # type: ignore[no-any-return]

    def find(self, ent: str, code: str) -> Row | None:
        rows = [r for r in self.rows(ent, q=code) if r.get("code") == code]
        return max(rows, key=lambda r: r.get("version") or 0) if rows else None

    def id(self, ent: str, code: str) -> str:
        row = self.find(ent, code)
        if not row:
            raise RuntimeError(f"{ent} {code} not found")
        return str(row["id"])

    def create(self, ent: str, **body: Any) -> Row:
        return self.post(self.url(ent), {**body, "attrs": DEMO})  # type: ignore[no-any-return]

    def ensure(self, ent: str, code: str, **body: Any) -> Row:
        return self.find(ent, code) or self.create(ent, code=code, **body)

    def activate(self, ent: str, row: Row) -> Row:
        if row.get("status") != "draft":
            return row
        return self.post(f"{self.url(ent)}/{row['id']}/status", {"status": "active"})  # type: ignore[no-any-return]

    def stage(self, lot: Row, stage: str, **body: Any) -> Row:
        return self.post(f"/mes/exec/lots/{lot['id']}/{stage}", body)  # type: ignore[no-any-return]

    def ctx(self, lot: Row) -> Row:
        return self.get(f"/mes/exec/lots/{lot['id']}")  # type: ignore[no-any-return]


@contextmanager
def feature(name: str) -> Iterator[list[str]]:
    """记录一项功能的结果；块内向 ``notes`` 追加说明，异常记为失败并继续后续项。"""
    notes: list[str] = []
    try:
        yield notes
    except Exception as ex:  # noqa: BLE001 - 巡检逐项汇报，不中断
        RESULTS.append((name, False, str(ex)[:600]))
        print(f"  ✗ {name}: {str(ex)[:600]}", flush=True)  # noqa: T201
    else:
        RESULTS.append((name, True, "; ".join(notes)))
        print(f"  ✓ {name}: {'; '.join(notes)}", flush=True)  # noqa: T201


def now_iso(delta_hours: float = 0) -> str:
    return (datetime.now(UTC) + timedelta(hours=delta_hours)).isoformat()


# ---------------- 主数据 ----------------
OPS = [  # (编码, 名称, 工序类型, 区域, 设备, 设备类型, 设备类别)
    ("SEMI-CP", "Chip probing (DEMO)", "test", "PROBE", "PRB01", "PROBER", "test"),
    ("SEMI-SAW", "Wafer saw (DEMO)", "process", "ASSY", "SAW01", "DICER", "process"),
    ("SEMI-DA", "Die attach (DEMO)", "process", "ASSY", "DA01", "DIEBOND", "process"),
    ("SEMI-WB", "Wire bond (DEMO)", "process", "ASSY", "WB01", "WIREBOND", "process"),
    ("SEMI-MOLD", "Molding (DEMO)", "process", "ASSY", "MLD01", "MOLDER", "process"),
    (
        "SEMI-SING",
        "Singulation (DEMO)",
        "process",
        "ASSY",
        "SNG01",
        "SINGULATE",
        "process",
    ),
    ("SEMI-FT", "Final test (DEMO)", "test", "ASSY", "FT01", "FTESTER", "test"),
]
BINS = [  # (编码, 名称, 良品, 颜色)
    ("1", "Pass (DEMO)", True, "#10b981"),
    ("2", "Pass grade B (DEMO)", True, "#84cc16"),
    ("5", "Open (DEMO)", False, "#f97316"),
    ("6", "Short (DEMO)", False, "#ef4444"),
    ("9", "Parametric fail (DEMO)", False, "#a855f7"),
]
MATERIALS = [  # (编码, 名称, 单位, 数量)
    ("EPOXY-8200", "Die attach epoxy (DEMO)", "G", 500),
    ("AU-WIRE-1M", "Gold wire 1 mil (DEMO)", "EA", 40),
    ("EMC-G700", "Mold compound (DEMO)", "G", 800),
]
STRIP = 20  # 每条引线框架的芯片数


def master(api: Api, ctx: Row) -> list[str]:
    ids = {}
    wcs = {
        a: api.ensure(
            "workcenter",
            f"WC-{a}",
            name=f"{a.title()} bay (DEMO)",
            area_id=api.id("area", a),
        )
        for a in {o[3] for o in OPS}
    }
    for code, name, kind, area, eq, etype, cat in OPS:
        et = api.ensure(
            "equipment_type", etype, name=f"{etype.title()} (DEMO)", category=cat
        )
        op = api.ensure(
            "operation",
            code,
            name=name,
            operation_type=kind,
            area_id=api.id("area", area),
            std_minutes=30,
        )
        e = api.ensure(
            "equipment",
            eq,
            name=f"{name.split(' (')[0]} tool (DEMO)",
            unit_kind="main",
            equipment_type_id=et["id"],
            workcenter_id=wcs[area]["id"],
            initial_state_id=api.id("e10_state", "SBY-IDLE"),
            ideal_uph=600,
        )
        if not api.rows("equipment_capability", equipment=e["id"], operation=op["id"]):
            api.create(
                "equipment_capability", equipment_id=e["id"], operation_id=op["id"]
            )
        ids[code] = op["id"]
        ctx.setdefault("eq", {})[code] = e
    ctx["ops"] = ids
    for code, name, good, color in BINS:
        api.ensure("bin_code", code, name=name, is_good=good, color=color)
    ctx["wbank"] = api.ensure(
        "bank", "WB-01", name="Wafer bank (DEMO)", bank_kind="wafer"
    )
    api.ensure("bank", "DB-01", name="Die bank (DEMO)", bank_kind="die")
    mt = api.ensure(
        "material_type",
        "ASSY-MAT",
        name="Assembly material (DEMO)",
        category="consumable",
    )
    ctx["mat"] = {
        c: api.ensure(
            "material", c, name=n, material_type_id=mt["id"], uom_id=api.id("uom", u)
        )
        for c, n, u, _ in MATERIALS
    }
    rc = api.find("recipe", "SEMI-CP-PGM")
    if not rc:
        rc = api.create(
            "recipe",
            code="SEMI-CP-PGM",
            name="CP test program (DEMO)",
            equipment_type_id=ctx["eq"]["SEMI-CP"]["equipment_type_id"],
            recipe_type="production",
        )
        api.create(
            "recipe_equipment",
            recipe_id=rc["id"],
            equipment_id=ctx["eq"]["SEMI-CP"]["id"],
        )
    ctx["recipe"] = api.activate("recipe", rc)
    mi = api.ensure(
        "measurement_item",
        "SEMI-VTH",
        name="Threshold voltage (DEMO)",
        meas_type="numeric",
        uom_id=api.id("uom", "A"),
        precision=1,
        oos_action="warn",
        ooc_action="auto_hold",
        oos_reason_id=api.id("reason_code", "HD-ENG"),
    )
    plan = api.find("dc_plan", "SEMI-CP-DC")
    if not plan:
        plan = api.create(
            "dc_plan",
            code="SEMI-CP-DC",
            name="CP Vth (DEMO)",
            operation_id=ids["SEMI-CP"],
        )
        api.create(
            "dc_plan_item",
            dc_plan_id=plan["id"],
            measurement_item_id=mi["id"],
            target=450,
            lsl=400,
            usl=500,
            lcl=438,
            cl=450,
            ucl=462,
            ooc_rules="1,2,3",
        )
    api.activate("dc_plan", plan)
    ctx["dc_item"] = api.rows("dc_plan_item", dc_plan=plan["id"])[0]
    api.ensure(
        "sampling_rule",
        "SEMI-CP-SMP",
        name="CP Vth sampling (DEMO)",
        level="wafer",
        operation_id=ids["SEMI-CP"],
        dc_plan_id=plan["id"],
        wafer_count=3,
        wafer_selection="first",
    )
    cp = route(api, "SEMI-CP-R", "CP flow (DEMO)", [{"seq": 10, "op": "SEMI-CP"}], ids)
    be = route(
        api,
        "SEMI-BE-R",
        "QFN assembly with unit conversion (DEMO)",
        [
            {"seq": 10, "op": "SEMI-SAW", "convert_to": "die", "convert_mode": "map"},
            {
                "seq": 20,
                "op": "SEMI-DA",
                "convert_to": "strip",
                "convert_mode": "assemble",
                "convert_ratio": STRIP,
                "materials": [("EPOXY-8200", 2, "G")],
            },
            {"seq": 30, "op": "SEMI-WB"},
            {"seq": 40, "op": "SEMI-MOLD"},
            {
                "seq": 50,
                "op": "SEMI-SING",
                "convert_to": "package",
                "convert_mode": "split",
                "convert_ratio": STRIP,
            },
            {"seq": 60, "op": "SEMI-FT"},
        ],
        ids,
        ctx["mat"],
    )
    ctx["cp_product"] = product(api, "SEMI-W40", "MCU A100 wafer for CP (DEMO)", cp)
    ctx["be_product"] = product(api, "SEMI-QFN", "MCU A100 QFN-48 assembly (DEMO)", be)
    bom = api.find("bom", "SEMI-QFN-BOM")
    if not bom:
        bom = api.create(
            "bom",
            code="SEMI-QFN-BOM",
            name="QFN-48 BOM (DEMO)",
            product_id=ctx["be_product"]["id"],
        )
        for op, mat, qty in (
            ("SEMI-DA", "EPOXY-8200", 0.02),
            ("SEMI-WB", "AU-WIRE-1M", 0.05),
            ("SEMI-MOLD", "EMC-G700", 0.1),
        ):
            api.create(
                "bom_line",
                bom_id=bom["id"],
                operation_id=ids[op],
                material_id=ctx["mat"][mat]["id"],
                qty=qty,
                uom_id=ctx["mat"][mat]["uom_id"],
                qty_basis="per_unit",
                scrap_rate=5,
            )
    ctx["bom"] = api.activate("bom", bom)
    return [
        f"{len(OPS)} operations / tools, {len(BINS)} bins, 2 banks, 2 routes, BOM {ctx['bom']['code']}"
    ]


def route(
    api: Api,
    code: str,
    name: str,
    steps: list[Row],
    ops: dict[str, str],
    mats: dict[str, Row] | None = None,
) -> Row:
    r = api.find("route", code)
    if not r:
        r = api.create("route", code=code, name=name, route_type="main")
        for st in steps:
            body = {k: v for k, v in st.items() if k not in ("op", "materials")}
            row = api.create(
                "route_step", route_id=r["id"], operation_id=ops[st["op"]], **body
            )
            for mat, qty, _uom in st.get("materials", []):
                m = (mats or {})[mat]
                api.create(
                    "step_resource",
                    route_step_id=row["id"],
                    resource_kind="material",
                    material_id=m["id"],
                    qty=qty,
                    uom_id=m["uom_id"],
                    qty_basis="per_lot",
                )
    return api.activate("route", r)


def product(api: Api, code: str, name: str, rt: Row) -> Row:
    p = api.find("product", code)
    if not p:
        p = api.create(
            "product",
            code=code,
            name=name,
            family_id=api.id("product_family", "MCU"),
            tech_node_id=api.id("tech_node", "N40"),
            uom_id=api.id("uom", "WFR"),
            tracking_level="wafer",
            gross_die=113,
        )
        api.create(
            "product_route",
            product_id=p["id"],
            route_id=rt["id"],
            is_default=True,
            priority=1,
        )
    return api.activate("product", p)


def work_order(api: Api, prod: Row, lot_type: str, qty: int, remarks: str) -> Row:
    wo = api.create(
        "work_order",
        product_id=prod["id"],
        lot_type_id=api.id("lot_type", lot_type),
        priority_id=api.id("lot_priority", "NORMAL"),
        planned_qty=qty,
        customer="ACME Semi (DEMO)",
        due_date=str(date.today() + timedelta(days=7)),
        remarks=remarks,
    )
    return api.post(f"/mes/work-order/{wo['id']}/transition", {"action": "release"})  # type: ignore[no-any-return]


# ---------------- 物料 ----------------
def materials_in(api: Api, ctx: Row) -> list[str]:
    rc = api.create("material_receipt", code=f"IN-DEMO-{RUN}", supplier="Henkel (DEMO)")
    lines = [
        api.create(
            "material_receipt_line",
            material_receipt_id=rc["id"],
            material_id=ctx["mat"][c]["id"],
            uom_id=ctx["mat"][c]["uom_id"],
            qty=q,
            supplier_lot=f"SL-{c}-{RUN}",
            expiry_date=str(date.today() + timedelta(days=180)),
        )
        for c, _, _, q in MATERIALS
    ]
    bad = api.create(
        "material_receipt_line",
        material_receipt_id=rc["id"],
        material_id=ctx["mat"]["EMC-G700"]["id"],
        uom_id=ctx["mat"]["EMC-G700"]["uom_id"],
        qty=100,
        supplier_lot=f"SL-EMC-BAD-{RUN}",
    )
    api.post(f"/mes/material-receipt/{rc['id']}/transition", {"action": "confirm"})
    for ln in lines:
        api.post(f"/mes/material-receipt/lines/{ln['id']}/iqc", {"result": "pass"})
    api.post(f"/mes/material-receipt/lines/{bad['id']}/iqc", {"result": "fail"})
    lots = api.rows("material_lot", q=rc["code"])
    ctx["mlots"] = {
        lt["material_id"]: lt for lt in lots if lt["ml_status"] == "available"
    }
    rejected = sum(1 for lt in lots if lt["ml_status"] == "rejected")
    return [f"{rc['code']}: {len(ctx['mlots'])} lots passed IQC, {rejected} rejected"]


def issue_and_mount(api: Api, ctx: Row) -> list[str]:
    wo = ctx["be_wo"]
    if wo.get("bom_id") != ctx["bom"]["id"]:
        raise RuntimeError("work order did not lock the active BOM")
    req = api.get(f"/mes/material-issue/requirements/{wo['id']}")["lines"]
    epoxy = ctx["mat"]["EPOXY-8200"]
    iss = api.create("material_issue", code=f"ISS-DEMO-{RUN}", work_order_id=wo["id"])
    api.create(
        "material_issue_line",
        material_issue_id=iss["id"],
        material_lot_id=ctx["mlots"][epoxy["id"]]["id"],
        qty=100,
    )
    api.post(f"/mes/material-issue/{iss['id']}/transition", {"action": "confirm"})
    child = api.find("material_lot", f"{iss['code']}-1")
    if not child or child["work_order_id"] != wo["id"]:
        raise RuntimeError("issued material lot not created for the work order")
    da = ctx["eq"]["SEMI-DA"]
    at = now_iso()  # 卸旧料与上新料同一时刻，区间首尾相接不重叠
    for m in api.rows("equipment_material_mount", equipment=da["id"]):
        if not m.get("unmounted_at"):
            api.call(
                "PATCH",
                f"/mes/equipment-material-mount/{m['id']}",
                {"unmounted_at": at},
            )
    api.create(
        "equipment_material_mount",
        equipment_id=da["id"],
        position="P1",
        material_lot_id=child["id"],
        mounted_at=at,
    )
    return [
        f"requirements {len(req)} materials",
        f"issued {child['code']} 100 g",
        "mounted on DA01/P1",
    ]


# ---------------- CP ----------------
def die_map(seed: str) -> list[list[Any]]:
    """直径 13 格的圆形晶圆：约 113 颗，边缘失效率更高。"""
    rnd = random.Random(seed)
    dies = []
    for y in range(-6, 7):
        for x in range(-6, 7):
            r2 = x * x + y * y
            if r2 > 36:
                continue
            p = rnd.random() - (0.08 if r2 > 28 else 0)
            b = "1" if p > 0.1 else "2" if p > 0.06 else rnd.choice(["5", "6", "9"])
            dies.append([x + 6, y + 6, b])
    return dies


def free_carrier(api: Api) -> str | None:
    used = {lt["carrier_id"] for lt in api.rows("lot") if lt.get("carrier_id")}
    for c in api.rows("carrier"):
        if c["id"] not in used and c.get("status_code") == "available":
            return str(c["id"])
    return None


def cp_test(api: Api, ctx: Row, n_lots: int = 10) -> list[str]:
    wo = work_order(api, ctx["cp_product"], "PROD", n_lots * 3, f"CP tour {RUN} (DEMO)")
    car = free_carrier(api)
    lots = api.post(
        f"/mes/work-order/{wo['id']}/start",
        {
            "lots": [
                {"qty": 3, "carrier_id": car if i == 0 else None} for i in range(n_lots)
            ]
        },
    )["data"]
    eq = ctx["eq"]["SEMI-CP"]["id"]
    held, oos = [], 0
    for i, lot in enumerate(lots):
        api.stage(lot, "move_in", equipment_id=eq)
        api.stage(lot, "track_in", equipment_id=eq, recipe_id=ctx["recipe"]["id"])
        units = api.ctx(lot)["units"]
        api.post(
            f"/mes/exec/lots/{lot['id']}/die-maps",
            {
                "test_kind": "cp",
                "source": f"cp_{lot['code']}.csv",
                "maps": [
                    {"unit_id": u["id"], "dies": die_map(u["code"])} for u in units
                ],
            },
        )
        dc = api.ctx(lot)["dc"]
        rnd = random.Random(lot["code"])
        shift = 18 if i == n_lots - 1 else 0  # 最后一批漂移：超出 UCL → 判异自动 Hold
        vals = []
        for it in dc["items"]:
            for k, u in enumerate(dc["unit_ids"] or [None]):
                v = round(450 + shift + rnd.gauss(0, 3), 1)
                if i == n_lots - 2:  # 单点超规格（OOS 提示），子组均值仍受控
                    v = 501.0 if k == 0 else 437.0
                    oos += k == 0
                vals.append(
                    {
                        "measurement_item_id": it["measurement_item_id"],
                        "unit_id": u,
                        "value": v,
                    }
                )
        r = api.stage(lot, "track_out", dc=vals)
        if r["lot"]["on_hold"]:
            held.append(r["lot"])
            continue
        api.stage(lot, "move_out")
    ctx["cp_lots"] = [api.ctx(lt)["lot"] for lt in lots]
    ctx["held"] = held
    done = [lt for lt in ctx["cp_lots"] if lt["lot_status"] == "completed"]
    if not held:
        raise RuntimeError("OOC lot was not held")
    return [
        f"WO {wo['code']}: {len(lots)} lots × 3 wafers",
        f"{len(done)} completed",
        f"{len(held)} held by OOC",
        f"{oos} OOS value",
    ]


def spc(api: Api, ctx: Row) -> list[str]:
    ch = api.get("/mes/exec/spc", dc_plan_item_id=ctx["dc_item"]["id"])
    pts = ch.get("points") or []
    bad = [p for p in pts if p.get("ooc") or p.get("rules")]
    if len(pts) < 5 or not bad:
        raise RuntimeError(f"chart has {len(pts)} points, {len(bad)} OOC")
    return [f"{len(pts)} subgroups, {len(bad)} OOC point(s)"]


def bank(api: Api, ctx: Row) -> list[str]:
    done = [lt for lt in ctx["cp_lots"] if lt["lot_status"] == "completed"]
    for lt in done:
        api.post(
            f"/mes/exec/lots/{lt['id']}/bank-in",
            {"bank_id": ctx["wbank"]["id"], "comment": "CP done (DEMO)"},
        )
    ctx["banked"] = done
    return [f"{len(done)} lots into {ctx['wbank']['code']}"]


def bank_issue(api: Api, ctx: Row) -> list[str]:
    b = ctx["banked"]
    part = api.ctx(b[3])["units"][:2]
    a = api.post(
        "/mes/exec/bank/issue",
        {
            "work_order_id": ctx["be_wo"]["id"],
            "lots": [{"lot_id": x["id"]} for x in b[:3]]
            + [{"lot_id": b[3]["id"], "unit_ids": [u["id"] for u in part]}],
            "comment": "Kitting for QFN line (DEMO)",
        },
    )
    c = api.post(
        "/mes/exec/bank/issue",
        {
            "work_order_id": ctx["be_wo"]["id"],
            "lots": [{"lot_id": x["id"]} for x in b[4:6]],
        },
    )
    ctx["be_a"], ctx["be_b"] = a["lot"], c["lot"]
    left = len(b) - 6
    return [
        f"{a['lot']['code']} ← 11 wafers",
        f"{c['lot']['code']} ← 6 wafers",
        f"{left} lots + 1 wafer stay banked",
    ]


def run_be(api: Api, ctx: Row, lot: Row, stop_after: int | None = None) -> list[str]:
    out = []
    for k, op in enumerate(
        ["SEMI-SAW", "SEMI-DA", "SEMI-WB", "SEMI-MOLD", "SEMI-SING", "SEMI-FT"]
    ):
        if stop_after is not None and k >= stop_after:
            break
        eq = ctx["eq"][op]["id"]
        cx = api.ctx(lot)
        if cx["next_stage"] == "move_in":
            api.stage(lot, "move_in", equipment_id=eq)
        api.stage(lot, "track_in", equipment_id=eq)
        r = api.stage(lot, "track_out")
        if r.get("converted"):
            c = r["converted"]
            out.append(
                f"{op}: → {c['count']} {c['to_kind']}"
                + (f" ({c['bad_dies']} bad)" if c["bad_dies"] else "")
            )
        api.stage(lot, "move_out")
    st = api.ctx(lot)["lot"]
    out.append(f"{st['code']} {st['lot_status']} qty {st['qty']}")
    return out


def store_and_ship(api: Api, ctx: Row) -> list[str]:
    lot = api.ctx(ctx["be_a"])["lot"]
    rc = api.create(
        "receipt",
        warehouse_id=api.id("warehouse", "WH-ASSY"),
        location_id=api.id("storage_location", "AS-R-01"),
    )
    api.create(
        "receipt_line",
        receipt_id=rc["id"],
        lot_id=lot["id"],
        good_qty=lot["qty"],
        scrap_qty=0,
    )
    api.post(f"/mes/receipt/{rc['id']}/transition", {"action": "submit"})
    api.post(f"/mes/receipt/{rc['id']}/transition", {"action": "confirm"})
    sh = api.create(
        "shipment",
        code=f"SH-DEMO-{RUN}",
        customer="ACME Semi (DEMO)",
        waybill=f"SF{RUN}",
    )
    q = lot["qty"] // 2
    api.create("shipment_line", shipment_id=sh["id"], lot_id=lot["id"], qty=q)
    api.post(f"/mes/shipment/{sh['id']}/transition", {"action": "confirm"})
    ctx["shipped"] = lot
    return [f"receipt {rc['code']}: {lot['qty']} pcs", f"{sh['code']}: {q} pcs shipped"]


def ncr(api: Api, ctx: Row) -> list[str]:
    held = ctx["held"][0]
    w = api.ctx(held)["units"][0]
    a = api.post(
        "/mes/exec/ncr",
        {
            "lot_id": held["id"],
            "title": "Vth shift on CP – OOC (DEMO)",
            "severity": "major",
            "defect_code_id": api.id("defect_code", "D-PRT"),
            "description": "Mean Vth above UCL; probe card suspected (DEMO)",
            "unit_ids": [w["id"]],
            "hold": False,
        },
    )["ncr"]
    api.post(
        f"/mes/exec/ncr/{a['id']}/propose",
        {"disposition": "use_as_is", "comment": "Within spec limits (DEMO)"},
    )
    b_units = api.ctx(ctx["be_b"])["units"][:2]
    b = api.post(
        "/mes/exec/ncr",
        {
            "lot_id": ctx["be_b"]["id"],
            "title": "Die attach voids found at AOI (DEMO)",
            "severity": "minor",
            "defect_code_id": api.id("defect_code", "D-SCR"),
            "unit_ids": [u["id"] for u in b_units],
            "hold": True,
            "reason_id": api.id("reason_code", "HD-ENG"),
        },
    )["ncr"]
    c = api.post(
        "/mes/exec/ncr",
        {
            "lot_id": ctx["be_b"]["id"],
            "title": "Duplicate report (DEMO)",
            "severity": "minor",
            "hold": False,
        },
    )["ncr"]
    api.post(
        f"/mes/exec/ncr/{c['id']}/cancel", {"comment": "Duplicate of " + b["code"]}
    )
    out = []
    for x in (a, b, c):
        d = api.get(f"/mes/exec/ncr/{x['id']}")["ncr"]
        out.append(f"{d['code']} {d['ncr_status']}")
    return out


def downtime(api: Api, ctx: Row) -> list[str]:
    eq = ctx["eq"]["SEMI-WB"]
    api.create(
        "downtime",
        equipment_id=eq["id"],
        start_at=now_iso(-3),
        end_at=now_iso(-2.25),
        reason_id=api.id("reason_code", "DT-ALM"),
        comment="Wire feed alarm, capillary replaced (DEMO)",
    )
    return [f"{eq['code']} 45 min"]


def reads(api: Api, ctx: Row) -> list[str]:
    pkg = api.ctx(ctx["shipped"])["units"][0]
    t = api.get("/mes/exec/trace", kind="wafer", code=pkg["code"])
    levels = {u["unit_kind"] for u in t["units"]["backward"]["units"]}
    if not {"strip", "die", "wafer"} <= levels:
        raise RuntimeError(f"unit trace back from package reached {sorted(levels)}")
    lt = api.get("/mes/exec/trace", kind="lot", code=ctx["shipped"]["code"])
    if not lt["forward"].get("shipments"):
        raise RuntimeError("lot trace shows no shipment")
    w = api.ctx(ctx["banked"][-1])["units"][0]
    maps = api.get(f"/mes/exec/units/{w['id']}/die-maps")["data"]
    api.get(f"/mes/exec/die-maps/{maps[0]['id']}")
    for p in (
        "/mes/exec/reports/wip",
        "/mes/exec/reports/output",
        "/mes/exec/reports/oee",
        "/mes/exec/reports/yield",
        "/mes/exec/reports/oee-trend",
        "/mes/exec/home",
        "/mes/exec/queue",
        "/mes/exec/holds",
        "/mes/exec/qtime/monitor",
        "/mes/exec/carriers/board",
        "/mes/eqp/board",
        f"/mes/exec/lots/{ctx['banked'][-1]['id']}/wafer-map",
    ):
        api.get(p)
    return [
        "package → strip → die → wafer trace",
        "lot trace shows shipment",
        "12 reports / boards",
    ]


def lists(api: Api) -> list[str]:
    meta = api.get("/mes/_meta")
    ents = meta["entities"] if isinstance(meta, dict) and "entities" in meta else meta
    bad = []
    for e in ents:
        if e.get("internal"):
            continue
        try:
            api.get("/mes/" + e.get("path", e["code"].replace("_", "-")), page_size=1)
        except RuntimeError as ex:
            bad.append(f"{e['code']}: {str(ex)[:80]}")
    if bad:
        raise RuntimeError("; ".join(bad[:5]))
    return [f"{len(ents)} entity lists"]


def token() -> tuple[str, str]:
    from sqlmodel import Session, select

    from app.core.db import engine
    from app.core.security import create_access_token
    from app.platform.tenants.models import Tenant
    from app.platform.users.models import User

    with Session(engine) as s:
        u = s.exec(select(User).where(User.is_superuser)).first()
        t = s.exec(select(Tenant).where(Tenant.slug == "default")).one()
        assert u is not None
        return create_access_token(u.id, timedelta(hours=3), tenant_id=t.id), str(t.id)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000/api/v1")
    args = ap.parse_args()
    api = Api(args.base, *token())
    ctx: Row = {}
    print(f"demo tour {RUN} → {args.base}", flush=True)  # noqa: T201
    with feature("主数据（工序 / 设备 / Bin / Bank / 路线 / 产品 / 量测 / BOM）") as n:
        n += master(api, ctx)
    with feature("来料接收 + IQC") as n:
        n += materials_in(api, ctx)
    with feature("封装工单下达（锁定 BOM）") as n:
        ctx["be_wo"] = work_order(
            api, ctx["be_product"], "ASSY", 50, f"QFN tour {RUN} (DEMO)"
        )
        n.append(ctx["be_wo"]["code"])
    with feature("领料 + 机台上料") as n:
        n += issue_and_mount(api, ctx)
    with feature("CP 测试：晶圆图导入、DC、OOS / OOC 自动 Hold、载具") as n:
        n += cp_test(api, ctx)
    with feature("SPC 控制图") as n:
        n += spc(api, ctx)
    with feature("Wafer Bank 入库") as n:
        n += bank(api, ctx)
    with feature("Bank 领用到封装工单") as n:
        n += bank_issue(api, ctx)
    with feature("封装全流程：划片 / 固晶 / 切单自动转换、扣料") as n:
        n += run_be(api, ctx, ctx["be_a"])
    with feature("封装在制：停在焊线") as n:
        n += run_be(api, ctx, ctx["be_b"], stop_after=2)
    with feature("成品入库 + 出货") as n:
        n += store_and_ship(api, ctx)
    with feature("NCR / MRB：评审中 / 待处置 / 已取消") as n:
        n += ncr(api, ctx)
    with feature("停机记录") as n:
        n += downtime(api, ctx)
    with feature("追溯 / 报表 / 看板") as n:
        n += reads(api, ctx)
    with feature("全部实体列表") as n:
        n += lists(api)
    ok = sum(1 for _, good, _ in RESULTS if good)
    print(f"\n{ok}/{len(RESULTS)} passed", flush=True)  # noqa: T201
    sys.exit(0 if ok == len(RESULTS) else 1)


if __name__ == "__main__":
    main()
