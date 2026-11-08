"""Deterministic template renderer: AlertIntent -> locked text in language L.

Composes approved phrase templates (headline, action, instructions, expiry, info).
If any part of the intent has no template, rendering reports it as uncovered and
the router must use another renderer (or the safe fallback).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from stentor.intent.schema import ACTION_VERB, AlertIntent, Instruction
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


def _variant(phs: list[str]) -> str:
    return "".join(sorted(kind_of(p) for p in phs))


def _headline(lx: Lexicon, hazard: str, place: str | None) -> str:
    name = lx.hazards.get(hazard, lx.hazards["other"])["name"]
    if place:
        return lx.headline_place.replace("{name}", name).replace("{P}", place)
    return lx.headline.replace("{name}", name)


def _action_sentence(lx: Lexicon, action: str, phs: list[str]) -> str | None:
    tpl = lx.actions.get(action, {}).get("text", {}).get(_variant(phs))
    return _fill(tpl, phs) if tpl else None


def _instruction_sentence(lx: Lexicon, ins: Instruction) -> str | None:
    key = ins.verb + (f":{ins.object}" if ins.object else "")
    spec = lx.instructions.get(key)
    if not spec:
        return None
    v = ("neg" if ins.negated else "pos") + (f"|{_variant(ins.placeholders)}" if ins.placeholders else "")
    tpl = spec["text"].get(v)
    return _fill(tpl, ins.placeholders) if tpl else None


def render(intent: AlertIntent, lang: str) -> TemplateRender:
    lx = load(lang)
    uncovered: list[str] = []
    used: set[str] = set()
    for ins in intent.instructions:
        used.update(ins.placeholders)

    free_places = [p for p in intent.area_refs if p not in used]
    if len(free_places) > 1:
        uncovered.append(f"headline with {len(free_places)} places")
    parts = [_headline(lx, intent.hazard.value, free_places[0] if free_places else None)]
    used.update(free_places[:1])

    if intent.expires:
        parts.append(lx.expires["text"].replace("{T}", intent.expires))
        used.add(intent.expires)

    action_verb = ACTION_VERB[intent.action]
    has_action = any(i.verb == action_verb for i in intent.instructions)
    if not has_action:
        s = _action_sentence(lx, intent.action.value, [])
        parts.append(s) if s else uncovered.append(f"action {intent.action.value}")

    for ins in intent.instructions:
        if ins.verb == action_verb:
            if ins.negated:
                uncovered.append(f"negated action {intent.action.value}")
                continue
            s = _action_sentence(lx, intent.action.value, ins.placeholders)
            label = f"action {intent.action.value} with {_variant(ins.placeholders) or 'no'} slots"
        else:
            s = _instruction_sentence(lx, ins)
            label = f"instruction {'not ' if ins.negated else ''}{ins.verb} {ins.object or ''}".strip()
        parts.append(s) if s else uncovered.append(label)

    for u in intent.info_refs:
        if u not in used:
            parts.append(lx.info["text"].replace("{U}", u))
            used.add(u)

    for p in intent.time_refs + intent.area_refs:
        if p not in used:
            uncovered.append(f"placeholder {p} has no template slot")

    return TemplateRender(text=" ".join(parts), uncovered=uncovered)


def render_generic(intent: AlertIntent, lang: str) -> tuple[str, AlertIntent]:
    """Pre-approved safe fallback: hazard + action + info. Drops places and times on
    purpose, so it is always expressible. Returns (text, the intent it expresses)."""
    lx = load(lang)
    reduced = AlertIntent(
        hazard=intent.hazard,
        action=intent.action,
        urgency=intent.urgency,
        instructions=[Instruction(verb=ACTION_VERB[intent.action], negated=False, placeholders=[])],
        info_refs=list(dict.fromkeys(intent.info_refs)),
    )
    parts = [_headline(lx, intent.hazard.value, None)]
    a = _action_sentence(lx, intent.action.value, [])
    if a:
        parts.append(a)
    for u in reduced.info_refs:
        parts.append(lx.info["text"].replace("{U}", u))
    return " ".join(parts), reduced
