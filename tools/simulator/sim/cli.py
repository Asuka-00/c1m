"""命令行：``python -m sim run scenarios/*.yaml --target http://127.0.0.1:8013``。

凭据只从环境变量读：
- ``SIM_TOKEN``：访问令牌；或者 ``SIM_USER`` + ``SIM_PASSWORD``（启动时登录换令牌，只放内存）。
- ``SIM_TENANT``：租户 id（X-Tenant-ID）。

目标与安全（D54）：
- ``--target`` > 环境变量 ``SIM_TARGET`` > 场景里的 ``target``。
- 只允许 127.0.0.1/localhost；端口必须列在 ``SIM_ALLOWED_PORTS``（逗号分隔）里，默认空 = 全部拒绝。
- ``--mode b11``（或 ``SIM_MODE=b11``）：占位，改走 ``POST /mes/eap/events``，默认 manual。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from sim.adapters import MODES
from sim.client import Client
from sim.runner import FAILED, PASSED, SKIPPED, Runner
from sim.safety import UnsafeTarget, check_target, env
from sim.scenario import ScenarioError, load


def _client(target: str) -> Client:
    c = Client(target, tenant=env("SIM_TENANT"))
    tok = env("SIM_TOKEN")
    if tok:
        c.token = tok
    else:
        user, pw = env("SIM_USER"), env("SIM_PASSWORD")
        if not (user and pw):
            raise SystemExit("缺少凭据：设置 SIM_TOKEN，或 SIM_USER + SIM_PASSWORD")
        c.login(user, pw)
    return c


def resolve_target(cli: str | None, scenario_target: str | None) -> str | None:
    return cli or os.environ.get("SIM_TARGET") or scenario_target


def cmd_validate(args) -> int:
    """只校验格式，不连后端；给了 --target/SIM_TARGET 时顺带检查白名单。"""
    rc = 0
    for f in args.scenarios:
        try:
            sc = load(f)
            target = resolve_target(args.target, None)
            note = ""
            if target:
                try:
                    note = f" target={check_target(target)}"
                except UnsafeTarget as e:
                    note = f" target 被拒：{e}"
                    rc = 2
            needs = sc.required_adapters(args.mode)
            print(f"OK   {f}  run_id={sc.run_id} steps={len(sc.steps)} needs={needs}{note}")
        except (ScenarioError, OSError) as e:
            print(f"BAD  {f}: {e}")
            rc = 2
    return rc


def cmd_run(args) -> int:
    try:
        scs = [load(f) for f in args.scenarios]
    except (ScenarioError, OSError) as e:
        print(f"场景错误：{e}", file=sys.stderr)
        return 2
    target = resolve_target(args.target, scs[0].target if scs else None)
    if not target:
        print("没有 --target / SIM_TARGET，场景里也没写 target", file=sys.stderr)
        return 2
    try:
        target = check_target(target)
    except UnsafeTarget as e:
        print(f"拒绝：{e}", file=sys.stderr)
        return 2
    print(f"目标 {target}  模式 {args.mode}")
    runner = Runner(_client(target), mode=args.mode)
    reports = []
    for sc in scs:
        rep = runner.run(sc)
        reports.append(rep)
        mark = {PASSED: "PASS", FAILED: "FAIL", SKIPPED: "SKIP"}.get(rep["status"], "ERR ")
        print(f"[{mark}] {sc.name} (run_id={sc.run_id})" + (f" - {rep['reason']}" if rep["reason"] else ""))
        for s in rep["steps"]:
            ok = {True: "ok", False: "FAIL", None: "skip"}[s.get("ok")]
            extra = f" HTTP {s['status']}" if "status" in s else ""
            extra += f" code={s['code']}" if s.get("code") else ""
            extra += f" ext={s['external_event_id']}" if s.get("external_event_id") else ""
            print(
                f"    {s['step']:>2}. {s['kind']:<14}{ok:<5}{extra}" + (f"  {s['message']}" if s.get("message") else "")
            )
    if args.report:
        Path(args.report).write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"报告：{args.report}")
    return 1 if any(r["status"] == FAILED for r in reports) else 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="sim", description="CIM 设备模拟器（模式 A）")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="执行场景")
    r.add_argument("scenarios", nargs="+")
    r.add_argument("--report", help="JSON 报告输出路径（不含令牌）")
    r.set_defaults(fn=cmd_run)
    v = sub.add_parser("validate", help="只校验场景格式，不连后端")
    v.add_argument("scenarios", nargs="+")
    v.set_defaults(fn=cmd_validate)
    for x in (r, v):
        x.add_argument("--target", help="覆盖场景 target（也可用 SIM_TARGET）；端口须在 SIM_ALLOWED_PORTS 里")
        x.add_argument(
            "--mode",
            choices=MODES,
            default=os.environ.get("SIM_MODE") or "manual",
            help="manual（默认，手工接口，不传 source）；b11 占位，走 POST /mes/eap/events",
        )
    a = p.parse_args(argv)
    return a.fn(a)
