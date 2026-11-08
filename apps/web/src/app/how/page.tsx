"use client";

import { useEffect, useState } from "react";
import { type Meta, getMeta } from "@/lib/api";

const STEPS: { name: string; what: string; example: React.ReactNode }[] = [
  {
    name: "Read",
    what: "The English alert becomes an Alert Intent: hazard, required action, places, times, quantities, phone numbers and every instruction with a flag for “do not”.",
    example: <>hazard <b>wildfire</b> · action <b>evacuate now</b> via <b>P2</b> · <b>NOT</b> return until <b>T1</b> · info <b>U1</b></>,
  },
  {
    name: "Lock",
    what: "Names, streets, times, quantities and phone numbers are replaced by tokens before any translation, so no model can change them. Times are re-formatted per language on the way back, never re-valued.",
    example: <>Wildfire near <span className="ph">P1</span>. Evacuate now via <span className="ph">P2</span>. Do NOT return until <span className="ph">T1</span>. Info: <span className="ph">U1</span>.</>,
  },
  {
    name: "Translate",
    what: "Approved phrase templates are used whenever they express the whole alert. Only what they cannot express goes to a model (an Adaption fine tuned model, then Claude), and that output is checked the same way.",
    example: <span lang="vi">Cảnh báo cháy rừng tại <span className="ph">P1</span>. Sơ tán ngay theo đường <span className="ph">P2</span>. KHÔNG quay lại trước <span className="ph">T1</span>. Thông tin: <span className="ph">U1</span>.</span>,
  },
  {
    name: "Read back",
    what: "Each translation is read back into an Alert Intent without seeing the English. With a Claude key this is a different model from the translator, so they do not share blind spots.",
    example: <>hazard wildfire · action evacuate now via P2 · NOT return until T1 · info U1</>,
  },
  {
    name: "Compare",
    what: "The two intents are compared slot by slot. Any critical difference blocks the language; the operator sees exactly which slot failed and why.",
    example: <>Hazard ✓ · Action ✓ · Places ✓ · Times ✓ · Phone/link ✓ · Negations ✓ · Steps ✓</>,
  },
  {
    name: "Send",
    what: "Verified languages go out as CAP 1.2 (one block per language), SMS, audio and a public page. A blocked language gets the pre-approved generic warning for that hazard instead of a wrong one.",
    example: <span lang="vi">Cảnh báo cháy rừng tại Altadena. Sơ tán ngay theo đường Lake Ave. KHÔNG quay lại trước 18:00. Thông tin: 211.</span>,
  },
];

const CHECKS: { name: string; catches: string; example: string }[] = [
  { name: "Every literal exactly once", catches: "A dropped, duplicated or invented name, time or number.", example: "Model writes “until 7:00 PM” instead of keeping ⟦T1⟧ (6:00 PM)." },
  { name: "Required action present", catches: "The approved phrase for the action is missing.", example: "“Evacuate now” rendered as “consider leaving”." },
  { name: "No softer action", catches: "A weaker action replaces the required one.", example: "“Evacuate now” becomes “prepare to evacuate”." },
  { name: "Negation count", catches: "Fewer “do not” markers than prohibitions.", example: "“Do NOT use elevators” becomes “Use elevators”." },
  { name: "Slot by slot read back", catches: "Any change of hazard, action, place, time, route vs destination, quantity, name or instruction.", example: "“Evacuate via Lake Ave” read back as “evacuate to Lake Ave”." },
  { name: "Literal restored verbatim", catches: "A literal lost while putting the values back.", example: "Phone number 211 missing from the final text." },
];

export default function How() {
  const [meta, setMeta] = useState<Meta | null>(null);
  useEffect(() => { getMeta().then(setMeta).catch(() => setMeta(null)); }, []);

  return (
    <main className="mx-auto max-w-5xl px-4 py-8">
      <h1 className="font-display text-4xl font-black uppercase tracking-wide">How STENTOR checks a translation</h1>
      <p className="mt-3 max-w-3xl text-lg">
        Machine translation exists. Agencies do not use it for alerts because a wrong alert is worse than no alert,
        and nobody can proofread ten languages under pressure. STENTOR does not ask anyone to trust a translation.
        It reads every translation back and only sends what still means the same thing.
      </p>

      <section aria-labelledby="pipe-h" className="mt-8">
        <h2 id="pipe-h" className="font-display text-2xl font-bold uppercase tracking-wide">The path of one alert</h2>
        <p className="text-sm text-slate-mute">Worked example: the demo wildfire alert, Vietnamese.</p>
        <ol className="mt-4 space-y-3">
          {STEPS.map((s, i) => (
            <li key={s.name} className="grid gap-3 rounded-xl border-2 border-ink bg-white p-4 md:grid-cols-[10rem_1fr]">
              <div>
                <span className="font-mono text-sm text-slate-mute">Step {i + 1}</span>
                <h3 className="font-display text-xl font-bold uppercase">{s.name}</h3>
              </div>
              <div>
                <p>{s.what}</p>
                <p className="mt-2 rounded-md bg-slate-paper px-3 py-2 text-sm">{s.example}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section aria-labelledby="checks-h" className="mt-10">
        <h2 id="checks-h" className="font-display text-2xl font-bold uppercase tracking-wide">The checks</h2>
        <p className="text-sm text-slate-mute">All are critical: one failure blocks the language.</p>
        <div className="mt-3 overflow-x-auto rounded-xl border-2 border-ink bg-white">
          <table className="w-full min-w-[40rem] text-left">
            <thead><tr className="border-b-2 border-ink text-sm"><th className="px-3 py-2">Check</th><th>What it catches</th><th className="pr-3">Example it blocks</th></tr></thead>
            <tbody>
              {CHECKS.map((c) => (
                <tr key={c.name} className="border-b border-slate-rule align-top">
                  <th scope="row" className="px-3 py-2 font-semibold">{c.name}</th>
                  <td className="py-2 pr-3">{c.catches}</td>
                  <td className="py-2 pr-3 text-slate-mute">{c.example}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section aria-labelledby="status-h" className="mt-10 grid gap-3 md:grid-cols-2">
        <h2 id="status-h" className="font-display text-2xl font-bold uppercase tracking-wide md:col-span-2">What each status means</h2>
        {[
          ["✓ Verified", "Every critical slot matches. Sent.", "border-ok"],
          ["! Review", "The meaning matches, but something needs a person: the templates leave out a word, or STENTOR had to assume the action. Not sent until someone decides.", "border-review"],
          ["✕ Blocked", "A critical slot differs. Nothing in this language is sent.", "border-blocked"],
          ["↺ Safe fallback", "The translation was blocked; the pre-approved generic warning for the hazard is sent instead, after passing the same checks.", "border-fallback"],
        ].map(([t, d, c]) => (
          <div key={t} className={`rounded-xl border-2 ${c} bg-white p-4`}>
            <h3 className="font-semibold">{t}</h3>
            <p className="mt-1 text-sm">{d}</p>
          </div>
        ))}
      </section>

      <section aria-labelledby="langs-h" className="mt-10">
        <h2 id="langs-h" className="font-display text-2xl font-bold uppercase tracking-wide">Languages</h2>
        <p className="text-sm text-slate-mute">
          Every language has an action lexicon, negation markers and {meta?.instruction_count ?? "about 30"} approved instruction templates.
          All were drafted with an LLM and are marked unreviewed until a native speaker checks them.
        </p>
        <div className="mt-3 overflow-x-auto rounded-xl border-2 border-ink bg-white">
          <table className="w-full min-w-[44rem] text-left text-sm">
            <thead><tr className="border-b-2 border-ink"><th className="px-3 py-2">Language</th><th>“Evacuate now.”</th><th>“Do NOT use elevators.”</th><th>Negation markers</th><th className="pr-3">Review</th></tr></thead>
            <tbody>
              {meta?.languages.map((l) => (
                <tr key={l.lang} className="border-b border-slate-rule align-top">
                  <th scope="row" className="px-3 py-2 font-semibold">{l.english_name} <span lang={l.lang} className="font-normal text-slate-mute">{l.name}</span></th>
                  <td lang={l.lang} dir={l.dir} className="py-2 pr-3">{l.evacuate_phrase}</td>
                  <td lang={l.lang} dir={l.dir} className="py-2 pr-3">{l.sample_prohibition}</td>
                  <td lang={l.lang} className="py-2 pr-3 font-mono">{l.negation_markers?.join(", ")}</td>
                  <td className={`py-2 pr-3 ${l.reviewed_by === "unreviewed" ? "text-review" : "text-ok"}`}>{l.reviewed_by === "unreviewed" ? "Needs a native speaker" : l.reviewed_by}</td>
                </tr>
              ))}
              {!meta && <tr><td colSpan={5} className="px-3 py-3 text-slate-mute">Start the API to see the live lexicons.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>

      <section aria-labelledby="limits-h" className="mt-10 rounded-xl border-2 border-review bg-review-bg p-5">
        <h2 id="limits-h" className="font-display text-2xl font-bold uppercase tracking-wide text-review">What STENTOR does not do</h2>
        <ul className="mt-2 list-disc space-y-1 pl-5">
          <li>It does not replace language access staff. It makes their approved wording reusable and shows them exactly what needs them.</li>
          <li>It does not judge style or politeness, only meaning in the slots it models. Words outside those slots send the alert to Review.</li>
          <li>It cannot lock a place name written in lower case (“near altadena”). It flags it instead.</li>
          <li>Without an API key the translator and the checker share one lexicon. That is safe for the templates it ships, but it is not an independent second opinion.</li>
          <li>It is not certified for production alerting and does not connect to IPAWS or carriers. CAP files are marked as an exercise.</li>
        </ul>
      </section>

      <section aria-labelledby="add-h" className="mt-10">
        <h2 id="add-h" className="font-display text-2xl font-bold uppercase tracking-wide">Adding or reviewing a language</h2>
        <ol className="mt-2 list-decimal space-y-1 pl-5">
          <li>Copy <code className="font-mono text-sm">services/api/stentor/lexicon/en.json</code> to a new language code.</li>
          <li>Translate the hazard names, action sentences and instruction templates. Keep every <code className="font-mono text-sm">{"{P}"}</code>, <code className="font-mono text-sm">{"{T}"}</code> slot.</li>
          <li>List the negation markers and, for each action and instruction, a short phrase that always appears in its template.</li>
          <li>Run <code className="font-mono text-sm">uv run pytest tests/test_lexicon.py</code>: every template must read back to the same meaning.</li>
          <li>When a native speaker has checked the action phrases and negation markers, set <code className="font-mono text-sm">reviewed_by</code> to their name.</li>
        </ol>
      </section>
    </main>
  );
}
