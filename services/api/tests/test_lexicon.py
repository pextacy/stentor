"""Lexicon consistency: every template must round trip through the parser, so that a
clean rendering is never blocked by our own lexicon, and markers must be where they
belong (negation only in negated templates, role words only in role variants)."""
import itertools

import pytest

from stentor.intent.schema import ACTION_VERB, ROUTE_ACTIONS, Action, AlertIntent, Hazard, Instruction
from stentor.lexicon import available, load
from stentor.render.template import render
from stentor.verify.backparse import parse_lexicon

ALL = available()


def test_all_eight_languages_present():
    assert set(ALL) == {"en", "vi", "tl", "ko", "ar", "ht", "es", "tr"}


@pytest.mark.parametrize("lang", ALL)
def test_metadata_complete(lang):
    lx = load(lang)
    en = load("en")
    assert lx.reviewed_by
    assert set(lx.hazards) == {h.value for h in Hazard}
    assert set(lx.actions) == {a.value for a in Action}
    assert set(lx.instructions) == set(en.instructions), set(en.instructions) ^ set(lx.instructions)
    for a in Action:
        assert set(lx.actions[a.value]["text"]) == set(en.actions[a.value]["text"]), (lang, a)
    for k, spec in en.instructions.items():
        assert set(lx.instructions[k]["text"]) == set(spec["text"]), (lang, k)
    for key in ("headline", "headline_place", "headline_distance", "headline_all_clear",
                "headline_all_clear_place", "event_name", "role_markers", "time"):
        assert lx.opt(key), (lang, key)


class _Ph:
    def __init__(self):
        self.n: dict[str, int] = {}

    def take(self, kinds: str) -> list[str]:
        out = []
        for k in kinds:
            self.n[k] = self.n.get(k, 0) + 1
            out.append(f"⟦{k}{self.n[k]}⟧")
        return out


def _intent(hz: Hazard, act: Action, a_variant: str, extra: Instruction | None, ph: _Ph) -> AlertIntent:
    kinds, _, role = a_variant.partition(":")
    a_phs = ph.take(kinds)
    obj = None
    if "P" in kinds and act in ROUTE_ACTIONS:
        obj = role or "via"
    ins = [Instruction(verb=ACTION_VERB[act], object=obj, negated=False, placeholders=a_phs)]
    if extra:
        ins.append(extra)
    head = ph.take("P")
    phs = head + [p for i in ins for p in i.placeholders]
    return AlertIntent(
        hazard=hz, action=act, urgency="immediate", instructions=ins,
        area_refs=[p for p in phs if "P" in p], time_refs=[p for p in phs if "T" in p],
        info_refs=[p for p in phs if "U" in p], number_refs=[p for p in phs if "N" in p],
    )


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
        ph = _Ph()
        extra = None
        if ins:
            key, v = ins
            kinds = v.split("|")[1] if "|" in v else ""
            verb, _, obj = key.partition(":")
            extra = Instruction(verb=verb, object=obj or None, negated=v.startswith("neg"), placeholders=ph.take(kinds))
        intent = _intent(hz, act, a_variant, extra, ph)
        out = render(intent, lang)
        assert out.ok, (lang, hz, act, a_variant, ins, out.uncovered)
        back = parse_lexicon(out.text, lang).intent
        want = sorted(i.model_dump_json() for i in intent.instructions)
        got = sorted(i.model_dump_json() for i in back.instructions)
        if (back.hazard, back.action) != (hz, act) or want != got:
            failures.append((hz.value, act.value, a_variant, ins, out.text, back.hazard.value, back.action.value,
                             [(i.verb, i.object, i.negated, i.placeholders) for i in back.instructions]))
    assert not failures, f"{len(failures)} failures, first: {failures[:3]}"


@pytest.mark.parametrize("lang", ALL)
def test_headline_variants_round_trip(lang):
    """Distance, event name, several places and the cancelled-warning headline."""
    ph = _Ph()
    p1, p2 = ph.take("PP")
    n1, = ph.take("N")
    e1, = ph.take("E")
    cases = [
        AlertIntent(hazard=Hazard.WILDFIRE, action=Action.EVACUATE_NOW, area_refs=[p1], number_refs=[n1],
                    instructions=[Instruction(verb="evacuate", negated=False)]),
        AlertIntent(hazard=Hazard.HURRICANE, action=Action.EVACUATE_NOW, area_refs=[p1, p2], event_refs=[e1],
                    instructions=[Instruction(verb="evacuate", negated=False)]),
        AlertIntent(hazard=Hazard.TSUNAMI, action=Action.ALL_CLEAR, area_refs=[p1],
                    instructions=[Instruction(verb="all_clear", negated=False)]),
    ]
    for intent in cases:
        out = render(intent, lang)
        assert out.ok, (lang, out.uncovered)
        back = parse_lexicon(out.text, lang).intent
        for slot in ("hazard", "action", "area_refs", "number_refs", "event_refs"):
            assert getattr(back, slot) == getattr(intent, slot), (lang, slot, out.text)


@pytest.mark.parametrize("lang", ALL)
def test_negation_markers_only_where_negated(lang):
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
    for key in ("headline", "headline_place", "headline_distance", "headline_all_clear", "headline_all_clear_place"):
        assert lx.negation_hits(lx.opt(key)) == 0, (lang, key)


@pytest.mark.parametrize("lang", ALL)
def test_route_and_destination_are_told_apart(lang):
    """The role word next to the place decides route ("via") vs destination ("to"),
    so "evacuate via X" and "evacuate to X" can never verify as each other."""
    from stentor.verify.backparse import _role

    lx = load(lang)
    for act in ROUTE_ACTIONS:
        texts = lx.actions[act.value]["text"]
        assert _role(lx, texts["P"].replace("{P}", "⟦P1⟧")) == "via", (lang, act, texts["P"])
        assert _role(lx, texts["P:to"].replace("{P}", "⟦P1⟧")) == "to", (lang, act, texts["P:to"])
