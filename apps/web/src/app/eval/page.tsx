"use client";

import { useEffect, useState } from "react";
import { getEval, getEvalRenderers } from "@/lib/api";

/* eslint-disable @typescript-eslint/no-explicit-any */
type EvalFile = any;

const LABEL: Record<string, string> = {
  drop_negation: "Dropped “not”", downgrade_action: "Softened action", shift_time: "Changed or swapped time", swap_place: "Swapped or invented place",
  swap_hazard: "Wrong hazard", drop_placeholder: "Dropped literal", duplicate_placeholder: "Duplicated literal",
};
const SUITE_LABEL: Record<string, string> = {
  clean: "Clean: 60 alerts in plain template wording",
  realistic: "Realistic: messy wording and every bug found in review",
};
const ICON: Record<string, string> = { VERIFIED: "✓", REVIEW: "!", FALLBACK: "↺", BLOCKED: "✕" };
const TONE: Record<string, string> = { VERIFIED: "text-ok", REVIEW: "text-review", FALLBACK: "text-fallback", BLOCKED: "text-blocked" };

function Tile({ value, label, sub }: { value: string; label: string; sub: string }) {
  return (
    <div className="rounded-xl border-2 border-ink bg-white p-4">
      <p className="font-display text-5xl font-black leading-none">{value}</p>
      <p className="mt-2 font-semibold">{label}</p>
      <p className="text-sm text-slate-mute">{sub}</p>
    </div>
  );
}

function Meter({ pct }: { pct: number | null }) {
  if (pct === null || pct === undefined) return <span className="text-slate-mute">n/a</span>;
  return (
    <span className="flex items-center gap-2" title={`${pct}%`}>
      <span className="h-2 w-24 overflow-hidden rounded-sm bg-slate-paper" aria-hidden="true">
        <span className="block h-full rounded-sm bg-ink" style={{ width: `${pct}%` }} />
      </span>
      <span className="font-mono">{pct}%</span>
    </span>
  );
}

export default function EvalPage() {
  const [data, setData] = useState<EvalFile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [renderers, setRenderers] = useState<any[]>([]);
  useEffect(() => {
    getEvalRenderers().then(setRenderers).catch(() => setRenderers([]));
    getEval().then(setData).catch(() => setError("No eval results yet. Run: cd services/api && uv run python ../../eval/run_eval.py --offline"));
  }, []);

  if (error) return <main className="mx-auto max-w-5xl p-6"><p role="alert" className="font-semibold text-blocked">{error}</p></main>;
  if (!data) return <main className="mx-auto max-w-5xl p-6"><p>Loading eval results…</p></main>;
  const s = data.summary;
  const m = data.meta;
  const missed = data.adversarial.filter((r: any) => !r.caught);
  const realistic = data.extraction?.realistic ?? [];
  const rows = data.clean as any[];
  const when = new Date(m.generated_at).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });

  return (
    <main className="mx-auto max-w-6xl px-4 py-6">
      <h1 className="font-display text-4xl font-black uppercase tracking-wide">Eval: does the check catch what kills people?</h1>
      <p className="mt-2 max-w-3xl text-slate-mute">
        {s.alerts} alerts × {s.langs.length} languages = {s.clean_cases} translations. Each translation was then corrupted in every way that
        applies and checked again. Run {when}. Reading: {m.extractor}. Checking: {m.backparser}.
      </p>

      <section aria-label="Headline results" className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Tile value={`${s.catch_rate_pct}%`} label="Injected errors caught" sub={`${s.adversarial_cases - s.missed} of ${s.adversarial_cases} corrupted translations never sent`} />
        <Tile value={`${s.false_block_rate_pct}%`} label="Wrongly blocked" sub={`clean translations blocked, of ${s.clean_cases}`} />
        <Tile value={`${s.status_as_expected_pct}%`} label="Status as expected" sub="Verified or Review exactly where we said it should be" />
        <Tile value={`${s.review_rate_pct}%`} label="Sent to a person" sub="Review: the templates leave out a word, or the action was assumed" />
      </section>

      <section aria-labelledby="suite-h" className="mt-8 rounded-xl border-2 border-ink bg-white p-4">
        <h2 id="suite-h" className="font-display text-2xl font-bold uppercase tracking-wide">By suite</h2>
        <div className="overflow-x-auto">
          <table className="mt-3 w-full min-w-[46rem] text-left">
            <thead><tr className="border-b-2 border-ink text-sm"><th className="py-2">Suite</th><th>Translations</th><th>Verified</th><th>Review</th><th>Wrongly blocked</th><th>Errors caught</th></tr></thead>
            <tbody>
              {Object.entries(s.suites).map(([k, v]: [string, any]) => (
                <tr key={k} className="border-b border-slate-rule">
                  <th scope="row" className="py-2 font-medium">{SUITE_LABEL[k] ?? k}</th>
                  <td className="font-mono">{v.cases}</td><td><Meter pct={v.verified_pct} /></td><td className="font-mono">{v.review_pct}%</td>
                  <td className="font-mono">{v.false_block_pct}%</td><td><Meter pct={v.catch_rate_pct} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <section aria-labelledby="corr-h" className="rounded-xl border-2 border-ink bg-white p-4">
          <h2 id="corr-h" className="font-display text-2xl font-bold uppercase tracking-wide">By injected error</h2>
          <table className="mt-3 w-full text-left">
            <thead><tr className="border-b-2 border-ink text-sm"><th className="py-2">Error</th><th>Cases</th><th>Caught</th></tr></thead>
            <tbody>
              {Object.entries(s.catch_by_corruption).map(([k, v]: [string, any]) => (
                <tr key={k} className="border-b border-slate-rule">
                  <th scope="row" className="py-2 font-medium">{LABEL[k] ?? k}</th>
                  <td className="font-mono">{v.cases}</td><td><Meter pct={v.catch_pct} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section aria-labelledby="lang-h" className="rounded-xl border-2 border-ink bg-white p-4">
          <h2 id="lang-h" className="font-display text-2xl font-bold uppercase tracking-wide">By language</h2>
          <table className="mt-3 w-full text-left">
            <thead><tr className="border-b-2 border-ink text-sm"><th className="py-2">Language</th><th>Verified</th><th>Blocked</th><th>Caught</th></tr></thead>
            <tbody>
              {Object.entries(s.by_lang).map(([k, v]: [string, any]) => (
                <tr key={k} className="border-b border-slate-rule">
                  <th scope="row" className="py-2 font-mono font-medium">{k}</th>
                  <td><Meter pct={v.verified_pct} /></td><td className="font-mono">{v.false_block_pct}%</td><td className="font-mono">{v.catch_pct}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>

      <section aria-labelledby="real-h" className="mt-6 rounded-xl border-2 border-ink bg-white p-4">
        <h2 id="real-h" className="font-display text-2xl font-bold uppercase tracking-wide">Realistic cases</h2>
        <p className="text-sm text-slate-mute">Each one is also a unit test. The note says what it guards against.</p>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[52rem] text-left text-sm">
            <thead><tr className="border-b-2 border-ink"><th className="py-2 pr-2">Alert</th><th className="pr-2">Read as</th><th className="pr-2">Result in every language</th><th>Why it is here</th></tr></thead>
            <tbody>
              {realistic.map((e: any) => {
                const st = rows.filter((r) => r.suite === "realistic" && r.id === e.id);
                const uniq = Array.from(new Set(st.map((r) => r.status)));
                return (
                  <tr key={e.id} className="border-b border-slate-rule align-top">
                    <td className="py-2 pr-2">{e.text}</td>
                    <td className="pr-2">{e.hazard.replace(/_/g, " ")}, {e.action.replace(/_/g, " ")}{e.negated ? `, ${e.negated} prohibition${e.negated > 1 ? "s" : ""}` : ""}</td>
                    <td className="pr-2 font-semibold">
                      {uniq.map((u) => <span key={u} className={TONE[u]}>{ICON[u]} {u.toLowerCase()} </span>)}
                      {e.uncovered?.length > 0 && <span className="block font-normal text-slate-mute">not covered: {e.uncovered.join(", ")}</span>}
                    </td>
                    <td className="text-slate-mute">{e.note}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <section aria-labelledby="adaption-h" className="mt-6 rounded-xl border-2 border-dashed border-slate-rule bg-white p-4">
        <h2 id="adaption-h" className="font-display text-2xl font-bold uppercase tracking-wide">Baseline vs Adaption fine tuned renderer</h2>
        {renderers.length > 0 ? (
          <table className="mt-3 w-full text-left">
            <caption className="sr-only">Model renderers measured with templates switched off</caption>
            <thead><tr className="border-b-2 border-ink text-sm"><th className="py-2">Renderer</th><th>Slot match</th><th>Literal survival</th><th>Blocked</th><th>Cases</th></tr></thead>
            <tbody>
              {renderers.map((r) => (
                <tr key={r.renderer} className="border-b border-slate-rule">
                  <th scope="row" className="py-2 font-medium">{r.renderer === "llm" ? "Baseline LLM" : r.renderer === "adaption" ? "Adaption fine tuned" : r.renderer}</th>
                  <td><Meter pct={r.slot_match_pct} /></td><td><Meter pct={r.placeholder_survival_pct} /></td>
                  <td className="font-mono">{r.false_block_rate_pct}%</td><td className="font-mono">{r.clean_cases}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="mt-2 text-slate-mute">No model renderer has been measured yet. Run the eval with --force-model llm (baseline) and --force-model adaption once a model is trained. We do not show numbers we have not measured.</p>
        )}
      </section>

      <section aria-labelledby="cav-h" className="mt-6 rounded-xl border-2 border-review bg-review-bg p-4">
        <h2 id="cav-h" className="font-semibold text-review"><span aria-hidden="true">! </span>Read these numbers with their limits</h2>
        <ul className="ml-5 mt-2 list-disc">
          {m.caveats.map((c: string) => <li key={c}>{c}</li>)}
        </ul>
      </section>

      {missed.length > 0 && (
        <section className="mt-6 rounded-xl border-2 border-blocked bg-white p-4">
          <h2 className="font-semibold text-blocked">Missed corruptions ({missed.length})</h2>
          <ul className="mt-2 font-mono text-sm">{missed.slice(0, 50).map((r: any, i: number) => <li key={i}>{r.suite} {r.id} {r.lang} {r.corruption} → {r.status}</li>)}</ul>
        </section>
      )}
    </main>
  );
}
