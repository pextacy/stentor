"use client";

import { useEffect, useState } from "react";
import {
  type GlossaryTerm, type Health, type Webhook,
  addGlossary, addWebhook, deleteGlossary, deleteWebhook, getGlossary, getHealth, getToken, getWebhooks, setToken, testWebhooks,
} from "@/lib/api";

const field = "rounded-md border-2 border-ink bg-white px-2 py-1 text-base";
const btn = "rounded-md border-2 border-ink px-3 py-1 text-sm font-semibold disabled:opacity-50";
const card = "rounded-xl border-2 border-ink bg-white p-4";

export default function Settings() {
  const [health, setHealth] = useState<Health | null>(null);
  const [token, setTok] = useState("");
  const [tokenMsg, setTokenMsg] = useState<string | null>(null);
  const [terms, setTerms] = useState<GlossaryTerm[]>([]);
  const [term, setTerm] = useState("");
  const [termNote, setTermNote] = useState("");
  const [hooks, setHooks] = useState<Webhook[]>([]);
  const [url, setUrl] = useState("");
  const [secret, setSecret] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const load = () => {
    getGlossary().then(setTerms).catch(() => setTerms([]));
    getWebhooks().then(setHooks).catch(() => setHooks([]));
  };
  useEffect(() => {
    setTok(getToken());
    getHealth().then(setHealth).catch(() => {});
    load();
  }, []);
  const run = async (fn: () => Promise<unknown>) => { setMsg(null); try { await fn(); load(); } catch (e) { setMsg((e as Error).message); } };

  return (
    <main className="mx-auto max-w-4xl px-4 py-6">
      <h1 className="font-display text-4xl font-black uppercase tracking-wide">Settings</h1>
      {msg && <p role="alert" className="mt-3 rounded-md border-2 border-blocked bg-blocked-bg p-2 font-semibold text-blocked">{msg}</p>}

      <section aria-labelledby="tok-h" className={`${card} mt-4`}>
        <h2 id="tok-h" className="font-display text-xl font-bold uppercase tracking-wide">Operator token</h2>
        <p className="mt-1 text-sm text-slate-mute">
          {health?.auth_required ? "This server requires a token for every change (STENTOR_OPERATOR_TOKEN)." : "This server does not require a token. Reading and writing are open (demo mode)."}
          {" "}The token is stored in this browser only.
        </p>
        <form className="mt-2 flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); setToken(token.trim()); setTokenMsg(token.trim() ? "Token saved in this browser." : "Token removed."); }}>
          <label className="sr-only" htmlFor="tok">Operator token</label>
          <input id="tok" type="password" autoComplete="off" className={`${field} min-w-0 flex-1`} value={token} onChange={(e) => setTok(e.target.value)} />
          <button type="submit" className={`${btn} bg-ink text-white`}>Save</button>
        </form>
        {tokenMsg && <p role="status" className="mt-1 text-sm">{tokenMsg}</p>}
      </section>

      <section aria-labelledby="gl-h" className={`${card} mt-4`}>
        <h2 id="gl-h" className="font-display text-xl font-bold uppercase tracking-wide">Glossary: never translate</h2>
        <p className="mt-1 text-sm text-slate-mute">Names that must stay exactly as written (organisations, programmes, local names in lower case). Found in an alert, they are locked like place names and every language must keep them.</p>
        <form className="mt-2 flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); run(async () => { await addGlossary(term.trim(), termNote.trim()); setTerm(""); setTermNote(""); }); }}>
          <label className="sr-only" htmlFor="gl-term">Term</label>
          <input id="gl-term" className={`${field} min-w-0 flex-1`} placeholder="Red Cross" value={term} onChange={(e) => setTerm(e.target.value)} />
          <label className="sr-only" htmlFor="gl-note">Note</label>
          <input id="gl-note" className={`${field} min-w-0 flex-1`} placeholder="Note (optional)" value={termNote} onChange={(e) => setTermNote(e.target.value)} />
          <button type="submit" disabled={term.trim().length < 2} className={`${btn} bg-ink text-white`}>Add</button>
        </form>
        <ul className="mt-3 flex flex-wrap gap-2">
          {terms.map((t) => (
            <li key={t.id} className="flex items-center gap-1 rounded-md border-2 border-slate-rule px-2 py-0.5 text-sm">
              <span className="ph">{t.term}</span>{t.note && <span className="text-slate-mute">{t.note}</span>}
              <button type="button" aria-label={`Remove ${t.term}`} className="ml-1 font-bold" onClick={() => run(() => deleteGlossary(t.id))}>×</button>
            </li>
          ))}
          {!terms.length && <li className="text-sm text-slate-mute">No terms yet.</li>}
        </ul>
      </section>

      <section aria-labelledby="wh-h" className={`${card} mt-4`}>
        <h2 id="wh-h" className="font-display text-xl font-bold uppercase tracking-wide">Webhooks</h2>
        <p className="mt-1 text-sm text-slate-mute">
          Each compiled, reviewed or cancelled alert is POSTed as JSON with only its sendable languages. Verify the
          <code className="mx-1 font-mono">X-Stentor-Signature</code>header: <code className="font-mono">sha256=</code> HMAC of the body with the secret. Chaos demo runs are never sent.
        </p>
        <form className="mt-2 flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); run(async () => { const h = await addWebhook(url.trim()); setSecret(h.secret ?? null); setUrl(""); }); }}>
          <label className="sr-only" htmlFor="wh-url">Webhook URL</label>
          <input id="wh-url" type="url" className={`${field} min-w-0 flex-1`} placeholder="https://example.org/hooks/stentor" value={url} onChange={(e) => setUrl(e.target.value)} />
          <button type="submit" disabled={!url.trim()} className={`${btn} bg-ink text-white`}>Add</button>
          <button type="button" disabled={!hooks.length} className={btn}
            onClick={() => run(async () => {
              const out = await testWebhooks();
              setMsg(out.map((o) => `${o.webhook}: ${o.ok ? "delivered" : "failed"} (${o.detail})`).join(" · ") || "No active webhooks.");
            })}>Send test event</button>
        </form>
        {secret && (
          <p role="status" className="mt-2 rounded-md border-2 border-review bg-review-bg p-2 text-sm">
            Secret for the new webhook, shown once: <code className="break-all font-mono">{secret}</code>
          </p>
        )}
        <ul className="mt-3 divide-y divide-slate-rule rounded-md border border-slate-rule">
          {hooks.map((h) => (
            <li key={h.id} className="flex items-center gap-2 px-2 py-1.5 text-sm">
              <span className="min-w-0 flex-1 truncate font-mono">{h.url}</span>
              <span className="text-xs text-slate-mute">{h.active ? "active" : "off"}</span>
              <button type="button" className={btn} onClick={() => run(() => deleteWebhook(h.id))}>Delete</button>
            </li>
          ))}
          {!hooks.length && <li className="px-2 py-1.5 text-sm text-slate-mute">No webhooks.</li>}
        </ul>
      </section>
    </main>
  );
}
