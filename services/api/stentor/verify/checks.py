"""Deterministic checks on rendered (locked) text. Small pure functions."""
from __future__ import annotations

from collections import Counter

from pydantic import BaseModel

from stentor.intent.schema import WEAKER_THAN, Action, AlertIntent
from stentor.lexicon import load
from stentor.lock import placeholders_in
from stentor.lock.locker import localized_value


class Check(BaseModel):
    name: str
    ok: bool
    critical: bool
    detail: str


def check_placeholders(source_locked: str, rendered: str) -> Check:
    want, got = Counter(placeholders_in(source_locked)), Counter(placeholders_in(rendered))
    if want == got:
        return Check(name="placeholders", ok=True, critical=True, detail=f"all {sum(want.values())} placeholders present exactly once")
    missing = sorted((want - got).elements())
    extra = sorted((got - want).elements())
    parts = []
    if missing:
        parts.append("missing " + ", ".join(missing))
    if extra:
        parts.append("unexpected or duplicated " + ", ".join(extra))
    return Check(name="placeholders", ok=False, critical=True, detail="; ".join(parts))


def check_action_present(intent: AlertIntent, rendered: str, lang: str) -> Check:
    lx = load(lang)
    norm = lx.norm(rendered)
    phrases = lx.action_phrases(intent.action.value)
    hit = next((p for p in phrases if lx.has(p, norm)), None)
    if hit:
        return Check(name="action_present", ok=True, critical=True, detail=f"found '{hit}' for {intent.action.value}")
    return Check(
        name="action_present", ok=False, critical=True,
        detail=f"no approved phrase for {intent.action.value} (expected one of: {', '.join(phrases) or 'none in lexicon'})",
    )


def check_no_weaker_action(intent: AlertIntent, rendered: str, lang: str) -> Check:
    lx = load(lang)
    norm = lx.norm(rendered)
    has_right = any(lx.has(p, norm) for p in lx.action_phrases(intent.action.value))
    for weaker in WEAKER_THAN.get(intent.action, []):
        hit = next((p for p in lx.action_phrases(weaker.value) if lx.has(p, norm)), None)
        if hit and not has_right:
            return Check(name="no_weaker_action", ok=False, critical=True,
                         detail=f"softened to {weaker.value} ('{hit}') instead of {intent.action.value}")
    return Check(name="no_weaker_action", ok=True, critical=True, detail="no softer action replaces the required one")


def check_negation_count(intent: AlertIntent, rendered: str, lang: str) -> Check:
    lx = load(lang)
    need = sum(1 for i in intent.instructions if i.negated)
    have = lx.negation_hits(rendered)
    ok = have >= need
    return Check(name="negation_count", ok=ok, critical=True,
                 detail=f"{have} negation marker(s) for {need} negated instruction(s)")


def check_literals_restored(restored: str, mapping: dict[str, str], source_locked: str, lang: str) -> Check:
    """After restore, every literal must appear as many times as its placeholder did."""
    need = Counter(placeholders_in(source_locked))
    bad = []
    for ph, n in need.items():
        val = localized_value(ph, mapping.get(ph, ph), lang)
        if restored.count(val) < n:
            bad.append(f"{ph}='{val}'")
    if bad:
        return Check(name="literals_restored", ok=False, critical=True, detail="literal missing after restore: " + ", ".join(bad))
    return Check(name="literals_restored", ok=True, critical=True, detail="every locked literal restored verbatim")


SHORT_ALERT_BUDGET = 360


def check_length(restored: str, budget: int = SHORT_ALERT_BUDGET) -> Check:
    n = len(restored)
    return Check(name="length", ok=n <= budget, critical=False, detail=f"{n} / {budget} characters for short alert channel")


def run_all(intent: AlertIntent, source_locked: str, rendered: str, restored: str, mapping: dict[str, str], lang: str) -> list[Check]:
    return [
        check_placeholders(source_locked, rendered),
        check_action_present(intent, rendered, lang),
        check_no_weaker_action(intent, rendered, lang),
        check_negation_count(intent, rendered, lang),
        check_literals_restored(restored, mapping, source_locked, lang),
        check_length(restored),
    ]


__all__ = ["Check", "run_all", "Action"]
