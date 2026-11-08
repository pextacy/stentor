"use client";

import { useEffect, useState } from "react";

type Lang = { lang: string; name: string; dir: string; tts: string; status: string; text: string };

export function useSpeech() {
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  const [speaking, setSpeaking] = useState(false);
  useEffect(() => {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
    const load = () => setVoices(window.speechSynthesis.getVoices());
    load();
    window.speechSynthesis.addEventListener("voiceschanged", load);
    return () => window.speechSynthesis.removeEventListener("voiceschanged", load);
  }, []);
  const voiceFor = (tts: string) =>
    voices.find((v) => v.lang.toLowerCase() === tts.toLowerCase()) ??
    voices.find((v) => v.lang.toLowerCase().startsWith(tts.split("-")[0].toLowerCase()));
  const speak = (text: string, tts: string) => {
    const v = voiceFor(tts);
    if (!v) return false;
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.voice = v;
    u.lang = v.lang;
    u.rate = 0.9;
    u.onend = () => setSpeaking(false);
    u.onerror = () => setSpeaking(false);
    setSpeaking(true);
    window.speechSynthesis.speak(u);
    return true;
  };
  const stop = () => {
    window.speechSynthesis.cancel();
    setSpeaking(false);
  };
  return { voiceFor, speak, stop, speaking, ready: voices.length > 0 };
}

export function AudioButton({ text, tts }: { text: string; tts: string }) {
  const { voiceFor, speak, stop, speaking, ready } = useSpeech();
  const has = ready && !!voiceFor(tts);
  if (!has) {
    return <p className="text-sm text-slate-mute">Audio is not available for this language on this device.</p>;
  }
  return (
    <button
      type="button"
      onClick={() => (speaking ? stop() : speak(text, tts))}
      className="inline-flex items-center gap-2 rounded-md border-2 border-ink bg-white px-3 py-1.5 font-semibold"
    >
      <span aria-hidden="true">{speaking ? "■" : "▶"}</span>
      {speaking ? "Stop audio" : "Play audio"}
    </button>
  );
}

export function CitizenPreview({ langs, pictogram, publicHref }: { langs: Lang[]; pictogram: React.ReactNode; publicHref?: string }) {
  const [sel, setSel] = useState(langs.find((l) => l.dir === "rtl")?.lang ?? langs[0]?.lang);
  const cur = langs.find((l) => l.lang === sel) ?? langs[0];
  if (!cur) return null;
  return (
    <section aria-labelledby="citizen-h" className="flex flex-col gap-4 lg:flex-row lg:items-start">
      <div className="lg:w-64">
        <h2 id="citizen-h" className="font-display text-2xl font-bold uppercase tracking-wide">Citizen preview</h2>
        <p className="mt-1 text-sm text-slate-mute">What a resident sees. Only verified and safe fallback languages appear here.</p>
        <fieldset className="mt-3">
          <legend className="text-xs font-semibold uppercase tracking-wider text-slate-mute">Language on phone</legend>
          <div className="mt-2 flex flex-wrap gap-2">
            {langs.map((l) => (
              <label key={l.lang} className={`cursor-pointer rounded-md border-2 px-2 py-1 text-sm font-medium ${l.lang === cur.lang ? "border-ink bg-ink text-white" : "border-slate-rule bg-white"}`}>
                <input type="radio" name="citizen-lang" value={l.lang} checked={l.lang === cur.lang} onChange={() => setSel(l.lang)} className="sr-only" />
                <span lang={l.lang}>{l.name}</span>
              </label>
            ))}
          </div>
        </fieldset>
        {publicHref && <a href={publicHref} className="mt-3 inline-block text-sm font-semibold underline">Open public alert page</a>}
      </div>

      <div className="mx-auto w-[300px] shrink-0 rounded-[2.5rem] border-[10px] border-ink bg-ink p-0 shadow-xl">
        <div className="overflow-hidden rounded-[1.8rem] bg-white">
          <div className="flex justify-between bg-slate-paper px-5 py-1.5 font-mono text-[11px] text-slate-mute" aria-hidden="true">
            <span>9:41</span><span>●●●● 5G</span>
          </div>
          <div className="tape h-2" aria-hidden="true" />
          <div className="space-y-3 p-4" lang={cur.lang} dir={cur.dir}>
            <p className="font-display text-sm font-black uppercase tracking-widest text-blocked" dir="ltr" lang="en">Emergency alert</p>
            <p className="text-[17px] leading-snug">{cur.text}</p>
            {cur.status === "FALLBACK" && <p className="text-xs text-slate-mute" dir="ltr" lang="en">Short safe version. Full details in English.</p>}
          </div>
          <div className="border-t border-slate-rule p-3" dir="ltr">
            <AudioButton text={cur.text} tts={cur.tts} />
          </div>
          <div className="scale-[0.82] border-t border-slate-rule">{pictogram}</div>
        </div>
      </div>
    </section>
  );
}
