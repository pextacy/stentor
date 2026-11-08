"""FastAPI entrypoint: `uv run uvicorn stentor.main:app --reload --port 8000`."""
from __future__ import annotations

import json
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

from stentor import __version__, db, llm
from stentor.channels.cap import build_cap
from stentor.config import get_settings
from stentor.examples import EXAMPLES
from stentor.intent.extract import IntentResult, extract
from stentor.intent.schema import AlertIntent
from stentor.lexicon import TARGET_LANGS, available, meta
from stentor.lock import placeholders_in
from stentor.pipeline import LangResult, compile_all
from stentor.verify.chaos import CORRUPTIONS, parse_chaos

settings = get_settings()
EVAL_RESULTS = Path(__file__).resolve().parents[3] / "eval" / "results"

app = FastAPI(title="STENTOR API", version=__version__,
              description="Verified multilingual emergency alert compiler")
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
    adaption_configured: bool


@app.get("/health", response_model=Health)
def health() -> Health:
    # Report whether keys are present, never their values.
    return Health(
        status="ok",
        version=__version__,
        renderer=settings.stentor_renderer,
        anthropic_configured=bool(settings.anthropic_api_key),
        adaption_configured=bool(settings.adaption_api_key),
    )


class LanguageInfo(BaseModel):
    lang: str
    name: str
    english_name: str
    dir: str
    tts: str
    reviewed_by: str
    approved: bool


class Example(BaseModel):
    id: str
    label: str
    text: str


class Meta(BaseModel):
    languages: list[LanguageInfo]
    default_langs: list[str]
    examples: list[Example]
    corruptions: list[str]
    backparser: str
    extractor: str


@app.get("/meta", response_model=Meta)
def get_meta() -> Meta:
    return Meta(
        languages=[LanguageInfo(**meta(lg)) for lg in available() if lg != "en"],
        default_langs=TARGET_LANGS,
        examples=[Example(**e) for e in EXAMPLES],
        corruptions=list(CORRUPTIONS),
        backparser=llm.BACKPARSE_MODEL if llm.available() else "lexicon",
        extractor=llm.EXTRACT_MODEL if llm.available() else "lexicon",
    )


class IntentRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


@app.post("/intent", response_model=IntentResult)
def post_intent(req: IntentRequest) -> IntentResult:
    return extract(req.text)


class CompileRequest(BaseModel):
    intent: AlertIntent
    locked_text: str
    mapping: dict[str, str]
    langs: list[str] = Field(default_factory=lambda: list(TARGET_LANGS))
    source_text: str | None = None


class CompileResponse(BaseModel):
    alert_id: str
    source_text: str
    intent: AlertIntent
    results: list[LangResult]
    chaos: str | None = None


@app.post("/compile", response_model=CompileResponse)
def post_compile(req: CompileRequest, chaos: str | None = Query(default=None, description="e.g. drop_negation:ar")) -> CompileResponse:
    known = set(available())
    bad = [lg for lg in req.langs if lg not in known or lg == "en"]
    if bad:
        raise HTTPException(422, f"unsupported languages: {', '.join(bad)}")
    unknown_ph = [p for p in placeholders_in(req.locked_text) if p not in req.mapping]
    if unknown_ph:
        raise HTTPException(422, f"placeholders without a mapping: {', '.join(unknown_ph)}")
    try:
        chaos_map = parse_chaos(chaos)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    results = compile_all(req.intent, req.locked_text, req.mapping, req.langs, chaos_map)
    source_text = req.source_text or req.locked_text
    alert_id = db.save_alert(source_text, req.locked_text, req.mapping, req.intent.model_dump(mode="json"),
                             [r.model_dump(mode="json") for r in results], chaos)
    return CompileResponse(alert_id=alert_id, source_text=source_text, intent=req.intent, results=results, chaos=chaos)


class AuditOut(BaseModel):
    created_at: str
    lang: str
    event: str
    status: str
    reason: str


class AlertOut(BaseModel):
    id: str
    created_at: str
    source_text: str
    locked_text: str
    mapping: dict[str, str]
    intent: AlertIntent
    results: list[LangResult]
    chaos: str | None
    audit: list[AuditOut]


def _load(alert_id: str) -> AlertOut:
    found = db.get_alert(alert_id)
    if not found:
        raise HTTPException(404, "alert not found")
    a, recs = found
    return AlertOut(
        id=a.id, created_at=a.created_at.isoformat(), source_text=a.source_text, locked_text=a.locked_text,
        mapping=json.loads(a.mapping_json), intent=AlertIntent.model_validate_json(a.intent_json),
        results=[LangResult.model_validate(r) for r in json.loads(a.results_json)], chaos=a.chaos,
        audit=[AuditOut(created_at=r.created_at.isoformat(), lang=r.lang, event=r.event, status=r.status, reason=r.reason) for r in recs],
    )


@app.get("/alerts/{alert_id}", response_model=AlertOut)
def get_alert(alert_id: str) -> AlertOut:
    return _load(alert_id)


class CapRequest(BaseModel):
    alert_id: str


@app.post("/export/cap", response_class=Response, responses={200: {"content": {"application/xml": {}}}})
def export_cap(req: CapRequest) -> Response:
    a = _load(req.alert_id)
    xml = build_cap(a.id, a.intent, a.mapping, a.source_text, [r.model_dump(mode="json") for r in a.results],
                    tz=ZoneInfo(settings.stentor_tz))
    included = [r.lang for r in a.results if r.status in ("VERIFIED", "FALLBACK")]
    db.audit(a.id, "*", "export_cap", "EXPORTED", f"CAP 1.2 exported with languages: en, {', '.join(included) or 'none'}")
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


@app.get("/public/{alert_id}", response_model=PublicAlert)
def public(alert_id: str, lang: str = "en") -> PublicAlert:
    a = _load(alert_id)
    langs = [PublicLang(lang="en", name="English", dir="ltr", tts="en-US", status="SOURCE", text=a.source_text.replace("⟦", "").replace("⟧", ""))]
    # Only sendable languages are ever shown to the public.
    langs += [PublicLang(lang=r.lang, name=r.name, dir=r.dir, tts=r.tts, status=r.status.value, text=r.text)
              for r in a.results if r.status.value in ("VERIFIED", "FALLBACK") and r.text]
    selected = next((x for x in langs if x.lang == lang), langs[0])
    return PublicAlert(
        id=a.id, created_at=a.created_at, hazard=a.intent.hazard.value, action=a.intent.action.value, intent=a.intent,
        places=[a.mapping[p] for p in dict.fromkeys(a.intent.area_refs) if p in a.mapping],
        times=[a.mapping[p] for p in dict.fromkeys(a.intent.time_refs) if p in a.mapping],
        languages=langs, selected=selected,
    )


class EvalRequest(BaseModel):
    langs: list[str] = Field(default_factory=lambda: list(TARGET_LANGS))
    suite: str = "all"


@app.post("/eval/run")
def eval_run(req: EvalRequest) -> dict:
    from stentor.evaluation import run_eval

    summary = run_eval(req.langs, EVAL_RESULTS / "latest.json")
    return summary["summary"]


@app.get("/eval/latest")
def eval_latest() -> dict:
    path = EVAL_RESULTS / "latest.json"
    if not path.exists():
        raise HTTPException(404, "no eval results yet; run eval/run_eval.py")
    return json.loads(path.read_text(encoding="utf-8"))
