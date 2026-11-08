"""Dedicated tests for the failures that kill people: negation drop, placeholder drop,
action downgrade. Each must be BLOCKED (and fall back) in every language."""
import pytest

from conftest import LANGS
from stentor.pipeline import compile_lang
from stentor.render.template import render
from stentor.verify.chaos import CORRUPTIONS, drop_negation
from stentor.verify.checks import check_negation_count, check_placeholders


@pytest.mark.parametrize("lang", LANGS)
def test_clean_demo_verified(demo, lang):
    r = compile_lang(demo.intent, demo.locked_text, demo.mapping, lang)
    assert r.status.value == "VERIFIED", r.reasons
    assert r.renderer == "template"
    for literal in ("Altadena", "Lake Ave", "211"):
        assert literal in r.text


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("kind", ["drop_negation", "drop_placeholder", "downgrade_action",
                                  "duplicate_placeholder", "swap_place", "shift_time", "swap_hazard"])
def test_injected_corruption_never_sent(demo, lang, kind):
    r = compile_lang(demo.intent, demo.locked_text, demo.mapping, lang, chaos=kind)
    assert r.status.value in ("FALLBACK", "BLOCKED"), (kind, lang, r.reasons)
    assert r.blocked_attempt is not None
    if r.status.value == "FALLBACK":
        assert r.renderer == "safe_template"
        assert "211" in r.text  # safe fallback keeps the info line


@pytest.mark.parametrize("lang", LANGS)
def test_negation_drop_detected_twice(demo, lang):
    """Lexicon count and slot diff must both catch a dropped 'not'."""
    rendered = render(demo.intent, lang).text
    corrupted = drop_negation(rendered, demo.intent, lang)
    assert corrupted and corrupted != rendered
    assert not check_negation_count(demo.intent, corrupted, lang).ok
    r = compile_lang(demo.intent, demo.locked_text, demo.mapping, lang, chaos="drop_negation")
    neg = next(d for d in r.diff if d.slot == "negations")
    assert not neg.match


def test_placeholder_check_counts_exactly():
    src = "A ⟦P1⟧ B ⟦T1⟧"
    assert check_placeholders(src, "x ⟦T1⟧ y ⟦P1⟧").ok
    assert not check_placeholders(src, "x ⟦T1⟧").ok
    assert not check_placeholders(src, "⟦P1⟧ ⟦P1⟧ ⟦T1⟧").ok
    assert not check_placeholders(src, "⟦P1⟧ ⟦T1⟧ ⟦P9⟧").ok


def test_korean_negation_drop_flips_meaning(demo):
    rendered = render(demo.intent, "ko").text
    assert "돌아오지 마십시오" in rendered
    assert "돌아오십시오" in drop_negation(rendered, demo.intent, "ko")


def test_all_corruptions_registered():
    assert set(CORRUPTIONS) == {"drop_negation", "downgrade_action", "shift_time", "swap_place",
                                "swap_hazard", "drop_placeholder", "duplicate_placeholder"}


def test_uncovered_alert_is_not_auto_verified():
    from stentor.intent.extract import extract

    ir = extract("Tornado warning for Moore. Shelter in place now. Go to a basement or interior room without windows.")
    assert not ir.template_coverage
    r = compile_lang(ir.intent, ir.locked_text, ir.mapping, "vi")
    assert r.status.value == "REVIEW"


def test_alert_without_action_sentence_is_not_blocked():
    """Regression (eval c17): 'Drop, cover and hold on' has no action sentence; the
    implied action must be made explicit, not counted as a mismatch."""
    from stentor.intent.extract import extract

    ir = extract("Earthquake warning for Hatay. Drop, cover and hold on. Do not use elevators. Info: 112.")
    assert ir.intent.instructions[0].verb == "monitor"
    for lang in LANGS:
        assert compile_lang(ir.intent, ir.locked_text, ir.mapping, lang).status.value == "VERIFIED"
