"""Placeholder locking: literals never pass through a model.

`apply(text)` replaces literals with tokens and returns the mapping:

    ⟦T1⟧ time or day      "6:00 PM", "3 pm tomorrow", "Friday"
    ⟦P1⟧ place            "Altadena", "Lake Ave", "St. Mary School", "I-5", "Exit 132"
    ⟦N1⟧ number/quantity  "2 miles", "one minute", "3"
    ⟦U1⟧ phone or link    "211", "1-800-555-1234", "www.ready.gov"
    ⟦E1⟧ event name       "Milton" in "Hurricane Milton"

`restore(text, mapping, lang)` puts the values back. It localizes only the *format*
of times, days and units, never the value, and isolates literals in RTL text.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

PH_RE = re.compile(r"⟦([TPNUE])(\d+)⟧")
# An explicit operator marker such as ⟦Altadena⟧ means "lock this as a place".
# Every bracketed span in operator text is a marker, even one shaped like ⟦P1⟧: the
# brackets are reserved for placeholders, so they never survive into the locked text.
EXPLICIT_RE = re.compile(r"⟦([^⟦⟧]{0,60})⟧")

SHORT_CODES = {"211", "311", "511", "911", "112", "999", "110", "119", "988"}

URL_RE = re.compile(
    r"\b(?:https?://[^\s]+|www\.[^\s]+|[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:gov|org|com|net|edu|info|us|uk|tr)(?:/[^\s]*)?)",
    re.I,
)
PHONE_RE = re.compile(r"(?<![\w⟦])(?:\+?1[\s.-])?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b")
CODE_RE = re.compile(r"(?<![\w⟦.:-])(\d{3})(?![\w:-])")

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_WD = r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)"
_DAYWORD = r"(?:today|tonight|tomorrow|this\s+(?:morning|afternoon|evening))"
# "p.m." is matched without its final dot, so a sentence ending in "3 p.m." keeps its period.
_CLOCK = r"(?:\d{1,2}(?::\d{2})?\s*(?:[ap]m\b|[ap]\.m(?=\.))|\d{1,2}:\d{2}|noon|midnight)"
TIME_RE = re.compile(
    rf"\b(?:(?:{_DAYWORD}|{_WD})\s+(?:at\s+)?)?{_CLOCK}(?:\.(?=\s+(?:on\s+)?(?:{_DAYWORD}|{_WD})\b))?(?:\s+(?:on\s+)?(?:{_DAYWORD}|{_WD})\b)?"
    rf"|\b{_WD}\b",
    re.I,
)

_NUMWORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
             "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30}
_UNIT = r"(?:minutes?|mins?|hours?|hrs?|miles?|mi|kilometers?|kilometres?|km|feet|foot|ft|meters?|metres?)"
QTY_RE = re.compile(rf"(?<![\w⟦])(\d+(?:[.,]\d+)?|{'|'.join(_NUMWORDS)})[\s-]*({_UNIT})\b", re.I)
NUMBER_RE = re.compile(r"(?<![\w⟦])\d+(?:[.,]\d+)?(?![\w⟧])")

_ABBR = r"(?:St|Mt|Ft|Pt)\."  # St. Mary, Mt. Wilson, Ft. Lauderdale
_CAPW = r"(?:[A-Z][\w'’-]*|\d+(?:st|nd|rd|th))"
STREET_SUFFIX = (
    r"(?:Ave|Avenue|St|Street|Rd|Road|Blvd|Boulevard|Dr|Drive|Hwy|Highway|Way|Lane|Ln|Pkwy|Parkway|"
    r"Bridge|Park|Canyon|Creek|River|Beach|Bay|Valley|Hills|Heights|School|Center|Centre|"
    r"Stadium|Hall|Church|Library|Mall|Plaza|Square|Station|Harbor|Port|Pier|Campus|Village|Hospital|Airport)"
)
# An optional house number belongs to the address: "120 Main St" is one literal.
STREET_RE = re.compile(rf"(?:\b\d{{1,6}}\s+)?(?:\b{_ABBR}\s+)?\b(?:{_CAPW}\s+){{1,3}}{STREET_SUFFIX}\b")
# Evacuation zones and similar designated areas: "Zone A", "Zones 3", "Sector 4B", "Gate 2".
ZONE_RE = re.compile(r"\b(?:Zones?|Sector|District|Ward|Block|Building|Bldg|Gate|Lot|Level|Floor|Unit|Area|Terminal|Pier|Section)\s+(?:[A-Z]{1,2}\b|\d{1,4}[A-Z]?\b)")
# Named geographic features with a generic head word first: "Mount Hood", "Lake Tahoe".
FEATURE_RE = re.compile(r"\b(?:Mount|Mt\.|Lake|Fort|Ft\.|Port|Cape|Point|Saint|Isle|Camp)\s+[A-Z][\w'’-]+(?:\s+[A-Z][\w'’-]+)?")
# Codes that mix letters and digits: licence plates, "N95", flight or unit numbers. Never translated.
ALNUM_RE = re.compile(r"(?<![\w⟦-])(?=[A-Za-z-]*\d)(?=[\d-]*[A-Za-z])[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?![\w⟧-])")
_ORDINAL = re.compile(r"\d+(?:st|nd|rd|th)", re.I)
# All-caps words that are emphasis, not names ("EVACUATE NOW", "for ALL residents").
CAPS_NOT_NAMES = {"ALL", "NOW", "NOT", "AREA", "ZONE", "ORDER", "ALERT", "WARNING", "DANGER", "EMERGENCY",
                  "IMMEDIATELY", "EVERYONE", "RESIDENTS", "HOME", "INSIDE", "INDOORS", "TODAY", "TONIGHT", "THE", "YOUR"}
ROUTE_RE = re.compile(r"\b(?:Highway|Hwy|Route|Interstate|Exit|I-|US-|SR-|CA-)\s?\d+[A-Z]?\b")
PREP_PLACE_RE = re.compile(
    r"\b(?:near|in|at|from|around|of|for|to|toward|towards|via|between|and|across|along|on|over|inside|outside|off)\s+"
    rf"((?:{_ABBR}\s+)?[A-Z][\w'’-]+(?:\s+(?:(?:of|de|del|la)\s+)?[A-Z][\w'’-]+)*)"
)
EVENT_RE = re.compile(r"\b(?:Hurricane|Tropical Storm|Typhoon|Cyclone|Storm)\s+([A-Z][a-z]+)\b")

# Capitalized words that are never place names on their own.
STOP_CAPS = {
    "The", "A", "An", "All", "Your", "You", "Info", "Information", "Do", "Not", "NOT",
    "Call", "Go", "Stay", "Leave", "Evacuate", "Use", "Avoid", "Boil", "Drink", "If",
    "This", "That", "Shelter", "Move", "Danger", "Warning", "Watch", "Alert", "Emergency",
    "Police", "Fire", "Officials", "County", "City", "Now", "Today", "Tonight", "Tomorrow",
    "Immediately", "Follow", "Check", "Keep", "Close", "Turn", "Return", "Drive", "Take",
    "Residents", "Lock", "Expect", "Prepare", "EVACUATE", "NOW", "Hurricane", "Tornado",
    "Flood", "Wildfire", "Earthquake", "Tsunami", "Evacuation", "Order", "Mandatory",
    *WEEKDAYS,
}
# Allowed at the end of a place name: "Ellicott City", "Orange County".
PLACE_SUFFIX_OK = {"City", "County"}


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    kind: str  # T P N U E
    value: str


def _spans(text: str, places: list[str] | None) -> list[Span]:
    found: list[Span] = []
    for m in URL_RE.finditer(text):
        v = m.group(0).rstrip(".,;:)")
        found.append(Span(m.start(), m.start() + len(v), "U", v))
    for m in PHONE_RE.finditer(text):
        found.append(Span(m.start(), m.end(), "U", m.group(0)))
    for m in TIME_RE.finditer(text):
        v = m.group(0).rstrip()
        found.append(Span(m.start(), m.start() + len(v), "T", v))
    for m in CODE_RE.finditer(text):
        prev = text[max(0, m.start() - 12) : m.start()].lower()
        if m.group(1) in SHORT_CODES or re.search(r"(call|dial|text|info:?|line)\s*$", prev):
            found.append(Span(m.start(), m.end(), "U", m.group(1)))
    for m in EVENT_RE.finditer(text):
        found.append(Span(m.start(1), m.end(1), "E", m.group(1)))
    for p in sorted(set(places or []), key=len, reverse=True):
        for m in re.finditer(rf"(?<!\w){re.escape(p)}(?!\w)", text):
            found.append(Span(m.start(), m.end(), "P", p))
    for m in ROUTE_RE.finditer(text):
        found.append(Span(m.start(), m.end(), "P", m.group(0)))
    for rx in (ZONE_RE, FEATURE_RE):
        for m in rx.finditer(text):
            found.append(Span(m.start(), m.end(), "P", m.group(0)))
    for m in STREET_RE.finditer(text):
        v = m.group(0)
        words = v.split()
        while words and words[0] in STOP_CAPS:
            words.pop(0)
        if len(words) >= 2:
            v2 = " ".join(words)
            s = m.start() + v.index(v2)
            found.append(Span(s, s + len(v2), "P", v2))
    for m in PREP_PLACE_RE.finditer(text):
        words = m.group(1).split()
        while words and words[-1] in STOP_CAPS - PLACE_SUFFIX_OK:
            words.pop()
        if not words or words[0] in STOP_CAPS:
            continue
        # All-caps words are usually emphasis; short acronyms ("UCLA", "LAX") are names.
        if all(w.isupper() for w in words) and not all(
                2 <= len(w) <= 5 and w.isalpha() and w not in CAPS_NOT_NAMES and w.capitalize() not in STOP_CAPS
                for w in words):
            continue
        v = " ".join(words)
        s = m.start(1)
        found.append(Span(s, s + len(v), "P", v))
    for m in QTY_RE.finditer(text):
        found.append(Span(m.start(), m.end(), "N", m.group(0)))
    for m in ALNUM_RE.finditer(text):
        if not _ORDINAL.fullmatch(m.group(0)):
            found.append(Span(m.start(), m.end(), "N", m.group(0)))
    for m in NUMBER_RE.finditer(text):
        found.append(Span(m.start(), m.end(), "N", m.group(0)))
    return found


PRIORITY = {"U": 0, "T": 1, "E": 2, "P": 3, "N": 4}


def _resolve(spans: list[Span]) -> list[Span]:
    """Higher priority kinds win, then longer spans; drop anything overlapping a winner."""
    ranked = sorted(spans, key=lambda s: (PRIORITY[s.kind], -(s.end - s.start), s.start))
    taken: list[Span] = []
    for s in ranked:
        if all(s.end <= t.start or s.start >= t.end for t in taken):
            taken.append(s)
    return sorted(taken, key=lambda s: s.start)


def apply(text: str, places: list[str] | None = None) -> tuple[str, dict[str, str]]:
    """Lock literals. Returns (locked_text, {placeholder: literal})."""
    explicit: list[str] = [m.group(1).strip() for m in EXPLICIT_RE.finditer(text)]
    text = EXPLICIT_RE.sub(lambda m: m.group(1), text).replace("⟦", "").replace("⟧", "")
    # An empty or whitespace place would match at every position of the text.
    names = [p.strip() for p in (places or []) + explicit if p and p.strip()]
    spans = _resolve(_spans(text, names))
    counters: Counter[str] = Counter()
    mapping: dict[str, str] = {}
    out: list[str] = []
    pos = 0
    for s in spans:
        counters[s.kind] += 1
        ph = f"⟦{s.kind}{counters[s.kind]}⟧"
        mapping[ph] = s.value
        out.append(text[pos : s.start])
        out.append(ph)
        pos = s.end
    out.append(text[pos:])
    return "".join(out), mapping


def placeholders_in(text: str) -> list[str]:
    return [m.group(0) for m in PH_RE.finditer(text)]


def kind_of(ph: str) -> str:
    m = PH_RE.fullmatch(ph)
    return m.group(1) if m else "?"


# ---------------------------------------------------------------- times

_TIME_PARSE = re.compile(
    rf"^(?:(?P<pre>{_DAYWORD}|{_WD})\s+(?:at\s+)?)?"
    r"(?:(?P<h>\d{1,2})(?::(?P<m>\d{2}))?\s*(?P<ap>[ap]\.?m\.?)?|(?P<word>noon|midnight))?"
    rf"(?:\s+(?:on\s+)?(?P<post>{_DAYWORD}|{_WD}))?$",
    re.I,
)


@dataclass(frozen=True)
class ParsedTime:
    day: str | None  # today | tonight | tomorrow
    weekday: int | None  # 0 = Monday
    hour: int | None
    minute: int


def parse_time(value: str) -> ParsedTime | None:
    """'3 pm tomorrow' -> ParsedTime('tomorrow', None, 15, 0). None if not understood."""
    v = value.strip()
    if v.capitalize() in WEEKDAYS:
        return ParsedTime(None, WEEKDAYS.index(v.capitalize()), None, 0)
    if v.lower() in ("today", "tonight", "tomorrow"):
        return ParsedTime(v.lower(), None, None, 0)
    m = _TIME_PARSE.match(v)
    if not m or not any(m.group(g) for g in ("h", "word", "pre", "post")):
        return None
    dayw = (m.group("pre") or m.group("post") or "").lower()
    day = weekday = None
    if dayw:
        cap = dayw.capitalize()
        if cap in WEEKDAYS:
            weekday = WEEKDAYS.index(cap)
        elif dayw.startswith("this"):
            day = "today"
        else:
            day = dayw
    if m.group("word"):
        return ParsedTime(day, weekday, 12 if m.group("word").lower() == "noon" else 0, 0)
    if m.group("h") is None:
        return ParsedTime(day, weekday, None, 0) if (day or weekday is not None) else None
    h, mi = int(m.group("h")), int(m.group("m") or 0)
    ap = (m.group("ap") or "").lower().replace(".", "")
    if not ap and m.group("m") is None:
        return None
    if ap == "pm" and h < 12:
        h += 12
    if ap == "am" and h == 12:
        h = 0
    if h > 23 or mi > 59:
        return None
    return ParsedTime(day, weekday, h, mi)


def _clock(style: str, h: int, mi: int) -> str:
    h12 = h % 12 or 12
    if style == "24h":
        return f"{h:02d}:{mi:02d}"
    if style == "ko":
        return f"{'오전' if h < 12 else '오후'} {h12}:{mi:02d}"
    if style == "es":
        return f"{'la' if h == 1 else 'las'} {h:02d}:{mi:02d}"
    if style == "ar":
        return f"{h12}:{mi:02d} {'ص' if h < 12 else 'م'}"
    return f"{h12}:{mi:02d} {'AM' if h < 12 else 'PM'}"


def format_time(value: str, lang: str) -> str:
    """Localize the format of a time literal. The clock value never changes."""
    from stentor.lexicon import load

    if lang == "en":
        return value
    p = parse_time(value)
    if p is None:
        return value
    t = load(lang).raw.get("time", {})
    style = t.get("style", "24h")
    dayw = t.get("day_words", {}).get(p.day) if p.day else None
    wd = t.get("weekdays", WEEKDAYS)[p.weekday] if p.weekday is not None else None
    if p.hour is None:
        if wd and t.get("weekday_article"):
            return t["weekday_article"] + wd
        return dayw or wd or value
    core = _clock(style, p.hour, p.minute)
    extra, joiner = (dayw, t.get("day_joiner", " ")) if dayw else (wd, t.get("weekday_joiner", " "))
    if not extra:
        return core
    if t.get("day_position") == "before":
        return f"{extra} {core}"
    return f"{core}{joiner}{extra}"


# ---------------------------------------------------------------- quantities

_UNIT_KEY = [
    (r"min", "minute"), (r"h(ou)?rs?$|hour", "hour"), (r"mi(le)?s?$|mile", "mile"),
    (r"k(ilo)?m", "km"), (r"f(ee|oo)?t", "foot"), (r"met", "meter"),
]


def parse_quantity(value: str) -> tuple[float, str] | None:
    m = QTY_RE.fullmatch(value.strip())
    if not m:
        return None
    raw, unit = m.group(1).lower(), m.group(2).lower()
    n = _NUMWORDS.get(raw)
    if n is None:
        try:
            n = float(raw.replace(",", "."))
        except ValueError:
            return None
    key = next((k for pat, k in _UNIT_KEY if re.match(pat, unit)), None)
    return (n, key) if key else None


def _plural_form(forms, n: float) -> str:
    if isinstance(forms, str):
        return forms
    if n == 1:
        return forms.get("one", forms.get("other"))
    if n == 2 and "two" in forms:
        return forms["two"]
    if 3 <= n <= 10 and float(n).is_integer() and "few" in forms:
        return forms["few"]
    return forms.get("other", forms.get("one"))


def format_quantity(value: str, lang: str) -> str:
    from stentor.lexicon import load

    if lang == "en":
        return value
    q = parse_quantity(value)
    if q is None:
        return value
    n, key = q
    lx = load(lang)
    forms = lx.raw.get("units", {}).get(key)
    if not forms:
        return value
    num = str(int(n)) if float(n).is_integer() else str(n)
    return lx.raw.get("unit_format", "{n} {u}").format(n=num, u=_plural_form(forms, n))


def localized_value(ph: str, value: str, lang: str) -> str:
    k = kind_of(ph)
    if k == "T":
        return format_time(value, lang)
    if k == "N":
        return format_quantity(value, lang)
    return value


RTL_LANGS = {"ar", "he", "fa", "ur"}
FSI, PDI = "⁨", "⁩"  # Unicode first strong isolate / pop directional isolate


def restore(text: str, mapping: dict[str, str], lang: str = "en") -> str:
    """Put literals back. In right-to-left languages each literal is wrapped in a
    directional isolate so "211." or "Lake Ave" cannot be reordered by the bidi algorithm."""
    wrap = (lambda v: f"{FSI}{v}{PDI}") if lang in RTL_LANGS else (lambda v: v)
    return PH_RE.sub(lambda m: wrap(localized_value(m.group(0), mapping.get(m.group(0), m.group(0)), lang)), text)


_SENT_START = re.compile(r"(^|[.!?؟]\s+)([\u2068]?)(\w)")


def finalize(text: str, lang: str) -> str:
    """Capitalize each sentence after literals are restored ("yarın 15:00 ..." ->
    "Yarın 15:00 ..."). Runs after verification and only changes letter case."""
    def up(m: re.Match) -> str:
        ch = m.group(3)
        upper = "İ" if (lang == "tr" and ch == "i") else ch.upper()
        return m.group(1) + m.group(2) + (upper if len(upper) == 1 else ch)
    return _SENT_START.sub(up, text)
