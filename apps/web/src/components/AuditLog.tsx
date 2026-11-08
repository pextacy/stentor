"use client";

import { useEffect, useState } from "react";
import { type AlertOut, getAlert } from "@/lib/api";

/** Every decision with its reason, as stored on the server (CLAUDE.md: judges and
 *  operators both need to see why something was blocked). */
export function AuditLog({ alertId, refreshKey }: { alertId: string; refreshKey?: number }) {
  const [alert, setAlert] = useState<AlertOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    getAlert(alertId).then(setAlert).catch((e: Error) => setError(e.message));
  }, [alertId, refreshKey]);
  if (error) return <p className="text-sm text-blocked">Audit log unavailable: {error}</p>;
  if (!alert) return <p className="text-sm text-slate-mute">Loading audit log…</p>;
  return (
    <details className="rounded-xl border-2 border-ink bg-white">
      <summary className="cursor-pointer px-4 py-3 font-display text-xl font-bold uppercase tracking-wide">
        Audit log <span className="font-sans text-sm font-normal normal-case text-slate-mute">({alert.audit.length} records for alert {alert.id})</span>
      </summary>
      <div className="max-h-96 overflow-auto border-t border-slate-rule">
        <table className="w-full text-left text-sm">
          <thead className="sticky top-0 bg-slate-paper">
            <tr><th className="px-3 py-1.5">Time (UTC)</th><th>Lang</th><th>Event</th><th>Status</th><th className="pr-3">Reason</th></tr>
          </thead>
          <tbody>
            {alert.audit.map((a, i) => (
              <tr key={i} className="border-t border-slate-rule/60 align-top">
                <td className="whitespace-nowrap px-3 py-1 font-mono text-xs">{a.created_at.slice(11, 19)}</td>
                <td className="font-mono">{a.lang}</td>
                <td>{a.event.replace(/_/g, " ")}</td>
                <td className="font-semibold">{a.status}</td>
                <td className="pr-3">{a.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}
