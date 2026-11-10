"""English alert -> (AlertIntent, locked text, mapping)."""
from __future__ import annotations

import logging
import re

from pydantic import BaseModel

from stentor import llm
from stentor.intent.schema import ACTION_VERB, Action, AlertIntent, Instruction
from stentor.lexicon import load
from stentor.quality import LintIssue, Readability, lint_intent, readability
from stentor.lock import apply
from stentor.render.template import render
from stentor.verify.backparse import parse_lexicon

log = logging.getLogger(__name__)

STOPWORDS = {
    "a", "an", "the", "for", "in", "near", "at", "of", "on", "to", "and", "or", "is", "are",
    "warning", "alert", "notice", "watch", "advisory", "emergency", "danger", "dangerous",
    "your", "you", "all", "please", "this", "that", "be", "will", "area", "areas", "now",
    "immediately", "issued", "has", "been", "by", "from", "with", "it", "do", "until",
    "effect", "info", "information", "more", "via", "residents", "s", "must", "should",
    "everyone", "people", "here", "there", "its", "city",
}
SYNONYMS = {"don't": "not", "dont": "not", "never": "not", "elevator": "elevators", "minute": "minutes"}
# Phrases that carry no instruction and may be left out of a translation.
IGNORABLE_PHRASES = re.compile(r"\bthis is not a (?:drill|test)\b|\bnot a (?:drill|test)\b", re.I)
# Words whose loss can flip what people are told to do. If the approved
# templates would drop one of them, the language is BLOCKED, never sent for review.
CRITICAL_WORDS = {"not", "no", "unless", "except"}


def _tokens(text: str) -> set[str]:
    t = re.sub(r"⟦[^⟧]*⟧", " ", IGNORABLE_PHRASES.sub(" ", text).casefold().replace("’", "'"))
    out = set()
    for w in re.findall(r"[a-z']+", t):
        w = SYNONYMS.get(w, w)
        if w not in STOPWORDS:
            out.add(w)
    return out


def coverage(source_locked: str, intent: AlertIntent) -> tuple[bool, list[str]]:
    """Does the English template rendering of this intent say everything the source says?
    Returns (covered, words the templates would drop).

    A source word counts as covered if the English rendering contains it, or if it is
    part of a phrase the lexicon recognized ("take shelter", "flash flood", "turn around,
    don't drown"): that phrase's meaning is carried by the approved template in every
    language. Everything else is reported, and the alert goes to Review."""
    en = render(intent, "en")
    if not en.ok:
        return False, en.uncovered
    lx = load("en")
    norm = lx.norm(source_locked)
    recognized: set[str] = set()
    for term in lx.hazard_terms(intent.hazard.value):
        if lx.has(term, norm):
            recognized |= _tokens(term)
    parsed = parse_lexicon(source_locked, "en")
    for phrase in parsed.matched_phrases:
        recognized |= _tokens(phrase)
    missing = sorted(_tokens(source_locked) - _tokens(en.text) - recognized)
    if not parsed.action_found and intent.action == Action.MONITOR:
        # The source states no protective action; "stay alert" was assumed, not said.
        missing.append("protective action (assumed 'stay alert')")
    return not missing, missing


def critical_gaps(missing: list[str]) -> list[str]:
    """Uncovered source words that can change what people do ("not", "unless")."""
    return [w for w in missing if w in CRITICAL_WORDS]


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
    method: str  # claude | gemini | lexicon
    warnings: list[str] = []
    template_coverage: bool
    uncovered: list[str] = []
    readability: Readability | None = None
    lint: list[LintIssue] = []
    glossary_locked: list[str] = []  # glossary terms found and locked as names


def instruction_keys() -> list[str]:
    return list(load("en").instructions.keys())


def _glossary_hits(text: str, glossary: list[str]) -> list[str]:
    """Glossary terms present in the text (case sensitive, whole words), longest first."""
    hits = []
    for term in sorted({g.strip() for g in glossary if g.strip()}, key=len, reverse=True):
        if re.search(rf"(?<![\w⟦]){re.escape(term)}(?![\w⟧])", text):
            hits.append(term)
    return hits


def extract(text: str, glossary: list[str] | None = None, tz: str = "UTC") -> IntentResult:
    warnings: list[str] = []
    places: list[str] = []
    glossary_hits = _glossary_hits(text, glossary or [])
    method = "lexicon"
    intent: AlertIntent | None = None

    if llm.available():
        try:
            places = llm.detect_places(text)
        except llm.LLMUnavailable as e:
            warnings.append(f"place detection fell back to rules: {e}")
    locked, mapping = apply(text, places + glossary_hits)

    rule = parse_lexicon(locked, "en")
    if llm.available():
        try:
            intent = llm.extract_intent(locked, instruction_keys())
            method = "gemini" if llm.provider() == "gemini" else "claude"
            if intent.model_dump() != rule.intent.model_dump():
                warnings.append("The model and the rule parser disagree on this intent. Check the intent card.")
        except llm.LLMUnavailable as e:
            warnings.append(f"model extraction unavailable, used rule parser: {e}")
    if intent is None:
        intent = rule.intent
        for s in rule.unmatched:
            warnings.append(f"sentence not understood by rule parser: '{s}'")
        if not rule.action_found:
            warnings.append("no protective action phrase found; STENTOR assumed 'monitor'. Set the required action on the intent card.")

    intent = ensure_action_instruction(intent)
    covered, missing = coverage(locked, intent)
    if not covered:
        warnings.append("approved templates do not cover all of this alert: " + ", ".join(missing))
        gaps = critical_gaps(missing)
        if gaps:
            warnings.append("a negation was not understood (" + ", ".join(f"'{g}'" for g in gaps) + "). Any language "
                            "that would leave it out is BLOCKED. Rephrase it or set the instruction on the intent card.")
    source_plain = re.sub(r"[⟦⟧]", "", text)
    return IntentResult(
        intent=intent, locked_text=locked, mapping=mapping, method=method,
        warnings=warnings, template_coverage=covered, uncovered=missing,
        readability=readability(source_plain), lint=lint_intent(intent, mapping, locked, tz=tz),
        glossary_locked=[g for g in glossary_hits if g in mapping.values()],
    )
