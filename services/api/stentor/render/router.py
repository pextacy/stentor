"""Renderer router: template > Adaption model > LLM (docs/DOCS.md section 3)."""
from __future__ import annotations

import os
from dataclasses import dataclass

from stentor import llm
from stentor.config import get_settings
from stentor.intent.schema import AlertIntent
from stentor.lexicon import load
from stentor.render import adaption
from stentor.render.template import render as render_template


@dataclass
class Rendering:
    text: str | None
    renderer: str  # template | adaption | llm | none
    notes: list[str]
    template_partial: bool = False  # templates used although they drop some source words


def route(intent: AlertIntent, locked_text: str, lang: str, covered: bool) -> Rendering:
    notes: list[str] = []
    tpl = render_template(intent, lang)
    # Eval only: STENTOR_FORCE_MODEL=1 skips templates to measure model renderers.
    force_model = os.environ.get("STENTOR_FORCE_MODEL") == "1"
    if force_model:
        notes.append("eval: templates skipped to measure the model renderer")
    if tpl.ok and covered and not force_model:
        return Rendering(tpl.text, "template", ["approved phrase templates cover the whole alert"])
    if not tpl.ok:
        notes.append("templates cannot express: " + "; ".join(tpl.uncovered))
    else:
        notes.append("templates do not cover every word of the source")

    settings = get_settings()
    if settings.stentor_renderer == "adaption" and adaption.supports(lang):
        try:
            return Rendering(adaption.render(locked_text, lang), "adaption", notes + ["rendered by Adaption alert model"])
        except adaption.AdaptionUnavailable as e:
            notes.append(f"Adaption renderer unavailable: {e}")

    if llm.available():
        lx = load(lang)
        phrases = lx.action_phrases(intent.action.value)
        try:
            text = llm.render_text(locked_text, intent, lx.english_name, phrases[0] if phrases else None, lx.negation_markers)
            return Rendering(text, "llm", notes + [f"rendered by {llm.RENDER_MODEL}"])
        except llm.LLMUnavailable as e:
            notes.append(f"LLM renderer unavailable: {e}")

    if tpl.ok:
        # Safer than nothing, but the operator must review what was dropped.
        return Rendering(tpl.text, "template", notes + ["no model renderer configured; using templates"], template_partial=True)
    return Rendering(None, "none", notes + ["no renderer can express this alert"])
