import { useEffect, useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

const get = (name) =>
  fetch(`/api/process/${name}/`).then((r) => {
    if (!r.ok) throw new Error(`${name}: server returned ${r.status}`);
    return r.json();
  });
const SEV = { high: "bg-red-100 text-red-800", medium: "bg-amber-100 text-amber-800",
              low: "bg-green-100 text-green-800", unrated: "bg-slate-100 text-slate-600" };
const num = (v, d = 0) => (v == null ? "–" : Number(v).toLocaleString("en-IN", { maximumFractionDigits: d }));
const pct = (v) => (v == null ? "–" : `${Math.round(v * 100)}%`);

const Card = ({ label, value, hint }) => (
  <div className="rounded-xl bg-white p-4 shadow-sm ring-1 ring-slate-200">
    <div className="text-sm text-slate-500">{label}</div>
    <div className="mt-1 text-2xl font-semibold text-slate-900">{value}</div>
    {hint && <div className="mt-1 text-xs text-slate-400">{hint}</div>}
  </div>
);
const Section = ({ title, children }) => (
  <section className="mt-8"><h2 className="mb-3 text-lg font-semibold text-slate-800">{title}</h2>{children}</section>
);

export default function App() {
  const [st, setSt] = useState({ loading: true, error: null, data: null });
  const [proc, setProc] = useState("all");

  useEffect(() => {
    Promise.all(["overview", "stages", "bottlenecks", "anomalies"].map(get))
      .then(([o, s, b, a]) => setSt({ loading: false, error: null, data: { o, s, b, a } }))
      .catch((e) => setSt({ loading: false, error: e.message, data: null }));
  }, []);

  const view = useMemo(() => {
    if (!st.data) return null;
    const { o, b, a } = st.data;
    const ov = o.data.overview;
    const inProc = (id) => proc === "all" || id === proc;
    const rows = ov.process_breakdown.filter((r) => inProc(r.process_id));
    const sum = (k) => rows.reduce((t, r) => t + (r[k] || 0), 0);
    const bn = b.data.bottlenecks.filter((r) => inProc(r.process_id));
    return {
      ov, anomalies: a.data.anomalies, warnings: o.meta.warnings,
      processes: [...new Set(ov.process_breakdown.map((r) => r.process_id))],
      total: sum("total_cases"), done: sum("completed_cases"), stalled: sum("stalled_or_abandoned_cases"),
      bottlenecks: bn, chart: bn.filter((r) => r.target_value != null).slice(0, 12).map((r) => ({
        name: r.activity, Actual: Math.round(r.mean_elapsed_h), Target: r.target_value })),
      findings: o.data.findings.filter((f) => inProc(f.scope.population.split(" ")[0])),
    };
  }, [st.data, proc]);

  if (st.loading) return <p className="p-8 text-slate-500">Loading process data…</p>;
  if (st.error) return (
    <div className="m-8 rounded-lg bg-red-50 p-4 text-red-800">
      Could not load data: {st.error}. Is the Django server running on port 8000?</div>);
  if (!view || view.ov.total_cases === 0) return <p className="p-8 text-slate-500">No process data available.</p>;

  return (
    <main className="mx-auto max-w-6xl p-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Process Intelligence</h1>
          <p className="text-sm text-slate-500">Period {view.ov.period} · Synthetic HUL data: signals to investigate, not proven causes</p>
        </div>
        <label className="text-sm text-slate-600">Process{" "}
          <select value={proc} onChange={(e) => setProc(e.target.value)} className="rounded border border-slate-300 bg-white p-1.5">
            <option value="all">All processes</option>
            {view.processes.map((p) => <option key={p}>{p}</option>)}
          </select>
        </label>
      </header>

      {view.warnings.length > 0 && (
        <details className="mt-4 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">
          <summary className="cursor-pointer font-medium">{view.warnings.length} data-quality notes</summary>
          <ul className="mt-2 list-disc pl-5">{view.warnings.map((w) => <li key={w}>{w}</li>)}</ul>
        </details>)}

      <div className="mt-6 grid grid-cols-2 gap-4 md:grid-cols-4">
        <Card label="Cases" value={num(view.total)} />
        <Card label="Completion rate" value={pct(view.total ? view.done / view.total : null)} hint={`${num(view.done)} completed`} />
        <Card label="Stalled or abandoned" value={num(view.stalled)} hint="no activity for 45+ days" />
        <Card label="Findings" value={view.findings.length} hint="high and medium severity" />
      </div>

      <Section title="Average stage time vs SOP target (hours)">
        {view.chart.length === 0 ? <p className="text-sm text-slate-500">No stages with a comparable target for this selection.</p> : (
          <div className="rounded-xl bg-white p-4 shadow-sm ring-1 ring-slate-200">
            <ResponsiveContainer width="100%" height={Math.max(260, view.chart.length * 38)}>
              <BarChart data={view.chart} layout="vertical" margin={{ left: 150 }}>
                <CartesianGrid strokeDasharray="3 3" /><XAxis type="number" />
                <YAxis type="category" dataKey="name" width={230} tick={{ fontSize: 11 }} />
                <Tooltip /><Legend />
                <Bar dataKey="Actual" fill="#2F5597" /><Bar dataKey="Target" fill="#cbd5e1" />
              </BarChart>
            </ResponsiveContainer>
          </div>)}
      </Section>

      <Section title="Bottleneck ranking">
        {view.bottlenecks.length === 0 ? <p className="text-sm text-slate-500">No stages to rank.</p> : (
          <div className="overflow-x-auto rounded-xl bg-white shadow-sm ring-1 ring-slate-200">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50 text-slate-500"><tr>
                {["#", "Stage", "Process", "Mean (h)", "Target (h)", "Over target", "Severity"].map((h) => <th key={h} className="p-3 font-medium">{h}</th>)}
              </tr></thead>
              <tbody>{view.bottlenecks.map((r) => (
                <tr key={r.rank} className="border-t border-slate-100">
                  <td className="p-3">{r.rank}</td><td className="p-3">{r.activity}</td>
                  <td className="p-3 text-slate-500">{r.process_id} · {r.case_type}</td>
                  <td className="p-3">{num(r.mean_elapsed_h)}</td>
                  <td className="p-3">{num(r.target_value)}{r.comparable === "approximate" && <span title="Approximate target"> ≈</span>}</td>
                  <td className="p-3">{pct(r.breach_rate)}</td>
                  <td className="p-3"><span className={`rounded-full px-2 py-0.5 text-xs ${SEV[r.severity]}`}>{r.severity}</span></td>
                </tr>))}</tbody>
            </table>
          </div>)}
      </Section>

      <Section title="Findings and evidence">
        {view.findings.length === 0 ? <p className="text-sm text-slate-500">No findings for this selection.</p> : (
          <div className="grid gap-4 md:grid-cols-2">{view.findings.map((f) => (
            <article key={f.finding_id} className="rounded-xl bg-white p-4 shadow-sm ring-1 ring-slate-200">
              <div className="flex items-start justify-between gap-2">
                <h3 className="font-medium text-slate-900">{f.title}</h3>
                <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs ${SEV[f.severity]}`}>{f.severity}</span>
              </div>
              <p className="mt-1 text-sm text-slate-600">Actual {num(f.actual_value)} {f.unit} vs target {num(f.target_value)} {f.unit}</p>
              <p className="mt-2 text-sm text-slate-700">{f.evidence[0].description}</p>
              <p className="mt-2 text-xs text-slate-500">Source: {f.evidence[0].source_file} · {f.scope.population} · Example cases: {f.evidence[0].record_ids.join(", ") || "–"}</p>
              <ul className="mt-2 list-disc pl-5 text-xs text-slate-500">{f.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
              <div className="mt-2 text-xs text-slate-400">{f.finding_id}</div>
            </article>))}</div>)}
      </Section>

      <Section title="Process anomalies (all processes)">
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          {Object.entries(view.anomalies.counts).map(([k, v]) => <Card key={k} label={k.replaceAll("_", " ")} value={num(v)} />)}
        </div>
      </Section>
    </main>
  );
}
