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

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    cache: "no-store",
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    let detail = `${res.status}`;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {}
    throw new Error(`The API refused the request: ${detail}`);
  }
  return res.json() as Promise<T>;
}

export const getHealth = (signal?: AbortSignal) => req<Health>("/health", { signal });
export const getMeta = () => req<Meta>("/meta");
export const postIntent = (text: string) =>
  req<IntentResult>("/intent", { method: "POST", body: JSON.stringify({ text }) });
export const postCompile = (
  body: { intent: AlertIntent; locked_text: string; mapping: Record<string, string>; langs: string[]; source_text: string },
  chaos?: string,
) =>
  req<CompileResponse>(`/compile${chaos ? `?chaos=${encodeURIComponent(chaos)}` : ""}`, {
    method: "POST",
    body: JSON.stringify(body),
  });
export const getPublic = (id: string, lang: string) => req<PublicAlert>(`/public/${id}?lang=${lang}`);
export const getEval = () => req<Record<string, any>>("/eval/latest"); // eslint-disable-line @typescript-eslint/no-explicit-any

export async function downloadCap(alertId: string): Promise<void> {
  const res = await fetch(`${API_URL}/export/cap`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ alert_id: alertId }),
  });
  if (!res.ok) throw new Error(`CAP export failed: ${res.status}`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `stentor-${alertId}.cap.xml`;
  a.click();
  URL.revokeObjectURL(url);
}
