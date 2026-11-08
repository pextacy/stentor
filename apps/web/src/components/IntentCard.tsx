"use client";

import type { AlertIntent, IntentResult, Meta } from "@/lib/api";
import { human, instructionSentence, isActionVerb } from "@/lib/phrases";
import { Locked } from "./Status";

export const HAZARDS: AlertIntent["hazard"][] = [
  "wildfire", "flood", "earthquake", "tsunami", "hurricane", "tornado", "extreme_heat", "hazmat", "active_threat", "boil_water", "other",
];
export const ACTIONS: AlertIntent["action"][] = [
  "evacuate_now", "prepare_to_evacuate", "shelter_in_place", "move_to_higher_ground", "stay_indoors", "avoid_area", "boil_water", "monitor", "all_clear",
];
const URGENCIES = ["immediate", "expected", "future"];
const KIND: Record<string, string> = { P: "Place", T: "Time", N: "Quantity", U: "Phone or link", E: "Name" };

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1 text-sm font-semibold">
      <span className="text-xs uppercase tracking-wider text-slate-mute">{label}</span>
      {children}
    </label>
  );
}

const selectCls = "rounded-md border-2 border-ink bg-white px-2 py-1.5 text-base font-medium";

export function IntentCard({
  result, intent, phrasebook, onChange,
}: {
  result: IntentResult;
  intent: AlertIntent;
  phrasebook: Meta["phrasebook"];
  onChange: (i: AlertIntent) => void;
}) {
  const set = <K extends keyof AlertIntent>(k: K, v: AlertIntent[K]) => onChange({ ...intent, [k]: v });
  const instructions = intent.instructions ?? [];
  const mapping = result.mapping;
  const edited = JSON.stringify(intent) !== JSON.stringify(result.intent);

  return (
    <section aria-labelledby="intent-h" className="rounded-xl border-2 border-ink bg-white">
      <div className="flex flex-wrap items-baseline justify-between gap-2 border-b-2 border-ink px-4 py-2">
        <h2 id="intent-h" className="font-display text-2xl font-bold uppercase tracking-wide">What STENTOR understood</h2>
        <span className="text-xs text-slate-mute">
          Read by {result.method === "claude" ? "Claude" : "the rule parser"}. Correct anything wrong, then translate.
        </span>
      </div>

      <div className="grid gap-4 p-4 sm:grid-cols-3">
        <Field label="Hazard">
          <select className={selectCls} value={intent.hazard} onChange={(e) => set("hazard", e.target.value as AlertIntent["hazard"])}>
            {HAZARDS.map((h) => <option key={h} value={h}>{human(h)}</option>)}
          </select>
        </Field>
        <Field label="Required action">
          <select className={selectCls} value={intent.action} onChange={(e) => set("action", e.target.value as AlertIntent["action"])}>
            {ACTIONS.map((a) => <option key={a} value={a}>{human(a)}</option>)}
          </select>
        </Field>
        <Field label="Urgency">
          <select className={selectCls} value={intent.urgency ?? "immediate"} onChange={(e) => set("urgency", e.target.value)}>
            {URGENCIES.map((u) => <option key={u} value={u}>{u}</option>)}
          </select>
        </Field>
      </div>

      <div className="border-t border-slate-rule px-4 py-3">
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-mute">Instructions, as every language will say them</h3>
        <ol className="flex flex-col gap-2">
          {instructions.map((ins, idx) => {
            const sentence = instructionSentence(ins, mapping, phrasebook);
            const action = isActionVerb(ins.verb);
            return (
              <li key={idx} className={`flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md border-2 px-3 py-2 ${ins.negated ? "border-blocked bg-blocked-bg" : "border-slate-rule"}`}>
                {action ? (
                  <span className="rounded bg-ink px-1.5 py-0.5 text-xs font-bold uppercase tracking-wider text-white">Action</span>
                ) : (
                  <label className="flex items-center gap-2 text-sm font-semibold" title="Toggle whether this is a prohibition">
                    <input
                      type="checkbox"
                      className="h-5 w-5 accent-[#A3221B]"
                      checked={ins.negated}
                      onChange={(e) => set("instructions", instructions.map((x, j) => (j === idx ? { ...x, negated: e.target.checked } : x)))}
                    />
                    <span className="sr-only">Prohibition:</span>NOT
                  </label>
                )}
                <span className="flex-1 text-base font-medium">
                  {sentence ?? (
                    <span className="text-review">
                      {ins.negated ? "not " : ""}{human(ins.verb)} {ins.object ? human(ins.object) : ""}: no approved wording. A model must render it, or it goes to review.
                    </span>
                  )}
                </span>
              </li>
            );
          })}
        </ol>
        {intent.expires && (
          <p className="mt-2 text-sm">The alert itself expires at <strong>{mapping[intent.expires]}</strong>.</p>
        )}
      </div>

      <div className="border-t border-slate-rule px-4 py-3">
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-mute">Locked literals (copied, never translated)</h3>
        <ul className="flex flex-wrap gap-2">
          {Object.entries(mapping).map(([ph, val]) => (
            <li key={ph} className="flex items-center gap-2 rounded-md border-2 border-ink bg-slate-paper px-2 py-1 text-sm">
              <span className="ph">{ph.slice(1, -1)}</span>
              <span className="font-medium">{val}</span>
              <span className="text-xs text-slate-mute">{KIND[ph[1]]}</span>
            </li>
          ))}
          {Object.keys(mapping).length === 0 && <li className="text-sm text-slate-mute">No names, times or numbers found.</li>}
        </ul>
        <details className="mt-2 text-sm text-slate-mute">
          <summary className="cursor-pointer">Show locked text</summary>
          <p className="mt-1"><Locked text={result.locked_text} /></p>
        </details>
      </div>

      {edited && (
        <p className="border-t-2 border-fallback bg-fallback-bg px-4 py-2 text-sm text-fallback" role="status">
          You changed the intent. Every language will be checked against your version.
        </p>
      )}
      {(result.warnings ?? []).length > 0 && (
        <div className="border-t-2 border-review bg-review-bg px-4 py-3 text-sm text-review" role="note">
          <p className="font-semibold"><span aria-hidden="true">! </span>Check before translating</p>
          <ul className="ml-5 list-disc">
            {(result.warnings ?? []).map((w) => <li key={w}>{w}</li>)}
          </ul>
        </div>
      )}
    </section>
  );
}
