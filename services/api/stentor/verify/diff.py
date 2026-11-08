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


class SlotDiff(BaseModel):
    slot: str
    critical: bool
    match: bool
    source: Any
    back: Any


def _ins_key(i: Instruction) -> tuple:
    return (i.verb.strip().lower(), i.negated, tuple(sorted(i.placeholders)))


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
    for slot in ("area_refs", "time_refs", "info_refs"):
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


def decide(checks: list, diffs: list[SlotDiff]) -> tuple[Status, list[str]]:
    reasons: list[str] = []
    for c in checks:
        if not c.ok:
            reasons.append(f"{'critical' if c.critical else 'non critical'} check {c.name} failed: {c.detail}")
    for d in diffs:
        if not d.match:
            reasons.append(f"{'critical' if d.critical else 'non critical'} slot {d.slot} differs: {d.source} -> {d.back}")
    if any(c.critical and not c.ok for c in checks) or any(d.critical and not d.match for d in diffs):
        return Status.BLOCKED, reasons
    if reasons:
        return Status.REVIEW, reasons
    return Status.VERIFIED, ["all critical checks and slots match"]
