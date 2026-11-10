"""Compile one intent into verified renderings for each language."""
from __future__ import annotations

from pydantic import BaseModel

from stentor import llm
from stentor.channels.budget import ChannelFit, channel_budget
from stentor.channels.sms import SmsInfo, sms_info
from stentor.intent.extract import coverage, critical_gaps, ensure_action_instruction, instruction_keys
from stentor.intent.schema import ACTION_VERB, AlertIntent
from stentor.lexicon import load, meta
from stentor.lock import placeholders_in, restore
from stentor.lock.locker import finalize
from stentor.render.router import route
from stentor.render.template import render as render_template
from stentor.render.template import render_generic
from stentor.verify.backparse import parse_lexicon
from stentor.verify.chaos import CORRUPTIONS
from stentor.verify.checks import SHORT_ALERT_BUDGET, Check, run_all
from stentor.verify.diff import SlotDiff, Status, decide, diff


class Verification(BaseModel):
    status: Status
    checks: list[Check]
    diff: list[SlotDiff]
    back_intent: AlertIntent | None
    backparser: str
    reasons: list[str]


class ReviewStamp(BaseModel):
    reviewer: str
    decision: str  # approve | reject
    note: str = ""
    at: str


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
    channels: list[ChannelFit] = []
    back_english: str | None = None  # what the translation says, rendered back into English
    blocked_back_english: str | None = None  # what the blocked attempt said, in English
    review: ReviewStamp | None = None  # operator decision on a REVIEW language


def forbids_own_action(intent: AlertIntent) -> bool:
    """True when the alert says "do NOT <required action>" and never says to do it."""
    verb = ACTION_VERB[intent.action]
    same = [i for i in intent.instructions if i.verb == verb]
    return any(i.negated for i in same) and not any(not i.negated for i in same)


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


def back_to_english(back: AlertIntent | None, mapping: dict[str, str]) -> str | None:
    """The English template rendering of the back parsed intent: an English-only operator
    can read what each language actually says. Parts with no template are described."""
    if back is None:
        return None
    r = render_template(back, "en")
    text = r.text
    if r.uncovered:
        text = (text + " " if text else "") + "[Also says: " + "; ".join(r.uncovered) + "]"
    return finalize(restore(text, mapping, "en"), "en") if text else None


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
            _, missing = coverage(locked_text, intent)
            gaps = critical_gaps(missing)
            if gaps:
                # Rule 3: a dropped "not" (or "unless", "only") is never a review item.
                extra.append(Check(name="template_coverage", ok=False, critical=True,
                                   detail="approved templates would drop a word that changes the instruction ("
                                          + ", ".join(f"'{g}'" for g in gaps) + "); blocked"))
            else:
                extra.append(Check(name="template_coverage", ok=False, critical=False,
                                   detail="approved templates do not express every word of the source; operator review needed"))
        ver = verify(intent, locked_text, rendered, mapping, lang, extra)
        too_long = next((c for c in ver.checks if c.name == "length" and not c.ok), None)
        if too_long and ver.status != Status.BLOCKED and llm.available():
            # Short alert budget: ask for a compressed version, then verify it from scratch.
            try:
                short = llm.compress(rendered, load(lang).english_name, SHORT_ALERT_BUDGET)
                sver = verify(intent, locked_text, short, mapping, lang, extra)
                if sver.status in (Status.VERIFIED, Status.REVIEW):
                    rendered, ver = short, sver
                    notes.append("compressed to fit the short alert budget and verified again")
                else:
                    notes.append("compressed version failed verification; kept the longer verified text")
            except llm.LLMUnavailable as e:
                notes.append(f"could not compress over-length alert: {e}")

    if ver is not None and ver.status != Status.BLOCKED:
        text = finalize(restore(rendered, mapping, lang), lang)
        return LangResult(**m, status=ver.status, text=text, locked_text=rendered, renderer=r.renderer,
                          backparser=ver.backparser, checks=ver.checks, diff=ver.diff, reasons=ver.reasons,
                          notes=notes, chaos=chaos, sms=sms_info(text), channels=channel_budget(text),
                          back_english=back_to_english(ver.back_intent, mapping))

    # BLOCKED (or nothing could render): use the pre-approved generic safe template.
    reasons = (ver.reasons if ver else ["No renderer could express this alert"])
    attempt = finalize(restore(rendered, mapping, lang), lang) if rendered else None
    if forbids_own_action(intent):
        # The generic template states the action. If the source only ever says "do NOT
        # <action>", sending it would tell people the exact opposite. Nothing is sent.
        return LangResult(**m, status=Status.BLOCKED, text=None, locked_text=None, renderer=r.renderer,
                          backparser=ver.backparser if ver else "none", checks=ver.checks if ver else [],
                          diff=ver.diff if ver else [],
                          reasons=reasons + [f"The source forbids the required action itself ({intent.action.value}); "
                                             "the generic warning would contradict it, so nothing is sent"],
                          notes=notes, chaos=chaos, blocked_attempt=attempt,
                          blocked_back_english=back_to_english(ver.back_intent if ver else None, mapping))
    generic_locked, reduced = render_generic(intent, lang)
    gen_source = " ".join(reduced.info_refs)
    fver = verify(reduced, gen_source, generic_locked, mapping, lang)
    if fver.status == Status.BLOCKED:
        return LangResult(**m, status=Status.BLOCKED, text=None, locked_text=None, renderer=r.renderer,
                          backparser=fver.backparser, checks=(ver.checks if ver else []) + fver.checks,
                          diff=ver.diff if ver else [], reasons=reasons + ["The safe fallback also failed its checks, so nothing is sent"],
                          notes=notes, chaos=chaos, blocked_attempt=attempt,
                          blocked_back_english=back_to_english(ver.back_intent if ver else None, mapping))
    text = finalize(restore(generic_locked, mapping, lang), lang)
    return LangResult(**m, status=Status.FALLBACK, text=text, locked_text=generic_locked, renderer="safe_template",
                      backparser=fver.backparser, checks=ver.checks if ver else fver.checks,
                      diff=ver.diff if ver else fver.diff,
                      reasons=reasons + ["Sent the pre-approved generic warning for this hazard instead"],
                      notes=notes, chaos=chaos, fallback_used=True, blocked_attempt=attempt, sms=sms_info(text),
                      channels=channel_budget(text), back_english=back_to_english(fver.back_intent, mapping),
                      blocked_back_english=back_to_english(ver.back_intent if ver else None, mapping))


def safe_fallback(intent: AlertIntent, mapping: dict[str, str], lang: str) -> tuple[str, str, Verification] | None:
    """The pre-approved generic warning for this hazard, verified. (text, locked, verification) or None."""
    generic_locked, reduced = render_generic(intent, lang)
    fver = verify(reduced, " ".join(reduced.info_refs), generic_locked, mapping, lang)
    if fver.status == Status.BLOCKED:
        return None
    return finalize(restore(generic_locked, mapping, lang), lang), generic_locked, fver


def compile_all(intent: AlertIntent, locked_text: str, mapping: dict[str, str], langs: list[str],
                chaos: dict[str, str] | None = None) -> list[LangResult]:
    intent = ensure_action_instruction(intent)
    covered, _ = coverage(locked_text, intent)
    chaos = chaos or {}
    return [compile_lang(intent, locked_text, mapping, lg, chaos.get(lg) or chaos.get("*"), covered) for lg in langs]
