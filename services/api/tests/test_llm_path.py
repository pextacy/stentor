"""Claude path with a fake client: checks request shape and that a back parser that
reports a dropped negation blocks the language. No network."""
import json
from types import SimpleNamespace

import pytest

from conftest import DEMO
from stentor import llm


class FakeMessages:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def create(self, **kw):
        self.calls.append(kw)
        payload = self.replies.pop(0)
        return SimpleNamespace(stop_reason="end_turn",
                               content=[SimpleNamespace(type="text", text=json.dumps(payload, ensure_ascii=False))])


@pytest.fixture
def fake(monkeypatch):
    def install(replies):
        msgs = FakeMessages(replies)
        monkeypatch.setattr(llm, "available", lambda: True)
        monkeypatch.setattr(llm, "_client", lambda: SimpleNamespace(beta=SimpleNamespace(messages=msgs)))
        return msgs
    return install


def _intent(negated=True):
    return {"hazard": "wildfire", "action": "evacuate_now", "urgency": "immediate",
            "area_refs": ["⟦P1⟧", "⟦P2⟧"], "time_refs": ["⟦T1⟧"], "expires": None,
            "instructions": [
                {"verb": "evacuate", "object": None, "negated": False, "placeholders": ["⟦P2⟧"]},
                {"verb": "return", "object": None, "negated": negated, "placeholders": ["⟦T1⟧"]}],
            "info_refs": ["⟦U1⟧"], "source": None, "extra_info": None}


def test_extract_uses_two_calls_and_schema(fake):
    from stentor.intent.extract import extract

    msgs = fake([{"places": ["Altadena", "Lake Ave"]}, _intent()])
    r = extract(DEMO)
    assert r.method == "claude"
    assert r.intent.instructions[1].negated
    call = msgs.calls[1]
    assert call["model"] == llm.EXTRACT_MODEL
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert call["fallbacks"] == "default"
    assert "⟦P1⟧" in call["messages"][0]["content"]


def test_backparse_model_differs_and_blocks_on_dropped_negation(fake, demo):
    from stentor.pipeline import compile_lang

    reduced = {**_intent(), "area_refs": [], "time_refs": [],
               "instructions": [{"verb": "evacuate", "object": None, "negated": False, "placeholders": []}]}
    msgs = fake([_intent(negated=False), reduced])  # second model says: not negated; then checks the fallback
    r = compile_lang(demo.intent, demo.locked_text, demo.mapping, "vi")
    assert msgs.calls[0]["model"] == llm.BACKPARSE_MODEL != llm.RENDER_MODEL
    assert r.backparser == llm.BACKPARSE_MODEL
    assert r.status.value == "FALLBACK"


def test_backparse_failure_blocks(monkeypatch, demo):
    from stentor.pipeline import compile_lang

    monkeypatch.setattr(llm, "available", lambda: True)

    def boom(*a, **k):
        raise llm.LLMUnavailable("down")

    monkeypatch.setattr(llm, "backparse", boom)
    r = compile_lang(demo.intent, demo.locked_text, demo.mapping, "ht")
    assert r.status.value in ("FALLBACK", "BLOCKED")
    assert any("back parse failed" in x for x in r.reasons)
