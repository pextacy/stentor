"""Source quality checks shown to the operator before translating.

* readability(): plain-language metrics for the English source (Flesch-Kincaid grade,
  sentence length, all-caps words). Informational only; it never changes a status.
* lint_intent(): contradictions and gaps in the intent card that verification cannot
  catch, because every translation would faithfully repeat the same mistake.
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from stentor.intent.schema import ACTION_VERB, Action, AlertIntent, Hazard
from stentor.lock import kind_of, placeholders_in
from stentor.lock.locker import parse_time

LONG_SENTENCE_WORDS = 20
TARGET_GRADE = 8.0


class Readability(BaseModel):
    words: int
    sentences: int
    words_per_sentence: float
    grade: float  # Flesch-Kincaid grade level
    long_sentences: list[str]
    all_caps_words: list[str]
    notes: list[str]


def _syllables(word: str) -> int:
    w = word.lower().strip("'")
    if not w:
        return 0
    if len(w) <= 3:
        return 1
    w = re.sub(r"(?:[^laeiouy]es|ed|[^laeiouy]e)$", "", w)
    w = re.sub(r"^y", "", w)
    return max(1, len(re.findall(r"[aeiouy]{1,2}", w)))


def readability(text: str) -> Readability:
    clean = re.sub(r"[⟦⟧]", "", text)
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", clean) if re.search(r"[A-Za-z]", s)]
    words = re.findall(r"[A-Za-z][A-Za-z'’-]*", clean)
    n_s, n_w = max(1, len(sentences)), max(1, len(words))
    syl = sum(_syllables(w) for w in words)
    grade = round(0.39 * (n_w / n_s) + 11.8 * (syl / n_w) - 15.59, 1) if words else 0.0
    long = [s for s in sentences if len(re.findall(r"[A-Za-z][A-Za-z'’-]*", s)) > LONG_SENTENCE_WORDS]
    caps = list(dict.fromkeys(w for w in words if len(w) > 2 and w.isupper()))
    notes = []
    if grade > TARGET_GRADE:
        notes.append(f"Reading grade {grade} is above {TARGET_GRADE:g}. Shorter words and sentences are easier for everyone.")
    if long:
        notes.append(f"{len(long)} sentence(s) longer than {LONG_SENTENCE_WORDS} words. Split them.")
    if len(caps) > 3:
        notes.append("Many words in capitals. Keep capitals for the one word that matters most (NOT, EVACUATE).")
    return Readability(words=len(words), sentences=len(sentences), words_per_sentence=round(n_w / n_s, 1),
                       grade=grade, long_sentences=long, all_caps_words=caps, notes=notes)


class LintIssue(BaseModel):
    code: str
    severity: str  # warning | info
    message: str


# Hazards for which an action makes sense. Anything else gets a warning, never a block.
PLAUSIBLE: dict[Action, set[Hazard]] = {
    Action.BOIL_WATER: {Hazard.BOIL_WATER, Hazard.FLOOD, Hazard.HURRICANE, Hazard.EARTHQUAKE, Hazard.OTHER},
    Action.MOVE_TO_HIGHER_GROUND: {Hazard.FLOOD, Hazard.TSUNAMI, Hazard.HURRICANE, Hazard.OTHER},
}
STAY_PUT = {Action.SHELTER_IN_PLACE, Action.STAY_INDOORS}


def _key(verb: str, obj: str | None) -> str:
    return verb + (f":{obj}" if obj else "")


def lint_intent(intent: AlertIntent, mapping: dict[str, str], locked_text: str | None = None,
                now: datetime | None = None, tz: str = "UTC") -> list[LintIssue]:
    out: list[LintIssue] = []
    add = lambda code, sev, msg: out.append(LintIssue(code=code, severity=sev, message=msg))  # noqa: E731
    pos = {_key(i.verb, i.object) for i in intent.instructions if not i.negated}
    neg = {_key(i.verb, i.object) for i in intent.instructions if i.negated}
    main = ACTION_VERB[intent.action]

    if intent.action in STAY_PUT and ("evacuate" in pos or "prepare" in pos):
        add("contradiction", "warning", "The alert says to stay inside and also to evacuate. Choose one action.")
    if intent.action == Action.EVACUATE_NOW and ("stay" in pos or "shelter" in pos):
        add("contradiction", "warning", "The alert says to evacuate and also to stay inside. Choose one action.")
    if intent.action in (Action.EVACUATE_NOW, Action.MOVE_TO_HIGHER_GROUND) and "go:outside" in neg:
        add("contradiction", "warning", "People must go outside to evacuate, but the alert says do not go outside.")
    if intent.action == Action.ALL_CLEAR and ("return" in neg or "return:until_cleared" in neg):
        add("contradiction", "warning", "An all clear that also says do not return. Is the danger really over?")
    if intent.action == Action.ALL_CLEAR and intent.urgency == "immediate":
        add("urgency", "info", "All clear messages are usually not urgent.")
    if intent.action in (Action.EVACUATE_NOW, Action.SHELTER_IN_PLACE) and intent.urgency == "future":
        add("urgency", "warning", f"{intent.action.value.replace('_', ' ')} with urgency 'future'. Life safety actions are immediate.")
    plausible = PLAUSIBLE.get(intent.action)
    if plausible and intent.hazard not in plausible:
        add("hazard_action", "warning",
            f"'{intent.action.value.replace('_', ' ')}' is unusual for a {intent.hazard.value.replace('_', ' ')}. Check the hazard and the action.")
    if pos & neg:
        add("contradiction", "warning", "The same instruction is both required and forbidden: " + ", ".join(sorted(pos & neg)))
    keys = Counter((i.verb, i.object, i.negated) for i in intent.instructions)
    dupes = [f"{'not ' if k[2] else ''}{_key(k[0], k[1])}" for k, n in keys.items() if n > 1 and k[0] != main]
    if dupes:
        add("duplicate", "info", "Instruction repeated: " + ", ".join(dupes))

    if intent.expires:
        if kind_of(intent.expires) != "T":
            add("expires", "warning", f"The expiry {intent.expires} is not a time.")
        elif intent.expires in mapping:
            p = parse_time(mapping[intent.expires])
            if p is None:
                add("expires", "info", f"Expiry '{mapping[intent.expires]}' cannot be turned into a date, so CAP leaves <expires> out.")
            elif p.hour is not None and p.weekday is None and p.day is None:
                local = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo(tz))
                if (p.hour, p.minute) <= (local.hour, local.minute):
                    add("expires", "warning", f"Expiry {mapping[intent.expires]} has already passed today ({tz}); it will be read as tomorrow.")
    if intent.action == Action.EVACUATE_NOW and not intent.area_refs and not any(i.placeholders for i in intent.instructions):
        add("area", "info", "No place is named. Say who must evacuate.")
    if not intent.info_refs:
        add("info", "info", "No phone number or link for more information.")

    used = set(intent.area_refs + intent.time_refs + intent.info_refs + intent.number_refs + intent.event_refs)
    used |= {p for i in intent.instructions for p in i.placeholders}
    if intent.expires:
        used.add(intent.expires)
    for ph in dict.fromkeys(placeholders_in(locked_text) if locked_text else mapping):
        if ph not in used:
            add("unused_literal", "warning", f"{ph} ('{mapping.get(ph, '?')}') is in the text but no slot of the intent uses it.")
    for ph in used:
        if ph not in mapping:
            add("unknown_placeholder", "warning", f"{ph} is used by the intent but has no value.")
    return out
