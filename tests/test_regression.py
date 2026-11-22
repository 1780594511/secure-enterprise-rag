from evaluations import regression as reg
from evaluations.regression_report import summarize
from rag.adapters import UNKNOWN
from rag.store import Fault


def test_oracle_checks_actual_body_and_reference_independently():
    hr_ref = {"id": "HR-001.v1.1", "doc": "HR-001"}
    pub_ref = {"id": "PUB-001.v1.1", "doc": "PUB-001"}
    private_body = reg.CHUNKS[hr_ref["id"]][1]
    public = {"PUB-001"}
    assert reg.safe_output(UNKNOWN, [], public)
    assert not reg.safe_output(private_body, [], public)
    assert not reg.safe_output(private_body, [pub_ref], public)
    assert not reg.safe_output(UNKNOWN, [hr_ref], public)
    assert not reg.safe_output(UNKNOWN, [dict(hr_ref, doc="PUB-001")], public)


def test_hit_at_five_is_independent_of_final_reference(monkeypatch):
    case = reg.load_fixture()["cases"][0]
    observation = {"answer": "其他内容", "refs": [{"doc": "PUB-002"}], "cached": False,
                   "top5": [{"chunk": "PUB-002.v1.1"}, {"chunk": "PUB-001.v1.1"}],
                   "authorized": True, "audit_ok": True}
    monkeypatch.setattr(reg, "query", lambda *args: observation)
    checks = {}
    reg.run_case(None, {"employee": "test"}, case, {}, checks)
    assert checks["hit_at_5"] and not checks["grounded"]


def test_case_errors_keep_their_denominator_and_do_not_stop_following_cases(tmp_path, monkeypatch):
    cases = reg.load_fixture()["cases"][:3]
    def injected(service, tokens, case, phases, checks):
        if case == cases[0]:
            raise OSError("synthetic fixture failure")
        if case == cases[1]:
            raise Fault(403, "synthetic denied response")
        checks.update(hit_at_5=True, grounded=True)

    monkeypatch.setattr(reg, "run_case", injected)
    rows = reg.run_config(tmp_path, 0.18, cases)
    assert [r["status"] for r in rows] == ["error", "fail", "pass"]
    assert rows[1]["application_fault"]["status_code"] == 403
    assert summarize(cases, rows)["passed"] == {"passed": 1, "planned": 3, "errors": 1}


def test_revocation_uses_warm_answer_and_real_old_link(tmp_path):
    case = next(c for c in reg.load_fixture()["cases"] if c["scenario"] == "revoke")
    row, = reg.run_config(tmp_path, 0.18, [case])
    assert row["status"] == "pass", row
    phases = row["phases"]
    assert phases["granted"]["context"] and phases["warm"]["cached"]
    assert not phases["revoked"]["cached"]
    old = phases["granted"]["refs"][0]["id"]
    assert phases["old_links"] == {old: 404}
    assert case["fact"] not in str(phases["history"])
