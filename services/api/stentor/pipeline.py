"""Compile one intent into verified renderings for each language."""
from __future__ import annotations

from pydantic import BaseModel

from stentor import llm
from stentor.channels.sms import SmsInfo, sms_info
from stentor.intent.extract import coverage, ensure_action_instruction, instruction_keys
from stentor.intent.schema import AlertIntent
from stentor.lexicon import load, meta
from stentor.lock import placeholders_in, restore
from stentor.render.router import route
from stentor.render.template import render_generic
from stentor.verify.backparse import parse_lexicon
from stentor.verify.chaos import CORRUPTIONS
from stentor.verify.checks import Check, run_all
from stentor.verify.diff import SlotDiff, Status, decide, diff


class Verification(BaseModel):
    status: Status
    checks: list[Check]
    diff: list[SlotDiff]
    back_intent: AlertIntent | None
    backparser: str
    reasons: list[str]


class LangResult(BaseModel):
    lang: str
    name: str
    english_name: str
    dir: str
    tts: str
    reviewed_by: str
    status: Status
    text: str | None  # restored, what would be sent
    locked_text: str | None
    renderer: str
    backparser: str
    checks: list[Check]
    diff: list[SlotDiff]
    reasons: list[str]
    notes: list[str]
    chaos: str | None = None
    fallback_used: bool = False
    blocked_attempt: str | None = None  # the rendering that was blocked, for the operator
    sms: SmsInfo | None = None


def verify(src: AlertIntent, source_locked: str, rendered: str, mapping: dict[str, str], lang: str,
           extra_checks: list[Check] | None = None) -> Verification:
    restored = restore(rendered, mapping, lang)
    checks = run_all(src, source_locked, rendered, restored, mapping, lang) + (extra_checks or [])
    backparser = "lexicon"
    back: AlertIntent | None = None
    if llm.available():
        try:
            back = llm.backparse(rendered, load(lang).english_name, list(dict.fromkeys(placeholders_in(source_locked))), instruction_keys())
            backparser = llm.BACKPARSE_MODEL
        except llm.LLMUnavailable as e:
            checks.append(Check(name="backparse_model", ok=False, critical=True,
                                detail=f"second model back parse failed ({e}); blocking is the safe choice"))
    if back is None:
        back = parse_lexicon(rendered, lang).intent
    diffs = diff(src, back, compare_noncritical=backparser != "lexicon")
    status, reasons = decide(checks, diffs)
    return Verification(status=status, checks=checks, diff=diffs, back_intent=back, backparser=backparser, reasons=reasons)


def compile_lang(intent: AlertIntent, locked_text: str, mapping: dict[str, str], lang: str,
                 chaos: str | None = None, covered: bool | None = None) -> LangResult:
    m = meta(lang)
    if covered is None:
        covered, _ = coverage(locked_text, intent)
    r = route(intent, locked_text, lang, covered)
    notes = list(r.notes)
    if r.text is None:
        rendered, ver = None, None
    else:
        rendered = r.text
        if chaos:
            corrupted = CORRUPTIONS[chaos](rendered, intent, lang)
            if corrupted is None:
                notes.append(f"chaos {chaos} does not apply to this alert")
            else:
                rendered = corrupted
                notes.append(f"CHAOS MODE: injected {chaos} after rendering, before verification")
        extra = []
        if r.template_partial:
            extra.append(Check(name="template_coverage", ok=False, critical=False,
                               detail="approved templates do not express every word of the source; operator review needed"))
        ver = verify(intent, locked_text, rendered, mapping, lang, extra)

    if ver is not None and ver.status != Status.BLOCKED:
        text = restore(rendered, mapping, lang)
        return LangResult(**m, status=ver.status, text=text, locked_text=rendered, renderer=r.renderer,
                          backparser=ver.backparser, checks=ver.checks, diff=ver.diff, reasons=ver.reasons,
                          notes=notes, chaos=chaos, sms=sms_info(text))

    # BLOCKED (or nothing could render): use the pre-approved generic safe template.
    generic_locked, reduced = render_generic(intent, lang)
    gen_source = " ".join(reduced.info_refs)
    fver = verify(reduced, gen_source, generic_locked, mapping, lang)
    reasons = (ver.reasons if ver else ["no renderer could express this alert"])
    attempt = restore(rendered, mapping, lang) if rendered else None
    if fver.status == Status.BLOCKED:
        return LangResult(**m, status=Status.BLOCKED, text=None, locked_text=None, renderer=r.renderer,
                          backparser=fver.backparser, checks=(ver.checks if ver else []) + fver.checks,
                          diff=ver.diff if ver else [], reasons=reasons + ["safe fallback also failed verification"],
                          notes=notes, chaos=chaos, blocked_attempt=attempt)
    text = restore(generic_locked, mapping, lang)
    return LangResult(**m, status=Status.FALLBACK, text=text, locked_text=generic_locked, renderer="safe_template",
                      backparser=fver.backparser, checks=ver.checks if ver else fver.checks,
                      diff=ver.diff if ver else fver.diff,
                      reasons=reasons + ["sent the pre-approved generic safe template for this hazard instead"],
                      notes=notes, chaos=chaos, fallback_used=True, blocked_attempt=attempt, sms=sms_info(text))


def compile_all(intent: AlertIntent, locked_text: str, mapping: dict[str, str], langs: list[str],
                chaos: dict[str, str] | None = None) -> list[LangResult]:
    intent = ensure_action_instruction(intent)
    covered, _ = coverage(locked_text, intent)
    chaos = chaos or {}
    return [compile_lang(intent, locked_text, mapping, lg, chaos.get(lg) or chaos.get("*"), covered) for lg in langs]
