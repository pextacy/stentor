"use client";

import { useEffect, useState } from "react";
import { API_URL, getHealth, type Health } from "@/lib/api";

type State =
  | { kind: "loading" }
  | { kind: "ok"; health: Health }
  | { kind: "error"; message: string };

export function HealthStatus() {
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    const ctrl = new AbortController();
    getHealth(ctrl.signal)
      .then((health) => setState({ kind: "ok", health }))
      .catch((e: unknown) => {
        if (ctrl.signal.aborted) return;
        setState({ kind: "error", message: e instanceof Error ? e.message : String(e) });
      });
    return () => ctrl.abort();
  }, []);

  // Status is never shown by colour only: icon + word.
  return (
    <section aria-live="polite" className="rounded-lg border border-neutral-300 p-4 text-base">
      <h2 className="mb-2 font-semibold">API status</h2>
      {state.kind === "loading" && <p>Checking {API_URL}/health …</p>}
      {state.kind === "ok" && (
        <div>
          <p className="font-semibold text-green-800" data-testid="health">
            <span aria-hidden="true">✓ </span>OK
          </p>
          <ul className="mt-2 text-sm text-neutral-700">
            <li>Version: {state.health.version}</li>
            <li>Renderer: {state.health.renderer}</li>
            <li>Anthropic key: {state.health.anthropic_configured ? "configured" : "missing"}</li>
            <li>Adaption key: {state.health.adaption_configured ? "configured" : "missing"}</li>
          </ul>
        </div>
      )}
      {state.kind === "error" && (
        <p className="font-semibold text-red-800" data-testid="health">
          <span aria-hidden="true">✕ </span>Unreachable ({state.message})
        </p>
      )}
    </section>
  );
}
