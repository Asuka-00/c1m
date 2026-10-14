"""失败时报告记录完整 response detail，凭据类键遮掉。"""

from __future__ import annotations

from test_p3_exec import run

from sim.runner import FAILED, PASSED
from sim.safety import MASK, is_secret_key, redact_detail


def test_failed_step_records_full_detail():
    rep, _ = run(
        [
            {
                "reticle_hold": {
                    "reticle": "R-SIM-04",
                    "reason": "x",
                    "no_idem": True,
                    "expect": {"status": 422, "loc": ["body", "reason"]},
                }
            }
        ]
    )
    assert rep["status"] == FAILED
    step = rep["steps"][0]
    det = step["response_detail"]
    assert isinstance(det, list) and det
    assert det[0]["loc"] == ["header", "Idempotency-Key"]
    assert "type" in det[0]


def test_passed_step_has_no_detail():
    rep, _ = run(
        [
            {
                "reticle_hold": {
                    "reticle": "R-SIM-04",
                    "reason": "x",
                    "no_idem": True,
                    "expect": {"status": 422, "code": "missing", "loc": ["header", "Idempotency-Key"]},
                }
            }
        ]
    )
    assert rep["status"] == PASSED
    assert "response_detail" not in rep["steps"][0]


def test_redact_detail_keeps_loc_type_msg_ctx():
    d = [{"loc": ["body", "unit_ids"], "type": "missing", "msg": "Field required", "ctx": {"reason": "x"}}]
    assert redact_detail(d) == d


def test_redact_detail_masks_secret_keys_nested():
    d = {
        "code": "bad",
        "ctx": {
            "token": "t",
            "api_key": "k",
            "Authorization": "Bearer x",
            "pw": "p",
            "Cookie": "c",
            "client_secret": "s",
            "credential_id": "c2",
            "idempotencyKey": "i",
            "monkey": 1,
            "keyboard": 2,
        },
        "items": [{"password": "p"}],
    }
    out = redact_detail(d)
    for k in ("token", "api_key", "Authorization", "pw", "Cookie", "client_secret", "credential_id", "idempotencyKey"):
        assert out["ctx"][k] == MASK, k
    assert out["ctx"]["monkey"] == 1 and out["ctx"]["keyboard"] == 2
    assert out["items"][0]["password"] == MASK
    assert out["code"] == "bad"
    assert d["ctx"]["token"] == "t"  # 不改原对象


def test_redact_detail_masks_input_when_loc_is_secret():
    d = [
        {"loc": ["body", "password"], "type": "string_too_short", "msg": "short", "input": "hunter2"},
        {"loc": ["body", "qty"], "type": "int_parsing", "msg": "bad", "input": "abc"},
    ]
    out = redact_detail(d)
    assert out[0]["input"] == MASK and out[0]["loc"] == ["body", "password"]
    assert out[1]["input"] == "abc"


def test_is_secret_key():
    assert is_secret_key("x-api-key") and is_secret_key("SECRET") and is_secret_key("set_cookie")
    assert not is_secret_key("unit_ids") and not is_secret_key("monkey")


def test_runner_level_failure_records_detail_and_redacts():
    # 非 send() 路径（如 expect_reticle 之类后续查询失败）也由 runner 统一取最近一次响应的 detail
    from sim import client as client_mod
    from sim.client import Resp
    from sim.runner import Runner, StepFailed
    from sim.scenario import parse

    class R(Runner):
        def _step(self, sc, st, entry, seq, sent, saved):
            client_mod.LAST["resp"] = Resp(
                422, {"detail": [{"loc": ["body", "token"], "type": "x", "msg": "m", "input": "s3cr3t"}]}, 1
            )
            raise StepFailed("boom")

    from sim.client import Client

    rep = R(Client("http://127.0.0.1:1", tenant="t"), stop_on_fail=False).run(
        parse({"run_id": "r", "steps": [{"expect_e10": {"eq": "EAP-LT01", "state": "PRD"}}]})
    )
    det = rep["steps"][0].get("response_detail")
    assert det == [{"loc": ["body", "token"], "type": "x", "msg": "m", "input": MASK}]
