"use client";

import { useEffect, useState } from "react";
import {
  type CapArea, type Draft, type IntentResult, type LintIssue, type Meta, type Preset,
  deleteDraft, deletePreset, getDrafts, getPresets, saveDraft, savePreset,
} from "@/lib/api";

const panel = "rounded-xl border-2 border-ink bg-white";
const small = "rounded-md border-2 border-ink bg-white px-2 py-1 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-50";
const input = "rounded-md border-2 border-ink bg-white px-2 py-1 text-base";

/** Plain-language and consistency checks on the source, before anything is translated. */
export function QualityPanel({ ir, lint }: { ir: IntentResult; lint: LintIssue[] }) {
  const rd = ir.readability;
  const warnings = lint.filter((i) => i.severity === "warning");
  const infos = lint.filter((i) => i.severity !== "warning");
  if (!rd && !lint.length) return null;
  return (
    <section aria-labelledby="quality-h" className={`${panel} p-4`}>
      <h2 id="quality-h" className="font-display text-xl font-bold uppercase tracking-wide">Source check</h2>
      {rd && (
        <dl className="mt-2 grid grid-cols-3 gap-2 text-center">
          <div className="rounded-md bg-slate-paper p-2">
            <dt className="text-xs uppercase tracking-wider text-slate-mute">Reading grade</dt>
            <dd className={`font-mono text-xl font-bold ${rd.grade > 8 ? "text-review" : "text-ok"}`}>{rd.grade}</dd>
          </div>
          <div className="rounded-md bg-slate-paper p-2">
            <dt className="text-xs uppercase tracking-wider text-slate-mute">Sentences</dt>
            <dd className="font-mono text-xl font-bold">{rd.sentences}</dd>
          </div>
          <div className="rounded-md bg-slate-paper p-2">
            <dt className="text-xs uppercase tracking-wider text-slate-mute">Words / sentence</dt>
            <dd className="font-mono text-xl font-bold">{rd.words_per_sentence}</dd>
          </div>
        </dl>
      )}
      {rd?.notes.length ? <ul className="mt-2 list-disc pl-5 text-sm text-review">{rd.notes.map((n) => <li key={n}>{n}</li>)}</ul> : null}
      {warnings.length > 0 && (
        <ul className="mt-3 space-y-1 text-sm" aria-label="Warnings about the intent">
          {warnings.map((w, i) => (
            <li key={i} className="rounded-md border-2 border-review bg-review-bg px-2 py-1 font-medium text-review">
              <span aria-hidden="true">! </span><span className="sr-only">Warning: </span>{w.message}
            </li>
          ))}
        </ul>
      )}
      {infos.length > 0 && (
        <ul className="mt-2 space-y-0.5 text-sm text-slate-mute">
          {infos.map((w, i) => <li key={i}><span aria-hidden="true">i </span>{w.message}</li>)}
        </ul>
      )}
      {ir.glossary_locked.length > 0 && (
        <p className="mt-2 text-sm text-slate-mute">Glossary names locked: {ir.glossary_locked.join(", ")}</p>
      )}
    </section>
  );
}

/** Saved alert drafts on the server, so a team can prepare wording before an incident. */
export function DraftsPanel({ text, langs, onLoad }: { text: string; langs: string[]; onLoad: (d: Draft) => void }) {
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [name, setName] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const refresh = () => getDrafts().then(setDrafts).catch(() => setDrafts([]));
  useEffect(() => { refresh(); }, []);
  const existing = drafts.find((d) => d.name.toLowerCase() === name.trim().toLowerCase());
  return (
    <details className={panel}>
      <summary className="cursor-pointer px-4 py-2 font-semibold">Drafts <span className="text-sm font-normal text-slate-mute">({drafts.length} saved)</span></summary>
      <div className="flex flex-col gap-2 border-t border-slate-rule p-4">
        <div className="flex flex-wrap gap-2">
          <label className="sr-only" htmlFor="draft-name">Draft name</label>
          <input id="draft-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Draft name" className={`${input} min-w-0 flex-1`} />
          <button type="button" className={small} disabled={!name.trim() || !text.trim()}
            onClick={async () => {
              try {
                await saveDraft({ name: name.trim(), text, langs }, existing?.id);
                setMsg(existing ? "Draft updated." : "Draft saved.");
                refresh();
              } catch (e) { setMsg((e as Error).message); }
            }}>
            {existing ? "Update draft" : "Save draft"}
          </button>
        </div>
        {msg && <p role="status" className="text-sm text-slate-mute">{msg}</p>}
        {drafts.length > 0 && (
          <ul className="divide-y divide-slate-rule rounded-md border border-slate-rule">
            {drafts.map((d) => (
              <li key={d.id} className="flex items-center gap-2 px-2 py-1.5 text-sm">
                <span className="min-w-0 flex-1 truncate"><strong>{d.name}</strong> <span className="text-slate-mute">{d.text}</span></span>
                <button type="button" className={small} onClick={() => { onLoad(d); setName(d.name); }}>Load</button>
                <button type="button" className={small} aria-label={`Delete draft ${d.name}`}
                  onClick={async () => { await deleteDraft(d.id).catch(() => {}); refresh(); }}>Delete</button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </details>
  );
}

/** Named language sets (audiences). Built-in ones cannot be deleted. */
export function PresetPicker({ langs, onPick }: { langs: string[]; onPick: (langs: string[]) => void }) {
  const [presets, setPresets] = useState<Preset[]>([]);
  const [name, setName] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const refresh = () => getPresets().then(setPresets).catch(() => setPresets([]));
  useEffect(() => { refresh(); }, []);
  const same = (a: string[], b: string[]) => a.length === b.length && a.every((x) => b.includes(x));
  return (
    <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
      <span className="text-xs font-semibold uppercase tracking-wider text-slate-mute">Presets</span>
      {presets.map((p) => (
        <span key={p.id} className="inline-flex items-center">
          <button type="button" aria-pressed={same(p.langs, langs)} onClick={() => onPick(p.langs)}
            className={`rounded-l-md border-2 px-2 py-0.5 font-medium ${same(p.langs, langs) ? "border-ink bg-ink text-white" : "border-slate-rule bg-white"} ${p.builtin ? "rounded-r-md" : ""}`}>
            {p.name}
          </button>
          {!p.builtin && (
            <button type="button" aria-label={`Delete preset ${p.name}`} onClick={async () => { await deletePreset(p.id).catch(() => {}); refresh(); }}
              className="rounded-r-md border-2 border-l-0 border-slate-rule bg-white px-1.5 py-0.5">×</button>
          )}
        </span>
      ))}
      <label className="sr-only" htmlFor="preset-name">New preset name</label>
      <input id="preset-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Save selection as…" className="w-40 rounded-md border-2 border-slate-rule px-2 py-0.5" />
      <button type="button" className={small} disabled={!name.trim() || !langs.length}
        onClick={async () => {
          try { await savePreset(name.trim(), langs); setName(""); setMsg(null); refresh(); } catch (e) { setMsg((e as Error).message); }
        }}>Save</button>
      {msg && <span role="status" className="text-blocked">{msg}</span>}
    </div>
  );
}

/** Optional CAP geometry. One "lat,lon" per line makes a polygon (closed automatically). */
export function AreaEditor({ value, onChange }: { value: CapArea | null; onChange: (a: CapArea | null) => void }) {
  const [desc, setDesc] = useState(value?.desc ?? "");
  const [poly, setPoly] = useState((value?.polygons?.[0] ?? []).map((p) => p.join(",")).join("\n"));
  const [circle, setCircle] = useState(value?.circles?.[0] ? `${value.circles[0].lat},${value.circles[0].lon} ${value.circles[0].radius_km}` : "");
  const [geocode, setGeocode] = useState(value?.geocodes?.[0] ? `${value.geocodes[0].name}=${value.geocodes[0].value}` : "");
  const [error, setError] = useState<string | null>(null);

  function apply(next: { desc?: string; poly?: string; circle?: string; geocode?: string }) {
    const d = next.desc ?? desc, p = next.poly ?? poly, c = next.circle ?? circle, g = next.geocode ?? geocode;
    const area: CapArea = { desc: d.trim() || null, polygons: [], circles: [], geocodes: [] };
    const problems: string[] = [];
    const pts = p.split("\n").map((l) => l.trim()).filter(Boolean).map((l) => l.split(/[,\s]+/).map(Number));
    if (pts.length) {
      if (pts.some((x) => x.length !== 2 || x.some(Number.isNaN))) problems.push("polygon lines must be 'lat,lon'");
      else if (pts.length < 3) problems.push("a polygon needs at least 3 points");
      else area.polygons = [pts as [number, number][]];
    }
    if (c.trim()) {
      const m = c.trim().match(/^(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)$/);
      if (!m) problems.push("circle must be 'lat,lon radius_km'");
      else area.circles = [{ lat: +m[1], lon: +m[2], radius_km: +m[3] }];
    }
    if (g.trim()) {
      const [n, v] = g.split("=").map((x) => x.trim());
      if (!n || !v) problems.push("geocode must be 'NAME=value'");
      else area.geocodes = [{ name: n, value: v }];
    }
    setError(problems.length ? problems.join("; ") : null);
    const empty = !area.desc && !area.polygons?.length && !area.circles?.length && !area.geocodes?.length;
    onChange(problems.length || empty ? null : area);
  }

  return (
    <details className="mt-3 rounded-md border-2 border-dashed border-slate-rule">
      <summary className="cursor-pointer px-3 py-2 text-sm font-semibold">
        Map area for CAP (optional){value ? " · set" : ""}
      </summary>
      <div className="grid gap-2 border-t border-slate-rule p-3 text-sm sm:grid-cols-2">
        <label className="flex flex-col gap-1 sm:col-span-2">Area description
          <input className={input} value={desc} onChange={(e) => { setDesc(e.target.value); apply({ desc: e.target.value }); }} placeholder="Altadena evacuation zone" />
        </label>
        <label className="flex flex-col gap-1">Polygon, one lat,lon per line
          <textarea className={`${input} font-mono text-sm`} rows={4} value={poly} onChange={(e) => { setPoly(e.target.value); apply({ poly: e.target.value }); }} placeholder={"34.18,-118.15\n34.20,-118.10\n34.17,-118.09"} />
        </label>
        <div className="flex flex-col gap-2">
          <label className="flex flex-col gap-1">Circle (lat,lon radius km)
            <input className={`${input} font-mono text-sm`} value={circle} onChange={(e) => { setCircle(e.target.value); apply({ circle: e.target.value }); }} placeholder="34.19,-118.13 2.5" />
          </label>
          <label className="flex flex-col gap-1">Geocode (NAME=value)
            <input className={`${input} font-mono text-sm`} value={geocode} onChange={(e) => { setGeocode(e.target.value); apply({ geocode: e.target.value }); }} placeholder="SAME=006037" />
          </label>
        </div>
        {error && <p role="alert" className="font-semibold text-blocked sm:col-span-2">{error}</p>}
      </div>
    </details>
  );
}

export type { Meta };
