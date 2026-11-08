"""Every alert in eval/suites/realistic.jsonl is a regression test: hazard, action,
negation count and the status in all seven languages must match what we expect.
Each bug found in review became one of these cases."""
import json
from pathlib import Path

import pytest

from stentor.intent.extract import extract
from stentor.pipeline import compile_lang

SUITE = Path(__file__).resolve().parents[3] / "eval" / "suites" / "realistic.jsonl"
CASES = [json.loads(line) for line in SUITE.read_text(encoding="utf-8").splitlines() if line.strip()]
LANGS = ["vi", "tl", "ko", "ar", "ht", "es", "tr"]


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_realistic_alert(case):
    ir = extract(case["text"])
    e = case["expect"]
    assert ir.intent.hazard.value == e["hazard"]
    assert ir.intent.action.value == e["action"]
    assert sum(i.negated for i in ir.intent.instructions) == e["negated"]
    for lang in LANGS:
        r = compile_lang(ir.intent, ir.locked_text, ir.mapping, lang)
        assert r.status.value == e["status"], (lang, r.text, r.reasons)


def test_time_order_swap_is_caught():
    """Regression: 'between 11:00 and 16:00' swapped to 'between 16:00 and 11:00'."""
    ir = extract("Heat wave in Ankara: stay indoors between 11:00 and 16:00.")
    for lang in LANGS:
        r = compile_lang(ir.intent, ir.locked_text, ir.mapping, lang, chaos="shift_time")
        assert r.status.value in ("FALLBACK", "BLOCKED"), lang


def test_route_vs_destination_not_interchangeable():
    from stentor.verify.diff import decide, diff

    via = extract("Wildfire. Evacuate now via Lake Ave.")
    to = extract("Wildfire. Evacuate now to Lake Ave.")
    assert via.intent.instructions[0].object == "via"
    assert to.intent.instructions[0].object == "to"
    status, _ = decide([], diff(via.intent, to.intent))
    assert status.value == "BLOCKED"


def test_object_matters_in_diff():
    """Review finding: 'do not drink tap water' must not verify as 'do not drink water'."""
    from stentor.intent.schema import Instruction
    from stentor.verify.diff import decide, diff

    a = extract("Boil water notice. Boil water before drinking. Do not drink tap water.").intent
    b = a.model_copy(update={"instructions": [a.instructions[0], Instruction(verb="drink", object="water", negated=True)]})
    status, _ = decide([], diff(a, b))
    assert status.value == "BLOCKED"
