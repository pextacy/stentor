"""Structural validator for CAP 1.2 documents (OASIS CAP v1.2, sections 3.2.1 to 3.2.4).

Checks element order, required elements, enumerated values, dateTime format, geometry
syntax and references. It is not a full XSD validation, but it catches every mistake a
hand-edited or generated alert usually makes, and it runs without extra dependencies."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from pydantic import BaseModel

NS = "urn:oasis:names:tc:emergency:cap:1.2"

ALERT_ORDER = ["identifier", "sender", "sent", "status", "msgType", "source", "scope", "restriction",
               "addresses", "code", "note", "references", "incidents", "info"]
ALERT_REQUIRED = ["identifier", "sender", "sent", "status", "msgType", "scope"]
INFO_ORDER = ["language", "category", "event", "responseType", "urgency", "severity", "certainty", "audience",
              "eventCode", "effective", "onset", "expires", "senderName", "headline", "description",
              "instruction", "web", "contact", "parameter", "resource", "area"]
INFO_REQUIRED = ["category", "event", "urgency", "severity", "certainty"]
AREA_ORDER = ["areaDesc", "polygon", "circle", "geocode", "altitude", "ceiling"]

ENUMS = {
    "status": {"Actual", "Exercise", "System", "Test", "Draft"},
    "msgType": {"Alert", "Update", "Cancel", "Ack", "Error"},
    "scope": {"Public", "Restricted", "Private"},
    "category": {"Geo", "Met", "Safety", "Security", "Rescue", "Fire", "Health", "Env", "Transport", "Infra", "CBRNE", "Other"},
    "responseType": {"Shelter", "Evacuate", "Prepare", "Execute", "Avoid", "Monitor", "Assess", "AllClear", "None"},
    "urgency": {"Immediate", "Expected", "Future", "Past", "Unknown"},
    "severity": {"Extreme", "Severe", "Moderate", "Minor", "Unknown"},
    "certainty": {"Observed", "Likely", "Possible", "Unlikely", "Unknown"},
}
DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$")
NUM = r"-?\d+(?:\.\d+)?"
POINT = re.compile(rf"^({NUM}),({NUM})$")
CIRCLE = re.compile(rf"^({NUM}),({NUM})\s+({NUM})$")
FORBIDDEN_CHARS = re.compile(r"[ ,<&]")  # identifier and sender (3.2.1)


class CapIssue(BaseModel):
    path: str
    message: str


class CapReport(BaseModel):
    valid: bool
    errors: list[CapIssue]
    warnings: list[CapIssue]
    info_blocks: int
    languages: list[str]


def _local(tag: str) -> str:
    return tag.split("}", 1)[-1]


def _order(parent: ET.Element, order: list[str], path: str, errors: list[CapIssue]) -> None:
    last = -1
    for child in parent:
        name = _local(child.tag)
        if name not in order:
            errors.append(CapIssue(path=path, message=f"unexpected element <{name}>"))
            continue
        idx = order.index(name)
        if idx < last:
            errors.append(CapIssue(path=path, message=f"<{name}> is out of order"))
        last = max(last, idx)


def _texts(parent: ET.Element, name: str) -> list[str]:
    return [(c.text or "").strip() for c in parent if _local(c.tag) == name]


def _point_ok(p: str) -> bool:
    m = POINT.match(p)
    return bool(m) and -90 <= float(m.group(1)) <= 90 and -180 <= float(m.group(2)) <= 180


def validate_cap(xml: str) -> CapReport:
    errors: list[CapIssue] = []
    warnings: list[CapIssue] = []
    try:
        root = ET.fromstring(xml.encode("utf-8") if isinstance(xml, str) else xml)
    except ET.ParseError as e:
        return CapReport(valid=False, errors=[CapIssue(path="/", message=f"not well formed XML: {e}")], warnings=[], info_blocks=0, languages=[])
    if root.tag != f"{{{NS}}}alert":
        errors.append(CapIssue(path="/", message=f"root must be <alert> in namespace {NS}"))
        return CapReport(valid=False, errors=errors, warnings=warnings, info_blocks=0, languages=[])
    for child in root.iter():
        if not child.tag.startswith(f"{{{NS}}}"):
            errors.append(CapIssue(path="/alert", message=f"element {child.tag} is not in the CAP 1.2 namespace"))

    _order(root, ALERT_ORDER, "/alert", errors)
    for name in ALERT_REQUIRED:
        n = len(_texts(root, name))
        if n != 1:
            errors.append(CapIssue(path="/alert", message=f"<{name}> must appear exactly once (found {n})"))
    for name in ("identifier", "sender"):
        for v in _texts(root, name):
            if not v or FORBIDDEN_CHARS.search(v):
                errors.append(CapIssue(path=f"/alert/{name}", message="must be non empty without spaces, commas or < &"))
    for name in ("status", "msgType", "scope"):
        for v in _texts(root, name):
            if v not in ENUMS[name]:
                errors.append(CapIssue(path=f"/alert/{name}", message=f"'{v}' is not one of {', '.join(sorted(ENUMS[name]))}"))
    for v in _texts(root, "sent"):
        if not DATETIME.match(v):
            errors.append(CapIssue(path="/alert/sent", message=f"'{v}' is not a CAP dateTime (YYYY-MM-DDThh:mm:ss+hh:mm, no Z)"))
    scope = (_texts(root, "scope") or [""])[0]
    if scope == "Restricted" and not _texts(root, "restriction"):
        errors.append(CapIssue(path="/alert", message="scope Restricted needs <restriction>"))
    if scope == "Private" and not _texts(root, "addresses"):
        errors.append(CapIssue(path="/alert", message="scope Private needs <addresses>"))
    msg = (_texts(root, "msgType") or [""])[0]
    refs = _texts(root, "references")
    if msg in ("Update", "Cancel", "Ack", "Error") and not refs:
        errors.append(CapIssue(path="/alert", message=f"msgType {msg} needs <references>"))
    for r in refs:
        for ref in r.split():
            parts = ref.split(",")
            if len(parts) != 3 or not DATETIME.match(parts[2]):
                errors.append(CapIssue(path="/alert/references", message=f"'{ref}' is not sender,identifier,sent"))

    infos = [c for c in root if _local(c.tag) == "info"]
    langs: list[str] = []
    if not infos and msg not in ("Cancel", "Ack", "Error"):
        warnings.append(CapIssue(path="/alert", message="no <info> block"))
    for i, info in enumerate(infos, 1):
        path = f"/alert/info[{i}]"
        _order(info, INFO_ORDER, path, errors)
        lang = (_texts(info, "language") or ["en-US"])[0]
        if lang in langs:
            errors.append(CapIssue(path=path, message=f"duplicate language {lang}"))
        langs.append(lang)
        for name in INFO_REQUIRED:
            if not _texts(info, name):
                errors.append(CapIssue(path=path, message=f"<{name}> is required"))
        for name in ("category", "responseType"):
            for v in _texts(info, name):
                if v not in ENUMS[name]:
                    errors.append(CapIssue(path=f"{path}/{name}", message=f"'{v}' is not valid"))
        for name in ("urgency", "severity", "certainty"):
            vals = _texts(info, name)
            if len(vals) > 1:
                errors.append(CapIssue(path=path, message=f"<{name}> must appear once"))
            for v in vals:
                if v not in ENUMS[name]:
                    errors.append(CapIssue(path=f"{path}/{name}", message=f"'{v}' is not valid"))
        for name in ("effective", "onset", "expires"):
            for v in _texts(info, name):
                if not DATETIME.match(v):
                    errors.append(CapIssue(path=f"{path}/{name}", message=f"'{v}' is not a CAP dateTime"))
        head = (_texts(info, "headline") or [""])[0]
        if len(head) > 160:
            warnings.append(CapIssue(path=f"{path}/headline", message="headline longer than 160 characters"))
        for p in [c for c in info if _local(c.tag) == "parameter"]:
            if not _texts(p, "valueName") or not _texts(p, "value"):
                errors.append(CapIssue(path=f"{path}/parameter", message="needs <valueName> and <value>"))
        for j, area in enumerate([c for c in info if _local(c.tag) == "area"], 1):
            apath = f"{path}/area[{j}]"
            _order(area, AREA_ORDER, apath, errors)
            if len(_texts(area, "areaDesc")) != 1:
                errors.append(CapIssue(path=apath, message="<areaDesc> must appear exactly once"))
            for poly in _texts(area, "polygon"):
                pts = poly.split()
                if len(pts) < 4 or pts[0] != pts[-1] or not all(_point_ok(p) for p in pts):
                    errors.append(CapIssue(path=f"{apath}/polygon", message="needs 4+ valid lat,lon points, first equal to last"))
            for c in _texts(area, "circle"):
                m = CIRCLE.match(c)
                if not m or not _point_ok(f"{m.group(1)},{m.group(2)}") or float(m.group(3)) < 0:
                    errors.append(CapIssue(path=f"{apath}/circle", message=f"'{c}' is not 'lat,lon radius'"))
            for g in [c for c in area if _local(c.tag) == "geocode"]:
                if not _texts(g, "valueName") or not _texts(g, "value"):
                    errors.append(CapIssue(path=f"{apath}/geocode", message="needs <valueName> and <value>"))
    return CapReport(valid=not errors, errors=errors, warnings=warnings, info_blocks=len(infos), languages=langs)
