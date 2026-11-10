"use client";

import { useEffect, useState } from "react";
import { StatusBadge } from "@/components/Status";
import { type AlertSummary, type Meta, type Status, feedUrl, getMeta, searchAlerts } from "@/lib/api";

const PAGE = 20;
const HAZARDS = ["wildfire", "flood", "earthquake", "tsunami", "hurricane", "tornado", "extreme_heat", "hazmat", "active_threat", "boil_water", "other"];
const STATUSES: Status[] = ["VERIFIED", "APPROVED", "FALLBACK", "REVIEW", "BLOCKED", "REJECTED"];
const field = "rounded-md border-2 border-ink bg-white px-2 py-1 text-base";

export default function History() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [q, setQ] = useState("");
  const [hazard, setHazard] = useState("");
  const [status, setStatus] = useState("");
  const [lang, setLang] = useState("");
  const [msgType, setMsgType] = useState("");
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<{ items: AlertSummary[]; total: number } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { getMeta().then(setMeta).catch(() => {}); }, []);
  useEffect(() => {
    const t = setTimeout(() => {
      searchAlerts({ q, hazard, status, lang, msg_type: msgType, limit: PAGE, offset })
        .then((d) => { setData(d); setError(null); })
        .catch((e: Error) => setError(e.message));
    }, 200);
    return () => clearTimeout(t);
  }, [q, hazard, status, lang, msgType, offset]);

  const set = (fn: (v: string) => void) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => { fn(e.target.value); setOffset(0); };

  return (
    <main className="mx-auto max-w-6xl px-4 py-6">
      <div className="flex flex-wrap items-baseline gap-3">
        <h1 className="font-display text-4xl font-black uppercase tracking-wide">Alert history</h1>
        <a href={feedUrl()} className="ml-auto text-sm font-semibold underline">Atom feed</a>
      </div>
      <form role="search" className="mt-4 grid gap-3 rounded-xl border-2 border-ink bg-white p-4 sm:grid-cols-2 lg:grid-cols-5" onSubmit={(e) => e.preventDefault()}>
        <label className="flex flex-col gap-1 text-xs font-semibold uppercase tracking-wider text-slate-mute lg:col-span-2">Search text or id
          <input type="search" className={field} value={q} onChange={set(setQ)} placeholder="Altadena" />
        </label>
        <label className="flex flex-col gap-1 text-xs font-semibold uppercase tracking-wider text-slate-mute">Hazard
          <select className={field} value={hazard} onChange={set(setHazard)}>
            <option value="">Any</option>
            {HAZARDS.map((h) => <option key={h} value={h}>{h.replace(/_/g, " ")}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs font-semibold uppercase tracking-wider text-slate-mute">Language
          <select className={field} value={lang} onChange={set(setLang)}>
            <option value="">Any</option>
            {meta?.languages.map((l) => <option key={l.lang} value={l.lang}>{l.english_name}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs font-semibold uppercase tracking-wider text-slate-mute">Status
          <select className={field} value={status} onChange={set(setStatus)}>
            <option value="">Any</option>
            {STATUSES.map((s) => <option key={s} value={s}>{s.toLowerCase()}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs font-semibold uppercase tracking-wider text-slate-mute">Message type
          <select className={field} value={msgType} onChange={set(setMsgType)}>
            <option value="">Any</option>
            {["Alert", "Update", "Cancel"].map((m) => <option key={m}>{m}</option>)}
          </select>
        </label>
      </form>

      {error && <p role="alert" className="mt-4 font-semibold text-blocked">{error}</p>}
      <p className="mt-4 text-sm text-slate-mute" aria-live="polite">
        {data ? `${data.total} alert${data.total === 1 ? "" : "s"}${data.total ? `, showing ${offset + 1} to ${Math.min(offset + PAGE, data.total)}` : ""}` : "Loading…"}
      </p>
      <ul className="mt-2 divide-y divide-slate-rule rounded-xl border-2 border-ink bg-white">
        {data?.items.map((a) => (
          <li key={a.id} className="flex flex-col gap-2 px-4 py-3 md:flex-row md:items-center">
            <div className="min-w-0 flex-1">
              <a href={`/alerts/${a.id}`} className="font-medium underline">{a.source_text}</a>
              <p className="mt-0.5 flex flex-wrap gap-2 text-xs text-slate-mute">
                <span className="font-mono">{a.id}</span>
                <span>{new Date(a.created_at).toLocaleString()}</span>
                {a.hazard && <span>{a.hazard.replace(/_/g, " ")}</span>}
                {a.msg_type !== "Alert" && <span className="rounded border border-ink px-1 font-bold text-ink">{a.msg_type}</span>}
                {a.superseded_by && <span>replaced by {a.superseded_by}</span>}
                {a.chaos && <span className="rounded bg-tape px-1 font-bold text-ink">chaos</span>}
              </p>
            </div>
            <ul className="flex flex-wrap gap-1" aria-label="Status per language">
              {Object.entries(a.statuses).map(([lg, st]) => (
                <li key={lg} className="flex items-center gap-1 text-xs"><span className="font-mono">{lg}</span><StatusBadge status={st as Status} /></li>
              ))}
            </ul>
          </li>
        ))}
        {data && !data.items.length && <li className="px-4 py-6 text-slate-mute">No alerts match.</li>}
      </ul>
      <nav aria-label="Pages" className="mt-3 flex gap-2">
        <button type="button" className="rounded-md border-2 border-ink bg-white px-3 py-1 font-semibold disabled:opacity-50" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Newer</button>
        <button type="button" className="rounded-md border-2 border-ink bg-white px-3 py-1 font-semibold disabled:opacity-50" disabled={!data || offset + PAGE >= data.total} onClick={() => setOffset(offset + PAGE)}>Older</button>
      </nav>
    </main>
  );
}
