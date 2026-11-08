"""Lexicon consistency: every template must round trip through the parser, so that a
clean rendering is never blocked by our own lexicon."""
import itertools

import pytest

from conftest import LANGS
from stentor.intent.schema import ACTION_VERB, Action, AlertIntent, Hazard, Instruction
from stentor.lexicon import load
from stentor.render.template import render
from stentor.verify.backparse import parse_lexicon

ALL = ["en", *LANGS]


@pytest.mark.parametrize("lang", ALL)
def test_metadata(lang):
    lx = load(lang)
    assert lx.reviewed_by
    assert set(lx.hazards) == {h.value for h in Hazard}
    assert set(lx.actions) == {a.value for a in Action}
    assert set(lx.instructions) == set(load("en").instructions)


def _ph(kinds: str, start: dict) -> list[str]:
    out = []
    for k in kinds:
        start[k] = start.get(k, 0) + 1
        out.append(f"⟦{k}{start[k]}⟧")
    return out


def _cases():
    en = load("en")
    for hz, act in itertools.product(Hazard, Action):
        for variant in en.actions[act.value]["text"]:
            yield hz, act, variant, None
    for key, spec in en.instructions.items():
        for variant in spec["text"]:
            yield Hazard.FLOOD, Action.EVACUATE_NOW, "", (key, variant)


@pytest.mark.parametrize("lang", ALL)
def test_every_template_round_trips(lang):
    failures = []
    for hz, act, a_variant, ins in _cases():
        counter: dict = {}
        a_phs = _ph(a_variant, counter)
        instructions = [Instruction(verb=ACTION_VERB[act], negated=False, placeholders=a_phs)]
        if ins:
            key, v = ins
            neg = v.startswith("neg")
            kinds = v.split("|")[1] if "|" in v else ""
            verb, _, obj = key.partition(":")
            instructions.append(Instruction(verb=verb, object=obj or None, negated=neg, placeholders=_ph(kinds, counter)))
        head = _ph("P", counter)
        all_phs = a_phs + head + [p for i in instructions[1:] for p in i.placeholders]
        intent = AlertIntent(
            hazard=hz, action=act, urgency="immediate",
            area_refs=[p for p in all_phs if "P" in p], time_refs=[p for p in all_phs if "T" in p],
            info_refs=[p for p in all_phs if "U" in p], instructions=instructions,
        )
        out = render(intent, lang)
        assert out.ok, (lang, out.uncovered)
        back = parse_lexicon(out.text, lang).intent
        if (back.hazard, back.action) != (hz, act) or sorted(map(repr, back.instructions)) != sorted(map(repr, instructions)):
            failures.append((hz.value, act.value, a_variant, ins, out.text, back.hazard.value, back.action.value,
                             [(i.verb, i.negated) for i in back.instructions]))
    assert not failures, failures[:5]


@pytest.mark.parametrize("lang", ALL)
def test_negated_templates_carry_marker_positive_do_not(lang):
    lx = load(lang)
    for key, spec in lx.instructions.items():
        for v, tpl in spec["text"].items():
            hits = lx.negation_hits(tpl)
            if v.startswith("neg"):
                assert hits >= 1, (lang, key, tpl)
            else:
                assert hits == 0, (lang, key, tpl)
    for a, spec in lx.actions.items():
        for tpl in spec["text"].values():
            assert lx.negation_hits(tpl) == 0, (lang, a, tpl)
