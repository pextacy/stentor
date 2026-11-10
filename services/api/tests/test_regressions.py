"""Bugs found in the A to Z review (2026-11-08). Each one is pinned here."""
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from stentor import llm
from stentor.intent.extract import extract
from stentor.intent.schema import Action, AlertIntent, Hazard, Instruction
from stentor.lock import apply, placeholders_in
from stentor.pipeline import compile_all, compile_lang, forbids_own_action
from stentor.verify.backparse import parse_lexicon

LANGS = ["ar", "es", "ht", "ko", "tl", "tr", "vi"]


# ---- 1. "Do not evacuate" must never become "Evacuate now" ------------------------

def test_negated_action_is_not_the_required_action():
    r = extract("Do not evacuate. Stay indoors.")
    assert r.intent.action == Action.STAY_INDOORS
    assert any(i.verb == "evacuate" and i.negated for i in r.intent.instructions)


def test_only_negated_action_falls_back_to_monitor_with_warning():
    r = extract("Wildfire nearby. Do not evacuate.")
    assert r.intent.action == Action.MONITOR
    assert any("no protective action" in w for w in r.warnings)


def test_back_parser_does_not_read_dropped_action_as_kept():
    # A translation that says "do not evacuate" does not carry evacuate_now.
    assert parse_lexicon("Do not evacuate.", "en").intent.action != Action.EVACUATE_NOW


@pytest.mark.parametrize("lang", LANGS)
def test_fallback_never_contradicts_a_forbidden_action(lang):
    # An operator (or a model) can still submit this contradictory intent.
    intent = AlertIntent(hazard=Hazard.WILDFIRE, action=Action.EVACUATE_NOW,
                         instructions=[Instruction(verb="evacuate", negated=True)])
    assert forbids_own_action(intent)
    r = compile_lang(intent, "Do not evacuate.", {}, lang)
    assert r.status.value == "BLOCKED"
    assert r.text is None
    assert any("forbids the required action" in x for x in r.reasons)


def test_positive_and_negated_same_action_still_falls_back():
    r = extract("Wildfire near Altadena. Do not evacuate via Lake Ave. Evacuate via Fair Oaks Ave.")
    assert not forbids_own_action(r.intent)
    for res in compile_all(r.intent, r.locked_text, r.mapping, LANGS):
        assert res.status.value in ("VERIFIED", "REVIEW", "FALLBACK")


# ---- 2. Reserved brackets in operator text ----------------------------------------

@pytest.mark.parametrize("text", [
    "Wildfire near Altadena ⟦P1⟧. Evacuate now.",
    "Evacuate ⟦⟧ now ⟦ ⟧.",
    "Fire near ⟦Lake ⟦Ave⟧⟧. Evacuate now.",
    "⟦P1⟧ ⟦T9⟧ evacuate",
])
def test_locked_text_has_only_mapped_unique_placeholders(text):
    locked, mapping = apply(text)
    phs = placeholders_in(locked)
    assert len(phs) == len(set(phs)), locked
    assert set(phs) == set(mapping), (locked, mapping)
    assert all(v.strip() for v in mapping.values()), mapping
    assert "⟦⟧" not in locked


def test_empty_place_names_are_ignored():
    locked, mapping = apply("Fire near Pasadena.", ["", "  ", "Pasadena"])
    assert mapping == {"⟦P1⟧": "Pasadena"}
    assert locked == "Fire near ⟦P1⟧."


def test_api_round_trip_with_reserved_brackets():
    from stentor.main import app

    c = TestClient(app)
    it = c.post("/intent", json={"text": "⟦P1⟧ ⟦T9⟧ evacuate now"}).json()
    r = c.post("/compile", json={"intent": it["intent"], "locked_text": it["locked_text"],
                                 "mapping": it["mapping"], "langs": ["es"]})
    assert r.status_code == 200, r.text


# ---- 3. Malformed model output never becomes a 500 ---------------------------------

def _fake(monkeypatch, text):
    msgs = SimpleNamespace(create=lambda **kw: SimpleNamespace(
        stop_reason="end_turn", content=[SimpleNamespace(type="text", text=text)]))
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "_client", lambda: SimpleNamespace(beta=SimpleNamespace(messages=msgs)))


def test_malformed_json_is_llm_unavailable(monkeypatch):
    _fake(monkeypatch, "{not json")
    with pytest.raises(llm.LLMUnavailable):
        llm.extract_intent("Evacuate now.", [])


def test_schema_breaking_intent_is_llm_unavailable(monkeypatch):
    _fake(monkeypatch, json.dumps({"hazard": "volcano", "action": "evacuate_now"}))
    with pytest.raises(llm.LLMUnavailable):
        llm.backparse("x", "Spanish", [], [])


def test_extract_falls_back_to_rules_on_bad_model_output(monkeypatch):
    _fake(monkeypatch, "{not json")
    r = extract("Wildfire near Altadena. EVACUATE NOW.")
    assert r.method == "lexicon"
    assert r.intent.action == Action.EVACUATE_NOW


# ---- 4. CAP export of an alert whose text is empty after sanitizing ----------------

def test_cap_export_with_empty_source_text():
    from stentor.main import app

    c = TestClient(app)
    it = c.post("/intent", json={"text": "⟦⟧"}).json()
    r = c.post("/compile", json={"intent": it["intent"], "locked_text": it["locked_text"],
                                 "mapping": it["mapping"], "langs": ["es"]})
    cap = c.post("/export/cap", json={"alert_id": r.json()["alert_id"]})
    assert cap.status_code == 200
    assert "<headline>" in cap.text


# ---- probe pass (2026-11-09): alerts a judge might type, beyond the demo script ----

import pytest as _pytest

from stentor.lock import apply as _apply


@_pytest.mark.parametrize("text,literal", [
    ("Mandatory evacuation for Zone A by 10 am.", "Zone A"),
    ("Cooling center at 120 Main St open until 9 pm.", "120 Main St"),
    ("Avalanche danger high on Mount Hood.", "Mount Hood"),
    ("Lockdown in effect at UCLA campus.", "UCLA"),
    ("Look for a red car, plate 7ABC123.", "7ABC123"),
    ("Wear an N95 mask outdoors.", "N95"),
    ("Gas leak in Building 7.", "Building 7"),
])
def test_literal_is_locked_whole(text, literal):
    """Rule 2: zones, addresses, acronyms, plates and codes are never given to a model."""
    _, mapping = _apply(text)
    assert literal in mapping.values(), mapping


def test_all_caps_emphasis_is_not_a_place():
    locked, mapping = _apply("Evacuate NOW. Stay away from ALL roads.")
    assert mapping == {} and "NOW" in locked and "ALL" in locked


def test_dropped_negation_is_blocked_not_review():
    """Rule 3: when the templates would leave out a sentence with 'not', no language may
    go to review with that sentence silently missing. It is blocked (safe fallback)."""
    from stentor.intent.extract import extract
    from stentor.pipeline import compile_lang

    ir = extract("Do not go to the hospital unless it is an emergency. Call 111 instead.")
    assert any("negation was not understood" in w for w in ir.warnings)
    for lang in ["vi", "ar", "ht"]:
        r = compile_lang(ir.intent, ir.locked_text, ir.mapping, lang)
        assert r.status.value in ("FALLBACK", "BLOCKED"), (lang, r.reasons)
        assert any(c.name == "template_coverage" and c.critical and not c.ok for c in r.checks)


def test_not_a_drill_is_not_a_dropped_negation():
    from stentor.intent.extract import critical_gaps, coverage, extract

    ir = extract("Lockdown in effect at UCLA campus. Stay inside, lock doors. This is not a drill.")
    _, missing = coverage(ir.locked_text, ir.intent)
    assert critical_gaps(missing) == []
