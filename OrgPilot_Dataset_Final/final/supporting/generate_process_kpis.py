"""OrgPilot AI - Member 2 (Process Intelligence)
Builds a SYNTHETIC IT-service-request event log and computes process KPIs with Pandas.
To run on real public benchmark data (e.g. BPIC 2012/2013/2014), skip build_log() and load a CSV with
columns: case_id, activity, timestamp, resource(team). Everything below is deterministic Pandas."""
import numpy as np, pandas as pd, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
OUT = "/mnt/user-data/outputs/Member_2/"
rng = np.random.default_rng(42)

# step: (activity, team, mean wait hours BEFORE step, sd)
FLOW = [("Request Submitted","Requester",0,0),
        ("Triage","Service Desk",2,1),
        ("Assigned to Team","Service Desk",3,1.5),
        ("Manager Approval","Engineering Manager",30,14),   # planted bottleneck
        ("Security Review","Security Team",20,9),           # planted bottleneck
        ("Implementation","Dev Team",8,4),
        ("QA Verification","QA Team",6,3),
        ("Closed - Completed","Service Desk",2,1)]

def build_log(n=600):
    rows=[]
    start0=pd.Timestamp("2024-01-01 09:00")
    for i in range(1,n+1):
        cid=f"REQ-{i:04d}"
        t=start0+pd.Timedelta(days=float(rng.uniform(0,180)))
        outcome="Completed"; r=rng.random()
        stop_after=None
        if r<0.12: outcome="Rejected"; stop_after="Manager Approval"
        elif r<0.18: outcome="Cancelled"; stop_after=rng.choice(["Triage","Security Review"])
        for act,team,m,sd in FLOW:
            if m: t+=pd.Timedelta(hours=max(0.2,rng.normal(m,sd)))
            rows.append((cid,act,t,team))
            if stop_after==act:
                t+=pd.Timedelta(hours=1)
                rows.append((cid,"Closed - "+outcome,t,"Service Desk")); break
    return pd.DataFrame(rows,columns=["case_id","activity","timestamp","resource"])

df=build_log().sort_values(["case_id","timestamp"]).reset_index(drop=True)
df["data_label"]="synthetic demo data"
df.to_csv(OUT+"process_event_log_synthetic.csv",index=False)

# --- case-level KPIs
g=df.groupby("case_id")
cs=g["timestamp"].agg(start="min",end="max")
cs["cycle_days"]=((cs.end-cs.start).dt.total_seconds()/86400).round(2)
cs["events"]=g.size()
cs["outcome"]=g["activity"].last().str.replace("Closed - ","",regex=False)
df["next_activity"]=g["activity"].shift(-1); df["next_ts"]=g["timestamp"].shift(-1); df["next_res"]=g["resource"].shift(-1)
df["wait_h"]=((df.next_ts-df.timestamp).dt.total_seconds()/3600)
pairs=df.dropna(subset=["next_activity"]).copy()
pairs["handoff"]=pairs.resource!=pairs.next_res
cs["handoffs"]=pairs.groupby("case_id")["handoff"].sum().reindex(cs.index).fillna(0).astype(int)
cs["handoff_rate"]=(cs.handoffs/(cs.events-1)).round(3)
cs["month"]=cs.start.dt.strftime("%Y-%m")
cs=cs.reset_index(); cs.to_csv(OUT+"process_kpi_case_summary.csv",index=False)

# --- step wait times (bottlenecks)
sw=(pairs.groupby(["activity","next_activity"])["wait_h"]
    .agg(mean_wait_h="mean",median_wait_h="median",p90_wait_h=lambda s:s.quantile(.9),cases="count").round(2)
    .reset_index().sort_values("mean_wait_h",ascending=False))
sw.to_csv(OUT+"process_kpi_step_wait_times.csv",index=False)

# --- handoffs between teams
ho=(pairs[pairs.handoff].groupby(["resource","next_res"]).size().reset_index(name="handoff_count")
    .rename(columns={"resource":"from_team","next_res":"to_team"}).sort_values("handoff_count",ascending=False))
ho.to_csv(OUT+"process_kpi_handoffs.csv",index=False)

# --- monthly cycle time (completed only) and outcome summary
comp=cs[cs.outcome=="Completed"]
mo=comp.groupby("month")["cycle_days"].agg(avg_cycle_days="mean",median_cycle_days="median",completed_cases="count").round(2).reset_index()
mo.to_csv(OUT+"process_kpi_monthly_cycle_time.csv",index=False)
oc=cs.groupby("outcome").agg(cases=("case_id","count"),avg_cycle_days=("cycle_days","mean")).round(2).reset_index()
oc["share"]=(oc.cases/oc.cases.sum()).round(3); oc.to_csv(OUT+"process_kpi_by_outcome.csv",index=False)

# --- charts
c1,c2,c3="#3B6FB6","#C0504D","#4E9A6B"
top=sw.head(8).iloc[::-1]
lab=top.activity+" → "+top.next_activity
fig,ax=plt.subplots(figsize=(9,5)); ax.barh(lab,top.mean_wait_h,color=[c2 if v>15 else c1 for v in top.mean_wait_h])
for y,v in enumerate(top.mean_wait_h): ax.text(v+.4,y,f"{v:.1f} h",va="center",fontsize=9)
ax.set_title("Process: avg waiting time before each step (hours) — synthetic demo data"); ax.set_xlabel("hours"); plt.tight_layout(); plt.savefig(OUT+"1_process_bottleneck_wait_times.png",dpi=130); plt.close()

h=ho.iloc[::-1]; fig,ax=plt.subplots(figsize=(9,5)); ax.barh(h.from_team+" → "+h.to_team,h.handoff_count,color=c1)
for y,v in enumerate(h.handoff_count): ax.text(v+3,y,str(v),va="center",fontsize=9)
ax.set_title("Process: team-to-team handoffs (count) — synthetic demo data"); plt.tight_layout(); plt.savefig(OUT+"2_process_handoffs_by_team.png",dpi=130); plt.close()

fig,ax=plt.subplots(figsize=(9,5)); ax.plot(mo.month,mo.avg_cycle_days,marker="o",color=c3)
for x,y,n in zip(mo.month,mo.avg_cycle_days,mo.completed_cases): ax.annotate(f"n={n}",(x,y),textcoords="offset points",xytext=(0,8),ha="center",fontsize=8)
ax.set_title("Process: avg cycle time of completed requests by start month (days) — synthetic demo data"); ax.set_ylabel("days"); plt.tight_layout(); plt.savefig(OUT+"3_process_cycle_time_by_month.png",dpi=130); plt.close()
print(cs.cycle_days.describe().round(2)); print(sw.head(5)); print(ho); print(oc); print(mo); print("overall handoff rate",pairs.handoff.mean().round(3))
