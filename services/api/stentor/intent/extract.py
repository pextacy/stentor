"""English alert -> (AlertIntent, locked text, mapping)."""
from __future__ import annotations

import logging
import re

from pydantic import BaseModel

from stentor import llm
from stentor.intent.schema import ACTION_VERB, AlertIntent, Instruction
from stentor.lexicon import load
from stentor.lock import apply
from stentor.render.template import render
from stentor.verify.backparse import parse_lexicon

log = logging.getLogger(__name__)

STOPWORDS = {
    "a", "an", "the", "for", "in", "near", "at", "of", "on", "to", "and", "or", "is", "are",
    "warning", "alert", "notice", "watch", "advisory", "emergency", "danger", "dangerous",
    "your", "you", "all", "please", "this", "that", "be", "will", "area", "areas", "now",
    "immediately", "issued", "has", "been", "by", "from", "with", "it", "do", "until",
    "effect", "info", "information", "more", "via", "residents", "s",
}
SYNONYMS = {"don't": "not", "dont": "not", "never": "not", "elevator": "elevators", "minute": "minutes"}


def _tokens(text: str) -> set[str]:
    t = re.sub(r"⟦[^⟧]*⟧", " ", text.casefold().replace("’", "'"))
    out = set()
    for w in re.findall(r"[a-z']+", t):
        w = SYNONYMS.get(w, w)
        if w not in STOPWORDS:
            out.add(w)
    return out


def coverage(source_locked: str, intent: AlertIntent) -> tuple[bool, list[str]]:
    """Does the English template rendering of this intent say everything the source says?
    Returns (covered, words the templates would drop).

    Words of a recognized hazard term ("flash flood", "gas leak") count as covered:
    the hazard is conveyed by its approved name in every language."""
    en = render(intent, "en")
    if not en.ok:
        return False, en.uncovered
    lx = load("en")
    norm = lx.norm(source_locked)
    hazard_words: set[str] = set()
    for term in lx.hazard_terms(intent.hazard.value):
        if lx.has(term, norm):
            hazard_words |= _tokens(term)
    missing = sorted(_tokens(source_locked) - _tokens(en.text) - hazard_words)
    return not missing, missing


def ensure_action_instruction(intent: AlertIntent) -> AlertIntent:
    """Every alert states its protective action. If the source has no sentence for it
    (e.g. only "Drop, cover and hold on."), make the implied action explicit so the
    operator sees it on the intent card and every language says it."""
    verb = ACTION_VERB[intent.action]
    if any(i.verb == verb for i in intent.instructions):
        return intent
    return intent.model_copy(update={"instructions": [Instruction(verb=verb, negated=False), *intent.instructions]})


class IntentResult(BaseModel):
    intent: AlertIntent
    locked_text: str
    mapping: dict[str, str]
    method: str  # claude | lexicon
    warnings: list[str] = []
    template_coverage: bool
    uncovered: list[str] = []


def instruction_keys() -> list[str]:
    return list(load("en").instructions.keys())


def extract(text: str) -> IntentResult:
    warnings: list[str] = []
    places: list[str] = []
    method = "lexicon"
    intent: AlertIntent | None = None

    if llm.available():
        try:
            places = llm.detect_places(text)
        except llm.LLMUnavailable as e:
            warnings.append(f"place detection fell back to rules: {e}")
    locked, mapping = apply(text, places)

    rule = parse_lexicon(locked, "en")
    if llm.available():
        try:
            intent = llm.extract_intent(locked, instruction_keys())
            method = "claude"
            if intent.model_dump() != rule.intent.model_dump():
                warnings.append("Claude and the rule parser disagree on this intent. Check the intent card.")
        except llm.LLMUnavailable as e:
            warnings.append(f"Claude extraction unavailable, used rule parser: {e}")
    if intent is None:
        intent = rule.intent
        for s in rule.unmatched:
            warnings.append(f"sentence not understood by rule parser: '{s}'")

    intent = ensure_action_instruction(intent)
    covered, missing = coverage(locked, intent)
    if not covered:
        warnings.append("approved templates do not cover all of this alert: " + ", ".join(missing))
    return IntentResult(
        intent=intent, locked_text=locked, mapping=mapping, method=method,
        warnings=warnings, template_coverage=covered, uncovered=missing,
    )
