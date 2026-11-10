import type { components } from "./schema";

export type S = components["schemas"];
export type AlertIntent = S["AlertIntent"];
export type Instruction = S["Instruction"];
export type IntentResult = S["IntentResult"];
export type CompileResponse = S["CompileResponse"];
export type LangResult = S["LangResult"];
export type Meta = S["Meta"];
export type PublicAlert = S["PublicAlert"];
export type Health = S["Health"];
export type Status = LangResult["status"];
export type AlertOut = S["AlertOut"];
export type AlertSummary = S["AlertSummary"];
export type RecentAlert = AlertSummary;
export type CapArea = S["CapArea"];
export type CapReport = S["CapReport"];
export type LintIssue = S["LintIssue"];
export type Draft = S["DraftOut"];
export type Preset = S["PresetOut"];
export type Stats = S["Stats"];
export type LexiconView = S["LexiconView"];
export type LintReport = S["LintReport"];
export type Signoff = S["SignoffOut"];
export type GlossaryTerm = S["GlossaryOut"];
export type Webhook = S["WebhookOut"];

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Optional operator token (when the API runs with STENTOR_OPERATOR_TOKEN). Kept in this
 *  browser only; sent on every request so write endpoints accept it. */
const TOKEN_KEY = "stentor-operator-token";
export function getToken(): string {
  try { return typeof window === "undefined" ? "" : window.localStorage.getItem(TOKEN_KEY) ?? ""; } catch { return ""; }
}
export function setToken(token: string): void {
  try {
    if (token) window.localStorage.setItem(TOKEN_KEY, token);
    else window.localStorage.removeItem(TOKEN_KEY);
  } catch {}
}
function authHeaders(): Record<string, string> {
  const t = getToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

async function raw(path: string, init?: RequestInit): Promise<Response> {
  const res = await fetch(`${API_URL}${path}`, {
    cache: "no-store",
    ...init,
    headers: { "Content-Type": "application/json", ...authHeaders(), ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    let detail = `${res.status}`;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {}
    if (res.status === 401) detail += ". Set the operator token in Settings.";
    throw new Error(`The API refused the request: ${detail}`);
  }
  return res;
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await raw(path, init);
  return (res.status === 204 ? undefined : res.json()) as Promise<T>;
}

const post = <T>(path: string, body: unknown) => req<T>(path, { method: "POST", body: JSON.stringify(body) });
const put = <T>(path: string, body: unknown) => req<T>(path, { method: "PUT", body: JSON.stringify(body) });
const del = (path: string) => req<void>(path, { method: "DELETE" });
const enc = encodeURIComponent;

export const getHealth = (signal?: AbortSignal) => req<Health>("/health", { signal });
export const getMeta = () => req<Meta>("/meta");
export const postIntent = (text: string) => post<IntentResult>("/intent", { text });
export const lintIntent = (intent: AlertIntent, mapping: Record<string, string>, locked_text?: string) =>
  post<LintIssue[]>("/intent/lint", { intent, mapping, locked_text });
export const postCompile = (
  body: { intent: AlertIntent; locked_text: string; mapping: Record<string, string>; langs: string[]; references?: string | null; area?: CapArea | null },
  chaos?: string,
) => post<CompileResponse>(`/compile${chaos ? `?chaos=${enc(chaos)}` : ""}`, body);
export const getAlert = (id: string) => req<AlertOut>(`/alerts/${enc(id)}`);
export const getRecent = (limit = 6) => req<RecentAlert[]>(`/alerts?limit=${limit}`);
export const getPublic = (id: string, lang: string) => req<PublicAlert>(`/public/${enc(id)}?lang=${enc(lang)}`);
export const getEvalRenderers = () => req<any[]>("/eval/renderers"); // eslint-disable-line @typescript-eslint/no-explicit-any
export const getEval = () => req<Record<string, any>>("/eval/latest"); // eslint-disable-line @typescript-eslint/no-explicit-any

export type AlertQuery = { q?: string; hazard?: string; status?: string; lang?: string; msg_type?: string; limit?: number; offset?: number };
export async function searchAlerts(query: AlertQuery): Promise<{ items: AlertSummary[]; total: number }> {
  const params = new URLSearchParams();
  Object.entries(query).forEach(([k, v]) => { if (v !== undefined && v !== "") params.set(k, String(v)); });
  const res = await raw(`/alerts?${params}`);
  return { items: await res.json(), total: Number(res.headers.get("x-total-count") ?? 0) };
}

export const reviewLang = (id: string, body: { lang: string; decision: "approve" | "reject"; reviewer: string; note?: string }) =>
  post<AlertOut>(`/alerts/${enc(id)}/review`, body);
export const cancelAlert = (id: string, reason: string) => post<CompileResponse>(`/alerts/${enc(id)}/cancel`, { reason });
export const validateStoredCap = (id: string) => req<CapReport>(`/alerts/${enc(id)}/cap/validate`);
export const validateCap = (xml: string) => post<CapReport>("/validate/cap", { xml });
export const getStats = (includeChaos = false) => req<Stats>(`/stats?include_chaos=${includeChaos}`);

export const getDrafts = () => req<Draft[]>("/drafts");
export const saveDraft = (d: { name: string; text: string; langs: string[] }, id?: string) =>
  id ? put<Draft>(`/drafts/${enc(id)}`, d) : post<Draft>("/drafts", d);
export const deleteDraft = (id: string) => del(`/drafts/${enc(id)}`);
export const getPresets = () => req<Preset[]>("/presets");
export const savePreset = (name: string, langs: string[]) => post<Preset>("/presets", { name, langs });
export const deletePreset = (id: string) => del(`/presets/${enc(id)}`);

export const getLexicon = (lang: string) => req<LexiconView>(`/lexicon/${enc(lang)}`);
export const getLexiconLint = (lang: string) => req<LintReport>(`/lexicon/${enc(lang)}/lint`);
export const getSignoffs = (lang: string) => req<Signoff[]>(`/lexicon/${enc(lang)}/signoffs`);
export const signoffLexicon = (lang: string, reviewer: string, note: string, native_speaker: boolean) =>
  post<Signoff>(`/lexicon/${enc(lang)}/signoff`, { reviewer, note, native_speaker });

export const getGlossary = () => req<GlossaryTerm[]>("/glossary");
export const addGlossary = (term: string, note: string) => post<GlossaryTerm>("/glossary", { term, note });
export const deleteGlossary = (id: string) => del(`/glossary/${enc(id)}`);
export const getWebhooks = () => req<Webhook[]>("/webhooks");
export const addWebhook = (url: string) => post<Webhook>("/webhooks", { url });
export const deleteWebhook = (id: string) => del(`/webhooks/${enc(id)}`);
export const testWebhooks = () => post<{ webhook: string; ok: boolean; detail: string }[]>("/webhooks/test", {});

/** Link to a GET export served by the API (JSON, text, CSV, SSML, CAP). */
export const exportUrl = (id: string, kind: "export.json" | "export.txt" | "export.csv" | "audit.csv" | "cap.xml") =>
  `${API_URL}/alerts/${enc(id)}/${kind}`;
export const ssmlUrl = (id: string, lang: string) => `${API_URL}/alerts/${enc(id)}/ssml?lang=${enc(lang)}`;
export const feedUrl = () => `${API_URL}/feed.atom`;

export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  // Firefox needs the link in the document, and revoking right after click() can
  // cancel the download in Safari and Firefox, so release the URL a moment later.
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function downloadCap(alertId: string, opts?: { status?: string; sender?: string; sender_name?: string }): Promise<void> {
  const res = await fetch(`${API_URL}/export/cap`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ alert_id: alertId, ...(opts ?? {}) }),
  });
  if (!res.ok) {
    let detail = `${res.status}`;
    try { detail = (await res.json()).detail ?? detail; } catch {}
    throw new Error(`CAP export failed: ${typeof detail === "string" ? detail : JSON.stringify(detail)}`);
  }
  saveBlob(await res.blob(), `stentor-${alertId}.cap.xml`);
}

/** Copy text; falls back to a hidden textarea where the async clipboard is unavailable. */
export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand("copy");
    ta.remove();
    return ok;
  }
}
