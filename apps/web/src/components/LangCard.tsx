"use client";

import type { LangResult } from "@/lib/api";
import { Locked, STATUS_STYLE, StatusBadge } from "./Status";

const SLOT_LABEL: Record<string, string> = {
  hazard: "Hazard", action: "Action", area_refs: "Places", time_refs: "Times", info_refs: "Phone/link",
  expires: "Expiry", negations: "Negations", instructions: "Instructions", urgency: "Urgency",
};

const RENDERER: Record<string, string> = {
  template: "Approved templates", llm: "Claude renderer", adaption: "Adaption model", safe_template: "Safe fallback template", none: "No renderer",
};

function fmt(v: unknown): string {
  if (v === null || v === undefined) return "none";
  if (Array.isArray(v)) return v.length ? v.join(", ") : "none";
  return String(v);
}

/** The slot ledger: one cell per critical slot, pass or fail, readable at a glance. */
export function SlotLedger({ r }: { r: LangResult }) {
  const slots = r.diff.filter((d) => d.critical);
  if (!slots.length) return null;
  return (
    <ul aria-label="Slot check" className="grid grid-cols-4 gap-px overflow-hidden rounded-md border-2 border-ink bg-ink">
      {slots.map((d) => (
        <li key={d.slot} className={`flex flex-col items-center px-1 py-1.5 text-center ${d.match ? "bg-white text-ok" : "bg-blocked text-white"}`}>
          <span aria-hidden="true" className="font-mono text-base font-bold leading-none">{d.match ? "✓" : "✕"}</span>
          <span className="mt-0.5 text-[11px] font-semibold uppercase leading-tight tracking-wide">{SLOT_LABEL[d.slot] ?? d.slot}</span>
          <span className="sr-only">{d.match ? "matches" : "does not match"}</span>
        </li>
      ))}
    </ul>
  );
}

export function LangCard({ r }: { r: LangResult }) {
  const bad = r.status === "BLOCKED" || r.status === "FALLBACK";
  const s = STATUS_STYLE[r.status];
  return (
    <article aria-labelledby={`lang-${r.lang}`} className={`flex flex-col rounded-xl border-2 bg-white ${bad ? "border-blocked" : r.status === "REVIEW" ? "border-review" : "border-ink"}`}>
      <header className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b-2 border-inherit px-4 py-2">
        <h3 id={`lang-${r.lang}`} className="font-display text-2xl font-bold uppercase tracking-wide">
          {r.english_name}
        </h3>
        <span lang={r.lang} dir={r.dir} className="text-sm text-slate-mute">{r.name}</span>
        <span className="ml-auto"><StatusBadge status={r.status} size="lg" /></span>
      </header>

      {r.chaos && (
        <p className="tape px-4 py-1 text-xs font-bold uppercase tracking-wider">
          <span className="bg-tape px-1 text-ink">Chaos mode: {r.chaos.replace("_", " ")} injected</span>
        </p>
      )}

      <div className="flex flex-1 flex-col gap-3 p-4">
        {r.text ? (
          <p lang={r.lang} dir={r.dir} className="text-lg leading-relaxed">{r.text}</p>
        ) : (
          <p className="font-semibold text-blocked">Nothing will be sent in this language.</p>
        )}

        {r.blocked_attempt && (
          <div className="rounded-md border-2 border-dashed border-blocked bg-blocked-bg p-3">
            <p className="text-xs font-bold uppercase tracking-wider text-blocked">Blocked rendering, not sent</p>
            <p lang={r.lang} dir={r.dir} className="mt-1 text-base text-ink line-through decoration-blocked decoration-2">{r.blocked_attempt}</p>
          </div>
        )}

        <SlotLedger r={r} />

        <p className="text-sm text-slate-mute">{s.explain}</p>

        <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
          <dt className="text-slate-mute">Rendered by</dt><dd className="font-medium">{RENDERER[r.renderer] ?? r.renderer}</dd>
          <dt className="text-slate-mute">Checked by</dt><dd className="font-medium">{r.backparser === "lexicon" ? "Lexicon back parser" : r.backparser}</dd>
          {r.sms && (<><dt className="text-slate-mute">SMS</dt><dd className="font-medium">{r.sms.segments} segment{r.sms.segments === 1 ? "" : "s"}, {r.sms.encoding}, {r.sms.units} units</dd></>)}
          <dt className="text-slate-mute">Lexicon</dt>
          <dd className={`font-medium ${r.reviewed_by === "unreviewed" ? "text-review" : ""}`}>{r.reviewed_by === "unreviewed" ? "Not yet reviewed by a native speaker" : `Reviewed by ${r.reviewed_by}`}</dd>
        </dl>

        <details className="group rounded-md border border-slate-rule">
          <summary className="cursor-pointer px-3 py-2 text-sm font-semibold">Why this status</summary>
          <div className="space-y-3 border-t border-slate-rule px-3 py-3 text-sm">
            <ul className="space-y-1">
              {r.reasons.map((x) => <li key={x}>{x}</li>)}
            </ul>
            <div className="overflow-x-auto"><table className="w-full min-w-[22rem] text-left text-sm">
              <caption className="mb-1 text-left text-xs font-semibold uppercase tracking-wider text-slate-mute">Slot diff: source vs back parsed</caption>
              <thead><tr className="border-b border-slate-rule"><th className="py-1 pr-2">Slot</th><th className="pr-2">Source</th><th className="pr-2">Read back</th><th>Match</th></tr></thead>
              <tbody>
                {r.diff.map((d) => (
                  <tr key={d.slot} className={`border-b border-slate-rule/60 align-top ${d.match ? "" : "bg-blocked-bg"}`}>
                    <th scope="row" className="py-1 pr-2 font-medium">{SLOT_LABEL[d.slot] ?? d.slot}</th>
                    <td className="pr-2"><Locked text={fmt(d.source)} /></td>
                    <td className="pr-2"><Locked text={fmt(d.back)} /></td>
                    <td className={d.match ? "text-ok" : "font-bold text-blocked"}>{d.match ? "✓ yes" : "✕ no"}</td>
                  </tr>
                ))}
              </tbody>
            </table></div>
            <ul className="space-y-1">
              {r.checks.map((c) => (
                <li key={c.name} className={c.ok ? "" : "font-semibold text-blocked"}>
                  <span aria-hidden="true" className="font-mono">{c.ok ? "✓" : "✕"} </span>
                  {c.name.replace(/_/g, " ")}{c.critical ? "" : " (non critical)"}: {c.detail}
                </li>
              ))}
            </ul>
            {r.notes.length > 0 && <ul className="list-disc pl-5 text-slate-mute">{r.notes.map((n) => <li key={n}>{n}</li>)}</ul>}
            {r.locked_text && <p className="text-slate-mute" lang={r.lang} dir={r.dir}>Locked: <Locked text={r.locked_text} /></p>}
          </div>
        </details>
      </div>
    </article>
  );
}
