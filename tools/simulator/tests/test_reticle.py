from datetime import datetime, timedelta, timezone

from sim.reticle import check_backfill_time, check_time_order, resolve_relative

NOW = datetime(2026, 10, 15, 2, 0, 0, tzinfo=timezone.utc)


def kinds(v):
    return [x.get("ctx", {}).get("reason", x["type"]) for x in check_backfill_time(v, NOW)]


def test_future_boundary_459_500_501():
    assert kinds(resolve_relative("$now+299s", NOW)) == []
    assert kinds(resolve_relative("$now+300s", NOW)) == []  # 正好 5:00 放行
    assert kinds(resolve_relative("$now+301s", NOW)) == ["future_time"]
    assert kinds(resolve_relative("$now-1h", NOW)) == []


def test_timezone_required_and_offsets():
    assert kinds("2026-10-15T01:00:00") == ["timezone_required"]
    assert kinds("2026-10-15T10:04:59+08:00") == []
    assert kinds("2026-10-15T10:05:01+08:00") == ["future_time"]
    assert kinds(None) == [] and kinds("not-a-time") == ["datetime_parsing"]


def test_time_order_equal_is_legal():
    m = NOW - timedelta(hours=1)
    assert check_time_order(m, m) is None
    assert check_time_order(m - timedelta(seconds=1), m) == {"status": 409, "code": "time_out_of_order"}
    assert check_time_order(m, None) is None


def test_resolve_passthrough():
    assert resolve_relative("2026-10-15T00:00:00Z", NOW) == "2026-10-15T00:00:00Z" and resolve_relative(5, NOW) == 5


def test_scenario_d82_backfill_cases():
    from sim.scenario import load

    sc = load("scenarios/p3-draft/reticle-report.yaml")
    bt = [s for s in sc.steps if str(s.args.get("idem", "")).startswith("ret-rep-bt")]
    fields = {"reticle_mount": "mounted_at", "reticle_unmount": "unmounted_at", "reticle_incident": "occurred_at"}
    for kind, f in fields.items():
        vals = {s.args.get(f): s.args["expect"]["status"] for s in bt if s.kind == kind}
        assert vals["$now+301s"] == 422 and vals["2026-10-15T01:00:00"] == 422 and vals["$now-1h"] == 409
    mnt = {
        s.args["mounted_at"]: s.args["expect"]["status"]
        for s in bt
        if s.kind == "reticle_mount" and s.args["reticle"] != "R-NOT-EXIST"
    }
    assert mnt["$now+299s"] == 200 and mnt["$now+300s"] in (200, 409)
    nx = [s.args["expect"]["status"] for s in bt if s.args["reticle"] == "R-NOT-EXIST"]
    assert nx == [422, 422, 404, 422]  # body 阶段先于 404


def test_d82_cont2_floor_excludes_usage_for_mount_but_not_incident():
    from sim.reticle import time_floor

    st, um, us = NOW - timedelta(hours=3), NOW - timedelta(hours=2), NOW - timedelta(minutes=10)
    assert time_floor("mount", [st], [um], [us]) == um  # usage 不计
    assert time_floor("unmount", [st], [], [us]) == st
    assert time_floor("incident", [st], [um], [us]) == us  # incident 计入最近 usage
    assert time_floor("mount") is None


def test_d82_cont2_incident_rules():
    from sim.reticle import check_incident, incident_unmount_time

    mounted = NOW - timedelta(hours=2)
    usage = NOW - timedelta(hours=1)
    assert check_incident(NOW - timedelta(minutes=90), usage, mounted) == TOO  # 早于最近 usage
    assert check_incident(NOW - timedelta(hours=3), None, mounted) == TOO  # 早于当前 mounted_at -> 整体 409
    assert check_incident(mounted, None, mounted) is None  # 相等合法
    occ = NOW - timedelta(minutes=30)
    assert incident_unmount_time(occ, NOW) == occ and incident_unmount_time(None, NOW) == NOW


TOO = {"status": 409, "code": "time_out_of_order"}
