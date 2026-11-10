"use client";

import { useEffect, useState } from "react";
import { STATUS_STYLE } from "@/components/Status";
import { type Stats, type Status, getStats } from "@/lib/api";

const ORDER: Status[] = ["VERIFIED", "APPROVED", "FALLBACK", "REVIEW", "BLOCKED", "REJECTED"];
const BAR: Record<Status, string> = {
  VERIFIED: "bg-ok", APPROVED: "bg-ok/70", FALLBACK: "bg-fallback", REVIEW: "bg-review", BLOCKED: "bg-blocked", REJECTED: "bg-blocked/70",
};

/** One stacked bar per language. Each segment carries its count as text, so the chart never relies on colour alone. */
function StackedBar({ counts }: { counts: Record<string, number> }) {
  const total = Object.values(counts).reduce((a, b) => a + b, 0) || 1;
  return (
    <div className="flex h-7 w-full overflow-hidden rounded border-2 border-ink">
      {ORDER.filter((s) => counts[s]).map((s) => (
        <div key={s} className={`${BAR[s]} flex items-center justify-center font-mono text-xs font-bold text-white`} style={{ width: `${(100 * counts[s]) / total}%` }}
          title={`${STATUS_STYLE[s].word}: ${counts[s]}`}>
          {(100 * counts[s]) / total >= 8 ? `${STATUS_STYLE[s].icon}${counts[s]}` : ""}
        </div>
      ))}
    </div>
  );
}

export default function StatsPage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [chaos, setChaos] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { getStats(chaos).then(setStats).catch((e: Error) => setError(e.message)); }, [chaos]);

  if (error) return <main className="mx-auto max-w-5xl p-6"><p role="alert" className="font-semibold text-blocked">{error}</p></main>;
  if (!stats) return <main className="mx-auto max-w-5xl p-6"><p>Loading…</p></main>;

  const tiles: [string, string][] = [
    ["Alerts", String(stats.alerts)],
    ["Language messages", String(stats.languages_compiled)],
    ["Sendable", stats.sendable_pct === null ? "–" : `${stats.sendable_pct}%`],
    ["Operator reviews", String(stats.operator_reviews)],
  ];
  return (
    <main className="mx-auto max-w-5xl px-4 py-6">
      <h1 className="font-display text-4xl font-black uppercase tracking-wide">Operations</h1>
      <p className="mt-1 text-slate-mute">{stats.note} These are live counts from this server, not eval results; the eval page has the measured catch rates.</p>
      <label className="mt-3 flex items-center gap-2 text-sm font-semibold">
        <input type="checkbox" className="h-4 w-4" checked={chaos} onChange={(e) => setChaos(e.target.checked)} />
        Include chaos demo runs ({stats.chaos_alerts})
      </label>

      <dl className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        {tiles.map(([k, v]) => (
          <div key={k} className="rounded-xl border-2 border-ink bg-white p-3">
            <dt className="text-xs font-semibold uppercase tracking-wider text-slate-mute">{k}</dt>
            <dd className="font-mono text-3xl font-bold">{v}</dd>
          </div>
        ))}
      </dl>

      <section aria-labelledby="st-h" className="mt-6 rounded-xl border-2 border-ink bg-white p-4">
        <h2 id="st-h" className="font-display text-xl font-bold uppercase tracking-wide">By status</h2>
        <ul className="mt-2 flex flex-wrap gap-3">
          {ORDER.map((s) => (
            <li key={s} className="flex items-center gap-2 text-sm">
              <span aria-hidden="true" className={`inline-block h-3 w-3 rounded-sm ${BAR[s]}`} />
              <span className="font-mono">{STATUS_STYLE[s].icon}</span> {STATUS_STYLE[s].word}: <strong>{stats.by_status[s] ?? 0}</strong>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="lg-h" className="mt-6 rounded-xl border-2 border-ink bg-white p-4">
        <h2 id="lg-h" className="font-display text-xl font-bold uppercase tracking-wide">By language</h2>
        <table className="mt-2 w-full text-left text-sm">
          <thead><tr><th className="w-16 py-1">Lang</th><th>Results</th><th className="w-14 text-right">Total</th></tr></thead>
          <tbody>
            {Object.entries(stats.by_lang).map(([lg, c]) => (
              <tr key={lg} className="border-t border-slate-rule">
                <th scope="row" className="py-1.5 font-mono">{lg}</th>
                <td className="py-1.5"><StackedBar counts={c} /><span className="sr-only">{ORDER.filter((s) => c[s]).map((s) => `${STATUS_STYLE[s].word} ${c[s]}`).join(", ")}</span></td>
                <td className="text-right font-mono">{Object.values(c).reduce((a, b) => a + b, 0)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <div className="mt-6 grid gap-4 md:grid-cols-2">
        <section aria-labelledby="hz-h" className="rounded-xl border-2 border-ink bg-white p-4">
          <h2 id="hz-h" className="font-display text-xl font-bold uppercase tracking-wide">By hazard</h2>
          <ul className="mt-2 space-y-1 text-sm">
            {Object.entries(stats.by_hazard).map(([h, n]) => (
              <li key={h} className="flex justify-between border-b border-slate-rule/60 py-0.5"><span>{h.replace(/_/g, " ")}</span><span className="font-mono">{n}</span></li>
            ))}
          </ul>
          <p className="mt-2 text-xs text-slate-mute">Messages: {Object.entries(stats.by_msg_type).map(([k, v]) => `${k} ${v}`).join(" · ") || "none"}</p>
        </section>
        <section aria-labelledby="rs-h" className="rounded-xl border-2 border-ink bg-white p-4">
          <h2 id="rs-h" className="font-display text-xl font-bold uppercase tracking-wide">Why languages were blocked</h2>
          {stats.top_block_reasons.length ? (
            <ol className="mt-2 space-y-1 text-sm">
              {stats.top_block_reasons.map(([r, n]) => (
                <li key={r} className="flex justify-between gap-3 border-b border-slate-rule/60 py-0.5"><span>{r}</span><span className="font-mono">{n}</span></li>
              ))}
            </ol>
          ) : <p className="mt-2 text-sm text-slate-mute">Nothing blocked{chaos ? "" : " outside chaos runs"}.</p>}
        </section>
      </div>
    </main>
  );
}
