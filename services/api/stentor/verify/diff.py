"""Slot by slot comparison of the source intent and the back parsed intent."""
from __future__ import annotations

from collections import Counter
from enum import Enum
from typing import Any

from pydantic import BaseModel

from stentor.intent.schema import AlertIntent, Instruction


class Status(str, Enum):
    VERIFIED = "VERIFIED"
    REVIEW = "REVIEW"
    BLOCKED = "BLOCKED"
    FALLBACK = "FALLBACK"
    APPROVED = "APPROVED"  # was REVIEW; a named operator checked it and approved sending
    REJECTED = "REJECTED"  # was REVIEW; the operator refused it and nothing is sent


# Only these statuses are ever exported, published or delivered.
SENDABLE = {Status.VERIFIED.value, Status.FALLBACK.value, Status.APPROVED.value}


class SlotDiff(BaseModel):
    slot: str
    critical: bool
    match: bool
    source: Any
    back: Any


def _norm_obj(obj: str | None) -> str | None:
    if not obj:
        return None
    o = obj.strip().lower().replace(" ", "_")
    return o.removeprefix("the_") or None


def _ins_key(i: Instruction) -> tuple:
    # The object matters: "do not drink tap water" vs "do not drink water", and for
    # evacuation "via ⟦P1⟧" (a route) vs "to ⟦P1⟧" (a destination).
    # Order matters within a kind: "between ⟦T1⟧ and ⟦T2⟧" is not "between ⟦T2⟧ and ⟦T1⟧".
    by_kind = tuple(sorted(i.placeholders, key=lambda p: p[1]))  # stable: keeps order inside a kind
    return (i.verb.strip().lower(), _norm_obj(i.object), i.negated, by_kind)


def _ins_view(items: list[Instruction]) -> list[str]:
    return [
        f"{'NOT ' if i.negated else ''}{i.verb}{' ' + i.object if i.object else ''}"
        f"{' [' + ' '.join(i.placeholders) + ']' if i.placeholders else ''}"
        for i in items
    ]


def diff(src: AlertIntent, back: AlertIntent, compare_noncritical: bool = True) -> list[SlotDiff]:
    out = [
        SlotDiff(slot="hazard", critical=True, match=src.hazard == back.hazard, source=src.hazard.value, back=back.hazard.value),
        SlotDiff(slot="action", critical=True, match=src.action == back.action, source=src.action.value, back=back.action.value),
    ]
    for slot in ("area_refs", "time_refs", "info_refs", "number_refs", "event_refs"):
        a, b = getattr(src, slot), getattr(back, slot)
        out.append(SlotDiff(slot=slot, critical=True, match=Counter(a) == Counter(b), source=a, back=b))
    out.append(SlotDiff(slot="expires", critical=True, match=src.expires == back.expires, source=src.expires, back=back.expires))
    neg_src = [i for i in src.instructions if i.negated]
    neg_back = [i for i in back.instructions if i.negated]
    out.append(SlotDiff(
        slot="negations", critical=True,
        match=Counter(map(_ins_key, neg_src)) == Counter(map(_ins_key, neg_back)),
        source=_ins_view(neg_src), back=_ins_view(neg_back),
    ))
    out.append(SlotDiff(
        slot="instructions", critical=True,
        match=Counter(map(_ins_key, src.instructions)) == Counter(map(_ins_key, back.instructions)),
        source=_ins_view(src.instructions), back=_ins_view(back.instructions),
    ))
    if compare_noncritical:
        for slot in ("urgency", "source", "extra_info"):
            a, b = getattr(src, slot), getattr(back, slot)
            if a is None or b is None:  # the back parser may not report it
                continue
            out.append(SlotDiff(slot=slot, critical=False, match=a == b, source=a, back=b))
    return out


CHECK_LABEL = {
    "placeholders": "A name, time, number or phone number was lost or changed",
    "action_present": "The required action is missing",
    "no_weaker_action": "The action was softened",
    "negation_count": "A \"do not\" is missing",
    "literals_restored": "A literal did not come back intact",
    "length": "Too long for the short alert channel",
    "template_coverage": "The approved templates leave out part of the source",
    "backparse_model": "The second model could not read the translation back",
}
SLOT_LABEL = {
    "hazard": "hazard", "action": "required action", "area_refs": "places", "time_refs": "times",
    "info_refs": "phone numbers or links", "number_refs": "numbers", "event_refs": "names", "expires": "expiry",
    "negations": "prohibitions (do not)", "instructions": "instructions", "urgency": "urgency",
    "source": "source", "extra_info": "extra information",
}


def _show(v: Any) -> str:
    if isinstance(v, list):
        return "; ".join(map(str, v)) if v else "none"
    return "none" if v is None else str(v)


def decide(checks: list, diffs: list[SlotDiff]) -> tuple[Status, list[str]]:
    """Status plus plain-language reasons (they are shown to operators and written to the audit log)."""
    reasons: list[str] = []
    for c in checks:
        if not c.ok:
            reasons.append(f"{CHECK_LABEL.get(c.name, c.name)} ({c.detail})")
    for d in diffs:
        if not d.match:
            reasons.append(f"The {SLOT_LABEL.get(d.slot, d.slot)} changed: source says {_show(d.source)}, translation says {_show(d.back)}")
    if any(c.critical and not c.ok for c in checks) or any(d.critical and not d.match for d in diffs):
        return Status.BLOCKED, reasons
    if reasons:
        return Status.REVIEW, reasons
    return Status.VERIFIED, ["All critical checks and slots match"]
