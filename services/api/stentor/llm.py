"""Claude calls: place detection, intent extraction, rendering, back parsing.

Only used when ANTHROPIC_API_KEY is configured. Every caller has a deterministic
path for when this is unavailable or fails.

Model choice: the renderer and the back parser are deliberately *different* models
(docs/PLAN.md: avoid correlated errors).
"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

import anthropic

from stentor.config import get_settings
from stentor.intent.schema import Action, AlertIntent, Hazard

EXTRACT_MODEL = "claude-opus-5-5"
RENDER_MODEL = "claude-opus-5-5"
BACKPARSE_MODEL = "claude-sonnet-5-5"

# Server side refusal fallback (Claude API). Routes a declined request to a
# fallback model by refusal category instead of failing the call.
_FALLBACK = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}


class LLMUnavailable(RuntimeError):
    pass


def available() -> bool:
    return bool(get_settings().anthropic_api_key)


@lru_cache
def _client() -> anthropic.Anthropic:
    key = get_settings().anthropic_api_key
    if not key:
        raise LLMUnavailable("ANTHROPIC_API_KEY is not set")
    return anthropic.Anthropic(api_key=key)


INSTRUCTION_SCHEMA = {
    "type": "object",
    "properties": {
        "verb": {"type": "string"},
        "object": {"type": ["string", "null"]},
        "negated": {"type": "boolean"},
        "placeholders": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["verb", "object", "negated", "placeholders"],
    "additionalProperties": False,
}

INTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "hazard": {"type": "string", "enum": [h.value for h in Hazard]},
        "action": {"type": "string", "enum": [a.value for a in Action]},
        "urgency": {"type": "string", "enum": ["immediate", "expected", "future"]},
        "area_refs": {"type": "array", "items": {"type": "string"}},
        "time_refs": {"type": "array", "items": {"type": "string"}},
        "expires": {"type": ["string", "null"]},
        "instructions": {"type": "array", "items": INSTRUCTION_SCHEMA},
        "info_refs": {"type": "array", "items": {"type": "string"}},
        "number_refs": {"type": "array", "items": {"type": "string"}},
        "event_refs": {"type": "array", "items": {"type": "string"}},
        "source": {"type": ["string", "null"]},
        "extra_info": {"type": ["string", "null"]},
    },
    "required": ["hazard", "action", "urgency", "area_refs", "time_refs", "expires",
                 "instructions", "info_refs", "number_refs", "event_refs", "source", "extra_info"],
    "additionalProperties": False,
}


def _json_call(model: str, system: str, user: str, schema: dict, effort: str) -> Any:
    try:
        resp = _client().beta.messages.create(
            model=model,
            max_tokens=16000,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
            **_FALLBACK,
        )
    except anthropic.APIConnectionError as e:
        raise LLMUnavailable(f"cannot reach Claude API: {e}") from e
    except anthropic.RateLimitError as e:
        raise LLMUnavailable("Claude API rate limited") from e
    except anthropic.APIStatusError as e:
        raise LLMUnavailable(f"Claude API error {e.status_code}") from e
    if resp.stop_reason == "refusal":
        raise LLMUnavailable("Claude declined the request")
    if resp.stop_reason == "max_tokens":
        raise LLMUnavailable("Claude output was truncated")
    text = next((b.text for b in resp.content if b.type == "text"), None)
    if text is None:
        raise LLMUnavailable("Claude returned no text")
    return json.loads(text)


# ------------------------------------------------------------------ extraction

PLACES_SYSTEM = (
    "You find literals in emergency alerts that must never be translated: place names, "
    "neighborhoods, street and road names, buildings and landmarks. Return them exactly as "
    "written in the text, one entry per distinct name. Do not include hazards, times, numbers "
    "or phone numbers."
)


def detect_places(text: str) -> list[str]:
    schema = {
        "type": "object",
        "properties": {"places": {"type": "array", "items": {"type": "string"}}},
        "required": ["places"],
        "additionalProperties": False,
    }
    data = _json_call(EXTRACT_MODEL, PLACES_SYSTEM, text, schema, effort="low")
    return [p for p in data["places"] if p and p in text]


def _extract_system(verbs: list[str]) -> str:
    return (
        "You convert an English emergency alert into a structured Alert Intent.\n"
        "The text contains locked placeholders like ⟦P1⟧ (place), ⟦T1⟧ (time or day), ⟦N1⟧ (number "
        "or quantity), ⟦U1⟧ (phone or URL), ⟦E1⟧ (event name such as a storm name). Refer to "
        "literals only by these placeholder ids, never by value.\n"
        "Rules:\n"
        "- hazard and action use the enum values. action is the single most important protective action.\n"
        "- instructions: one entry per imperative sentence, in order, including the main action sentence. "
        "negated is true for 'do not', 'don't', 'never'. placeholders lists the ids in that sentence.\n"
        f"- verb/object: prefer these normalized keys when they fit (verb:object): {', '.join(verbs)}. "
        "For action sentences use the verb evacuate, prepare, shelter, move, stay, avoid, boil, monitor or all_clear. "
        "For evacuate/prepare with a place: object is 'via' when the place is a route, 'to' when it is a "
        "destination; if the place is only the affected area, leave it out of the instruction and object null.\n"
        "- A phrase like 'stay out of damaged buildings' is a negated instruction (enter:damaged_buildings, negated true).\n"
        "- area_refs: every P. time_refs: every T. info_refs: every U. number_refs: every N. event_refs: every E.\n"
        "- expires: the T placeholder for when the alert itself ends, or null.\n"
        "- Do not infer anything that is not stated."
    )


def extract_intent(locked_text: str, verbs: list[str]) -> AlertIntent:
    data = _json_call(EXTRACT_MODEL, _extract_system(verbs), locked_text, INTENT_SCHEMA, effort="medium")
    return AlertIntent.model_validate(data)


# ------------------------------------------------------------------- rendering

def render_text(locked_text: str, intent: AlertIntent, lang_name: str, action_phrase: str | None,
                negation_markers: list[str]) -> str:
    system = (
        f"You translate emergency alerts from English into {lang_name}. Lives depend on exact meaning.\n"
        "- Short, plain, imperative sentences, reading level about grade 6. One instruction per sentence.\n"
        "- Copy every placeholder like ⟦P1⟧ exactly once, unchanged. Never translate or expand them.\n"
        "- Never soften the action. Keep every negation."
        + (f" Express the main action with the phrase '{action_phrase}'." if action_phrase else "")
        + (f" Use one of these negation words for each 'do not': {', '.join(negation_markers)}." if negation_markers else "")
        + "\n- No emoji, no extra advice, no commentary."
    )
    schema = {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"], "additionalProperties": False}
    return _json_call(RENDER_MODEL, system, locked_text, schema, effort="medium")["text"]


# ---------------------------------------------------------------- back parsing

def backparse(rendered: str, lang_name: str, placeholders: list[str], verbs: list[str]) -> AlertIntent:
    system = (
        f"You read an emergency alert written in {lang_name} and extract its meaning as an Alert Intent. "
        "You are not shown any other version of the alert. Report what the text says, not what it "
        "probably meant: if a 'not' is missing, the instruction is not negated; if the action is weaker, "
        "report the weaker action.\n"
        f"Valid placeholders: {' '.join(placeholders) or 'none'}. Refer to them by id.\n"
        f"Normalized instruction keys (verb:object): {', '.join(verbs)}. Write verbs in English."
    )
    data = _json_call(BACKPARSE_MODEL, system, rendered, INTENT_SCHEMA, effort="low")
    return AlertIntent.model_validate(data)


def compress(locked_rendered: str, lang_name: str, limit: int) -> str:
    system = (
        f"You shorten an emergency alert written in {lang_name} to at most {limit} characters "
        "(placeholders count as their token length). Keep the hazard, the main action, every negation "
        "and every placeholder like ⟦P1⟧ exactly once. Drop only courtesy words and repetition. "
        "Answer in the same language."
    )
    schema = {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"], "additionalProperties": False}
    return _json_call(RENDER_MODEL, system, locked_rendered, schema, effort="medium")["text"]
