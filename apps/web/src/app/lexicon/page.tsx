"use client";

import { useEffect, useMemo, useState } from "react";
import {
  type LexiconView, type LintReport, type Meta, type Signoff,
  getLexicon, getLexiconLint, getMeta, getSignoffs, signoffLexicon,
} from "@/lib/api";

const field = "rounded-md border-2 border-ink bg-white px-2 py-1 text-base";
const SECTIONS = ["all", "hazard", "action", "instruction", "headline", "other"];

export default function LexiconPage() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [lang, setLang] = useState("vi");
  const [view, setView] = useState<LexiconView | null>(null);
  const [lint, setLint] = useState<LintReport | null>(null);
  const [signoffs, setSignoffs] = useState<Signoff[]>([]);
  const [section, setSection] = useState("all");
  const [filter, setFilter] = useState("");
  const [reviewer, setReviewer] = useState("");
  const [note, setNote] = useState("");
  const [native, setNative] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    getMeta().then(setMeta).catch(() => {});
    const q = new URLSearchParams(window.location.search).get("lang");
    if (q) setLang(q);
  }, []);
  useEffect(() => {
    setView(null); setLint(null); setMsg(null);
    getLexicon(lang).then(setView).catch((e: Error) => setMsg(e.message));
    getLexiconLint(lang).then(setLint).catch(() => {});
    getSignoffs(lang).then(setSignoffs).catch(() => setSignoffs([]));
  }, [lang]);

  const rows = useMemo(() => {
    const f = filter.trim().toLowerCase();
    return (view?.rows ?? []).filter((r) => (section === "all" || r.section === section)
      && (!f || [r.key, r.en, r.text, ...r.match].some((x) => x.toLowerCase().includes(f))));
  }, [view, section, filter]);

  return (
    <main className="mx-auto max-w-6xl px-4 py-6">
      <h1 className="font-display text-4xl font-black uppercase tracking-wide">Lexicons</h1>
      <p className="mt-1 max-w-3xl text-slate-mute">Every approved phrase next to its English source. A language access coordinator who reads both can check the whole lexicon in one pass, then sign it off.</p>

      <div className="mt-4 flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-xs font-semibold uppercase tracking-wider text-slate-mute">Language
          <select className={field} value={lang} onChange={(e) => { setLang(e.target.value); history.replaceState(null, "", `?lang=${e.target.value}`); }}>
            {meta?.languages.map((l) => <option key={l.lang} value={l.lang}>{l.english_name} ({l.name})</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs font-semibold uppercase tracking-wider text-slate-mute">Section
          <select className={field} value={section} onChange={(e) => setSection(e.target.value)}>
            {SECTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs font-semibold uppercase tracking-wider text-slate-mute">Filter
          <input type="search" className={field} value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="elevators" />
        </label>
      </div>

      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <section aria-labelledby="lint-h" className="rounded-xl border-2 border-ink bg-white p-4">
          <h2 id="lint-h" className="font-display text-xl font-bold uppercase tracking-wide">Lint</h2>
          {!lint ? <p className="text-sm text-slate-mute">Checking every template…</p> : (
            <>
              <p className={`mt-1 font-semibold ${lint.ok ? "text-ok" : "text-blocked"}`}>
                <span aria-hidden="true">{lint.ok ? "✓ " : "✕ "}</span>
                {lint.ok ? `Clean: ${lint.checked_templates} templates read back to their own meaning.` : `${lint.errors} error(s)`}
                {lint.warnings ? ` ${lint.warnings} warning(s).` : ""}
              </p>
              <ul className="mt-2 max-h-48 space-y-1 overflow-auto text-sm">
                {lint.findings.map((f, i) => (
                  <li key={i} className={f.severity === "error" ? "text-blocked" : "text-review"}>
                    <span className="font-mono">{f.where}</span>: {f.message}
                  </li>
                ))}
              </ul>
            </>
          )}
        </section>

        <section aria-labelledby="so-h" className="rounded-xl border-2 border-ink bg-white p-4">
          <h2 id="so-h" className="font-display text-xl font-bold uppercase tracking-wide">Native speaker sign-off</h2>
          <p className="text-sm text-slate-mute">File status: <strong>{view?.reviewed_by ?? "…"}</strong>. Sign-offs are recorded in the audit trail; they do not rewrite the lexicon file.</p>
          {signoffs.length > 0 && (
            <ul className="mt-2 text-sm">{signoffs.map((s, i) => <li key={i}>{s.reviewer}, {new Date(s.created_at).toLocaleDateString()}{s.note ? `: ${s.note}` : ""}</li>)}</ul>
          )}
          <form className="mt-3 flex flex-col gap-2" onSubmit={async (e) => {
            e.preventDefault();
            try {
              await signoffLexicon(lang, reviewer.trim(), note.trim(), native);
              setMsg("Sign-off recorded."); setNote(""); setNative(false);
              getSignoffs(lang).then(setSignoffs);
            } catch (err) { setMsg((err as Error).message); }
          }}>
            <div className="flex flex-wrap gap-2">
              <label className="sr-only" htmlFor="so-name">Reviewer name</label>
              <input id="so-name" className={`${field} min-w-0 flex-1`} placeholder="Your name" value={reviewer} onChange={(e) => setReviewer(e.target.value)} />
              <label className="sr-only" htmlFor="so-note">Note</label>
              <input id="so-note" className={`${field} min-w-0 flex-1`} placeholder="Note (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
            </div>
            <label className="flex items-start gap-2 text-sm">
              <input type="checkbox" className="mt-1 h-4 w-4" checked={native} onChange={(e) => setNative(e.target.checked)} />
              I am a native speaker of {view?.english_name ?? "this language"} and I checked every phrase below.
            </label>
            <button type="submit" disabled={!native || reviewer.trim().length < 2 || !lint?.ok}
              className="self-start rounded-md border-2 border-ink bg-ink px-3 py-1.5 font-semibold text-white disabled:opacity-50">Sign off</button>
            {msg && <p role="status" className="text-sm">{msg}</p>}
          </form>
        </section>
      </div>

      {view && (
        <section aria-labelledby="rows-h" className="mt-6 rounded-xl border-2 border-ink bg-white">
          <h2 id="rows-h" className="px-4 pt-3 font-display text-xl font-bold uppercase tracking-wide">
            Phrases <span className="font-sans text-sm font-normal normal-case text-slate-mute">({rows.length}) · negation markers: <span lang={lang}>{view.negation_markers.join(", ")}</span></span>
          </h2>
          <div className="mt-2 overflow-x-auto">
            <table className="w-full min-w-[40rem] text-left text-sm">
              <thead className="bg-slate-paper"><tr><th className="px-3 py-1.5">Key</th><th>English</th><th>{view.english_name}</th><th className="pr-3">Matched as</th></tr></thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={i} className={`border-t border-slate-rule/60 align-top ${r.text ? "" : "bg-blocked-bg"}`}>
                    <td className="px-3 py-1 font-mono text-xs">{r.section}<br />{r.key}{r.variant ? ` · ${r.variant}` : ""}</td>
                    <td className="py-1 pr-2">{r.en}</td>
                    <td className="py-1 pr-2" lang={lang} dir={view.dir}>{r.text || <span className="font-semibold text-blocked">missing</span>}</td>
                    <td className="py-1 pr-3 text-xs text-slate-mute" lang={lang} dir={view.dir}>{r.match.join(" · ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </main>
  );
}
