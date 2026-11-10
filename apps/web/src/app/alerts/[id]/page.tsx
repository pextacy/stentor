"use client";

import { useEffect, useState } from "react";
import { AuditLog } from "@/components/AuditLog";
import { LangCard } from "@/components/LangCard";
import { StatusBadge, isSendable } from "@/components/Status";
import {
  type AlertOut, type CapReport, type LangResult,
  cancelAlert, downloadCap, exportUrl, getAlert, reviewLang, ssmlUrl, validateStoredCap,
} from "@/lib/api";

const btn = "rounded-md border-2 border-ink px-3 py-1.5 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-50";
const input = "rounded-md border-2 border-ink bg-white px-2 py-1 text-base";
const REVIEWER_KEY = "stentor-reviewer-name";

function ReviewForm({ alertId, r, onDone }: { alertId: string; r: LangResult; onDone: (a: AlertOut) => void }) {
  const [reviewer, setReviewer] = useState("");
  const [note, setNote] = useState("");
  const [checked, setChecked] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { try { setReviewer(localStorage.getItem(REVIEWER_KEY) ?? ""); } catch {} }, []);

  async function decide(decision: "approve" | "reject") {
    setBusy(true);
    setError(null);
    try {
      try { localStorage.setItem(REVIEWER_KEY, reviewer.trim()); } catch {}
      onDone(await reviewLang(alertId, { lang: r.lang, decision, reviewer: reviewer.trim(), note: note.trim() }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="rounded-md border-2 border-review bg-review-bg p-3" onSubmit={(e) => e.preventDefault()}
      aria-label={`Review the ${r.english_name} translation`}>
      <p className="text-sm font-semibold text-review">{r.english_name} needs a person before it can be sent.</p>
      <ul className="mt-1 list-disc pl-5 text-sm">{r.reasons.map((x) => <li key={x}>{x}</li>)}</ul>
      <div className="mt-2 flex flex-wrap gap-2">
        <label className="flex flex-col text-xs font-semibold">Your name
          <input className={input} value={reviewer} onChange={(e) => setReviewer(e.target.value)} required minLength={2} autoComplete="name" />
        </label>
        <label className="flex min-w-0 flex-1 flex-col text-xs font-semibold">Note (optional)
          <input className={input} value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} />
        </label>
      </div>
      <label className="mt-2 flex items-start gap-2 text-sm">
        <input type="checkbox" className="mt-1 h-4 w-4" checked={checked} onChange={(e) => setChecked(e.target.checked)} />
        I read this {r.english_name} text, or had a speaker read it, and it says what the English says.
      </label>
      <div className="mt-2 flex flex-wrap gap-2">
        <button type="button" className={`${btn} bg-ok text-white`} disabled={busy || !checked || reviewer.trim().length < 2} onClick={() => decide("approve")}>
          Approve for sending
        </button>
        <button type="button" className={`${btn} bg-white`} disabled={busy || reviewer.trim().length < 2} onClick={() => decide("reject")}>
          Reject, send the safe fallback
        </button>
      </div>
      {error && <p role="alert" className="mt-2 text-sm font-semibold text-blocked">{error}</p>}
    </form>
  );
}

export default function AlertDetail({ params }: { params: { id: string } }) {
  const [a, setA] = useState<AlertOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cap, setCap] = useState<CapReport | null>(null);
  const [capStatus, setCapStatus] = useState("Exercise");
  const [sender, setSender] = useState("stentor-demo@example.org");
  const [senderName, setSenderName] = useState("STENTOR demo operator");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState<null | string>(null);
  const [auditKey, setAuditKey] = useState(0);

  const refresh = (next?: AlertOut) => {
    if (next) setA(next);
    else getAlert(params.id).then(setA).catch((e: Error) => setError(e.message));
    setCap(null);
    setAuditKey((k) => k + 1);
  };
  useEffect(() => { refresh(); }, [params.id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (error) return <main className="mx-auto max-w-5xl p-6"><p role="alert" className="font-semibold text-blocked">{error}</p></main>;
  if (!a) return <main className="mx-auto max-w-5xl p-6"><p>Loading alert…</p></main>;

  const sendable = a.results.filter((r) => isSendable(r.status) && r.text);
  const review = a.results.filter((r) => r.status === "REVIEW");
  const live = !a.superseded_by && a.msg_type !== "Cancel";
  const common = { renderer: a.results[0]?.renderer ?? "", backparser: a.results[0]?.backparser ?? "" };

  return (
    <main className="mx-auto max-w-6xl px-4 py-6">
      <p className="text-sm text-slate-mute"><a href="/history" className="underline">All alerts</a> / {a.id}</p>
      <header className="mt-2 rounded-xl border-2 border-ink bg-white p-4">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="font-display text-3xl font-black uppercase tracking-wide">Alert {a.id}</h1>
          <span className="rounded border-2 border-ink px-2 text-sm font-bold">{a.msg_type}</span>
          {a.chaos && <span className="rounded bg-tape px-2 text-sm font-bold">chaos demo: {a.chaos}</span>}
          <span className="ml-auto font-mono text-sm text-slate-mute">{new Date(a.created_at).toLocaleString()}</span>
        </div>
        <p className="mt-2 text-lg">{a.source_text}</p>
        {a.references && <p className="mt-1 text-sm">Replaces alert <a className="underline" href={`/alerts/${a.references}`}>{a.references}</a>.</p>}
        {a.superseded_by && (
          <p className="mt-2 rounded-md bg-fallback-bg px-2 py-1 text-sm font-semibold text-fallback">
            Replaced by <a className="underline" href={`/alerts/${a.superseded_by}`}>{a.superseded_by}</a>. This alert can no longer be changed.
          </p>
        )}
        <div className="mt-3 flex flex-wrap gap-2">
          {a.results.map((r) => <span key={r.lang} className="flex items-center gap-1 text-sm"><span className="font-mono">{r.lang}</span><StatusBadge status={r.status} /></span>)}
        </div>
      </header>

      {review.length > 0 && (
        <section aria-labelledby="review-h" className="mt-5 space-y-3">
          <h2 id="review-h" className="font-display text-2xl font-bold uppercase tracking-wide">Waiting for review</h2>
          {review.map((r) => <ReviewForm key={r.lang} alertId={a.id} r={r} onDone={(next) => refresh(next)} />)}
        </section>
      )}

      <section aria-labelledby="life-h" className="mt-5 grid gap-4 md:grid-cols-2">
        <div className="rounded-xl border-2 border-ink bg-white p-4">
          <h2 id="life-h" className="font-display text-xl font-bold uppercase tracking-wide">Update or cancel</h2>
          {live ? (
            <>
              <p className="mt-1 text-sm text-slate-mute">An update or cancellation is translated and verified like any alert, and refers to this one in CAP.</p>
              <div className="mt-3 flex flex-wrap gap-2">
                <a className={`${btn} bg-white`} href={`/?update=${a.id}`}>Write an update</a>
              </div>
              <div className="mt-3 flex flex-wrap items-end gap-2">
                <label className="flex min-w-0 flex-1 flex-col text-xs font-semibold">Reason for cancelling (kept in the audit log)
                  <input className={input} value={reason} onChange={(e) => setReason(e.target.value)} maxLength={300} />
                </label>
                <button type="button" className={`${btn} bg-ink text-white`} disabled={busy !== null}
                  onClick={async () => {
                    if (!window.confirm("Cancel this alert in every language?")) return;
                    setBusy("cancel");
                    try { const c = await cancelAlert(a.id, reason); window.location.href = `/alerts/${c.alert_id}`; }
                    catch (e) { setError((e as Error).message); } finally { setBusy(null); }
                  }}>
                  {busy === "cancel" ? "Cancelling…" : "Cancel this alert"}
                </button>
              </div>
            </>
          ) : <p className="mt-1 text-sm text-slate-mute">This alert is {a.msg_type === "Cancel" ? "a cancellation" : "replaced"}; it cannot be updated or cancelled.</p>}
        </div>

        <div className="rounded-xl border-2 border-ink bg-white p-4">
          <h2 className="font-display text-xl font-bold uppercase tracking-wide">CAP 1.2</h2>
          <div className="mt-2 grid gap-2 sm:grid-cols-3">
            <label className="flex flex-col text-xs font-semibold">Status
              <select className={input} value={capStatus} onChange={(e) => setCapStatus(e.target.value)}>
                {["Exercise", "Test", "Draft", "System"].map((s) => <option key={s}>{s}</option>)}
              </select>
            </label>
            <label className="flex flex-col text-xs font-semibold">Sender
              <input className={input} value={sender} onChange={(e) => setSender(e.target.value)} />
            </label>
            <label className="flex flex-col text-xs font-semibold">Sender name
              <input className={input} value={senderName} onChange={(e) => setSenderName(e.target.value)} />
            </label>
          </div>
          <p className="mt-1 text-xs text-slate-mute">Status Actual is not offered: STENTOR is not certified for production alerting.</p>
          <div className="mt-3 flex flex-wrap gap-2">
            <button type="button" className={`${btn} bg-ink text-white`} disabled={busy !== null}
              onClick={async () => {
                setBusy("cap");
                try { await downloadCap(a.id, { status: capStatus, sender, sender_name: senderName }); setAuditKey((k) => k + 1); }
                catch (e) { setError((e as Error).message); } finally { setBusy(null); }
              }}>Download CAP</button>
            <button type="button" className={`${btn} bg-white`} onClick={() => validateStoredCap(a.id).then(setCap).catch((e: Error) => setError(e.message))}>
              Validate CAP
            </button>
          </div>
          {cap && (
            <div role="status" className={`mt-2 rounded-md border-2 p-2 text-sm ${cap.valid ? "border-ok bg-ok-bg text-ok" : "border-blocked bg-blocked-bg text-blocked"}`}>
              <p className="font-semibold">{cap.valid ? "✓ Valid CAP 1.2" : `✕ ${cap.errors.length} error(s)`} · {cap.info_blocks} info blocks ({cap.languages.join(", ")})</p>
              {[...cap.errors, ...cap.warnings].map((x, i) => <p key={i}>{x.path}: {x.message}</p>)}
            </div>
          )}
        </div>
      </section>

      <section aria-labelledby="exp-h" className="mt-5 rounded-xl border-2 border-ink bg-white p-4">
        <h2 id="exp-h" className="font-display text-xl font-bold uppercase tracking-wide">Exports</h2>
        <p className="mt-1 text-sm text-slate-mute">Text and JSON contain only sendable languages. The CSV lists every language with its status.</p>
        <div className="mt-2 flex flex-wrap gap-2">
          <a className={btn} href={exportUrl(a.id, "export.json")} target="_blank" rel="noreferrer">JSON bundle</a>
          <a className={btn} href={exportUrl(a.id, "export.txt")}>Plain text</a>
          <a className={btn} href={exportUrl(a.id, "export.csv")}>Results CSV</a>
          <a className={btn} href={`/a/${a.id}`}>Public page</a>
          <a className={btn} href={`/a/${a.id}/print`}>Printable poster</a>
        </div>
        <h3 className="mt-4 text-xs font-semibold uppercase tracking-wider text-slate-mute">Broadcast speech (SSML)</h3>
        <div className="mt-1 flex flex-wrap gap-2 text-sm">
          <a className="underline" href={ssmlUrl(a.id, "en")} target="_blank" rel="noreferrer">English</a>
          {sendable.map((r) => <a key={r.lang} className="underline" href={ssmlUrl(a.id, r.lang)} target="_blank" rel="noreferrer">{r.english_name}</a>)}
        </div>
      </section>

      <div className="mt-5 grid gap-4 xl:grid-cols-2">
        {a.results.map((r) => <LangCard key={r.lang} r={r} common={common} />)}
      </div>
      <div className="mt-5"><AuditLog alertId={a.id} refreshKey={auditKey} /></div>
    </main>
  );
}
