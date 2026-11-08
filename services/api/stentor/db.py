"""SQLite storage: alerts and the audit log."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from sqlmodel import Field, Session, SQLModel, create_engine, select

DB_PATH = Path(__file__).resolve().parents[1] / "stentor.db"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Alert(SQLModel, table=True):
    id: str = Field(primary_key=True)
    created_at: datetime = Field(default_factory=_now)
    source_text: str
    locked_text: str
    mapping_json: str
    intent_json: str
    results_json: str
    chaos: str | None = None


class AuditRecord(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    alert_id: str = Field(index=True)
    created_at: datetime = Field(default_factory=_now)
    lang: str
    event: str
    status: str
    reason: str


@lru_cache
def engine():
    import os

    url = os.environ.get("STENTOR_DB_URL", f"sqlite:///{DB_PATH}")
    kwargs: dict = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {}
    if url == "sqlite://":  # in-memory (tests): one shared connection
        from sqlalchemy.pool import StaticPool

        kwargs["poolclass"] = StaticPool
    eng = create_engine(url, **kwargs)
    SQLModel.metadata.create_all(eng)
    return eng


def save_alert(source_text: str, locked_text: str, mapping: dict, intent: dict, results: list[dict], chaos: str | None) -> str:
    alert_id = uuid.uuid4().hex[:10]
    with Session(engine()) as s:
        s.add(Alert(id=alert_id, source_text=source_text, locked_text=locked_text,
                    mapping_json=json.dumps(mapping, ensure_ascii=False),
                    intent_json=json.dumps(intent, ensure_ascii=False),
                    results_json=json.dumps(results, ensure_ascii=False), chaos=chaos))
        for r in results:
            for reason in r["reasons"]:
                s.add(AuditRecord(alert_id=alert_id, lang=r["lang"], event="verification", status=r["status"], reason=reason))
            for note in r["notes"]:
                s.add(AuditRecord(alert_id=alert_id, lang=r["lang"], event="render", status=r["status"], reason=note))
        s.commit()
    return alert_id


def audit(alert_id: str, lang: str, event: str, status: str, reason: str) -> None:
    with Session(engine()) as s:
        s.add(AuditRecord(alert_id=alert_id, lang=lang, event=event, status=status, reason=reason))
        s.commit()


def get_alert(alert_id: str) -> tuple[Alert, list[AuditRecord]] | None:
    with Session(engine()) as s:
        a = s.get(Alert, alert_id)
        if a is None:
            return None
        recs = list(s.exec(select(AuditRecord).where(AuditRecord.alert_id == alert_id).order_by(AuditRecord.id)))
        s.expunge_all()
        return a, recs
