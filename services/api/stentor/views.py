"""Stored alert views shared by the API modules."""
from __future__ import annotations

import json

from fastapi import HTTPException
from pydantic import BaseModel

from stentor import db
from stentor.channels.geo import CapArea
from stentor.intent.schema import AlertIntent
from stentor.pipeline import LangResult


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
    msg_type: str = "Alert"
    references: str | None = None
    superseded_by: str | None = None
    area: CapArea | None = None


def load_alert(alert_id: str) -> AlertOut:
    found = db.get_alert(alert_id)
    if not found:
        raise HTTPException(404, "alert not found")
    a, recs = found
    return AlertOut(
        id=a.id, created_at=a.created_at.isoformat(), source_text=a.source_text, locked_text=a.locked_text,
        mapping=json.loads(a.mapping_json), intent=AlertIntent.model_validate_json(a.intent_json),
        results=[LangResult.model_validate(r) for r in json.loads(a.results_json)], chaos=a.chaos,
        audit=[AuditOut(created_at=r.created_at.isoformat(), lang=r.lang, event=r.event, status=r.status, reason=r.reason) for r in recs],
        msg_type=a.msg_type or "Alert", references=a.references, superseded_by=a.superseded_by,
        area=CapArea.model_validate_json(a.area_json) if a.area_json else None,
    )
