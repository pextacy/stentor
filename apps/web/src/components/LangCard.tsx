"use client";

import { useState } from "react";
import { type LangResult, copyText } from "@/lib/api";
import { Locked, STATUS_STYLE, StatusBadge } from "./Status";

const CHANNEL_LABEL: Record<string, string> = { wea_90: "WEA 90", wea_360: "WEA 360", sms_1: "1 SMS" };

export function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const [done, setDone] = useState<null | boolean>(null);
  return (
    <button
      type="button"
      onClick={async () => { setDone(await copyText(text)); setTimeout(() => setDone(null), 2000); }}
      className="rounded-md border-2 border-ink bg-white px-2 py-0.5 text-sm font-semibold"
    >
      <span aria-live="polite">{done === null ? label : done ? "Copied" : "Copy failed"}</span>
    </button>
  );
}

/** Which delivery channels the sent text fits, never by colour alone. */
export function ChannelFits({ r }: { r: LangResult }) {
  if (!r.channels?.length) return null;
  return (
    <ul aria-label="Channel fit" className="flex flex-wrap gap-2 text-xs">
      {r.channels.map((c) => (
        <li key={c.channel} title={c.note || undefined}
          className={`rounded border px-1.5 py-0.5 font-mono ${c.fits ? "border-ok text-ok" : "border-review bg-review-bg text-review"}`}>
          <span aria-hidden="true">{c.fits ? "✓" : "!"} </span>{CHANNEL_LABEL[c.channel] ?? c.channel} {c.used}/{c.limit}
          <span className="sr-only">{c.fits ? " fits" : " too long"}</span>
        </li>
      ))}
    </ul>
  );
}

export const SLOT_LABEL: Record<string, string> = {
  hazard: "Hazard", action: "Action", area_refs: "Places", time_refs: "Times", info_refs: "Phone",
  number_refs: "Numbers", event_refs: "Names", expires: "Expiry", negations: "Do-nots", instructions: "Steps",
  urgency: "Urgency",
};

export const RENDERER: Record<string, string> = {
  template: "approved templates", llm: "Claude", adaption: "Adaption model", safe_template: "safe fallback template", none: "no renderer",
};

export const backparserLabel = (b: string) => (b === "lexicon" ? "lexicon back parser" : b);

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
    <ul aria-label="Slot check" className="grid grid-cols-5 gap-px overflow-hidden rounded-md border-2 border-ink bg-ink">
      {slots.map((d) => (
        <li key={d.slot} className={`flex flex-col items-center px-1 py-1.5 text-center ${d.match ? "bg-white text-ok" : "bg-blocked text-white"}`}>
          <span aria-hidden="true" className="font-mono text-base font-bold leading-none">{d.match ? "✓" : "✕"}</span>
          <span className="mt-0.5 break-all text-[11px] font-semibold leading-tight">{SLOT_LABEL[d.slot] ?? d.slot}</span>
          <span className="sr-only">{d.match ? "matches" : "does not match"}</span>
        </li>
      ))}
    </ul>
  );
}

export function LangCard({ r, common }: { r: LangResult; common: { renderer: string; backparser: string } }) {
  const bad = r.status === "BLOCKED" || r.status === "FALLBACK" || r.status === "REJECTED";
  const s = STATUS_STYLE[r.status];
  const differs = r.renderer !== common.renderer || r.backparser !== common.backparser;
  const reason = r.reasons.find((x) => !x.startsWith("Sent the pre-approved"));
  return (
    <article aria-labelledby={`lang-${r.lang}`} className={`flex flex-col rounded-xl border-2 bg-white ${bad ? "border-blocked" : r.status === "REVIEW" ? "border-review" : "border-ink"}`}>
      <header className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b-2 border-inherit px-4 py-2">
        <h3 id={`lang-${r.lang}`} className="font-display text-2xl font-bold uppercase tracking-wide">{r.english_name}</h3>
        <span lang={r.lang} dir={r.dir} className="text-sm text-slate-mute">{r.name}</span>
        <span className="ml-auto"><StatusBadge status={r.status} size="lg" /></span>
      </header>

      {r.chaos && (
        <p className="tape px-4 py-1 text-xs font-bold uppercase tracking-wider">
          <span className="bg-tape px-1 text-ink">Chaos mode: {r.chaos.replace(/_/g, " ")} injected</span>
        </p>
      )}

      <div className="flex flex-1 flex-col gap-3 p-4">
        {r.text ? (
          <div className="flex items-start gap-2">
            <p lang={r.lang} dir={r.dir} className="flex-1 text-lg leading-relaxed">{r.text}</p>
            <CopyButton text={r.text} />
          </div>
        ) : (
          <p className="font-semibold text-blocked">Nothing will be sent in this language.</p>
        )}

        {r.blocked_attempt && (
          <div className="rounded-md border-2 border-dashed border-blocked bg-blocked-bg p-3">
            <p className="text-xs font-bold uppercase tracking-wider text-blocked">Blocked translation, not sent</p>
            <p lang={r.lang} dir={r.dir} className="mt-1 text-base text-ink line-through decoration-blocked decoration-2">{r.blocked_attempt}</p>
          </div>
        )}

        {r.back_english && (
          <p className="rounded-md bg-slate-paper px-3 py-2 text-sm">
            <span className="font-semibold">Read back in English: </span>
            <span lang="en">{r.back_english}</span>
          </p>
        )}
        {r.blocked_back_english && (
          <p className="rounded-md bg-blocked-bg px-3 py-2 text-sm">
            <span className="font-semibold text-blocked">The blocked translation said: </span>
            <span lang="en">{r.blocked_back_english}</span>
          </p>
        )}

        <SlotLedger r={r} />
        <ChannelFits r={r} />
        {r.review && (
          <p className="text-sm font-medium">
            {r.review.decision === "approve" ? "Approved" : "Rejected"} by {r.review.reviewer}
            {r.review.note ? `: ${r.review.note}` : ""}
          </p>
        )}

        {r.status !== "VERIFIED" && (
          <p className={`text-sm font-medium ${bad ? "text-blocked" : "text-review"}`}>
            {s.explain}{reason ? ` ${reason}.` : ""}
          </p>
        )}

        <p className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-slate-mute">
          {r.sms && <span>SMS: {r.sms.segments} segment{r.sms.segments === 1 ? "" : "s"} ({r.sms.encoding}, {r.sms.units} characters)</span>}
          {differs && <span>Rendered by {RENDERER[r.renderer] ?? r.renderer}, checked by {backparserLabel(r.backparser)}</span>}
        </p>

        <details className="rounded-md border border-slate-rule">
          <summary className="cursor-pointer px-3 py-2 text-sm font-semibold">Slot by slot comparison</summary>
          <div className="space-y-3 border-t border-slate-rule px-3 py-3 text-sm">
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-mute">Source intent vs what the translation says</p>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[22rem] text-left text-sm">
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
              </table>
            </div>
            <ul className="space-y-1">
              {r.checks.map((c) => (
                <li key={c.name} className={c.ok ? "" : "font-semibold text-blocked"}>
                  <span aria-hidden="true" className="font-mono">{c.ok ? "✓" : "✕"} </span>
                  {c.name.replace(/_/g, " ")}{c.critical ? "" : " (non critical)"}: {c.detail}
                </li>
              ))}
            </ul>
            {r.notes.length > 0 && <ul className="list-disc pl-5 text-slate-mute">{r.notes.map((n) => <li key={n}>{n}</li>)}</ul>}
            {r.locked_text && (
              <div className="text-slate-mute">
                <p>Locked text as translated:</p>
                <p lang={r.lang} dir={r.dir}><Locked text={r.locked_text} /></p>
              </div>
            )}
          </div>
        </details>
      </div>
    </article>
  );
}
