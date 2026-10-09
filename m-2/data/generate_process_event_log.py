"""
Synthetic process event-log generator for OrgPilot AI - Member 2 (Process Intelligence).

Built from the four HUL O2V SOPs (HR-TAL-001, HR-TAL-002, SCM-ECO-001, SCM-ECO-002):
activities, responsible teams and timings follow each SOP's Section 5 process flow.
ALL records are synthetic. Nothing here is real HUL process data.
"""
import os
import numpy as np
import pandas as pd
from datetime import datetime, timedelta, timezone

OUT = os.path.dirname(os.path.abspath(__file__))
rng = np.random.default_rng(2026)

IST = timezone(timedelta(hours=5, minutes=30))
CUTOFF = datetime(2026, 9, 30, 23, 59, tzinfo=IST)       # data extraction date
START_MIN = datetime(2024, 1, 1, 9, 0, tzinfo=IST)
START_MAX = datetime(2026, 9, 20, 18, 0, tzinfo=IST)
SPAN = (START_MAX - START_MIN).total_seconds()

SITES = ["Nalagarh", "Etah", "Haridwar", "Baddi", "Orai", "Rajpura", "Sumerpur", "Sonipat",
         "Dowlaiswaram (Rajahmundry)", "Cochin", "Hosur", "Mangaluru", "Mysuru", "Puducherry",
         "Mumbai (Andheri HQ)", "Gurugram", "Kolkata", "Bengaluru", "Chennai"]
RURAL_STATES = ["Uttar Pradesh", "Bihar", "Madhya Pradesh", "Rajasthan", "Maharashtra", "West Bengal",
                "Odisha", "Andhra Pradesh", "Telangana", "Karnataka", "Tamil Nadu", "Assam",
                "Jharkhand", "Chhattisgarh", "Gujarat", "Punjab"]

# activity tuple: (activity, team, mean_wait_h, mean_processing_h, probability_present, rework_probability)
PROCS = [
    dict(process_id="HR-TAL-001", case_type="planning_submission", prefix="HRTAL1", n=500, loc="sites", acts=[
        ("Issue planning calendar & templates", "HR Business Partner", 0, 6, 1.0, 0.0),
        ("Submit location/function requirements", "Plant HR Manager / Function Head", 24, 180, 1.0, 0.0),
        ("Validate against revenue forecast", "Finance Business Partner", 30, 50, 1.0, 0.0),
        ("Model diversity & attrition scenarios", "D&I Lead", 12, 36, 1.0, 0.0),
        ("Consolidate & review with CHRO", "HR Business Partner", 70, 36, 1.0, 0.05),
        ("ExCo / Board approval", "Chief HR Officer", 90, 20, 1.0, 0.0),
        ("Publish approved budget into HRIS", "HR Business Partner", 24, 24, 1.0, 0.0),
    ]),
    dict(process_id="HR-TAL-002", case_type="hire", prefix="HRTAL2H", n=700, loc="sites", acts=[
        ("Release requisition", "Talent Acquisition Partner", 0, 4, 1.0, 0.0),
        ("Source & screen candidates", "Talent Acquisition Partner", 12, 240, 1.0, 0.04),
        ("Interview & offer", "Reporting Manager / TA Partner", 30, 190, 1.0, 0.06),
        ("Onboard in HRIS", "HR Shared Services", 14, 4, 1.0, 0.0),
        ("Induction & role setup", "Plant HR Manager / L&D", 24, 96, 1.0, 0.0),
    ]),
    dict(process_id="HR-TAL-002", case_type="exit", prefix="HRTAL2X", n=250, loc="sites", acts=[
        ("Exit trigger recorded", "HR Shared Services", 0, 4, 1.0, 0.0),
        ("Exit processing", "Payroll Team", 48, 500, 1.0, 0.0),
    ]),
    dict(process_id="SCM-ECO-001", case_type="vendor_onboarding", prefix="SCMECO1", n=600, loc="sites_proc", acts=[
        ("Vendor identification", "Category Buyer", 0, 24, 1.0, 0.0),
        ("RPP documentation submission", "Prospective Vendor", 24, 150, 1.0, 0.12),
        ("RPP compliance assessment", "Responsible Sourcing Analyst", 24, 190, 1.0, 0.0),
        ("On-site audit", "Third-Party Auditor", 130, 260, 0.35, 0.0),
        ("Commercial & compliance approval", "Category Manager / CPO", 80, 24, 1.0, 0.0),
        ("Vendor master creation", "Category Buyer", 12, 6, 1.0, 0.0),
    ]),
    dict(process_id="SCM-ECO-002", case_type="partner_onboarding", prefix="SCMECO2P", n=450, loc="states", acts=[
        ("Coverage gap identification", "Rural Sales Development Officer", 0, 12, 1.0, 0.0),
        ("Candidate identification & screening", "Rural Sales Development Officer", 24, 200, 1.0, 0.0),
        ("Orientation & training", "Rural Sales Development Officer", 100, 40, 1.0, 0.0),
        ("Credit linkage & initial stock", "Micro-credit Coordinator", 130, 60, 1.0, 0.05),
        ("Partner activation in RDMS", "Area Distribution Manager", 70, 8, 1.0, 0.0),
    ]),
    dict(process_id="SCM-ECO-002", case_type="order_fulfilment", prefix="SCMECO2O", n=800, loc="states", acts=[
        ("Monthly order placement", "Shakti Partner", 0, 2, 1.0, 0.0),
        ("Order fulfillment & delivery", "Logistics / Rural Sales Officer", 36, 84, 1.0, 0.0),
    ]),
]


def ln(mean, sigma=0.55):
    if mean <= 0:
        return 0.0
    mu = np.log(mean) - sigma ** 2 / 2
    return float(rng.lognormal(mu, sigma))


def hrs(x):
    return timedelta(hours=float(x))


def to_business(dt):
    if dt.hour < 9:
        return dt.replace(hour=9, minute=int(rng.integers(0, 60)), second=0, microsecond=0)
    if dt.hour >= 19:
        return (dt + timedelta(days=1)).replace(hour=9, minute=int(rng.integers(0, 60)), second=0, microsecond=0)
    return dt.replace(second=0, microsecond=0)


def pick_location(kind):
    if kind == "states":
        return str(rng.choice(RURAL_STATES)), "state"
    w = np.array([1] * 14 + ([8, 1, 1, 1, 1] if kind == "sites_proc" else [3, 1.5, 1, 1.5, 1]), float)
    return str(rng.choice(SITES, p=w / w.sum())), "site"


def modifier(p, act, loc, ref, progress):
    """Deliberately planted patterns so the dashboard has something to find (see README)."""
    wm = pm = 1.0
    pid, ct = p["process_id"], p["case_type"]
    if pid == "SCM-ECO-002" and ct == "order_fulfilment" and act == "Order fulfillment & delivery" and 6 <= ref.month <= 9:
        wm = pm = 1.5
    if pid == "SCM-ECO-002" and ct == "partner_onboarding" and act == "Credit linkage & initial stock" and 6 <= ref.month <= 9:
        wm *= 1.3
    if pid == "HR-TAL-002" and ct == "hire" and act == "Interview & offer":
        if loc in ("Orai", "Sumerpur", "Etah"):
            wm *= 1.4
            pm *= 1.4
        elif loc == "Hosur":
            wm *= 0.85
            pm *= 0.85
    if pid == "SCM-ECO-001" and act == "On-site audit":
        wm *= (1 + 0.35 * progress)
    return wm, pm


def gen_case(p, idx):
    case_id = f"{p['prefix']}-{idx:05d}"
    loc, loc_type = pick_location(p["loc"])
    t0 = to_business(START_MIN + timedelta(seconds=float(rng.uniform(0, SPAN))))
    progress = (t0 - START_MIN).total_seconds() / SPAN
    rows, oracle = [], []
    prev_done, act_idx = None, 0
    base = dict(case_id=case_id, process_id=p["process_id"], case_type=p["case_type"],
                location=loc, location_type=loc_type)
    for act, team, wm_mean, pm_mean, p_present, p_rework in p["acts"]:
        if p_present < 1.0 and rng.random() > p_present:
            continue
        occ = 2 if (p_rework > 0 and rng.random() < p_rework) else 1
        for o in range(occ):
            ref = prev_done if prev_done is not None else t0
            wmult, pmult = modifier(p, act, loc, ref, progress)
            if prev_done is None:
                started = t0
            else:
                started = to_business(prev_done + hrs(ln(wm_mean if o == 0 else wm_mean * 0.5 + 4) * wmult))
            done = started + hrs(ln(pm_mean if o == 0 else pm_mean * 0.6) * pmult)
            rows.append(dict(base, activity=act, team=team, status="started", ts=started, act_idx=act_idx))
            rows.append(dict(base, activity=act, team=team, status="completed", ts=done, act_idx=act_idx))
            prev_done = done
            act_idx += 1
        if occ == 2:
            oracle.append(dict(issue_type="rework_repeated_activity", case_id=case_id, event_id="",
                               detail=f"'{act}' performed twice (legitimate rework, not an error)"))
    n_act = act_idx

    # at most one injected defect per case
    u = rng.random()
    if u < 0.03 and n_act >= 3:
        k = int(rng.integers(1, n_act))
        keep_started = rng.random() < 0.5
        rows = [r for r in rows if r["act_idx"] < k or (r["act_idx"] == k and r["status"] == "started" and keep_started)]
        oracle.append(dict(issue_type="abandoned_case", case_id=case_id, event_id="",
                           detail=f"Case stops after {k} completed activities"))
    elif u < 0.05 and n_act >= 4:
        k = int(rng.integers(1, n_act - 1))
        name = next(r["activity"] for r in rows if r["act_idx"] == k)
        rows = [r for r in rows if r["act_idx"] != k]
        oracle.append(dict(issue_type="missing_activity", case_id=case_id, event_id="",
                           detail=f"Mandatory/performed activity '{name}' has no events"))
    elif u < 0.075 and n_act >= 2:
        i = int(rng.integers(0, n_act - 1))
        a = [r for r in rows if r["act_idx"] == i]
        b = [r for r in rows if r["act_idx"] == i + 1]
        na, nb = a[0]["activity"], b[0]["activity"]
        ta, tb = a[0]["team"], b[0]["team"]
        for r in a:
            r["activity"], r["team"] = nb, tb
        for r in b:
            r["activity"], r["team"] = na, ta
        oracle.append(dict(issue_type="out_of_order_sequence", case_id=case_id, event_id="",
                           detail=f"'{na}' and '{nb}' logged in swapped order"))
    elif u < 0.08 and n_act >= 1:
        i = int(rng.integers(0, n_act))
        s = next(r for r in rows if r["act_idx"] == i and r["status"] == "started")
        c = next(r for r in rows if r["act_idx"] == i and r["status"] == "completed")
        c["ts"] = s["ts"] - hrs(rng.uniform(1, 6))
        oracle.append(dict(issue_type="negative_duration", case_id=case_id, event_id="",
                           detail=f"'{s['activity']}' completed before it started"))

    kept = [r for r in rows if r["ts"] <= CUTOFF]
    if len(kept) < len(rows):
        oracle.append(dict(issue_type="in_progress_at_cutoff", case_id=case_id, event_id="",
                           detail="Case still open at extraction date (informational, not a defect)"))
    return kept, oracle


rows, oracle = [], []
for p in PROCS:
    for i in range(1, p["n"] + 1):
        r, o = gen_case(p, i)
        rows += r
        oracle += o

rows.sort(key=lambda r: r["ts"])
for i, r in enumerate(rows, 1):
    r["event_id"] = f"EVT-{i:06d}"
    r["ts_str"] = r["ts"].isoformat(timespec="seconds")

N = len(rows)
perm = rng.permutation(N)
n_dup, n_miss, n_inv, n_utc = int(N * .015), int(N * .007), int(N * .003), int(N * .005)
dup_idx = perm[:n_dup]
miss_idx = perm[n_dup:n_dup + n_miss]
inv_idx = perm[n_dup + n_miss:n_dup + n_miss + n_inv]
utc_idx = perm[n_dup + n_miss + n_inv:n_dup + n_miss + n_inv + n_utc]

BAD = ["31-02-2025 10:00", "N/A", "0000-00-00 00:00:00", "2025-13-45T99:99:00", "TBD"]
for i in utc_idx:
    rows[i]["ts_str"] = rows[i]["ts"].astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    oracle.append(dict(issue_type="utc_timestamp_format", case_id=rows[i]["case_id"], event_id=rows[i]["event_id"],
                       detail="Valid instant written in UTC (Z) instead of IST +05:30"))
for i in miss_idx:
    rows[i]["ts_str"] = ""
    oracle.append(dict(issue_type="missing_timestamp", case_id=rows[i]["case_id"], event_id=rows[i]["event_id"],
                       detail="Timestamp blank"))
for i in inv_idx:
    rows[i]["ts_str"] = str(rng.choice(BAD))
    oracle.append(dict(issue_type="invalid_timestamp", case_id=rows[i]["case_id"], event_id=rows[i]["event_id"],
                       detail="Timestamp not parseable"))
dups, nxt = [], N + 1
for i in dup_idx:
    d = dict(rows[i])
    d["event_id"] = f"EVT-{nxt:06d}"
    nxt += 1
    dups.append(d)
    oracle.append(dict(issue_type="duplicate_event", case_id=d["case_id"], event_id=d["event_id"],
                       detail=f"Exact duplicate of {rows[i]['event_id']}"))
rows = sorted(rows + dups, key=lambda r: r["ts"])

COLS = ["event_id", "case_id", "process_id", "case_type", "activity", "status", "timestamp", "team",
        "location", "location_type"]
log = pd.DataFrame([{**{c: r[c] for c in COLS if c != "timestamp"}, "timestamp": r["ts_str"]} for r in rows])[COLS]
log.to_csv(f"{OUT}/process_event_log.csv", index=False)

oc = pd.DataFrame(oracle)
oc.insert(0, "issue_id", [f"ISS-{i:05d}" for i in range(1, len(oc) + 1)])
oc.to_csv(f"{OUT}/process_injected_issues.csv", index=False)

# ---------------- expected sequences ----------------
seq = []
for p in PROCS:
    for n, (act, team, wm, pm, pp, rw) in enumerate(p["acts"], 1):
        seq.append(dict(process_id=p["process_id"], case_type=p["case_type"], step_no=n, activity=act, team=team,
                        optional=pp < 1.0,
                        condition=("Only for High risk_rating vendors or spend > Rs 5 Cr/yr (SCM-ECO-001 Business Rules)"
                                   if pp < 1.0 else "")))
pd.DataFrame(seq).to_csv(f"{OUT}/process_expected_sequences.csv", index=False)

# ---------------- targets (from SOP text) ----------------
T = []


def t(pid, ct, act, metric, val, unit, comp, basis, doc, section, wording, note=""):
    T.append(dict(process_id=pid, case_type=ct, activity=act, metric=metric, target_value=val, unit=unit,
                  comparable=comp, target_basis=basis, source_doc=doc, source_section=section,
                  sop_wording=wording, note=note))


H = "stage_elapsed_hours"
t("HR-TAL-001", "planning_submission", "Submit location/function requirements", H, 240, "hours", "yes", "SLA", "HR-TAL-001", "5 step 2", "Late submissions escalated after Day 10", "Calendar days assumed")
t("HR-TAL-001", "planning_submission", "Consolidate & review with CHRO", H, 72, "hours", "approximate", "SLA", "HR-TAL-001", "5 step 5", "Review completed within 3 business days", "Business days approximated as 72 calendar hours")
t("HR-TAL-001", "planning_submission", "Issue planning calendar & templates", "not_time_based", "", "", "no", "SLA", "HR-TAL-001", "5 step 1", "100% of locations receive template by Week 1", "Coverage %, not a duration")
t("HR-TAL-001", "planning_submission", "Validate against revenue forecast", "not_time_based", "", "", "no", "SLA", "HR-TAL-001", "5 step 3", "Variance >5% requires written justification", "Variance rule, not a duration")
t("HR-TAL-002", "hire", "Source & screen candidates", H, 360, "hours", "approximate", "timing_window", "HR-TAL-002", "5 step 2", "Days 1-15", "Window length derived from cumulative day boundaries")
t("HR-TAL-002", "hire", "Interview & offer", H, 240, "hours", "approximate", "timing_window", "HR-TAL-002", "5 step 3", "Days 15-25", "Window length derived from cumulative day boundaries")
t("HR-TAL-002", "hire", "Onboard in HRIS", H, 24, "hours", "approximate", "SLA", "HR-TAL-002", "5 step 4", "Record created within 24 hours of joining", "SOP clock starts at joining date; log measures from previous step completion")
t("HR-TAL-002", "hire", "Induction & role setup", H, 168, "hours", "approximate", "timing_window", "HR-TAL-002", "5 step 5", "Week 1", "")
t("HR-TAL-002", "exit", "Exit processing", H, 720, "hours", "yes", "SLA", "HR-TAL-002", "5 step 8", "Full-and-final settlement within 30 days of last working day", "Calendar days assumed")
t("SCM-ECO-001", "vendor_onboarding", "RPP documentation submission", H, 240, "hours", "approximate", "timing_window", "SCM-ECO-001", "5 step 2", "Days 1-10", "Window length derived")
t("SCM-ECO-001", "vendor_onboarding", "RPP compliance assessment", H, 240, "hours", "approximate", "timing_window", "SCM-ECO-001", "5 step 3", "Days 10-20", "Window length derived")
t("SCM-ECO-001", "vendor_onboarding", "On-site audit", H, 360, "hours", "approximate", "timing_window", "SCM-ECO-001", "5 step 4", "Days 20-35", "Window length derived")
t("SCM-ECO-001", "vendor_onboarding", "Commercial & compliance approval", H, 120, "hours", "approximate", "timing_window", "SCM-ECO-001", "5 step 5", "Days 35-40", "Window length derived")
t("SCM-ECO-001", "vendor_onboarding", "*", "case_cycle_hours", 960, "hours", "yes", "KPI", "SCM-ECO-001", "7 KPI: Onboarding cycle time", "<=40 days", "Identification to vendor master creation")
t("SCM-ECO-002", "partner_onboarding", "Candidate identification & screening", H, 336, "hours", "approximate", "timing_window", "SCM-ECO-002", "5 step 2", "Weeks 1-2", "")
t("SCM-ECO-002", "partner_onboarding", "Orientation & training", H, 168, "hours", "approximate", "timing_window", "SCM-ECO-002", "5 step 3", "Week 3", "")
t("SCM-ECO-002", "partner_onboarding", "Credit linkage & initial stock", H, 168, "hours", "approximate", "timing_window", "SCM-ECO-002", "5 step 4", "Week 4", "")
t("SCM-ECO-002", "partner_onboarding", "Partner activation in RDMS", H, 120, "hours", "approximate", "SLA", "SCM-ECO-002", "5 step 5", "Record created within 5 business days of stock issuance", "Business days approximated as 120 calendar hours")
t("SCM-ECO-002", "order_fulfilment", "Order fulfillment & delivery", H, 168, "hours", "yes", "SLA", "SCM-ECO-002", "5 step 7", "Delivery within 7 days of order placement", "SOP allows seasonal exceptions (monsoon) - not modelled in the log")
tg = pd.DataFrame(T)
tg.insert(0, "target_id", [f"TGT-{i:03d}" for i in range(1, len(tg) + 1)])
tg.to_csv(f"{OUT}/process_targets.csv", index=False)

# ---------------- README ----------------
n_cases = log["case_id"].nunique()
ic = oc["issue_type"].value_counts().to_dict()
readme = f"""# HUL Process Event Log (SYNTHETIC) - OrgPilot AI, Member 2

**Everything in this folder is synthetic.** No real HUL process data exists publicly. Activities, responsible teams,
timing windows and SLAs come from the four O2V SOPs (HR-TAL-001, HR-TAL-002, SCM-ECO-001, SCM-ECO-002); every case,
timestamp and delay is generated.

## Files
| File | Purpose |
|---|---|
| `process_event_log.csv` | Main input: {len(log):,} event rows, {n_cases:,} cases, 6 case types across 4 processes |
| `process_targets.csv` | Targets taken from the SOP text, with a `comparable` flag (yes / approximate / no) |
| `process_expected_sequences.csv` | Expected activity order per case type, with optional steps flagged (for sequence-anomaly checks) |
| `process_injected_issues.csv` | Answer key listing every deliberately injected data defect. Use it to TEST your detectors; do not load it as input data |
| `generate_process_event_log.py` | Regenerates everything (fixed seed 2026) |

## Event log columns
`event_id`, `case_id`, `process_id`, `case_type`, `activity`, `status` (started / completed), `timestamp`
(ISO 8601, IST +05:30 unless noted below), `team`, `location`, `location_type` (site = plant/office city, state = Shakti rural state).

## How metrics map to the log
- Wait time = `started` of an activity minus `completed` of the previous activity.
- Stage elapsed time (`stage_elapsed_hours`) = `completed` of an activity minus `completed` of the previous activity.
- Case cycle time = last event minus first event of a case.
- Handoff delay = wait time where the `team` differs from the previous activity's team.

## Targets
`comparable = yes`: SOP gives a clear duration. `approximate`: SOP uses business days, a timing window, or a clock that starts
at a different event than the log measures (see `note`). `no`: SOP rule is not a duration. Only compare when `comparable` is yes
or approximate, and label approximate comparisons as such.

## Planted patterns (for demo; NOT real HUL findings)
- SCM-ECO-001: on-site audit is the slowest stage and its wait grows over 2024-2026; cases with an audit tend to exceed the 40-day cycle target.
- SCM-ECO-002: credit linkage often exceeds its window, worse in Jun-Sep; order delivery slows in Jun-Sep.
- HR-TAL-002: Interview & offer is slower at Orai, Sumerpur and Etah, and faster at Hosur.
- HR-TAL-001: CHRO review tends to exceed the 3-business-day SLA.
Treat any such pattern as a signal to investigate, never as a proven cause.

## Injected data-quality issues (answer key: `process_injected_issues.csv`)
Counts: {ic}
- `in_progress_at_cutoff` and `rework_repeated_activity` are informational, not defects.
- Data cutoff (extraction date): 2026-09-30. Cases started after ~2026-09-20 may be open.
- `utc_timestamp_format` rows are valid instants written with a Z suffix. Parse with a timezone-aware parser.
- Duplicates have a different `event_id` but identical case, activity, status and timestamp.
- On-site audit is legitimately skipped in about 65% of vendor cases (optional), so absence there is not an anomaly.

## Limitations
Case IDs are independent of the Talent/Ecosystem master data (no employee/vendor IDs are linked). Weekends and holidays are not modelled.
"""
open(f"{OUT}/README.md", "w").write(readme)
print("events:", len(log), "cases:", n_cases)
print(oc["issue_type"].value_counts())
