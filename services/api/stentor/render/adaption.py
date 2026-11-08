"""Adaption fine tuned alert renderer (optional track, docs/PLAN.md section 3).

Wired behind STENTOR_RENDERER=adaption. Until a model is trained and
STENTOR_MODEL_ID is set, `supports()` is False and the router skips it.
Inference uses the Responses API: POST {base}/api/v1/responses.
"""
from __future__ import annotations

import httpx

from stentor.config import get_settings

# Languages the trained model was evaluated on. Primary target: Haitian Creole.
TRAINED_LANGS = {"ht"}

INSTRUCTIONS = (
    "Rewrite the English emergency alert as a short, plain, imperative alert in {lang}. "
    "Keep every placeholder like ⟦P1⟧ exactly once and unchanged. Never soften the action. "
    "Keep every negation. Output only the alert."
)
LANG_NAMES = {"ht": "Haitian Creole", "tl": "Tagalog", "vi": "Vietnamese", "ko": "Korean", "ar": "Arabic"}


class AdaptionUnavailable(RuntimeError):
    pass


def supports(lang: str) -> bool:
    s = get_settings()
    return bool(s.adaption_api_key and s.stentor_model_id) and lang in TRAINED_LANGS


def render(locked_text: str, lang: str) -> str:
    s = get_settings()
    if not supports(lang):
        raise AdaptionUnavailable("no trained Adaption model configured for this language")
    try:
        r = httpx.post(
            f"{s.adaption_base_url.rstrip('/')}/api/v1/responses",
            headers={"Authorization": f"Bearer {s.adaption_api_key}"},
            json={
                "model": s.stentor_model_id,
                "instructions": INSTRUCTIONS.format(lang=LANG_NAMES.get(lang, lang)),
                "input": locked_text,
                "temperature": 0,
                "max_output_tokens": 512,
            },
            timeout=60,
        )
        r.raise_for_status()
        body = r.json()
    except (httpx.HTTPError, ValueError) as e:
        raise AdaptionUnavailable(str(e)) from e
    if body.get("status") not in (None, "completed"):
        raise AdaptionUnavailable(f"response status {body.get('status')}: {body.get('error')}")
    text = (body.get("output_text") or "").strip()
    if not text:
        raise AdaptionUnavailable("empty response")
    return text
