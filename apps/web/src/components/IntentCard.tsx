"use client";

import type { AlertIntent, IntentResult } from "@/lib/api";
import { Locked } from "./Status";

export const HAZARDS: AlertIntent["hazard"][] = [
  "wildfire", "flood", "earthquake", "tsunami", "hurricane", "tornado", "extreme_heat", "hazmat", "active_threat", "boil_water", "other",
];
export const ACTIONS: AlertIntent["action"][] = [
  "evacuate_now", "prepare_to_evacuate", "shelter_in_place", "move_to_higher_ground", "stay_indoors", "avoid_area", "boil_water", "monitor", "all_clear",
];
const URGENCIES = ["immediate", "expected", "future"];

const KIND: Record<string, string> = { P: "Place", T: "Time", N: "Number", U: "Phone or link" };
const human = (s: string) => s.replace(/_/g, " ");

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
  result,
  intent,
  onChange,
}: {
  result: IntentResult;
  intent: AlertIntent;
  onChange: (i: AlertIntent) => void;
}) {
  const set = <K extends keyof AlertIntent>(k: K, v: AlertIntent[K]) => onChange({ ...intent, [k]: v });
  const instructions = intent.instructions ?? [];

  return (
    <section aria-labelledby="intent-h" className="rounded-xl border-2 border-ink bg-white">
      <div className="flex items-baseline justify-between border-b-2 border-ink px-4 py-2">
        <h2 id="intent-h" className="font-display text-2xl font-bold uppercase tracking-wide">Intent card</h2>
        <span className="text-xs text-slate-mute">
          Read by {result.method === "claude" ? "Claude" : "rule parser"}. Check it, then compile.
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
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-mute">Instructions, in order</h3>
        <ol className="flex flex-col gap-2">
          {instructions.map((ins, idx) => (
            <li key={idx} className={`flex flex-wrap items-center gap-3 rounded-md border-2 px-3 py-2 ${ins.negated ? "border-blocked bg-blocked-bg" : "border-slate-rule"}`}>
              <label className="flex items-center gap-2 text-sm font-semibold">
                <input
                  type="checkbox"
                  className="h-5 w-5 accent-[#A3221B]"
                  checked={ins.negated}
                  onChange={(e) => {
                    const next = instructions.map((x, j) => (j === idx ? { ...x, negated: e.target.checked } : x));
                    set("instructions", next);
                  }}
                />
                Do NOT
              </label>
              <span className="text-base font-medium">
                {ins.verb.replace("_", " ")} {ins.object ? human(ins.object) : ""}
              </span>
              {(ins.placeholders ?? []).map((p) => (
                <span key={p} className="ph">{p.slice(1, -1)} = {result.mapping[p]}</span>
              ))}
            </li>
          ))}
        </ol>
        {intent.expires && <p className="mt-2 text-sm">Alert expires at <span className="ph">{intent.expires.slice(1, -1)}</span> {result.mapping[intent.expires]}</p>}
      </div>

      <div className="border-t border-slate-rule px-4 py-3">
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-mute">Locked literals (never translated)</h3>
        <ul className="flex flex-wrap gap-2">
          {Object.entries(result.mapping).map(([ph, val]) => (
            <li key={ph} className="flex items-center gap-2 rounded-md border-2 border-ink bg-slate-paper px-2 py-1 text-sm">
              <span className="ph">{ph.slice(1, -1)}</span>
              <span className="font-medium">{val}</span>
              <span className="text-xs text-slate-mute">{KIND[ph[1]]}</span>
            </li>
          ))}
          {Object.keys(result.mapping).length === 0 && <li className="text-sm text-slate-mute">No literals found.</li>}
        </ul>
        <p className="mt-3 text-sm text-slate-mute">
          Locked text: <Locked text={result.locked_text} />
        </p>
      </div>

      {(result.warnings ?? []).length > 0 && (
        <div className="border-t-2 border-review bg-review-bg px-4 py-3 text-sm text-review" role="note">
          <p className="font-semibold"><span aria-hidden="true">! </span>Check before compiling</p>
          <ul className="ml-5 list-disc">
            {(result.warnings ?? []).map((w) => <li key={w}>{w}</li>)}
          </ul>
        </div>
      )}
    </section>
  );
}
