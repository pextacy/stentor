import type { Status } from "@/lib/api";

// Status is never shown by colour only: icon + word, always.
export const STATUS_STYLE: Record<Status, { icon: string; word: string; cls: string; explain: string }> = {
  VERIFIED: { icon: "✓", word: "Verified", cls: "bg-ok-bg text-ok border-ok", explain: "Meaning matches the source in every critical slot." },
  REVIEW: { icon: "!", word: "Review", cls: "bg-review-bg text-review border-review", explain: "Critical slots match, but something needs a person to check it. Not sent automatically." },
  BLOCKED: { icon: "✕", word: "Blocked", cls: "bg-blocked-bg text-blocked border-blocked", explain: "A critical slot does not match. Nothing is sent in this language." },
  FALLBACK: { icon: "↺", word: "Safe fallback", cls: "bg-fallback-bg text-fallback border-fallback", explain: "The translation was blocked. The pre-approved generic warning is sent instead." },
  APPROVED: { icon: "✓", word: "Approved", cls: "bg-ok-bg text-ok border-ok border-dashed", explain: "Needed review. A named operator checked it and approved sending." },
  REJECTED: { icon: "✕", word: "Rejected", cls: "bg-blocked-bg text-blocked border-blocked border-dashed", explain: "Needed review. The operator rejected it and no safe fallback could be verified. Nothing is sent." },
};

export const SENDABLE: Status[] = ["VERIFIED", "FALLBACK", "APPROVED"];
export const isSendable = (s: Status) => SENDABLE.includes(s);

export function StatusBadge({ status, size = "md" }: { status: Status; size?: "md" | "lg" }) {
  const s = STATUS_STYLE[status];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-md border-2 font-semibold uppercase tracking-wide ${s.cls} ${
        size === "lg" ? "px-3 py-1 text-base" : "px-2 py-0.5 text-sm"
      }`}
    >
      <span aria-hidden="true" className="font-mono">{s.icon}</span>
      {s.word}
    </span>
  );
}

/** Show ⟦P1⟧ style tokens as locked tags. */
export function Locked({ text }: { text: string }) {
  const parts = text.split(/(⟦[A-Z]\d+⟧)/g);
  return (
    <>
      {parts.map((p, i) =>
        /^⟦[A-Z]\d+⟧$/.test(p) ? <span key={i} className="ph" dir="ltr">{p.slice(1, -1)}</span> : <span key={i}>{p}</span>,
      )}
    </>
  );
}
