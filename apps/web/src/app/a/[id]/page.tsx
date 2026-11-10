"use client";

import { useEffect, useRef, useState } from "react";
import { AudioButton } from "@/components/CitizenPreview";
import { Pictogram, PictogramSvg, downloadSvg } from "@/components/Pictogram";
import { type PublicAlert, copyText, getPublic } from "@/lib/api";

const LARGE_KEY = "stentor-large-text";

/** Best match for the reader's browser languages among the languages this alert has. */
function preferredLang(available: string[]): string | null {
  const wanted = typeof navigator === "undefined" ? [] : navigator.languages ?? [navigator.language];
  for (const w of wanted) {
    const base = w.toLowerCase().split("-")[0];
    if (available.includes(base)) return base;
  }
  return null;
}

export default function PublicAlertPage({ params }: { params: { id: string } }) {
  // null until the URL has been read, so the first request already uses ?lang=
  const [lang, setLang] = useState<string | null>(null);
  const explicit = useRef(false); // language chosen by the link or the reader
  const [data, setData] = useState<PublicAlert | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [large, setLarge] = useState(false);
  const [shared, setShared] = useState<string | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    const q = new URLSearchParams(window.location.search).get("lang");
    explicit.current = Boolean(q);
    setLang(q ?? "en");
    try { setLarge(localStorage.getItem(LARGE_KEY) === "1"); } catch {}
  }, []);

  useEffect(() => {
    if (lang === null) return;
    let live = true;
    getPublic(params.id, lang)
      .then((d) => {
        if (!live) return;
        setData(d);
        // No ?lang= in the link: open in the reader's own language when the alert has it.
        if (!explicit.current) {
          const pick = preferredLang(d.languages.map((l) => l.lang));
          explicit.current = true;
          if (pick && pick !== d.selected.lang) setLang(pick);
        }
      })
      .catch(() => { if (live) setError("This alert could not be found. Check the link."); });
    return () => { live = false; };
  }, [params.id, lang]);

  if (error) return <main className="mx-auto max-w-2xl p-6"><p role="alert" className="text-lg font-semibold text-blocked">{error}</p></main>;
  if (!data) return <main className="mx-auto max-w-2xl p-6"><p>Loading alert…</p></main>;
  const cur = data.selected;
  const link = typeof window === "undefined" ? "" : `${window.location.origin}/a/${data.id}?lang=${cur.lang}`;

  async function share() {
    const nav = navigator as Navigator & { share?: (d: ShareData) => Promise<void> };
    try {
      if (nav.share) { await nav.share({ title: "Emergency alert", text: cur.text, url: link }); setShared("Shared."); return; }
    } catch { /* fall back to copying */ }
    setShared((await copyText(link)) ? "Link copied." : "Could not copy the link.");
  }

  const btn = "rounded-md border-2 border-ink bg-white px-3 py-1 text-sm font-semibold";
  return (
    <main className="mx-auto max-w-2xl px-4 py-6">
      {data.superseded_by && (
        <p role="alert" className="mb-3 rounded-md border-2 border-fallback bg-fallback-bg p-3 font-semibold text-fallback">
          This alert was updated or cancelled. <a className="underline" href={`/a/${data.superseded_by}?lang=${cur.lang}`}>See the latest message</a>.
        </p>
      )}
      {data.expired && !data.superseded_by && (
        <p role="alert" className="mb-3 rounded-md border-2 border-slate-mute bg-slate-paper p-3 font-semibold">
          This alert ended at {new Date(data.expires_at!).toLocaleString()}. Follow current official instructions.
        </p>
      )}
      <div className="tape h-3 rounded-t-md" aria-hidden="true" />
      <article className="rounded-b-xl border-2 border-t-0 border-ink bg-white p-5">
        <div className="flex flex-wrap items-center gap-2">
          <p className="font-display text-lg font-black uppercase tracking-widest text-blocked">
            {data.msg_type === "Cancel" ? "Alert cancelled" : data.msg_type === "Update" ? "Alert update" : "Emergency alert"}
          </p>
          <div className="ml-auto flex flex-wrap gap-2">
            <button type="button" aria-pressed={large} className={btn}
              onClick={() => { setLarge(!large); try { localStorage.setItem(LARGE_KEY, large ? "0" : "1"); } catch {} }}>
              {large ? "Normal text" : "Large text"}
            </button>
            <button type="button" className={btn} onClick={share}>Share</button>
          </div>
        </div>
        {shared && <p role="status" className="mt-1 text-sm text-slate-mute">{shared}</p>}
        <nav aria-label="Language" className="mt-3 flex flex-wrap gap-2">
          {data.languages.map((l) => (
            <button
              key={l.lang}
              type="button"
              lang={l.lang}
              aria-pressed={l.lang === cur.lang}
              onClick={() => { setLang(l.lang); history.replaceState(null, "", `?lang=${l.lang}`); }}
              className={`rounded-md border-2 px-3 py-1 text-base font-medium ${l.lang === cur.lang ? "border-ink bg-ink text-white" : "border-slate-rule"}`}
            >
              {l.name}
            </button>
          ))}
        </nav>
        <div lang={cur.lang} dir={cur.dir} className="mt-5">
          <p className={large ? "text-4xl font-semibold leading-snug" : "text-2xl leading-snug"}>{cur.text}</p>
          {cur.status === "FALLBACK" && <p className="mt-2 text-sm text-slate-mute" dir="ltr" lang="en">Short safe version. The full message is available in English.</p>}
        </div>
        {data.expires_at && !data.expired && (
          <p className="mt-3 text-sm text-slate-mute" dir="ltr" lang="en">In effect until {new Date(data.expires_at).toLocaleString()}.</p>
        )}
        <div className="mt-4"><AudioButton text={cur.text} tts={cur.tts} /></div>
        <div className="mt-5"><Pictogram intent={data.intent} places={data.places} times={data.times} /></div>
        <div className="mt-3 flex flex-wrap gap-3 text-sm">
          <button type="button" className="font-semibold underline" onClick={() => downloadSvg(svgRef.current, `stentor-${data.id}-pictogram.svg`)}>Download pictogram (SVG)</button>
          <a className="font-semibold underline" href={`/a/${data.id}/print`}>Printable poster</a>
        </div>
        <div className="hidden" aria-hidden="true"><PictogramSvg intent={data.intent} places={data.places} times={data.times} svgRef={svgRef} /></div>
        <p className="mt-5 text-xs text-slate-mute">Demo alert generated by STENTOR. Not an official warning.</p>
      </article>
    </main>
  );
}
