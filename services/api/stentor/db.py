"""SQLite storage: alerts, the audit log, and operator data (drafts, presets, glossary,
webhooks, lexicon sign-offs)."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from sqlalchemy import inspect, text
from sqlmodel import Field, Session, SQLModel, create_engine, select

DB_PATH = Path(__file__).resolve().parents[1] / "stentor.db"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc(dt: datetime) -> datetime:
    # SQLite drops tzinfo; every stored datetime is UTC.
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class Alert(SQLModel, table=True):
    id: str = Field(primary_key=True)
    created_at: datetime = Field(default_factory=_now)
    source_text: str
    locked_text: str
    mapping_json: str
    intent_json: str
    results_json: str
    chaos: str | None = None
    msg_type: str = "Alert"  # CAP msgType: Alert | Update | Cancel
    references: str | None = None  # id of the alert this one updates or cancels
    area_json: str | None = None  # optional CAP geometry (polygons, circles, geocodes)
    superseded_by: str | None = None  # set when a later Update or Cancel references this alert


class AuditRecord(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    alert_id: str = Field(index=True)
    created_at: datetime = Field(default_factory=_now)
    lang: str
    event: str
    status: str
    reason: str


class Draft(SQLModel, table=True):
    id: str = Field(primary_key=True)
    name: str
    text: str
    langs_json: str = "[]"
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class Preset(SQLModel, table=True):
    id: str = Field(primary_key=True)
    name: str = Field(index=True, unique=True)
    langs_json: str
    created_at: datetime = Field(default_factory=_now)


class GlossaryTerm(SQLModel, table=True):
    id: str = Field(primary_key=True)
    term: str = Field(index=True, unique=True)
    note: str = ""
    created_at: datetime = Field(default_factory=_now)


class LexiconSignoff(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    lang: str = Field(index=True)
    reviewer: str
    note: str = ""
    created_at: datetime = Field(default_factory=_now)


class Webhook(SQLModel, table=True):
    id: str = Field(primary_key=True)
    url: str
    secret: str
    active: bool = True
    created_at: datetime = Field(default_factory=_now)


def _migrate(eng) -> None:
    """Add columns introduced after a database was created (SQLite has no create_all for columns)."""
    insp = inspect(eng)
    for table in SQLModel.metadata.sorted_tables:
        if not insp.has_table(table.name):
            continue
        have = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name in have:
                continue
            ddl_type = col.type.compile(dialect=eng.dialect)
            default = col.default.arg if col.default is not None and not callable(col.default.arg) else None
            clause = f" DEFAULT {json.dumps(default) if isinstance(default, str) else int(default)}" if default is not None else ""
            with eng.begin() as conn:
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {ddl_type}{clause}'))


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
    _migrate(eng)
    return eng


def session() -> Session:
    return Session(engine(), expire_on_commit=False)


def new_id() -> str:
    return uuid.uuid4().hex[:10]


# ---------------------------------------------------------------- alerts

def save_alert(source_text: str, locked_text: str, mapping: dict, intent: dict, results: list[dict], chaos: str | None,
               msg_type: str = "Alert", references: str | None = None, area: dict | None = None) -> str:
    alert_id = new_id()
    with session() as s:
        s.add(Alert(id=alert_id, source_text=source_text, locked_text=locked_text,
                    mapping_json=json.dumps(mapping, ensure_ascii=False),
                    intent_json=json.dumps(intent, ensure_ascii=False),
                    results_json=json.dumps(results, ensure_ascii=False), chaos=chaos,
                    msg_type=msg_type, references=references,
                    area_json=json.dumps(area, ensure_ascii=False) if area else None))
        for r in results:
            for reason in r["reasons"]:
                s.add(AuditRecord(alert_id=alert_id, lang=r["lang"], event="verification", status=r["status"], reason=reason))
            for note in r["notes"]:
                s.add(AuditRecord(alert_id=alert_id, lang=r["lang"], event="render", status=r["status"], reason=note))
        if references:
            prev = s.get(Alert, references)
            if prev is not None:
                prev.superseded_by = alert_id
                s.add(prev)
                s.add(AuditRecord(alert_id=references, lang="*", event=msg_type.lower(), status=msg_type.upper(),
                                  reason=f"{msg_type} message {alert_id} references this alert"))
            s.add(AuditRecord(alert_id=alert_id, lang="*", event=msg_type.lower(), status=msg_type.upper(),
                              reason=f"{msg_type} of alert {references}"))
        s.commit()
    return alert_id


def update_results(alert_id: str, results: list[dict]) -> None:
    with session() as s:
        a = s.get(Alert, alert_id)
        if a is None:
            raise KeyError(alert_id)
        a.results_json = json.dumps(results, ensure_ascii=False)
        s.add(a)
        s.commit()


def audit(alert_id: str, lang: str, event: str, status: str, reason: str) -> None:
    with session() as s:
        s.add(AuditRecord(alert_id=alert_id, lang=lang, event=event, status=status, reason=reason))
        s.commit()


def get_alert(alert_id: str) -> tuple[Alert, list[AuditRecord]] | None:
    with session() as s:
        a = s.get(Alert, alert_id)
        if a is None:
            return None
        recs = list(s.exec(select(AuditRecord).where(AuditRecord.alert_id == alert_id).order_by(AuditRecord.id)))
        a.created_at = _utc(a.created_at)
        for r in recs:
            r.created_at = _utc(r.created_at)
        s.expunge_all()
        return a, recs


def all_alerts() -> list[Alert]:
    """Newest first. Fine for the demo scale; a real deployment would push filters into SQL."""
    with session() as s:
        rows = list(s.exec(select(Alert).order_by(Alert.created_at.desc())))
        for a in rows:
            a.created_at = _utc(a.created_at)
        s.expunge_all()
        return rows


def summary(a: Alert) -> dict:
    results = json.loads(a.results_json)
    intent = json.loads(a.intent_json)
    return {
        "id": a.id,
        "created_at": a.created_at.isoformat(),
        "source_text": a.source_text,
        "chaos": a.chaos,
        "hazard": intent.get("hazard"),
        "action": intent.get("action"),
        "msg_type": a.msg_type or "Alert",
        "references": a.references,
        "superseded_by": a.superseded_by,
        "statuses": {r["lang"]: r["status"] for r in results},
    }


def recent_alerts(limit: int = 10) -> list[dict]:
    return [summary(a) for a in all_alerts()[:limit]]


def find_duplicate(source_text: str, within: timedelta) -> str | None:
    cutoff = _now() - within
    for a in all_alerts():
        if a.created_at < cutoff:
            break
        if a.source_text.strip().casefold() == source_text.strip().casefold():
            return a.id
    return None


def audit_since(since: datetime | None = None) -> list[AuditRecord]:
    with session() as s:
        q = select(AuditRecord)
        if since:
            q = q.where(AuditRecord.created_at >= since)
        rows = list(s.exec(q))
        s.expunge_all()
        return rows


# ---------------------------------------------------------------- generic CRUD helpers

def list_rows(model, order=None) -> list:
    with session() as s:
        q = select(model)
        if order is not None:
            q = q.order_by(order)
        rows = list(s.exec(q))
        s.expunge_all()
        return rows


def get_row(model, key):
    with session() as s:
        row = s.get(model, key)
        if row is not None:
            s.expunge(row)
        return row


def put_row(row):
    with session() as s:
        s.add(row)
        s.commit()
        s.refresh(row)
        s.expunge(row)
        return row


def delete_row(model, key) -> bool:
    with session() as s:
        row = s.get(model, key)
        if row is None:
            return False
        s.delete(row)
        s.commit()
        return True


def glossary_terms() -> list[str]:
    return [g.term for g in list_rows(GlossaryTerm)]


def signoffs(lang: str | None = None) -> list[LexiconSignoff]:
    with session() as s:
        q = select(LexiconSignoff).order_by(LexiconSignoff.id)
        if lang:
            q = q.where(LexiconSignoff.lang == lang)
        rows = list(s.exec(q))
        for r in rows:
            r.created_at = _utc(r.created_at)
        s.expunge_all()
        return rows
