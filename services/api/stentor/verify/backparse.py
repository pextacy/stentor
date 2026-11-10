"""Deterministic lexicon parser: text in language L -> AlertIntent.

Used two ways:
* English extraction when no Claude key is configured (and as a cross check).
* Back parsing of rendered translations when no second model is available.

It is never shown the English source. It only sees the rendered text, the language
and the lexicon. Because it shares the lexicon with the template renderer, its
errors can be correlated with the renderer's; the Claude back parser (a different
model) exists to break that correlation when a key is configured.

Algorithm, per sentence:
1. Split into clauses on "and" / commas when it holds more than one instruction
   (English only), so "Evacuate now and do not use elevators" gives two instructions
   and the "not" belongs to the second one only.
2. Find every action phrase and instruction phrase. Overlapping matches keep the longer
   one ("stay away from the beach" beats "stay away from"). One instruction per verb
   per clause, by lexicon priority.
3. Negation is per clause: a marker in the clause, or a phrase that implies it
   ("stay out of damaged buildings").
4. Placeholders bind by role. A place in an evacuation clause is a route only after
   "via/using/take", a destination after "to/toward"; otherwise it is an affected area
   ("Evacuate now from Altadena", "residents of ⟦P1⟧ must evacuate").
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from stentor.intent.schema import (
    ACTION_VERB, DEFAULT_URGENCY, ROUTE_ACTIONS, Action, AlertIntent, Hazard, Instruction,
)
from stentor.lexicon import Lexicon, load
from stentor.lock import kind_of, placeholders_in

ABBREV_DOT = re.compile(r"\b(St|Mt|Ft|Pt|Dr|Ave|Blvd|Rd|Hwy|No|vs|approx)\.(?=\s)")
SENTENCE_SPLIT = re.compile(r"(?<=[.!?؟。])\s+|\n+")
CLAUSE_SPLIT = re.compile(r",\s*(?:and\s+)?|;\s*|\s+and\s+(?=(?:do\s+not|don'?t|never|[a-z]+\s))", re.I)
_DOT = "․"  # one dot leader, stands in for abbreviation dots while splitting


def split_sentences(text: str, lx: Lexicon | None = None) -> list[str]:
    protected = ABBREV_DOT.sub(lambda m: m.group(1) + _DOT, text)
    parts = [s.strip().replace(_DOT, ".") for s in SENTENCE_SPLIT.split(protected) if s and s.strip()]
    if lx is not None and lx.opt("split_colon"):
        out: list[str] = []
        for p in parts:
            head, sep, tail = p.partition(": ")
            # Keep "Info: ⟦U1⟧" together; split "Heat wave in ⟦P1⟧: stay indoors".
            if sep and tail and not tail.startswith("⟦") and len(head.split()) >= 2:
                out += [head + ".", tail]
            else:
                out.append(p)
        parts = out
    return parts


@dataclass
class Match:
    start: int
    end: int
    kind: str  # action | headline_action | instruction
    key: str  # action value or instruction key
    phrase: str
    implied_neg: bool = False
    priority: int = 0


@dataclass
class SentenceParse:
    text: str
    kind: str  # headline | action | instruction | info | expires | unknown
    keys: list[str] = field(default_factory=list)


@dataclass
class ParseResult:
    intent: AlertIntent
    sentences: list[SentenceParse] = field(default_factory=list)
    matched_phrases: list[str] = field(default_factory=list)
    action_found: bool = True

    @property
    def unmatched(self) -> list[str]:
        return [s.text for s in self.sentences if s.kind == "unknown"]


def _hazard_terms(lx: Lexicon) -> list[str]:
    return sorted({lx.norm(t) for hz in lx.hazards for t in lx.hazard_terms(hz)}, key=len, reverse=True)


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


def _blank_hazards(lx: Lexicon, norm: str) -> str:
    """Replace hazard terms with spaces of the same length, so positions stay aligned
    ("boil water notice" must not read as the boil_water action)."""
    out = norm
    for t in _hazard_terms(lx):
        for s, e in lx.find_all(t, out):
            out = out[:s] + " " * (e - s) + out[e:]
    return out


def _matches(lx: Lexicon, clause: str) -> list[Match]:
    norm = lx.norm(clause)
    blanked = _blank_hazards(lx, norm)
    has_p = any(kind_of(p) == "P" for p in placeholders_in(clause))
    found: list[Match] = []
    for a, spec in lx.actions.items():
        for ph in spec.get("match", []):
            for s, e in lx.find_all(ph, blanked):
                found.append(Match(s, e, "action", a, ph))
        for ph in spec.get("headline_match", []):
            for s, e in lx.find_all(ph, norm):
                found.append(Match(s, e, "headline_action", a, ph))
    for prio, (key, spec) in enumerate(lx.instructions.items()):
        if spec.get("needs") == "P" and not has_p:
            continue
        implied = {lx.norm(x) for x in spec.get("implied_neg", [])}
        for ph in spec.get("match", []):
            for s, e in lx.find_all(ph, norm):
                found.append(Match(s, e, "instruction", key, ph, lx.norm(ph) in implied, prio))
    # Longer phrase wins on overlap; ties go to actions, then lexicon priority.
    found.sort(key=lambda m: (-(m.end - m.start), m.kind != "action", m.priority, m.start))
    kept: list[Match] = []
    for m in found:
        if all(m.end <= k.start or m.start >= k.end for k in kept):
            kept.append(m)
    # Same verb in one clause: a specific key beats the generic one ("return until
    # officials say it is safe" beats "return"); different objects are both kept
    # ("take your medications and pets").
    instr = [m for m in kept if m.kind == "instruction"]
    drop = set()
    for m in instr:
        verb, _, obj = m.key.partition(":")
        if not obj and any(o.key.partition(":")[0] == verb and o.key != m.key for o in instr):
            drop.add(id(m))
    kept = [m for m in kept if id(m) not in drop]
    return sorted(kept, key=lambda m: m.start)


def _variant_kinds(spec_text: dict) -> set[str]:
    kinds: set[str] = set()
    for v in spec_text:
        types = v.split("|")[-1] if "|" in v else (v if v and v not in ("neg", "pos") else "")
        kinds.update(c for c in types.split(":")[0] if c in "TPNUE")
    return kinds


def _role(lx: Lexicon, clause: str) -> str | None:
    """Route ("via") or destination ("to") for the first place in an evacuation clause,
    decided by the role word closest to the placeholder, on either side (English puts it
    before: "via ⟦P1⟧"; Korean and Turkish after: "⟦P1⟧ 경로로", "⟦P1⟧ üzerinden").
    "Prepare to evacuate via ⟦P1⟧" is a route: "via" is closer than "to"."""
    place = next((p for p in placeholders_in(clause) if kind_of(p) == "P"), None)
    if place is None:
        return None
    i = clause.index(place)
    left, right = lx.norm(clause[:i]), lx.norm(clause[i + len(place):])
    best: tuple[int, str] | None = None
    for role, markers in lx.opt("role_markers", {}).items():
        for mk in markers:
            spans_l = lx.find_all(mk, left)
            if spans_l:
                d = len(left) - spans_l[-1][1]
                best = min(best, (d, role)) if best else (d, role)
            spans_r = lx.find_all(mk, right)
            if spans_r:
                d = spans_r[0][0]
                best = min(best, (d, role)) if best else (d, role)
    if best is None or best[0] > 3:  # the role word must sit next to the place
        return None
    return best[1]


def _clauses(lx: Lexicon, sentence: str) -> list[str]:
    if not lx.opt("split_clauses") or len(_matches(lx, sentence)) < 2:
        return [sentence]
    parts = [p.strip() for p in CLAUSE_SPLIT.split(sentence) if p and p.strip()]
    return parts or [sentence]


def parse_lexicon(text: str, lang: str) -> ParseResult:
    lx = load(lang)
    norm_all = lx.norm(text)
    hazard = _first_hazard(lx, norm_all)
    instructions: list[Instruction] = []
    action_hits: list[tuple[int, Action, bool]] = []  # (order, action, negated)
    expires: str | None = None
    sentences: list[SentenceParse] = []
    matched: list[str] = []
    order = 0

    for sent in split_sentences(text, lx):
        sent_keys: list[str] = []
        sent_kind = "unknown"
        for clause in _clauses(lx, sent):
            ms = _matches(lx, clause)
            phs = placeholders_in(clause)
            neg_marker = lx.negation_hits(clause) > 0
            first_instruction = True
            for m in ms:
                order += 1
                matched.append(m.phrase)
                if m.kind == "headline_action":
                    action_hits.append((order, Action(m.key), neg_marker))
                    sent_kind = "headline"
                    continue
                if m.kind == "action":
                    act = Action(m.key)
                    action_hits.append((order, act, neg_marker))
                    kinds = _variant_kinds(lx.actions[act.value]["text"])
                    bound = [p for p in phs if kind_of(p) in kinds and kind_of(p) != "P"]
                    obj = None
                    places = [p for p in phs if kind_of(p) == "P"]
                    if places and "P" in kinds:
                        if act in ROUTE_ACTIONS:
                            obj = _role(lx, clause)
                            if obj:
                                bound += places
                        else:
                            bound += places
                    bound = [p for p in phs if p in bound]  # keep text order
                    instructions.append(Instruction(verb=ACTION_VERB[act], object=obj, negated=neg_marker, placeholders=bound))
                    sent_kind = "action" if sent_kind == "unknown" else sent_kind
                    sent_keys.append(act.value)
                else:
                    spec = lx.instructions[m.key]
                    kinds = _variant_kinds(spec["text"])
                    bound = [p for p in phs if kind_of(p) in kinds] if first_instruction else []
                    first_instruction = False
                    verb, _, obj = m.key.partition(":")
                    instructions.append(Instruction(verb=verb, object=obj or None,
                                                    negated=neg_marker or m.implied_neg, placeholders=bound))
                    sent_kind = "instruction" if sent_kind == "unknown" else sent_kind
                    sent_keys.append(m.key)
        if sent_kind == "unknown":
            norm = lx.norm(sent)
            phs = placeholders_in(sent)
            has_hazard = any(lx.has(t, norm) for hz in lx.hazards for t in lx.hazard_terms(hz))
            t_phs = [p for p in phs if kind_of(p) == "T"]
            if any(kind_of(p) == "U" for p in phs) and any(lx.has(m, norm) for m in lx.info["match"]):
                sent_kind = "info"
            elif t_phs and any(lx.has(m, norm) for m in lx.expires["match"]):
                expires = expires or t_phs[0]
                sent_kind = "headline" if has_hazard else "expires"
            elif has_hazard:
                sent_kind = "headline"
        sentences.append(SentenceParse(sent, sent_kind, sent_keys))

    # Drop exact duplicates ("EVACUATION ORDER ... Leave now." states one action).
    unique: list[Instruction] = []
    for i in instructions:
        if i not in unique:
            unique.append(i)

    all_phs = placeholders_in(text)
    # The required action is the first one the alert tells people to DO. "Do not
    # evacuate. Stay indoors." must read as stay_indoors, never as evacuate_now.
    positive = [h for h in action_hits if not h[2]]
    action_found = bool(positive)
    act = min(positive, key=lambda x: x[0])[1] if positive else Action.MONITOR
    intent = AlertIntent(
        hazard=hazard,
        action=act,
        urgency=DEFAULT_URGENCY[act],
        area_refs=[p for p in all_phs if kind_of(p) == "P"],
        time_refs=[p for p in all_phs if kind_of(p) == "T"],
        expires=expires,
        instructions=unique,
        info_refs=[p for p in all_phs if kind_of(p) == "U"],
        number_refs=[p for p in all_phs if kind_of(p) == "N"],
        event_refs=[p for p in all_phs if kind_of(p) == "E"],
    )
    return ParseResult(intent=intent, sentences=sentences, matched_phrases=matched, action_found=action_found)
