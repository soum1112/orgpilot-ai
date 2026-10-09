import pandas as pd
import pytest

from process_kpis import ProcessAnalytics

TEAM = {"A": "T1", "B": "T2", "C": "T3", "D": "T4"}

SEQ = pd.DataFrame([
    dict(process_id="P1", case_type="c1", step_no=1, activity="A", team="T1", optional=False),
    dict(process_id="P1", case_type="c1", step_no=2, activity="B", team="T2", optional=False),
    dict(process_id="P1", case_type="c1", step_no=3, activity="C", team="T3", optional=False),
    dict(process_id="P1", case_type="c1", step_no=4, activity="D", team="T4", optional=True),
])
TGT = pd.DataFrame([
    dict(process_id="P1", case_type="c1", activity="B", metric="stage_elapsed_hours", target_value="10",
         unit="hours", comparable="yes", target_basis="SLA", sop_wording="B within 10h", note=""),
    dict(process_id="P1", case_type="c1", activity="C", metric="not_time_based", target_value="",
         unit="", comparable="no", target_basis="SLA", sop_wording="C needs sign-off", note=""),
    dict(process_id="P1", case_type="c1", activity="*", metric="case_cycle_hours", target_value="30",
         unit="hours", comparable="yes", target_basis="KPI", sop_wording="<=30h", note=""),
])


def mk(case, spec):
    rows = []
    for i, (act, status, ts) in enumerate(spec):
        rows.append(dict(event_id=f"{case}-{i}", case_id=case, process_id="P1", case_type="c1", activity=act,
                         status=status, timestamp=ts, team=TEAM[act], location="X", location_type="site"))
    return rows


def full_case(case, b_start="12:00", b_end="20:00"):
    """A 09:00-10:00, B <b_start>-<b_end>, C 20:00 - next day 09:00 (IST)."""
    d = "2025-01-01T"
    return mk(case, [
        ("A", "started", d + "09:00:00+05:30"), ("A", "completed", d + "10:00:00+05:30"),
        ("B", "started", d + b_start + ":00+05:30"), ("B", "completed", d + b_end + ":00+05:30"),
        ("C", "started", d + "20:00:00+05:30"), ("C", "completed", "2025-01-02T09:00:00+05:30"),
    ])


def pa(rows, **kw):
    return ProcessAnalytics(pd.DataFrame(rows), TGT, SEQ, min_stage_n=1, **kw)


def stage(p, act):
    return next(s for s in p.stages_summary() if s["activity"] == act)


def test_cycle_wait_processing_elapsed_times():
    p = pa(full_case("c1"))
    s = stage(p, "B")
    assert s["mean_wait_h"] == 2.0          # B started 12:00, A completed 10:00
    assert s["mean_processing_h"] == 8.0    # 12:00 -> 20:00
    assert s["mean_elapsed_h"] == 10.0      # A completed 10:00 -> B completed 20:00
    assert p.overview()["mean_cycle_h"] == 24.0   # 09:00 -> next day 09:00


def test_incomplete_case_not_completed_and_excluded_from_cycle():
    rows = full_case("c1") + [r for r in full_case("c2") if r["activity"] != "C"]
    ov = pa(rows).overview()
    assert ov["total_cases"] == 2 and ov["completed_cases"] == 1
    assert ov["completion_rate"] == 0.5
    assert ov["mean_cycle_h"] == 24.0       # only the completed case counts


def test_duplicate_events_removed_and_reported():
    rows = full_case("c1")
    rows.append(dict(rows[0], event_id="dup"))
    p = pa(rows)
    assert p.quality["duplicate_events_removed"] == 1
    assert any("duplicate" in w for w in p.warnings())


def test_missing_and_invalid_timestamps_reported_not_silent():
    rows = full_case("c1")
    rows[1]["timestamp"] = ""
    rows[2]["timestamp"] = "N/A"
    p = pa(rows)
    assert p.quality["missing_timestamp"] == 1 and p.quality["invalid_timestamp"] == 1
    assert p.quality["rows_used"] == len(rows) - 2
    assert len(p.warnings()) >= 2


def test_utc_and_ist_timestamps_are_the_same_instant():
    rows = full_case("c1")
    rows[0]["timestamp"] = "2025-01-01T03:30:00Z"      # == 09:00 IST
    assert pa(rows).overview()["mean_cycle_h"] == 24.0


def test_empty_dataset_does_not_crash():
    empty = pd.DataFrame(columns=["case_id", "activity", "status", "timestamp"])
    p = ProcessAnalytics(empty, TGT, SEQ)
    ov = p.overview()
    assert ov["total_cases"] == 0 and ov["completion_rate"] is None
    assert p.stages_summary() == [] and p.bottlenecks() == [] and p.findings() == []
    assert p.anomalies()["counts"]["out_of_order_cases"] == 0


def test_missing_required_column_raises():
    with pytest.raises(ValueError):
        ProcessAnalytics(pd.DataFrame({"case_id": ["x"]}))


def test_breach_rate_against_target_strictly_greater():
    # c1 elapsed = 10h (== target, not a breach); c2 elapsed = 12h (breach)
    rows = full_case("c1") + full_case("c2", b_start="13:00", b_end="22:00")
    s = stage(pa(rows), "B")
    assert s["target_value"] == 10.0 and s["breach_count"] == 1 and s["breach_rate"] == 0.5


def test_non_comparable_target_is_not_compared():
    s = stage(pa(full_case("c1")), "C")
    assert s["target_value"] is None and s["breach_rate"] is None


def test_no_valid_elapsed_gives_none_not_division_error():
    rows = [r for r in full_case("c1") if r["activity"] == "A"]     # only the first activity
    s = stage(pa(rows), "A")
    assert s["n_valid_elapsed"] == 0 and s["mean_elapsed_h"] is None


def test_negative_duration_flagged_and_excluded():
    rows = full_case("c1")
    rows[3]["timestamp"] = "2025-01-01T11:00:00+05:30"   # B completed before it started (12:00)
    p = pa(rows)
    assert p.quality["negative_duration_stages"] == 1
    assert stage(p, "B")["n_valid_elapsed"] == 0
    assert p.anomalies()["counts"]["negative_duration_cases"] == 1


def test_out_of_order_sequence_detected():
    rows = full_case("c1")
    for r in rows:                       # swap the labels of A and B, keep the timestamps
        if r["activity"] == "A":
            r["activity"], r["team"] = "B", "T2"
        elif r["activity"] == "B":
            r["activity"], r["team"] = "A", "T1"
    assert pa(rows).anomalies()["counts"]["out_of_order_cases"] == 1


def test_skipped_mandatory_step_detected_but_optional_and_in_progress_are_not():
    skipped = [r for r in full_case("s") if r["activity"] != "B"]             # A and C but no B
    no_optional = full_case("ok")                                              # D (optional) absent: fine
    in_progress = [r for r in full_case("ip") if r["activity"] == "A"]         # only A so far: fine
    c = pa(skipped + no_optional + in_progress).anomalies()["counts"]
    assert c["skipped_mandatory_step_cases"] == 1


def test_rework_counted():
    rows = full_case("c1") + mk("c1", [("B", "started", "2025-01-01T21:00:00+05:30"),
                                       ("B", "completed", "2025-01-01T21:30:00+05:30")])
    assert pa(rows).anomalies()["counts"]["cases_with_rework"] == 1


def test_handoff_wait_only_when_team_changes():
    s = stage(pa(full_case("c1")), "B")
    assert s["handoff_observations"] == 1 and s["mean_handoff_wait_h"] == 2.0


def test_findings_follow_shared_contract_and_state_limitations():
    rows = []
    for i in range(5):
        rows += full_case(f"x{i}", b_start="13:00", b_end="23:00")   # elapsed 13h > 10h target
    f = pa(rows).findings()
    assert f, "expected at least one finding"
    required = {"finding_id", "domain", "title", "metric", "actual_value", "target_value", "unit",
                "severity", "scope", "evidence", "limitations"}
    assert required <= set(f[0].keys())
    assert f[0]["domain"] == "process" and f[0]["finding_id"] == "PROC-001"
    assert f[0]["evidence"][0]["source_file"] == "process_event_log.csv"
    assert any("cause" in l for l in f[0]["limitations"])


def test_envelope_shape():
    env = pa(full_case("c1")).envelope({"x": 1})
    assert env["status"] == "ok" and env["data"]["x"] == 1 and "generated_at" in env["data"]
    assert "source_files" in env["meta"] and "warnings" in env["meta"]


def test_out_of_order_cases_excluded_from_stage_timing_but_reported():
    swapped = full_case("bad")
    for r in swapped:
        if r["activity"] == "A":
            r["activity"], r["team"] = "B", "T2"
        elif r["activity"] == "B":
            r["activity"], r["team"] = "A", "T1"
    p = pa(swapped + full_case("good"))
    assert stage(p, "B")["n_valid_elapsed"] == 1           # only the well-ordered case is measured
    assert p.anomalies()["counts"]["out_of_order_cases"] == 1
    assert any("out-of-order" in w for w in p.warnings())
