"""
validate_detectors.py - checks the anomaly detectors against the answer key
(process_injected_issues.csv). Run:  python validate_detectors.py [folder_with_csvs]
The answer key is for TESTING only; it is never used by the analytics themselves.
"""
import sys
from pathlib import Path
import pandas as pd
from process_kpis import ProcessAnalytics

folder = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent
pa = ProcessAnalytics.from_files(folder)
key = pd.read_csv(folder / "process_injected_issues.csv", dtype=str)


def score(name, flagged, issue_type):
    f, i = set(flagged), set(key[key.issue_type == issue_type].case_id)
    tp = len(f & i)
    prec = tp / len(f) if f else float("nan")
    rec = tp / len(i) if i else float("nan")
    print(f"{name:<26} flagged={len(f):>4}  injected={len(i):>4}  correct={tp:>4}  precision={prec:.2f}  recall={rec:.2f}")


score("out-of-order sequence", pa._ooo, "out_of_order_sequence")
score("skipped mandatory step", [c for c, _ in pa._skipped], "missing_activity")
score("negative duration", pa.stages[pa.stages.negative_duration].case_id.unique(), "negative_duration")
score("stalled/abandoned", pa.cases[pa.cases.state == "stalled_or_abandoned"].case_id, "abandoned_case")
score("rework (repeated step)", pa.stages[pa.stages.completed_count > 1].case_id.unique(), "rework_repeated_activity")
q = pa.quality
print("\nEvent-level defects (counted, then excluded):")
for k, t in [("missing_timestamp", "missing_timestamp"), ("invalid_timestamp", "invalid_timestamp"),
             ("duplicate_events_removed", "duplicate_event")]:
    print(f"  {k:<26} found={q[k]:>4}  injected={(key.issue_type == t).sum():>4}")
