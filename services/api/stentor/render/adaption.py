"""Adaption fine tuned alert renderer (optional track, docs/PLAN.md section 3).

Wired behind STENTOR_RENDERER=adaption. Until a model is trained and
STENTOR_MODEL_ID is set, `supports()` is False and the router skips it.
"""
from __future__ import annotations

import httpx

from stentor.config import get_settings

# Languages the trained model was evaluated on. Primary target: Haitian Creole.
TRAINED_LANGS = {"ht"}


class AdaptionUnavailable(RuntimeError):
    pass


def supports(lang: str) -> bool:
    s = get_settings()
    return bool(s.adaption_api_key and s.stentor_model_id) and lang in TRAINED_LANGS


def render(locked_text: str, lang: str) -> str:
    s = get_settings()
    if not supports(lang):
        raise AdaptionUnavailable("no trained Adaption model configured for this language")
    # TODO(stentor): confirm the inference endpoint and payload against docs.adaptionlabs.ai
    # once the model is trained. This assumes an OpenAI-style completion route.
    try:
        r = httpx.post(
            f"{s.adaption_base_url.rstrip('/')}/api/v1/models/{s.stentor_model_id}/generate",
            headers={"Authorization": f"Bearer {s.adaption_api_key}"},
            json={"input": locked_text, "target_language": lang},
            timeout=30,
        )
        r.raise_for_status()
        text = r.json().get("output") or r.json().get("text")
    except (httpx.HTTPError, ValueError) as e:
        raise AdaptionUnavailable(str(e)) from e
    if not text:
        raise AdaptionUnavailable("empty response")
    return text
