"""Operator workflow, exports, lexicon tools, settings data and platform endpoints
(docs/FEATURES.md). The core pipeline endpoints stay in main.py."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel, Field

from stentor import db, middleware, webhooks
from stentor.channels.cap_validate import CapReport, validate_cap
from stentor.channels.exports import audit_csv, json_bundle, results_csv, text_bundle
from stentor.channels.feed import build_feed
from stentor.channels.ssml import build_ssml
from stentor.config import get_settings
from stentor.intent.extract import extract
from stentor.intent.schema import Action, AlertIntent, Instruction
from stentor.lexicon import TARGET_LANGS, available, meta
from stentor.lexicon.tools import LexiconView, LintReport, explore, lint
from stentor.lock import placeholders_in, restore
from stentor.main import (CompileResponse, cap_xml, check_langs, check_replaceable, count_statuses, notify,
                          settings)
from stentor.pipeline import ReviewStamp, compile_all, safe_fallback
from stentor.quality import LintIssue, lint_intent
from stentor.render.template import render as render_template
from stentor.verify.diff import SENDABLE, Status
from stentor.views import AlertOut, load_alert

router = APIRouter()


def _lang_ok(lang: str) -> None:
    if lang not in available() or lang == "en":
        raise HTTPException(404, f"no lexicon for language '{lang}'")


# ---------------------------------------------------------------- 1. operator review

class ReviewRequest(BaseModel):
    lang: str
    decision: str = Field(pattern="^(approve|reject)$")
    reviewer: str = Field(min_length=2, max_length=80)
    note: str = Field(default="", max_length=500)


@router.post("/alerts/{alert_id}/review", response_model=AlertOut)
def review(alert_id: str, req: ReviewRequest, background: BackgroundTasks) -> AlertOut:
    """A REVIEW language is never sent automatically. A named operator approves it
    (APPROVED, sendable) or rejects it (the verified safe fallback is sent instead, or
    nothing if the fallback cannot be verified). Every decision is audited."""
    a = load_alert(alert_id)
    r = next((x for x in a.results if x.lang == req.lang), None)
    if r is None:
        raise HTTPException(404, f"language '{req.lang}' is not part of this alert")
    if r.status != Status.REVIEW:
        raise HTTPException(409, f"only languages in REVIEW can be decided; {req.lang} is {r.status.value}")
    stamp = ReviewStamp(reviewer=req.reviewer.strip(), decision=req.decision, note=req.note.strip(),
                        at=datetime.now().astimezone().isoformat(timespec="seconds"))
    if req.decision == "approve":
        r.status = Status.APPROVED
        r.review = stamp
        r.reasons = r.reasons + [f"Approved for sending by {stamp.reviewer}" + (f": {stamp.note}" if stamp.note else "")]
        reason = r.reasons[-1]
    else:
        fb = safe_fallback(a.intent, a.mapping, r.lang)
        r.review = stamp
        rejected = f"Rejected by {stamp.reviewer}" + (f": {stamp.note}" if stamp.note else "")
        if fb is None:
            r.status, r.blocked_attempt, r.text, r.locked_text = Status.REJECTED, r.text, None, None
            r.reasons = r.reasons + [rejected, "The safe fallback also failed its checks, so nothing is sent"]
        else:
            text, locked, _ = fb
            r.blocked_attempt = r.text
            r.status, r.text, r.locked_text, r.renderer, r.fallback_used = Status.FALLBACK, text, locked, "safe_template", True
            r.reasons = r.reasons + [rejected, "Sent the pre-approved generic warning for this hazard instead"]
        reason = rejected
    db.update_results(alert_id, [x.model_dump(mode="json") for x in a.results])
    db.audit(alert_id, r.lang, "operator_review", r.status.value, reason)
    notify(background, "reviewed", alert_id)
    return load_alert(alert_id)


# ---------------------------------------------------------------- 2. cancel (Update is POST /compile with references)

class CancelRequest(BaseModel):
    reason: str = Field(default="", max_length=300)


@router.post("/alerts/{alert_id}/cancel", response_model=CompileResponse)
def cancel(alert_id: str, req: CancelRequest, background: BackgroundTasks) -> CompileResponse:
    """A CAP Cancel message, itself translated and verified in every language of the original:
    "The wildfire warning for Altadena has been cancelled." """
    prev = check_replaceable(alert_id)
    intent = AlertIntent(hazard=prev.intent.hazard, action=Action.ALL_CLEAR, urgency="future",
                         area_refs=list(dict.fromkeys(prev.intent.area_refs)),
                         instructions=[Instruction(verb="all_clear", negated=False)])
    en = render_template(intent, "en")
    if not en.ok:
        raise HTTPException(422, "no approved wording for this cancellation: " + "; ".join(en.uncovered))
    locked = en.text
    mapping = {p: prev.mapping[p] for p in dict.fromkeys(placeholders_in(locked)) if p in prev.mapping}
    langs = [r.lang for r in prev.results]
    results = compile_all(intent, locked, mapping, langs)
    source = restore(locked, mapping, "en")
    new_id = db.save_alert(source, locked, mapping, intent.model_dump(mode="json"), [r.model_dump(mode="json") for r in results],
                           None, msg_type="Cancel", references=alert_id,
                           area=prev.area.model_dump(mode="json") if prev.area else None)
    if req.reason.strip():
        db.audit(new_id, "*", "cancel", "CANCEL", f"Operator reason: {req.reason.strip()}")
    count_statuses(results)
    notify(background, "cancelled", new_id)
    return CompileResponse(alert_id=new_id, source_text=source, intent=intent, results=results,
                           msg_type="Cancel", references=alert_id)


# ---------------------------------------------------------------- 5. CAP validation

class CapValidateRequest(BaseModel):
    xml: str = Field(min_length=1, max_length=500_000)


@router.post("/validate/cap", response_model=CapReport)
def validate(req: CapValidateRequest) -> CapReport:
    return validate_cap(req.xml)


@router.get("/alerts/{alert_id}/cap.xml", response_class=Response, responses={200: {"content": {"application/xml": {}}}})
def cap_get(alert_id: str) -> Response:
    """Read-only CAP (status Exercise) for feeds and links. Not audited as an export."""
    return Response(cap_xml(load_alert(alert_id)), media_type="application/xml")


@router.get("/alerts/{alert_id}/cap/validate", response_model=CapReport)
def cap_validate_stored(alert_id: str) -> CapReport:
    return validate_cap(cap_xml(load_alert(alert_id)))


# ---------------------------------------------------------------- 6. exports, 22. SSML, 23. audit CSV

def _download(body: str, media: str, name: str) -> Response:
    return Response(body, media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/alerts/{alert_id}/export.json")
def export_json(alert_id: str) -> dict:
    return json_bundle(load_alert(alert_id).model_dump(mode="json"))


@router.get("/alerts/{alert_id}/export.txt", response_class=PlainTextResponse)
def export_txt(alert_id: str) -> Response:
    return _download(text_bundle(load_alert(alert_id).model_dump(mode="json")), "text/plain; charset=utf-8", f"stentor-{alert_id}.txt")


@router.get("/alerts/{alert_id}/export.csv", response_class=PlainTextResponse)
def export_csv(alert_id: str) -> Response:
    return _download(results_csv(load_alert(alert_id).model_dump(mode="json")), "text/csv; charset=utf-8", f"stentor-{alert_id}.csv")


@router.get("/alerts/{alert_id}/audit.csv", response_class=PlainTextResponse)
def export_audit(alert_id: str) -> Response:
    a = load_alert(alert_id)
    return _download(audit_csv(a.id, [x.model_dump() for x in a.audit]), "text/csv; charset=utf-8", f"stentor-{alert_id}-audit.csv")


@router.get("/alerts/{alert_id}/ssml", response_class=Response, responses={200: {"content": {"application/ssml+xml": {}}}})
def ssml(alert_id: str, lang: str = "en", repeat: int = Query(default=2, ge=1, le=3)) -> Response:
    a = load_alert(alert_id)
    if lang == "en":
        return Response(build_ssml(a.locked_text, a.mapping, "en", "en-US", repeat), media_type="application/ssml+xml")
    r = next((x for x in a.results if x.lang == lang), None)
    if r is None or r.status.value not in SENDABLE or not r.locked_text:
        raise HTTPException(404, f"no sendable text in '{lang}' for this alert")
    return Response(build_ssml(r.locked_text, a.mapping, lang, r.tts, repeat), media_type="application/ssml+xml")


# ---------------------------------------------------------------- 7. Atom feed

@router.get("/feed.atom", response_class=Response, responses={200: {"content": {"application/atom+xml": {}}}})
def feed(limit: int = Query(default=20, ge=1, le=100)) -> Response:
    entries = []
    for a in db.all_alerts():
        if a.chaos:  # demo corruption runs are not published
            continue
        results = json.loads(a.results_json)
        langs = [{"lang": "en", "text": a.source_text}] + [
            {"lang": r["lang"], "text": r["text"]} for r in results if r["status"] in SENDABLE and r.get("text")]
        entries.append({"id": a.id, "created_at": a.created_at, "title": a.source_text.split(". ")[0][:120],
                        "summary": a.source_text, "msg_type": a.msg_type or "Alert", "languages": langs})
        if len(entries) >= limit:
            break
    s = get_settings()
    return Response(build_feed(entries, s.public_base_url, s.api_public_url), media_type="application/atom+xml")


# ---------------------------------------------------------------- 8. batch

class BatchItem(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    langs: list[str] | None = None


class BatchRequest(BaseModel):
    items: list[BatchItem] = Field(min_length=1, max_length=20)
    langs: list[str] = Field(default_factory=lambda: list(TARGET_LANGS))


class BatchResult(BaseModel):
    text: str
    alert_id: str | None = None
    statuses: dict[str, str] = {}
    warnings: list[str] = []
    error: str | None = None


@router.post("/batch", response_model=list[BatchResult])
def batch(req: BatchRequest, background: BackgroundTasks) -> list[BatchResult]:
    """Prepare many alerts at once (e.g. a pre-scripted set for a season). Each is read,
    translated, verified and stored exactly as if compiled one by one. No chaos here."""
    check_langs(req.langs)
    out: list[BatchResult] = []
    glossary = db.glossary_terms()
    for item in req.items:
        try:
            langs = check_langs(item.langs or req.langs)
            ir = extract(item.text, glossary, tz=settings.stentor_tz)
            results = compile_all(ir.intent, ir.locked_text, ir.mapping, langs)
            source = restore(ir.locked_text, ir.mapping, "en")
            aid = db.save_alert(source, ir.locked_text, ir.mapping, ir.intent.model_dump(mode="json"),
                                [r.model_dump(mode="json") for r in results], None)
            db.audit(aid, "*", "batch", "CREATED", "compiled as part of a batch")
            count_statuses(results)
            notify(background, "compiled", aid)
            out.append(BatchResult(text=item.text, alert_id=aid, statuses={r.lang: r.status.value for r in results},
                                   warnings=ir.warnings + [i.message for i in ir.lint if i.severity == "warning"]))
        except HTTPException as e:
            out.append(BatchResult(text=item.text, error=str(e.detail)))
    return out


# ---------------------------------------------------------------- 9. drafts

class DraftIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=2000)
    langs: list[str] = []


class DraftOut(DraftIn):
    id: str
    created_at: str
    updated_at: str


def _draft_out(d: db.Draft) -> DraftOut:
    return DraftOut(id=d.id, name=d.name, text=d.text, langs=json.loads(d.langs_json),
                    created_at=d.created_at.isoformat(), updated_at=d.updated_at.isoformat())


@router.get("/drafts", response_model=list[DraftOut])
def drafts() -> list[DraftOut]:
    return [_draft_out(d) for d in sorted(db.list_rows(db.Draft), key=lambda d: d.updated_at, reverse=True)]


@router.post("/drafts", response_model=DraftOut, status_code=201)
def draft_create(req: DraftIn) -> DraftOut:
    if req.langs:
        check_langs(req.langs)
    return _draft_out(db.put_row(db.Draft(id=db.new_id(), name=req.name.strip(), text=req.text, langs_json=json.dumps(req.langs))))


@router.put("/drafts/{draft_id}", response_model=DraftOut)
def draft_update(draft_id: str, req: DraftIn) -> DraftOut:
    d = db.get_row(db.Draft, draft_id)
    if d is None:
        raise HTTPException(404, "draft not found")
    if req.langs:
        check_langs(req.langs)
    d.name, d.text, d.langs_json, d.updated_at = req.name.strip(), req.text, json.dumps(req.langs), db._now()
    return _draft_out(db.put_row(d))


@router.delete("/drafts/{draft_id}", status_code=204)
def draft_delete(draft_id: str) -> Response:
    if not db.delete_row(db.Draft, draft_id):
        raise HTTPException(404, "draft not found")
    return Response(status_code=204)


# ---------------------------------------------------------------- 10. language presets

class PresetIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    langs: list[str] = Field(min_length=1)


class PresetOut(PresetIn):
    id: str
    builtin: bool = False


def builtin_presets() -> list[PresetOut]:
    every = [lg for lg in available() if lg != "en"]
    return [PresetOut(id="builtin-prd", name="PRD demo set", langs=list(TARGET_LANGS), builtin=True),
            PresetOut(id="builtin-all", name="All languages", langs=every, builtin=True)]


@router.get("/presets", response_model=list[PresetOut])
def presets() -> list[PresetOut]:
    stored = [PresetOut(id=p.id, name=p.name, langs=json.loads(p.langs_json)) for p in db.list_rows(db.Preset, db.Preset.name)]
    return builtin_presets() + stored


@router.post("/presets", response_model=PresetOut, status_code=201)
def preset_create(req: PresetIn) -> PresetOut:
    langs = check_langs(req.langs)
    name = req.name.strip()
    if any(p.name.casefold() == name.casefold() for p in presets()):
        raise HTTPException(409, f"a preset named '{name}' already exists")
    p = db.put_row(db.Preset(id=db.new_id(), name=name, langs_json=json.dumps(langs)))
    return PresetOut(id=p.id, name=p.name, langs=langs)


@router.delete("/presets/{preset_id}", status_code=204)
def preset_delete(preset_id: str) -> Response:
    if preset_id.startswith("builtin-"):
        raise HTTPException(409, "built-in presets cannot be deleted")
    if not db.delete_row(db.Preset, preset_id):
        raise HTTPException(404, "preset not found")
    return Response(status_code=204)


# ---------------------------------------------------------------- 12. statistics

class Stats(BaseModel):
    alerts: int
    chaos_alerts: int
    languages_compiled: int
    by_status: dict[str, int]
    by_lang: dict[str, dict[str, int]]
    by_hazard: dict[str, int]
    by_msg_type: dict[str, int]
    top_block_reasons: list[tuple[str, int]]
    sendable_pct: float | None
    operator_reviews: int
    note: str


def _reason_kind(reason: str) -> str:
    for cut in (" (", ": source says"):
        if cut in reason:
            reason = reason.split(cut, 1)[0]
    return reason


@router.get("/stats", response_model=Stats)
def stats(include_chaos: bool = False) -> Stats:
    """Counts over alerts compiled on this server. Operational numbers, not eval results."""
    alerts = db.all_alerts()
    by_status: Counter = Counter()
    by_lang: dict[str, Counter] = defaultdict(Counter)
    by_hazard: Counter = Counter()
    by_msg: Counter = Counter()
    reasons: Counter = Counter()
    reviews = 0
    counted = 0
    chaos_n = sum(1 for a in alerts if a.chaos)
    for a in alerts:
        if a.chaos and not include_chaos:
            continue
        counted += 1
        by_hazard[json.loads(a.intent_json).get("hazard", "other")] += 1
        by_msg[a.msg_type or "Alert"] += 1
        for r in json.loads(a.results_json):
            by_status[r["status"]] += 1
            by_lang[r["lang"]][r["status"]] += 1
            if r.get("review"):
                reviews += 1
            if r["status"] in ("BLOCKED", "FALLBACK", "REJECTED"):
                for reason in r["reasons"]:
                    if not reason.startswith(("Sent the pre-approved", "The safe fallback", "Rejected by")):
                        reasons[_reason_kind(reason)] += 1
    total = sum(by_status.values())
    sendable = sum(v for k, v in by_status.items() if k in SENDABLE)
    return Stats(alerts=counted, chaos_alerts=chaos_n, languages_compiled=total, by_status=dict(by_status),
                 by_lang={k: dict(v) for k, v in sorted(by_lang.items())}, by_hazard=dict(by_hazard.most_common()),
                 by_msg_type=dict(by_msg), top_block_reasons=reasons.most_common(8),
                 sendable_pct=round(100 * sendable / total, 1) if total else None, operator_reviews=reviews,
                 note="Counts of alerts compiled on this server" + ("" if include_chaos else ", chaos demo runs excluded") + ".")


# ---------------------------------------------------------------- 13-15. lexicon tools

@router.get("/lexicon/{lang}", response_model=LexiconView)
def lexicon_view(lang: str) -> LexiconView:
    _lang_ok(lang)
    return explore(lang)


@router.get("/lexicon/{lang}/lint", response_model=LintReport)
def lexicon_lint(lang: str) -> LintReport:
    _lang_ok(lang)
    return lint(lang)


class SignoffIn(BaseModel):
    reviewer: str = Field(min_length=2, max_length=80)
    note: str = Field(default="", max_length=500)
    native_speaker: bool = Field(description="the reviewer confirms they are a native speaker")


class SignoffOut(BaseModel):
    lang: str
    reviewer: str
    note: str
    created_at: str


@router.get("/lexicon/{lang}/signoffs", response_model=list[SignoffOut])
def lexicon_signoffs(lang: str) -> list[SignoffOut]:
    _lang_ok(lang)
    return [SignoffOut(lang=s.lang, reviewer=s.reviewer, note=s.note, created_at=s.created_at.isoformat()) for s in db.signoffs(lang)]


@router.post("/lexicon/{lang}/signoff", response_model=SignoffOut, status_code=201)
def lexicon_signoff(lang: str, req: SignoffIn) -> SignoffOut:
    """Record that a native speaker checked this lexicon. The lexicon must lint clean first:
    signing off a lexicon that cannot read its own templates back would be meaningless."""
    _lang_ok(lang)
    if not req.native_speaker:
        raise HTTPException(422, "only a native speaker can sign off a lexicon")
    report = lint(lang)
    if not report.ok:
        raise HTTPException(409, f"lexicon has {report.errors} lint error(s); fix them before signing off")
    s = db.put_row(db.LexiconSignoff(lang=lang, reviewer=req.reviewer.strip(), note=req.note.strip()))
    db.audit("lexicon", lang, "lexicon_signoff", "SIGNED_OFF", f"{s.reviewer} signed off the {meta(lang)['english_name']} lexicon")
    return SignoffOut(lang=lang, reviewer=s.reviewer, note=s.note, created_at=db._utc(s.created_at).isoformat())


# ---------------------------------------------------------------- 17. intent lint for an edited intent card

class LintRequest(BaseModel):
    intent: AlertIntent
    mapping: dict[str, str]
    locked_text: str | None = None


@router.post("/intent/lint", response_model=list[LintIssue])
def intent_lint(req: LintRequest) -> list[LintIssue]:
    return lint_intent(req.intent, req.mapping, req.locked_text, tz=settings.stentor_tz)


# ---------------------------------------------------------------- 18. glossary

class GlossaryIn(BaseModel):
    term: str = Field(min_length=2, max_length=60, pattern=r"^[^⟦⟧]+$")
    note: str = Field(default="", max_length=200)


class GlossaryOut(GlossaryIn):
    id: str


@router.get("/glossary", response_model=list[GlossaryOut])
def glossary() -> list[GlossaryOut]:
    return [GlossaryOut(id=g.id, term=g.term, note=g.note) for g in db.list_rows(db.GlossaryTerm, db.GlossaryTerm.term)]


@router.post("/glossary", response_model=GlossaryOut, status_code=201)
def glossary_add(req: GlossaryIn) -> GlossaryOut:
    term = req.term.strip()
    if any(g.term.casefold() == term.casefold() for g in db.list_rows(db.GlossaryTerm)):
        raise HTTPException(409, f"'{term}' is already in the glossary")
    g = db.put_row(db.GlossaryTerm(id=db.new_id(), term=term, note=req.note.strip()))
    return GlossaryOut(id=g.id, term=g.term, note=g.note)


@router.delete("/glossary/{term_id}", status_code=204)
def glossary_delete(term_id: str) -> Response:
    if not db.delete_row(db.GlossaryTerm, term_id):
        raise HTTPException(404, "term not found")
    return Response(status_code=204)


# ---------------------------------------------------------------- 24. webhooks

class WebhookIn(BaseModel):
    url: str = Field(min_length=8, max_length=500)


class WebhookOut(BaseModel):
    id: str
    url: str
    active: bool
    created_at: str
    secret: str | None = None  # returned once, at creation


@router.get("/webhooks", response_model=list[WebhookOut])
def webhook_list() -> list[WebhookOut]:
    return [WebhookOut(id=h.id, url=h.url, active=h.active, created_at=h.created_at.isoformat()) for h in db.list_rows(db.Webhook)]


@router.post("/webhooks", response_model=WebhookOut, status_code=201)
def webhook_add(req: WebhookIn) -> WebhookOut:
    if not webhooks.valid_url(req.url):
        raise HTTPException(422, "webhook URL must be http(s)://host/...")
    h = db.put_row(db.Webhook(id=db.new_id(), url=req.url, secret=webhooks.new_secret()))
    return WebhookOut(id=h.id, url=h.url, active=h.active, created_at=h.created_at.isoformat(), secret=h.secret)


@router.delete("/webhooks/{hook_id}", status_code=204)
def webhook_delete(hook_id: str) -> Response:
    if not db.delete_row(db.Webhook, hook_id):
        raise HTTPException(404, "webhook not found")
    return Response(status_code=204)


@router.post("/webhooks/test")
def webhook_test() -> list[dict]:
    """Send a signed test event to every active webhook, now, and report each result."""
    return webhooks.deliver("test", "webhook-test", {"message": "STENTOR webhook test. Not an alert."})


# ---------------------------------------------------------------- 29. metrics

@router.get("/metrics", response_class=PlainTextResponse)
def metrics() -> str:
    return middleware.METRICS.render()
