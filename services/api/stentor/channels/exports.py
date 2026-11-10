"""Exports of a compiled alert: JSON bundle, plain text, CSV, audit CSV.

The text and JSON bundles carry only sendable languages; the CSV lists every language
with its status, because it is an operator report, not a message."""
from __future__ import annotations

import csv
import io

SENDABLE = ("VERIFIED", "FALLBACK", "APPROVED")


def sendable(results: list[dict]) -> list[dict]:
    return [r for r in results if r["status"] in SENDABLE and r.get("text")]


def json_bundle(alert: dict) -> dict:
    return {
        "id": alert["id"],
        "created_at": alert["created_at"],
        "msg_type": alert.get("msg_type", "Alert"),
        "references": alert.get("references"),
        "source": {"lang": "en", "text": alert["source_text"]},
        "hazard": alert["intent"]["hazard"],
        "action": alert["intent"]["action"],
        "messages": [
            {"lang": r["lang"], "name": r["name"], "dir": r["dir"], "status": r["status"], "text": r["text"],
             "renderer": r["renderer"], "sms_segments": (r.get("sms") or {}).get("segments")}
            for r in sendable(alert["results"])
        ],
        "withheld": [{"lang": r["lang"], "status": r["status"]} for r in alert["results"] if r["status"] not in SENDABLE],
    }


def text_bundle(alert: dict) -> str:
    lines = [f"STENTOR alert {alert['id']} ({alert.get('msg_type', 'Alert')}), {alert['created_at']}",
             "Demo output. Not an official warning.", "", "[en] SOURCE", alert["source_text"], ""]
    for r in sendable(alert["results"]):
        lines += [f"[{r['lang']}] {r['english_name']} - {r['status']}", r["text"], ""]
    held = [r for r in alert["results"] if r["status"] not in SENDABLE]
    if held:
        lines.append("Withheld (not sent): " + ", ".join(f"{r['lang']} {r['status']}" for r in held))
    return "\n".join(lines).rstrip() + "\n"


def _csv(rows: list[list]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerows(rows)
    return "﻿" + buf.getvalue()  # BOM so spreadsheet apps read UTF-8 (Arabic, Korean)


def results_csv(alert: dict) -> str:
    rows = [["alert_id", "lang", "language", "status", "sent", "renderer", "backparser", "characters",
             "sms_segments", "sms_encoding", "reviewer", "reasons", "text"]]
    for r in alert["results"]:
        sms = r.get("sms") or {}
        rows.append([alert["id"], r["lang"], r["english_name"], r["status"], "yes" if r["status"] in SENDABLE else "no",
                     r["renderer"], r["backparser"], len(r.get("text") or ""), sms.get("segments", ""), sms.get("encoding", ""),
                     (r.get("review") or {}).get("reviewer", ""), " | ".join(r["reasons"]), r.get("text") or ""])
    return _csv(rows)


def audit_csv(alert_id: str, audit: list[dict]) -> str:
    rows = [["alert_id", "created_at", "lang", "event", "status", "reason"]]
    rows += [[alert_id, a["created_at"], a["lang"], a["event"], a["status"], a["reason"]] for a in audit]
    return _csv(rows)
