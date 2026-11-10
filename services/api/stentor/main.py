"""FastAPI entrypoint: `uv run uvicorn stentor.main:app --reload --port 8000`."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

from stentor import __version__, db, llm, middleware, webhooks
from stentor.channels.cap import ALLOWED_STATUSES, _expires, build_cap
from stentor.channels.exports import json_bundle
from stentor.channels.geo import CapArea
from stentor.config import get_settings
from stentor.examples import EXAMPLES
from stentor.intent.extract import IntentResult, extract
from stentor.intent.schema import AlertIntent
from stentor.lexicon import TARGET_LANGS, available, meta
from stentor.lexicon import load as load_lexicon
from stentor.lock import placeholders_in, restore
from stentor.pipeline import LangResult, compile_all
from stentor.verify.chaos import CORRUPTIONS, parse_chaos
from stentor.verify.diff import SENDABLE
from stentor.views import AlertOut, AuditOut, load_alert  # noqa: F401 (AuditOut re-exported)

settings = get_settings()
EVAL_RESULTS = Path(__file__).resolve().parents[3] / "eval" / "results"

app = FastAPI(title="STENTOR API", version=__version__,
              description="Verified multilingual emergency alert compiler")
middleware.install(app, get_settings)  # before CORS, so CORS stays outermost
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Health(BaseModel):
    status: str
    version: str
    renderer: str
    anthropic_configured: bool
    llm_provider: str = "none"  # anthropic | gemini | none
    adaption_configured: bool
    auth_required: bool = False


@app.get("/health", response_model=Health)
def health() -> Health:
    # Report whether keys are present, never their values.
    return Health(
        status="ok",
        version=__version__,
        renderer=settings.stentor_renderer,
        anthropic_configured=bool(settings.anthropic_api_key),
        llm_provider=llm.provider(),
        adaption_configured=bool(settings.adaption_api_key),
        auth_required=bool(get_settings().stentor_operator_token),
    )


class LanguageInfo(BaseModel):
    lang: str
    name: str
    english_name: str
    dir: str
    tts: str
    reviewed_by: str
    approved: bool
    negation_markers: list[str] = []
    evacuate_phrase: str = ""
    sample_prohibition: str = ""
    signed_off_by: list[str] = []  # native speakers who signed off this lexicon (newest last)


class Example(BaseModel):
    id: str
    label: str
    text: str


class Phrasebook(BaseModel):
    """English wording of every approved template, so the intent card can show each
    instruction as the sentence it will become."""
    actions: dict[str, dict[str, str]]
    instructions: dict[str, dict[str, str]]


class Meta(BaseModel):
    languages: list[LanguageInfo]
    default_langs: list[str]
    examples: list[Example]
    corruptions: list[str]
    backparser: str
    extractor: str
    phrasebook: Phrasebook
    instruction_count: int


def _language_info(lg: str) -> LanguageInfo:
    lx = load_lexicon(lg)
    return LanguageInfo(
        **meta(lg),
        negation_markers=lx.negation_markers,
        evacuate_phrase=lx.actions["evacuate_now"]["text"][""],
        sample_prohibition=lx.instructions["use:elevators"]["text"]["neg"],
        signed_off_by=list(dict.fromkeys(so.reviewer for so in db.signoffs(lg))),
    )


@app.get("/meta", response_model=Meta)
def get_meta() -> Meta:
    return Meta(
        languages=[_language_info(lg) for lg in available() if lg != "en"],
        default_langs=TARGET_LANGS,
        examples=[Example(**e) for e in EXAMPLES],
        corruptions=list(CORRUPTIONS),
        backparser=llm.BACKPARSE_MODEL if llm.available() else "lexicon",
        extractor=llm.EXTRACT_MODEL if llm.available() else "lexicon",
        phrasebook=Phrasebook(
            actions={a: spec["text"] for a, spec in load_lexicon("en").actions.items()},
            instructions={k: spec["text"] for k, spec in load_lexicon("en").instructions.items()},
        ),
        instruction_count=len(load_lexicon("en").instructions),
    )


class IntentRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


@app.post("/intent", response_model=IntentResult)
def post_intent(req: IntentRequest) -> IntentResult:
    return extract(req.text, db.glossary_terms(), tz=get_settings().stentor_tz)


class CompileRequest(BaseModel):
    intent: AlertIntent
    locked_text: str
    mapping: dict[str, str]
    langs: list[str] = Field(default_factory=lambda: list(TARGET_LANGS))
    source_text: str | None = None
    references: str | None = Field(default=None, description="alert id this one updates (CAP msgType Update)")
    area: CapArea | None = None


class CompileResponse(BaseModel):
    alert_id: str
    source_text: str
    intent: AlertIntent
    results: list[LangResult]
    chaos: str | None = None
    msg_type: str = "Alert"
    references: str | None = None
    duplicate_of: str | None = None  # same English text compiled recently


def check_langs(langs_in: list[str]) -> list[str]:
    langs = list(dict.fromkeys(langs_in))  # duplicates would mean duplicate CAP <info> blocks
    if not langs:
        raise HTTPException(422, "choose at least one language")
    known = set(available())
    bad = [lg for lg in langs if lg not in known or lg == "en"]
    if bad:
        raise HTTPException(422, f"unsupported languages: {', '.join(bad)}")
    return langs


def check_replaceable(alert_id: str) -> AlertOut:
    """An Update or Cancel may only replace a live alert."""
    prev = load_alert(alert_id)
    if prev.msg_type == "Cancel":
        raise HTTPException(409, "this alert is a cancellation; it cannot be updated or cancelled")
    if prev.superseded_by:
        raise HTTPException(409, f"this alert was already replaced by {prev.superseded_by}; work on that one")
    return prev


def notify(background: BackgroundTasks, event: str, alert_id: str) -> None:
    if not db.list_rows(db.Webhook):
        return
    background.add_task(lambda: webhooks.deliver(event, alert_id, json_bundle(load_alert(alert_id).model_dump(mode="json"))))


def count_statuses(results: list[LangResult]) -> None:
    for r in results:
        middleware.METRICS.inc("stentor_languages_total", status=r.status.value, lang=r.lang)


@app.post("/compile", response_model=CompileResponse)
def post_compile(req: CompileRequest, background: BackgroundTasks,
                 chaos: str | None = Query(default=None, description="e.g. drop_negation:ar")) -> CompileResponse:
    langs = check_langs(req.langs)
    if req.references:
        check_replaceable(req.references)
    unknown_ph = [p for p in placeholders_in(req.locked_text) if p not in req.mapping]
    if unknown_ph:
        raise HTTPException(422, f"placeholders without a mapping: {', '.join(unknown_ph)}")
    try:
        chaos_map = parse_chaos(chaos)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    stray = [lg for lg in chaos_map if lg != "*" and lg not in langs]
    if stray:
        raise HTTPException(422, f"chaos targets a language that is not being compiled: {', '.join(stray)}")
    results = compile_all(req.intent, req.locked_text, req.mapping, langs, chaos_map)
    # The English text that is stored, exported to CAP and shown publicly is always the
    # one that was verified: rebuilt from the locked text, never taken from the client.
    source_text = restore(req.locked_text, req.mapping, "en")
    duplicate = db.find_duplicate(source_text, timedelta(minutes=get_settings().stentor_duplicate_minutes))
    msg_type = "Update" if req.references else "Alert"
    alert_id = db.save_alert(source_text, req.locked_text, req.mapping, req.intent.model_dump(mode="json"),
                             [r.model_dump(mode="json") for r in results], chaos, msg_type=msg_type,
                             references=req.references, area=req.area.model_dump(mode="json") if req.area and (req.area.desc or not req.area.empty()) else None)
    if duplicate and not req.references:
        db.audit(alert_id, "*", "duplicate", "WARNING", f"same English text as alert {duplicate}, compiled recently")
    count_statuses(results)
    if not chaos:  # chaos runs are demos; never push them downstream
        notify(background, "compiled", alert_id)
    return CompileResponse(alert_id=alert_id, source_text=source_text, intent=req.intent, results=results, chaos=chaos,
                           msg_type=msg_type, references=req.references, duplicate_of=None if req.references else duplicate)


class AlertSummary(BaseModel):
    id: str
    created_at: str
    source_text: str
    chaos: str | None
    hazard: str | None
    action: str | None
    msg_type: str
    references: str | None
    superseded_by: str | None
    statuses: dict[str, str]


@app.get("/alerts", response_model=list[AlertSummary])
def list_alerts(response: Response, limit: int = Query(default=10, ge=1, le=100), offset: int = Query(default=0, ge=0),
                q: str | None = Query(default=None, max_length=200), hazard: str | None = None,
                status: str | None = Query(default=None, description="any language with this status"),
                lang: str | None = None, msg_type: str | None = None, chaos: bool | None = None) -> list[AlertSummary]:
    """Newest first. The total number of matches is in the X-Total-Count header."""
    items = [db.summary(a) for a in db.all_alerts()]
    if q:
        needle = q.casefold()
        items = [i for i in items if needle in i["source_text"].casefold() or needle == i["id"]]
    if hazard:
        items = [i for i in items if i["hazard"] == hazard]
    if lang:
        items = [i for i in items if lang in i["statuses"]]
    if status:
        items = [i for i in items if (i["statuses"].get(lang) == status if lang else status in i["statuses"].values())]
    if msg_type:
        items = [i for i in items if i["msg_type"] == msg_type]
    if chaos is not None:
        items = [i for i in items if bool(i["chaos"]) == chaos]
    response.headers["X-Total-Count"] = str(len(items))
    return [AlertSummary(**i) for i in items[offset: offset + limit]]


def _load(alert_id: str) -> AlertOut:
    return load_alert(alert_id)


@app.get("/alerts/{alert_id}", response_model=AlertOut)
def get_alert(alert_id: str) -> AlertOut:
    return _load(alert_id)


class CapRequest(BaseModel):
    alert_id: str
    status: Literal["Exercise", "System", "Test", "Draft", "Actual"] = "Exercise"
    sender: str = Field(default="stentor-demo@example.org", min_length=3, max_length=120, pattern=r"^[^\s,<&]+$")
    sender_name: str = Field(default="STENTOR demo operator", min_length=1, max_length=120)


def cap_xml(a: AlertOut, status: str = "Exercise", sender: str = "stentor-demo@example.org",
            sender_name: str = "STENTOR demo operator") -> str:
    refs = None
    if a.references:
        found = db.get_alert(a.references)
        if found:
            refs = [(sender, a.references, found[0].created_at)]
    return build_cap(a.id, a.intent, a.mapping, a.source_text, [r.model_dump(mode="json") for r in a.results],
                     sent=datetime.fromisoformat(a.created_at), status=status, sender=sender, sender_name=sender_name,
                     tz=ZoneInfo(settings.stentor_tz), web=f"{settings.public_base_url.rstrip('/')}/a/{a.id}",
                     msg_type=a.msg_type, references=refs, area=a.area)


@app.post("/export/cap", response_class=Response, responses={200: {"content": {"application/xml": {}}}})
def export_cap(req: CapRequest) -> Response:
    if req.status not in ALLOWED_STATUSES:
        raise HTTPException(422, "STENTOR is not certified for production alerting; CAP status Actual is refused. "
                                 f"Use one of: {', '.join(ALLOWED_STATUSES)}")
    a = _load(req.alert_id)
    xml = cap_xml(a, req.status, req.sender, req.sender_name)
    included = [r.lang for r in a.results if r.status.value in SENDABLE]
    db.audit(a.id, "*", "export_cap", "EXPORTED",
             f"CAP 1.2 ({req.status}, {a.msg_type}) exported with languages: en, {', '.join(included) or 'none'}")
    return Response(xml, media_type="application/xml",
                    headers={"Content-Disposition": f'attachment; filename="stentor-{a.id}.cap.xml"'})


class PublicLang(BaseModel):
    lang: str
    name: str
    dir: str
    tts: str
    status: str
    text: str


class PublicAlert(BaseModel):
    id: str
    created_at: str
    hazard: str
    action: str
    intent: AlertIntent
    places: list[str]
    times: list[str]
    languages: list[PublicLang]
    selected: PublicLang
    msg_type: str = "Alert"
    expires_at: str | None = None  # CAP style dateTime, when the alert stops applying
    expired: bool = False
    superseded_by: str | None = None  # a newer Update or Cancel exists; show that one


@app.get("/public/{alert_id}", response_model=PublicAlert)
def public(alert_id: str, lang: str = "en", now: datetime | None = None) -> PublicAlert:
    a = _load(alert_id)
    langs = [PublicLang(lang="en", name="English", dir="ltr", tts="en-US", status="SOURCE", text=a.source_text.replace("⟦", "").replace("⟧", ""))]
    # Only sendable languages are ever shown to the public.
    langs += [PublicLang(lang=r.lang, name=r.name, dir=r.dir, tts=r.tts, status=r.status.value, text=r.text)
              for r in a.results if r.status.value in SENDABLE and r.text]
    selected = next((x for x in langs if x.lang == lang), langs[0])
    sent = datetime.fromisoformat(a.created_at).astimezone(ZoneInfo(settings.stentor_tz))
    expires_at = _expires(a.intent, a.mapping, sent)
    expired = bool(expires_at) and datetime.fromisoformat(expires_at) <= (now or datetime.now(timezone.utc))
    return PublicAlert(
        id=a.id, created_at=a.created_at, hazard=a.intent.hazard.value, action=a.intent.action.value, intent=a.intent,
        places=[a.mapping[p] for p in dict.fromkeys(a.intent.area_refs) if p in a.mapping],
        times=[a.mapping[p] for p in dict.fromkeys(a.intent.time_refs) if p in a.mapping],
        languages=langs, selected=selected, msg_type=a.msg_type, expires_at=expires_at, expired=expired,
        superseded_by=a.superseded_by,
    )


class EvalRequest(BaseModel):
    langs: list[str] = Field(default_factory=lambda: [lg for lg in available() if lg != "en"])
    suites: list[str] = Field(default_factory=lambda: ["clean", "realistic"])


@app.post("/eval/run")
def eval_run(req: EvalRequest) -> dict:
    from stentor.evaluation import SUITES, run_eval

    bad = [lg for lg in req.langs if lg not in available() or lg == "en"] + [s for s in req.suites if s not in SUITES]
    if bad or not req.langs or not req.suites:
        raise HTTPException(422, f"unknown languages or suites: {', '.join(bad) or 'none given'}")
    if llm.available():
        raise HTTPException(409, "with an API key the eval calls Claude for every case; run eval/run_eval.py from the terminal instead")
    result = run_eval(req.langs, EVAL_RESULTS / "latest.json", req.suites)
    s = result["summary"]
    return {k: v for k, v in s.items() if k != "suites"}


@app.get("/eval/latest")
def eval_latest() -> dict:
    path = EVAL_RESULTS / "latest.json"
    if not path.exists():
        raise HTTPException(404, "no eval results yet; run eval/run_eval.py")
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/eval/renderers")
def eval_renderers() -> list[dict]:
    """Baseline LLM vs Adaption model, from eval runs with --force-model. Empty until measured."""
    out = []
    for path in sorted(EVAL_RESULTS.glob("renderer-*.json")):
        d = json.loads(path.read_text(encoding="utf-8"))
        s = d["summary"]
        name = path.stem.removeprefix("renderer-")
        out.append({
            "renderer": name,
            "generated_at": d["meta"]["generated_at"],
            "slot_match_pct": s["slot_match_by_renderer_pct"].get(name),
            "placeholder_survival_pct": s["placeholder_survival_pct"],
            "false_block_rate_pct": s["false_block_rate_pct"],
            "catch_rate_pct": s["catch_rate_pct"],
            "clean_cases": s["clean_cases"],
        })
    return out


from stentor.routes import router as _router  # noqa: E402  (routes import from this module)

app.include_router(_router)
