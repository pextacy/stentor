"""Deterministic template renderer: AlertIntent -> locked text in language L.

Composes approved phrase templates (headline, expiry, actions, instructions, info).
If any part of the intent has no template, rendering reports it as uncovered and
the router must use another renderer (or the safe fallback).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from stentor.intent.schema import ACTION_VERB, VERB_ACTION, Action, AlertIntent, Instruction
from stentor.lexicon import Lexicon, load
from stentor.lock import kind_of


@dataclass
class TemplateRender:
    text: str
    uncovered: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.uncovered


def _fill(template: str, phs: list[str]) -> str:
    out = template
    for p in phs:
        out = out.replace("{" + kind_of(p) + "}", p, 1)
    return out


def _types(phs: list[str]) -> str:
    return "".join(sorted(kind_of(p) for p in phs))


def _cap(sentence: str) -> str:
    """Capitalize the first letter unless the sentence starts with a placeholder."""
    for i, ch in enumerate(sentence):
        if ch == "⟦":
            return sentence
        if ch.isalpha():
            return sentence[:i] + ch.upper() + sentence[i + 1 :]
    return sentence


def _hazard_name(lx: Lexicon, hazard: str, events: list[str]) -> str:
    name = lx.hazards.get(hazard, lx.hazards["other"])["name"]
    if events:
        name = lx.opt("event_name", "{name} {E}").replace("{name}", name).replace("{E}", events[0])
    return name


def _headline(lx: Lexicon, intent: AlertIntent, places: list[str], numbers: list[str],
              events: list[str]) -> tuple[str, list[str]]:
    """Returns (sentence, uncovered reasons)."""
    name = _hazard_name(lx, intent.hazard.value, events)
    sep = lx.opt("list_sep", ", ")
    place = sep.join(places) if places else None
    problems: list[str] = []
    if len(events) > 1:
        problems.append("more than one event name")
    if numbers:
        if len(numbers) == 1 and place and lx.opt("headline_distance"):
            tpl = lx.opt("headline_distance").replace("{N}", numbers[0])
        else:
            return "", [f"headline with number(s) {' '.join(numbers)}"]
    elif intent.action == Action.ALL_CLEAR and lx.opt("headline_all_clear"):
        tpl = lx.opt("headline_all_clear_place") if place else lx.opt("headline_all_clear")
    else:
        tpl = lx.headline_place if place else lx.headline
    out = tpl.replace("{name}", name)
    if place:
        out = out.replace("{P}", place)
    return _cap(out), problems


def _action_sentence(lx: Lexicon, action: str, phs: list[str], role: str | None = None) -> str | None:
    key = _types(phs) + (":to" if role == "to" and phs else "")
    tpl = lx.actions.get(action, {}).get("text", {}).get(key)
    return _cap(_fill(tpl, phs)) if tpl else None


def _instruction_sentence(lx: Lexicon, ins: Instruction) -> str | None:
    key = ins.verb + (f":{ins.object}" if ins.object else "")
    spec = lx.instructions.get(key)
    if not spec:
        return None
    v = ("neg" if ins.negated else "pos") + (f"|{_types(ins.placeholders)}" if ins.placeholders else "")
    tpl = spec["text"].get(v)
    return _cap(_fill(tpl, ins.placeholders)) if tpl else None


def _describe(ins: Instruction) -> str:
    return f"{'not ' if ins.negated else ''}{ins.verb}{' ' + ins.object if ins.object else ''}" + (
        f" with {_types(ins.placeholders)}" if ins.placeholders else "")


def render(intent: AlertIntent, lang: str) -> TemplateRender:
    lx = load(lang)
    uncovered: list[str] = []
    used: set[str] = set()
    for ins in intent.instructions:
        used.update(ins.placeholders)

    free_places = [p for p in dict.fromkeys(intent.area_refs) if p not in used]
    instr_numbers = {p for i in intent.instructions for p in i.placeholders if kind_of(p) == "N"}
    all_numbers = [p for p in dict.fromkeys(_all_placeholders(intent)) if kind_of(p) == "N"]
    free_numbers = [p for p in all_numbers if p not in instr_numbers]
    events = list(dict.fromkeys(intent.event_refs))
    head, problems = _headline(lx, intent, free_places, free_numbers, events)
    uncovered += problems
    parts = [head] if head else []
    used.update(free_places)
    used.update(free_numbers)
    used.update(events)

    if intent.expires:
        parts.append(_cap(lx.expires["text"].replace("{T}", intent.expires)))
        used.add(intent.expires)

    main_verb = ACTION_VERB[intent.action]
    if not any(i.verb == main_verb for i in intent.instructions):
        s = _action_sentence(lx, intent.action.value, [])
        parts.append(s) if s else uncovered.append(f"action {intent.action.value}")

    for ins in intent.instructions:
        act = VERB_ACTION.get(ins.verb)
        if act is not None:
            if ins.negated:
                uncovered.append(f"negated action {act.value}")
                continue
            s = _action_sentence(lx, act.value, ins.placeholders, ins.object)
        else:
            s = _instruction_sentence(lx, ins)
        parts.append(s) if s else uncovered.append(_describe(ins))

    for u in dict.fromkeys(intent.info_refs):
        if u not in used:
            parts.append(_cap(lx.info["text"].replace("{U}", u)))
            used.add(u)

    for p in intent.time_refs + intent.area_refs:
        if p not in used:
            uncovered.append(f"placeholder {p} has no template slot")

    return TemplateRender(text=" ".join(parts), uncovered=uncovered)


def _all_placeholders(intent: AlertIntent) -> list[str]:
    out = (list(intent.area_refs) + list(intent.time_refs) + list(intent.info_refs)
           + list(intent.number_refs) + list(intent.event_refs))
    for i in intent.instructions:
        out += i.placeholders
    return out


def render_generic(intent: AlertIntent, lang: str) -> tuple[str, AlertIntent]:
    """Pre-approved safe fallback: hazard + action + info. Drops places, times and names
    on purpose, so it is always expressible. Returns (text, the intent it expresses)."""
    lx = load(lang)
    reduced = AlertIntent(
        hazard=intent.hazard,
        action=intent.action,
        urgency=intent.urgency,
        instructions=[Instruction(verb=ACTION_VERB[intent.action], negated=False, placeholders=[])],
        info_refs=list(dict.fromkeys(intent.info_refs)),
    )
    head, _ = _headline(lx, reduced, [], [], [])
    parts = [head]
    a = _action_sentence(lx, intent.action.value, [])
    if a:
        parts.append(a)
    for u in reduced.info_refs:
        parts.append(_cap(lx.info["text"].replace("{U}", u)))
    return " ".join(parts), reduced
