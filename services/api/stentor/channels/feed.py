"""Atom 1.0 feed of published alerts. Only sendable languages appear (CLAUDE.md rule 1)."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timezone

ATOM = "http://www.w3.org/2005/Atom"


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_feed(entries: list[dict], base_url: str, api_url: str, updated: datetime | None = None) -> str:
    """entries: {id, created_at (datetime), title, summary, msg_type, languages: [{lang, text}]}"""
    ET.register_namespace("", ATOM)
    feed = ET.Element(f"{{{ATOM}}}feed")

    def sub(parent, tag, text=None, **attrs):
        el = ET.SubElement(parent, f"{{{ATOM}}}{tag}", attrs)
        if text is not None:
            el.text = text
        return el

    sub(feed, "id", f"{base_url.rstrip('/')}/feed")
    sub(feed, "title", "STENTOR alerts (demo, not official warnings)")
    sub(feed, "updated", _iso(updated or (entries[0]["created_at"] if entries else datetime.now(timezone.utc))))
    sub(feed, "link", href=f"{api_url.rstrip('/')}/feed.atom", rel="self")
    author = sub(feed, "author")
    sub(author, "name", "STENTOR demo operator")
    for e in entries:
        entry = sub(feed, "entry")
        sub(entry, "id", f"urn:stentor:alert:{e['id']}")
        prefix = "" if e["msg_type"] == "Alert" else f"[{e['msg_type']}] "
        sub(entry, "title", prefix + e["title"])
        sub(entry, "updated", _iso(e["created_at"]))
        sub(entry, "link", href=f"{base_url.rstrip('/')}/a/{e['id']}", rel="alternate")
        sub(entry, "link", href=f"{api_url.rstrip('/')}/alerts/{e['id']}/cap.xml", rel="alternate", type="application/cap+xml")
        for lg in e["languages"]:
            sub(entry, "link", href=f"{base_url.rstrip('/')}/a/{e['id']}?lang={lg['lang']}", rel="alternate", hreflang=lg["lang"])
        sub(entry, "summary", e["summary"])
        content = sub(entry, "content", type="text")
        content.text = "\n\n".join(f"[{lg['lang']}] {lg['text']}" for lg in e["languages"])
    ET.indent(feed)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(feed, encoding="unicode")
