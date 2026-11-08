"""Corruptions that imitate real translation failures.

Used by chaos mode (demo) and by the adversarial eval. Each function takes the
rendered *locked* text and returns the corrupted text, or None when the corruption
does not apply (for example dropping a negation from an alert that has none).
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable

from stentor.intent.schema import WEAKER_THAN, AlertIntent, Hazard
from stentor.lexicon import load
from stentor.lock import kind_of, placeholders_in
from stentor.verify.backparse import split_sentences


def _ci_find(haystack: str, needle: str) -> re.Match | None:
    n = unicodedata.normalize("NFC", needle)
    return re.search(re.escape(n), unicodedata.normalize("NFC", haystack), re.I)


def _find_phrase(lx, text: str, phrase: str) -> tuple[int, int] | None:
    """Locate a lexicon phrase in raw text, tolerating diacritics the way matching does."""
    m = _ci_find(text, phrase)
    if m:
        return m.span()
    target = lx.norm(phrase)
    # slide a window over raw text and compare normalized forms
    for i in range(len(text)):
        for j in range(i + 1, min(len(text), i + len(phrase) + 6) + 1):
            if lx.norm(text[i:j]) == target:
                return i, j
    return None


def drop_negation(text: str, intent: AlertIntent, lang: str) -> str | None:
    """Remove the negation from the first negated sentence, the way a model does when it
    'simplifies' an instruction. Uses the lexicon's drop rules for languages where the
    negation is a suffix (Korean, Turkish); otherwise removes the marker word."""
    lx = load(lang)
    rules = lx.opt("negation_drop", [])
    for sent in split_sentences(text, lx):
        if lx.negation_hits(sent) == 0:
            continue
        new = sent
        if rules:
            for old_s, new_s in rules:
                new = new.replace(old_s, new_s)
        else:
            for mk in sorted(lx.negation_markers, key=len, reverse=True):
                new = re.sub(rf"(?<![\w']){re.escape(mk)}(?![\w'])\s*", "", new, flags=re.I)
            new = re.sub(r"\b(Do|do)\s+(?=[a-z])", "", new) if lang == "en" else new
        new = new.strip()
        if new and new != sent:
            for i, ch in enumerate(new):
                if ch.isalpha():
                    new = new[:i] + ch.upper() + new[i + 1:]
                    break
            return text.replace(sent, new, 1)
    return None


def downgrade_action(text: str, intent: AlertIntent, lang: str) -> str | None:
    lx = load(lang)
    weaker = WEAKER_THAN.get(intent.action, [])
    if not weaker:
        return None
    soft = lx.action_phrases(weaker[0].value)
    for ph in lx.action_phrases(intent.action.value):
        span = _find_phrase(lx, text, ph)
        if span and soft:
            return text[: span[0]] + soft[0] + text[span[1] :]
    return None


def _swap_or_replace(text: str, kind: str, literal: str) -> str | None:
    """Swap two placeholders that carry different meaning, else replace one with a
    literal the model invented. Two places in one headline list ("⟦P1⟧, ⟦P2⟧") are not
    swapped: their order carries no meaning, so that would not be a real corruption."""
    sentences = split_sentences(text)
    where = {}
    for i, sent in enumerate(sentences):
        for p in placeholders_in(sent):
            if kind_of(p) == kind:
                where.setdefault(p, []).append(i)
    uniq = list(where)
    for a in uniq:
        for b in uniq:
            same_list = where[a] == where[b] and re.search(re.escape(a) + r"\s*[,،]\s*" + re.escape(b), text)
            if a < b and not same_list:
                return text.replace(a, "\0").replace(b, a).replace("\0", b)
    if uniq:
        return text.replace(uniq[0], literal, 1)
    return None


def shift_time(text: str, intent: AlertIntent, lang: str) -> str | None:
    # A model that rewrites the clock value instead of keeping the placeholder.
    return _swap_or_replace(text, "T", "7:00 PM")


def swap_place(text: str, intent: AlertIntent, lang: str) -> str | None:
    return _swap_or_replace(text, "P", "Pasadena")


def swap_hazard(text: str, intent: AlertIntent, lang: str) -> str | None:
    lx = load(lang)
    other = Hazard.FLOOD if intent.hazard != Hazard.FLOOD else Hazard.EARTHQUAKE
    new_name = lx.hazards[other.value]["name"]
    for term in sorted(lx.hazard_terms(intent.hazard.value), key=len, reverse=True):
        span = _find_phrase(lx, text, term)
        if span:
            return text[: span[0]] + new_name + text[span[1] :]
    return None


def drop_placeholder(text: str, intent: AlertIntent, lang: str) -> str | None:
    phs = placeholders_in(text)
    if not phs:
        return None
    return text.replace(phs[-1], "", 1)


def duplicate_placeholder(text: str, intent: AlertIntent, lang: str) -> str | None:
    phs = placeholders_in(text)
    if not phs:
        return None
    return text.replace(phs[0], f"{phs[0]} {phs[0]}", 1)


CORRUPTIONS: dict[str, Callable[[str, AlertIntent, str], str | None]] = {
    "drop_negation": drop_negation,
    "downgrade_action": downgrade_action,
    "shift_time": shift_time,
    "swap_place": swap_place,
    "swap_hazard": swap_hazard,
    "drop_placeholder": drop_placeholder,
    "duplicate_placeholder": duplicate_placeholder,
}


def parse_chaos(spec: str | None) -> dict[str, str]:
    """'drop_negation:ar,swap_place:vi' -> {'ar': 'drop_negation', 'vi': 'swap_place'}"""
    out: dict[str, str] = {}
    for part in (spec or "").split(","):
        part = part.strip()
        if not part:
            continue
        kind, _, lang = part.partition(":")
        if kind not in CORRUPTIONS:
            raise ValueError(f"unknown chaos corruption '{kind}'")
        out[lang or "*"] = kind
    return out
