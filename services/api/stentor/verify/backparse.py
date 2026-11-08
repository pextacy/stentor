"""Deterministic lexicon parser: text in language L -> AlertIntent.

Used two ways:
* English extraction when no Claude key is configured (and as a cross check).
* Back parsing of rendered translations when no second model is available.

It is never shown the English source. It only sees the rendered text, the language
and the lexicon. Because it shares the lexicon with the template renderer, its
errors can be correlated with the renderer's; the Claude back parser (a different
model) exists to break that correlation when a key is configured.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from stentor.intent.schema import ACTION_VERB, DEFAULT_URGENCY, Action, AlertIntent, Hazard, Instruction
from stentor.lexicon import Lexicon, load
from stentor.lock import kind_of, placeholders_in

SENTENCE_SPLIT = re.compile(r"(?<=[.!?؟。])\s+|\n+")


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in SENTENCE_SPLIT.split(text) if s and s.strip()]


@dataclass
class SentenceParse:
    text: str
    kind: str  # headline | action | instruction | info | expires | unknown
    key: str | None = None


@dataclass
class ParseResult:
    intent: AlertIntent
    sentences: list[SentenceParse] = field(default_factory=list)

    @property
    def unmatched(self) -> list[str]:
        return [s.text for s in self.sentences if s.kind == "unknown"]


def _first_hazard(lx: Lexicon, norm_text: str) -> Hazard:
    best: tuple[int, int, str] | None = None  # (pos, -len, hazard)
    for hz in lx.hazards:
        for term in lx.hazard_terms(hz):
            pos = lx.find(term, norm_text)
            if pos >= 0:
                cand = (pos, -len(lx.norm(term)), hz)
                if best is None or cand < best:
                    best = cand
    return Hazard(best[2]) if best else Hazard.OTHER


def _strip_hazard_terms(lx: Lexicon, norm_sentence: str) -> str:
    out = norm_sentence
    terms = sorted({lx.norm(t) for hz in lx.hazards for t in lx.hazard_terms(hz)}, key=len, reverse=True)
    for t in terms:
        if t:
            out = out.replace(t, " ")
    return out


def _action_in(lx: Lexicon, norm_sentence: str) -> tuple[int, Action] | None:
    best: tuple[int, Action] | None = None
    for a, spec in lx.actions.items():
        for ph in spec.get("match", []):
            pos = lx.find(ph, norm_sentence)
            if pos >= 0 and (best is None or pos < best[0]):
                best = (pos, Action(a))
    return best


def _instruction_in(lx: Lexicon, norm_sentence: str) -> str | None:
    for key, spec in lx.instructions.items():  # file order = priority
        if any(lx.has(ph, norm_sentence) for ph in spec.get("match", [])):
            return key
    return None


def parse_lexicon(text: str, lang: str) -> ParseResult:
    lx = load(lang)
    norm_all = lx.norm(text)
    hazard = _first_hazard(lx, norm_all)

    action: Action | None = None
    action_pos = 10**9
    instructions: list[Instruction] = []
    expires: str | None = None
    sentences: list[SentenceParse] = []

    offset = 0
    for sent in split_sentences(text):
        phs = placeholders_in(sent)
        norm = lx.norm(sent)
        negated = lx.negation_hits(sent) > 0
        hit = _action_in(lx, _strip_hazard_terms(lx, norm))
        if hit:
            pos, act = hit
            if offset + pos < action_pos:
                action, action_pos = act, offset + pos
            instructions.append(Instruction(verb=ACTION_VERB[act], object=None, negated=negated, placeholders=phs))
            sentences.append(SentenceParse(sent, "action", act.value))
        elif key := _instruction_in(lx, norm):
            verb, _, obj = key.partition(":")
            instructions.append(Instruction(verb=verb, object=obj or None, negated=negated, placeholders=phs))
            sentences.append(SentenceParse(sent, "instruction", key))
        elif any(kind_of(p) == "U" for p in phs) and any(lx.has(m, norm) for m in lx.info["match"]):
            sentences.append(SentenceParse(sent, "info"))
        elif any(kind_of(p) == "T" for p in phs) and any(lx.has(m, norm) for m in lx.expires["match"]) and not any(
            lx.has(t, norm) for hz in lx.hazards for t in lx.hazard_terms(hz)
        ):
            expires = expires or next(p for p in phs if kind_of(p) == "T")
            sentences.append(SentenceParse(sent, "expires"))
        elif any(lx.has(t, norm) for hz in lx.hazards for t in lx.hazard_terms(hz)):
            # A headline may carry the expiry: "Flood warning for ⟦P1⟧ until ⟦T1⟧."
            t_phs = [p for p in phs if kind_of(p) == "T"]
            if t_phs and any(lx.has(m, norm) for m in lx.expires["match"]):
                expires = expires or t_phs[0]
            sentences.append(SentenceParse(sent, "headline"))
        else:
            sentences.append(SentenceParse(sent, "unknown"))
        offset += len(norm) + 1

    all_phs = placeholders_in(text)
    act = action or Action.MONITOR
    intent = AlertIntent(
        hazard=hazard,
        action=act,
        urgency=DEFAULT_URGENCY[act],
        area_refs=[p for p in all_phs if kind_of(p) == "P"],
        time_refs=[p for p in all_phs if kind_of(p) == "T"],
        expires=expires,
        instructions=instructions,
        info_refs=[p for p in all_phs if kind_of(p) == "U"],
    )
    return ParseResult(intent=intent, sentences=sentences)
