"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AuditLog } from "@/components/AuditLog";
import { CitizenPreview } from "@/components/CitizenPreview";
import { AreaEditor, DraftsPanel, PresetPicker, QualityPanel } from "@/components/ConsoleTools";
import { IntentCard } from "@/components/IntentCard";
import { LangCard, RENDERER, backparserLabel } from "@/components/LangCard";
import { Pictogram } from "@/components/Pictogram";
import { StatusBadge, isSendable } from "@/components/Status";
import {
  type AlertIntent, type CapArea, type CompileResponse, type Health, type IntentResult, type LintIssue, type Meta,
  type RecentAlert, type Status,
  API_URL, downloadCap, getAlert, getHealth, getMeta, getRecent, lintIntent, postCompile, postIntent,
} from "@/lib/api";

const AUTOSAVE_KEY = "stentor-console-autosave";

function loadAutosave(): { text?: string; langs?: string[] } {
  try { return JSON.parse(window.localStorage.getItem(AUTOSAVE_KEY) ?? "{}"); } catch { return {}; }
}

type Busy = null | "intent" | "compile" | "cap";

function mostCommon(values: string[]): string {
  const counts = new Map<string, number>();
  values.forEach((v) => counts.set(v, (counts.get(v) ?? 0) + 1));
  return Array.from(counts.entries()).sort((a, b) => b[1] - a[1])[0]?.[0] ?? "";
}

export default function Console() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [recent, setRecent] = useState<RecentAlert[]>([]);
  const [apiError, setApiError] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [ir, setIr] = useState<IntentResult | null>(null);
  const [intent, setIntent] = useState<AlertIntent | null>(null);
  const [langs, setLangs] = useState<string[]>([]);
  const [chaosOn, setChaosOn] = useState(false);
  const [chaosKind, setChaosKind] = useState("drop_negation");
  const [chaosLang, setChaosLang] = useState("ar");
  const [res, setRes] = useState<CompileResponse | null>(null);
  const [busy, setBusy] = useState<Busy>(null);
  const [error, setError] = useState<string | null>(null);
  const [took, setTook] = useState<number | null>(null);
  const [lint, setLint] = useState<LintIssue[]>([]);
  const [area, setArea] = useState<CapArea | null>(null);
  const [updateOf, setUpdateOf] = useState<string | null>(null);
  const [restored, setRestored] = useState(false);
  const compileRef = useRef<() => void>(() => {});

  useEffect(() => {
    Promise.all([getMeta(), getHealth()])
      .then(([m, h]) => {
        setMeta(m);
        setHealth(h);
        const known = new Set(m.languages.map((l) => l.lang));
        const saved = loadAutosave();
        const update = new URLSearchParams(window.location.search).get("update");
        if (update) {
          // Update of an earlier alert: start from its text and languages (CAP msgType Update).
          getAlert(update).then((a) => {
            setUpdateOf(a.id);
            setText(a.source_text);
            setLangs(a.results.map((r) => r.lang));
            if (a.area) setArea(a.area);
          }).catch(() => setError(`Alert ${update} could not be loaded for an update.`));
        } else {
          setText(saved.text || m.examples[0]?.text || "");
        }
        const savedLangs = (saved.langs ?? []).filter((l) => known.has(l));
        setLangs(savedLangs.length ? savedLangs : m.default_langs);
        setRestored(Boolean(saved.text) && !update);
      })
      .catch(() => setApiError(`The STENTOR API at ${API_URL} is not reachable. Start it with: cd services/api && uv run uvicorn stentor.main:app --port 8000`));
    getRecent().then(setRecent).catch(() => setRecent([]));
  }, []);

  // The chaos target must always be one of the languages being compiled.
  useEffect(() => {
    if (langs.length && !langs.includes(chaosLang)) setChaosLang(langs.includes("ar") ? "ar" : langs[0]);
  }, [langs, chaosLang]);

  // Autosave: the text and language choice survive a reload or a closed tab, in this browser only.
  useEffect(() => {
    if (!meta) return;
    try { window.localStorage.setItem(AUTOSAVE_KEY, JSON.stringify({ text, langs })); } catch {}
  }, [text, langs, meta]);

  // Re-check the intent card after every edit, so contradictions show before translating.
  useEffect(() => {
    if (!ir || !intent) return;
    const t = setTimeout(() => { lintIntent(intent, ir.mapping, ir.locked_text).then(setLint).catch(() => {}); }, 250);
    return () => clearTimeout(t);
  }, [ir, intent]);

  const langInfo = useMemo(() => Object.fromEntries((meta?.languages ?? []).map((l) => [l.lang, l])), [meta]);

  function resetFrom(step: "text" | "intent") {
    if (step === "text") { setIr(null); setIntent(null); }
    setRes(null);
    setTook(null);
  }

  async function readIntent() {
    setBusy("intent");
    setError(null);
    resetFrom("text");
    try {
      const r = await postIntent(text);
      setIr(r);
      setIntent(r.intent);
      setLint(r.lint);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function compile() {
    if (!ir || !intent) return;
    setBusy("compile");
    setError(null);
    const t0 = performance.now();
    try {
      const r = await postCompile(
        { intent, locked_text: ir.locked_text, mapping: ir.mapping, langs, references: updateOf, area },
        chaosOn ? `${chaosKind}:${chaosLang}` : undefined,
      );
      setRes(r);
      setTook((performance.now() - t0) / 1000);
      if (updateOf) { setUpdateOf(null); window.history.replaceState(null, "", "/"); }
      getRecent().then(setRecent).catch(() => {});
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function exportCap() {
    if (!res) return;
    setBusy("cap");
    setError(null);
    try {
      await downloadCap(res.alert_id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  const counts = useMemo(() => {
    const c: Record<Status, number> = { VERIFIED: 0, REVIEW: 0, BLOCKED: 0, FALLBACK: 0, APPROVED: 0, REJECTED: 0 };
    res?.results.forEach((r) => (c[r.status] += 1));
    return c;
  }, [res]);

  compileRef.current = () => { if (ir && intent && busy === null && langs.length) compile(); };
  // Keyboard: Ctrl/Cmd+Enter reads the alert (in the text box); Ctrl/Cmd+Shift+Enter translates and verifies.
  const onKey = useCallback((e: KeyboardEvent) => {
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === "Enter") { e.preventDefault(); compileRef.current(); }
  }, []);
  useEffect(() => {
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onKey]);

  const common = useMemo(() => ({
    renderer: mostCommon(res?.results.map((r) => r.renderer) ?? []),
    backparser: mostCommon(res?.results.map((r) => r.backparser) ?? []),
  }), [res]);
  const unreviewed = res ? res.results.filter((r) => r.reviewed_by === "unreviewed").length : 0;

  const sendable = res ? res.results.filter((r) => isSendable(r.status) && r.text) : [];
  const places = ir && intent ? Array.from(new Set((intent.area_refs ?? []).map((p) => ir.mapping[p]).filter(Boolean))) : [];
  const times = ir && intent ? Array.from(new Set((intent.time_refs ?? []).map((p) => ir.mapping[p]).filter(Boolean))) : [];
  const btn = "rounded-md border-2 border-ink px-4 py-2 text-base font-semibold disabled:cursor-not-allowed disabled:opacity-50";

  return (
    <main className="mx-auto max-w-7xl px-4 py-6">
      {apiError && (
        <p role="alert" className="mb-4 rounded-md border-2 border-blocked bg-blocked-bg p-3 font-semibold text-blocked">{apiError}</p>
      )}
      {health && (
        <p className="mb-4 text-sm text-slate-mute">
          Reading: <strong className="text-ink">{meta?.extractor === "lexicon" ? "rule parser" : meta?.extractor}</strong>
          {" · "}Checking: <strong className="text-ink">{meta?.backparser === "lexicon" ? "lexicon back parser" : meta?.backparser}</strong>
          {!health.anthropic_configured && " · No Claude key: approved templates translate and the lexicon checks them."}
        </p>
      )}

      {updateOf && (
        <p role="status" className="mb-4 rounded-md border-2 border-fallback bg-fallback-bg p-3 font-semibold text-fallback">
          Updating alert {updateOf}. The result is sent as a CAP Update that replaces it.{" "}
          <button type="button" className="underline" onClick={() => { setUpdateOf(null); window.history.replaceState(null, "", "/"); }}>Make a new alert instead</button>
        </p>
      )}
      {restored && !updateOf && (
        <p role="status" className="mb-4 text-sm text-slate-mute">
          Restored your last text from this browser.{" "}
          <button type="button" className="underline" onClick={() => { setText(meta?.examples[0]?.text ?? ""); setRestored(false); resetFrom("text"); }}>Start from the demo example</button>
        </p>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <div className="flex min-w-0 flex-col gap-5">
          <section aria-labelledby="compose-h" className="rounded-xl border-2 border-ink bg-white">
            <div className="flex items-baseline justify-between border-b-2 border-ink px-4 py-2">
              <h2 id="compose-h" className="font-display text-2xl font-bold uppercase tracking-wide">Write the alert</h2>
              <span className="text-xs text-slate-mute">In English, plain words</span>
            </div>
            <div className="flex flex-col gap-3 p-4">
              <label className="flex flex-col gap-1 text-sm font-semibold">
                <span className="text-xs uppercase tracking-wider text-slate-mute">Start from an example</span>
                <select
                  className="w-full min-w-0 rounded-md border-2 border-ink bg-white px-2 py-1.5 text-base"
                  value=""
                  onChange={(e) => {
                    const ex = meta?.examples.find((x) => x.id === e.target.value);
                    if (ex) { setText(ex.text); resetFrom("text"); }
                  }}
                >
                  <option value="" disabled>Choose an example alert</option>
                  {meta?.examples.map((x) => <option key={x.id} value={x.id}>{x.label}</option>)}
                </select>
              </label>
              <label className="flex flex-col gap-1 text-sm font-semibold">
                <span className="text-xs uppercase tracking-wider text-slate-mute">Alert text</span>
                <textarea
                  value={text}
                  onChange={(e) => { setText(e.target.value); resetFrom("text"); }}
                  onKeyDown={(e) => {
                    if ((e.ctrlKey || e.metaKey) && !e.shiftKey && e.key === "Enter" && text.trim() && busy === null) { e.preventDefault(); readIntent(); }
                  }}
                  aria-describedby="compose-keys"
                  rows={4}
                  className="rounded-md border-2 border-ink p-3 text-lg leading-snug"
                />
              </label>
              <p className="text-xs text-slate-mute">Names, times, numbers and phone numbers are found and locked automatically. To force a name, wrap it: ⟦Altadena⟧.</p>
              <p id="compose-keys" className="text-xs text-slate-mute">Keys: <kbd className="font-mono">Ctrl/⌘ + Enter</kbd> reads the alert, <kbd className="font-mono">Ctrl/⌘ + Shift + Enter</kbd> translates and verifies.</p>
              <button type="button" onClick={readIntent} disabled={!text.trim() || busy !== null} className={`${btn} bg-ink text-white`}>
                {busy === "intent" ? "Reading…" : "Read the alert"}
              </button>
            </div>
          </section>

          <DraftsPanel text={text} langs={langs}
            onLoad={(d) => { setText(d.text); if (d.langs.length) setLangs(d.langs); resetFrom("text"); }} />

          {ir && intent && meta && (
            <IntentCard result={ir} intent={intent} phrasebook={meta.phrasebook}
              onChange={(i) => { setIntent(i); resetFrom("intent"); }} />
          )}

          {ir && <QualityPanel ir={ir} lint={lint} />}

          {ir && intent && (
            <section aria-labelledby="compile-h" className="rounded-xl border-2 border-ink bg-white p-4">
              <h2 id="compile-h" className="sr-only">Translate and verify</h2>
              <fieldset>
                <legend className="text-xs font-semibold uppercase tracking-wider text-slate-mute">Languages</legend>
                <div className="mt-2 flex flex-wrap gap-2">
                  {meta?.languages.map((l) => (
                    <label key={l.lang} className="flex items-center gap-2 rounded-md border-2 border-slate-rule px-2 py-1 text-sm font-medium">
                      <input
                        type="checkbox"
                        className="h-4 w-4 accent-[#13212E]"
                        checked={langs.includes(l.lang)}
                        onChange={(e) => { setLangs(e.target.checked ? [...langs, l.lang] : langs.filter((x) => x !== l.lang)); resetFrom("intent"); }}
                      />
                      {l.english_name}
                    </label>
                  ))}
                </div>
                <PresetPicker langs={langs} onPick={(l) => { setLangs(l); resetFrom("intent"); }} />
              </fieldset>

              <AreaEditor value={area} onChange={(a) => { setArea(a); resetFrom("intent"); }} />

              <div className={`mt-4 rounded-md border-2 ${chaosOn ? "border-ink" : "border-dashed border-slate-rule"}`}>
                {chaosOn && <div className="tape h-2" aria-hidden="true" />}
                <div className="p-3">
                  <label className="flex items-center gap-2 font-semibold">
                    <input type="checkbox" className="h-5 w-5 accent-[#13212E]" checked={chaosOn} onChange={(e) => { setChaosOn(e.target.checked); resetFrom("intent"); }} />
                    Chaos mode: inject a translation error (demo only)
                  </label>
                  <p className="mt-1 text-sm text-slate-mute">Corrupts one language after translating and before checking, to show that the error is caught.</p>
                  {chaosOn && (
                    <div className="mt-2 flex flex-wrap gap-3">
                      <label className="flex flex-col text-xs font-semibold uppercase tracking-wider text-slate-mute">
                        Error
                        <select value={chaosKind} onChange={(e) => { setChaosKind(e.target.value); resetFrom("intent"); }} className="mt-1 rounded-md border-2 border-ink bg-white px-2 py-1 text-base normal-case tracking-normal text-ink">
                          {meta?.corruptions.map((c) => <option key={c} value={c}>{c.replace(/_/g, " ")}</option>)}
                        </select>
                      </label>
                      <label className="flex flex-col text-xs font-semibold uppercase tracking-wider text-slate-mute">
                        In language
                        <select value={chaosLang} onChange={(e) => { setChaosLang(e.target.value); resetFrom("intent"); }} className="mt-1 rounded-md border-2 border-ink bg-white px-2 py-1 text-base normal-case tracking-normal text-ink">
                          {langs.map((l) => <option key={l} value={l}>{langInfo[l]?.english_name ?? l}</option>)}
                        </select>
                      </label>
                    </div>
                  )}
                </div>
              </div>

              <button type="button" onClick={compile} disabled={busy !== null || langs.length === 0} className={`${btn} mt-4 w-full bg-tape text-ink`}>
                {busy === "compile" ? "Translating and checking…" : `Translate and verify ${langs.length} language${langs.length === 1 ? "" : "s"}`}
              </button>
            </section>
          )}
        </div>

        <div className="flex min-w-0 flex-col gap-5" aria-live="polite">
          {error && <p role="alert" className="rounded-md border-2 border-blocked bg-blocked-bg p-3 font-semibold text-blocked">{error}</p>}

          {!res && (
            <section className="rounded-xl border-2 border-dashed border-slate-rule p-8 text-slate-mute">
              <h2 className="font-display text-3xl font-black uppercase tracking-wide text-ink">One alert in. Every language checked.</h2>
              <ol className="mt-4 list-decimal space-y-1 pl-5 text-base">
                <li>Write the alert in English, or pick an example.</li>
                <li>Read it: STENTOR shows what it understood and locks names, times and numbers.</li>
                <li>Translate and verify: each language is read back and compared slot by slot.</li>
                <li>Only languages whose meaning matches are sent. A blocked language gets a safe generic warning.</li>
              </ol>
              {recent.length > 0 && (
                <div className="mt-6">
                  <h3 className="text-xs font-semibold uppercase tracking-wider">Recent alerts</h3>
                  <ul className="mt-2 divide-y divide-slate-rule rounded-md border border-slate-rule bg-white text-ink">
                    {recent.map((a) => (
                      <li key={a.id} className="flex flex-wrap items-center gap-2 px-3 py-2 text-sm">
                        <a href={`/alerts/${a.id}`} className="flex-1 truncate underline">{a.source_text}</a>
                        {a.msg_type !== "Alert" && <span className="rounded border border-ink px-1 text-xs font-bold">{a.msg_type}</span>}
                        {a.chaos && <span className="rounded bg-tape px-1 text-xs font-bold">chaos</span>}
                        <span className="font-mono text-xs text-slate-mute">
                          {Object.values(a.statuses).filter((s) => s === "VERIFIED").length}/{Object.keys(a.statuses).length} verified
                        </span>
                      </li>
                    ))}
                  </ul>
                  <a href="/history" className="mt-2 inline-block text-sm font-semibold text-ink underline">All alerts</a>
                </div>
              )}
            </section>
          )}

          {res && (
            <>
              <section aria-labelledby="summary-h" className="rounded-xl border-2 border-ink bg-ink p-4 text-white">
                <h2 id="summary-h" className="sr-only">Result summary</h2>
                <div className="flex flex-wrap items-center gap-3">
                  {(["VERIFIED", "APPROVED", "FALLBACK", "REVIEW", "BLOCKED", "REJECTED"] as const).map((s) =>
                    counts[s] ? (
                      <span key={s} className="flex items-center gap-2"><StatusBadge status={s} /><span className="font-mono text-lg">×{counts[s]}</span></span>
                    ) : null,
                  )}
                  {took !== null && <span className="ml-auto font-mono text-sm text-slate-rule">checked in {took < 1 ? `${Math.round(took * 1000)} ms` : `${took.toFixed(1)} s`}</span>}
                </div>
                {res.msg_type !== "Alert" && (
                  <p className="mt-2 text-sm font-semibold text-tape">CAP {res.msg_type} of alert {res.references}.</p>
                )}
                {res.duplicate_of && (
                  <p role="status" className="mt-2 rounded-md bg-review-bg px-2 py-1 text-sm font-semibold text-review">
                    The same English text was compiled recently as alert{" "}
                    <a className="underline" href={`/alerts/${res.duplicate_of}`}>{res.duplicate_of}</a>. Check it is not a duplicate send.
                  </p>
                )}
                <p className="mt-2 text-sm text-slate-rule">
                  Translated by {RENDERER[common.renderer] ?? common.renderer}, checked by {backparserLabel(common.backparser)}.
                  {unreviewed > 0 && ` ${unreviewed} of ${res.results.length} lexicons are not yet reviewed by a native speaker.`}
                </p>
                <div className="mt-3 flex flex-wrap gap-3">
                  <button type="button" onClick={exportCap} disabled={busy !== null} className={`${btn} border-white bg-white text-ink`}>
                    {busy === "cap" ? "Exporting…" : "Download CAP 1.2 XML"}
                  </button>
                  <a href={`/a/${res.alert_id}`} className={`${btn} border-white text-white`}>Public alert page</a>
                  <a href={`/alerts/${res.alert_id}`} className={`${btn} border-white text-white`}>
                    {counts.REVIEW ? `Review ${counts.REVIEW} language${counts.REVIEW === 1 ? "" : "s"}` : "Details and exports"}
                  </a>
                  <span className="self-center text-sm text-slate-rule">CAP holds English plus {sendable.length} sendable language{sendable.length === 1 ? "" : "s"}.</span>
                </div>
              </section>

              <div className="grid gap-4 xl:grid-cols-2">
                {res.results.map((r) => <LangCard key={r.lang} r={r} common={common} />)}
              </div>

              <AuditLog alertId={res.alert_id} />
            </>
          )}
        </div>
      </div>

      {res && intent && (
        <div className="mt-8 rounded-xl border-2 border-ink bg-white p-5">
          <CitizenPreview
            key={res.alert_id}
            langs={[{ lang: "en", name: "English", dir: "ltr", tts: "en-US", status: "SOURCE", text: res.source_text }, ...sendable.map((r) => ({ lang: r.lang, name: r.name, dir: r.dir, tts: r.tts, status: r.status, text: r.text! }))]}
            pictogram={<Pictogram intent={res.intent} places={places} times={times} />}
            publicHref={`/a/${res.alert_id}`}
          />
        </div>
      )}
    </main>
  );
}
