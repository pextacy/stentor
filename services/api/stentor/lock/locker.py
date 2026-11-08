"""Placeholder locking: literals never pass through a model.

`apply(text)` replaces times, places, numbers, phones and URLs with tokens such as
`⟦T1⟧` and returns the mapping. `restore(text, mapping, lang)` puts the values back,
localizing only the *format* of times (never the value).
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

PH_RE = re.compile(r"⟦([TPNU])(\d+)⟧")
# An explicit operator marker such as ⟦Altadena⟧ means "lock this as a place".
EXPLICIT_RE = re.compile(r"⟦(?![TPNU]\d+⟧)([^⟦⟧]{1,60})⟧")

SHORT_CODES = {"211", "311", "911", "112", "999", "110", "119", "988"}

URL_RE = re.compile(
    r"\b(?:https?://[^\s]+|www\.[^\s]+|[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:gov|org|com|net|edu|info)(?:/[^\s]*)?)",
    re.I,
)
PHONE_RE = re.compile(r"(?<![\w⟦])\+?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b")
CODE_RE = re.compile(r"(?<![\w⟦.:])(\d{3})(?![\w:])")
_DAY = r"(?:(?:today|tonight|tomorrow|this\s+(?:morning|afternoon|evening))\s+(?:at\s+)?)?"
TIME_RE = re.compile(
    rf"\b{_DAY}(?:\d{{1,2}}(?::\d{{2}})?\s*(?:[ap]m\b|[ap]\.m\.)|\d{{1,2}}:\d{{2}}|noon|midnight)",
    re.I,
)
STREET_SUFFIX = (
    r"(?:Ave|Avenue|St|Street|Rd|Road|Blvd|Boulevard|Dr|Drive|Hwy|Highway|Way|Lane|Ln|"
    r"Bridge|Park|Canyon|Creek|River|Beach|Bay|Valley|Hills|Heights|School|Center|Centre|"
    r"Stadium|Hall|Church|Library|Mall|Plaza|Square|Station|Harbor|Port|Pier|Campus|Village)"
)
STREET_RE = re.compile(rf"\b(?:[A-Z][\w'’-]*\s+){{1,3}}{STREET_SUFFIX}\b")
ROUTE_RE = re.compile(r"\b(?:Highway|Hwy|Route|Interstate|I-|US-|SR-)\s?\d+[A-Z]?\b")
PREP_PLACE_RE = re.compile(
    r"\b(?:near|in|at|from|around|of|for|to|toward|towards|via|between|and)\s+"
    r"((?:[A-Z][\w'’-]+)(?:\s+(?:(?:of|de|del|la)\s+)?(?:[A-Z][\w'’-]+))*)"
)
NUMBER_RE = re.compile(r"(?<![\w⟦])\d+(?:[.,]\d+)?(?![\w⟧])")

# Capitalized words that are never place names on their own.
STOP_CAPS = {
    "The", "A", "An", "All", "Your", "You", "Info", "Information", "Do", "Not", "NOT",
    "Call", "Go", "Stay", "Leave", "Evacuate", "Use", "Avoid", "Boil", "Drink", "If",
    "This", "That", "Shelter", "Move", "Danger", "Warning", "Watch", "Alert", "Emergency",
    "Police", "Fire", "Officials", "County", "City", "Now", "Today", "Tonight", "Tomorrow",
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
    "Immediately", "Follow", "Check", "Keep", "Close", "Turn", "Return", "Drive",
}


# Allowed at the end of a place name: "Ellicott City", "Orange County".
PLACE_SUFFIX_OK = {"City", "County"}


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    kind: str  # T P N U
    value: str


def _spans(text: str, places: list[str] | None) -> list[Span]:
    found: list[Span] = []
    for m in URL_RE.finditer(text):
        v = m.group(0).rstrip(".,;:)")
        found.append(Span(m.start(), m.start() + len(v), "U", v))
    for m in PHONE_RE.finditer(text):
        found.append(Span(m.start(), m.end(), "U", m.group(0)))
    for m in TIME_RE.finditer(text):
        found.append(Span(m.start(), m.end(), "T", m.group(0)))
    for m in CODE_RE.finditer(text):
        prev = text[max(0, m.start() - 12) : m.start()].lower()
        if m.group(1) in SHORT_CODES or re.search(r"(call|dial|text|info:?|line)\s*$", prev):
            found.append(Span(m.start(), m.end(), "U", m.group(1)))
    for p in sorted(set(places or []), key=len, reverse=True):
        for m in re.finditer(rf"(?<!\w){re.escape(p)}(?!\w)", text):
            found.append(Span(m.start(), m.end(), "P", p))
    for m in ROUTE_RE.finditer(text):
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
        if not words or words[0] in STOP_CAPS or all(w.isupper() for w in words):
            continue
        v = " ".join(words)
        s = m.start(1)
        found.append(Span(s, s + len(v), "P", v))
    for m in NUMBER_RE.finditer(text):
        found.append(Span(m.start(), m.end(), "N", m.group(0)))
    return found


def _resolve(spans: list[Span]) -> list[Span]:
    """Higher priority kinds win, then longer spans; drop anything overlapping a winner."""
    # Priority: U > T > P > N, longer first inside a kind.
    prio = {"U": 0, "T": 1, "P": 2, "N": 3}
    ranked = sorted(spans, key=lambda s: (prio[s.kind], -(s.end - s.start), s.start))
    taken: list[Span] = []
    for s in ranked:
        if all(s.end <= t.start or s.start >= t.end for t in taken):
            taken.append(s)
    return sorted(taken, key=lambda s: s.start)


def apply(text: str, places: list[str] | None = None) -> tuple[str, dict[str, str]]:
    """Lock literals. Returns (locked_text, {placeholder: literal})."""
    # 1. explicit operator markers ⟦Name⟧ -> places
    explicit: list[str] = [m.group(1).strip() for m in EXPLICIT_RE.finditer(text)]
    text = EXPLICIT_RE.sub(lambda m: m.group(1), text)
    spans = _resolve(_spans(text, (places or []) + explicit))
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


# ---------------------------------------------------------------- restore

_DAY_WORDS = {
    "en": {"today": "today", "tonight": "tonight", "tomorrow": "tomorrow"},
    "vi": {"today": "hôm nay", "tonight": "tối nay", "tomorrow": "ngày mai"},
    "tl": {"today": "ngayong araw", "tonight": "mamayang gabi", "tomorrow": "bukas"},
    "ko": {"today": "오늘", "tonight": "오늘 밤", "tomorrow": "내일"},
    "ar": {"today": "اليوم", "tonight": "الليلة", "tomorrow": "غدًا"},
    "ht": {"today": "jodi a", "tonight": "aswè a", "tomorrow": "demen"},
}

_TIME_PARSE = re.compile(
    r"^(?:(today|tonight|tomorrow)\s+(?:at\s+)?)?(?:(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)?|(noon|midnight))$",
    re.I,
)


def parse_time(value: str) -> tuple[str | None, int, int] | None:
    """'tomorrow 8am' -> ('tomorrow', 8, 0). None if not a simple clock time."""
    m = _TIME_PARSE.match(value.strip())
    if not m:
        return None
    day = m.group(1).lower() if m.group(1) else None
    if m.group(5):
        return day, (12 if m.group(5).lower() == "noon" else 0), 0
    h, mi = int(m.group(2)), int(m.group(3) or 0)
    ampm = (m.group(4) or "").lower().replace(".", "")
    if ampm == "pm" and h < 12:
        h += 12
    if ampm == "am" and h == 12:
        h = 0
    if not ampm and m.group(3) is None:
        return None
    if h > 23 or mi > 59:
        return None
    return day, h, mi


def format_time(value: str, lang: str) -> str:
    """Localize the format of a time literal. The clock value never changes."""
    parsed = parse_time(value)
    if parsed is None or lang == "en":
        return value
    day, h, mi = parsed
    h12 = h % 12 or 12
    dw = _DAY_WORDS.get(lang, {}).get(day, day) if day else None
    if lang == "vi":
        core = f"{h:02d}:{mi:02d}"
        return f"{core} {dw}" if dw else core
    if lang == "ko":
        core = f"{'오전' if h < 12 else '오후'} {h12}:{mi:02d}"
        return f"{dw} {core}" if dw else core
    if lang == "ar":
        core = f"{h12}:{mi:02d} {'ص' if h < 12 else 'م'}"
        return f"{dw} {core}" if dw else core
    core = f"{h12}:{mi:02d} {'AM' if h < 12 else 'PM'}"
    return f"{core} {dw}" if dw else core


def localized_value(ph: str, value: str, lang: str) -> str:
    return format_time(value, lang) if kind_of(ph) == "T" else value


RTL_LANGS = {"ar", "he", "fa", "ur"}
FSI, PDI = "\u2068", "\u2069"  # Unicode first strong isolate / pop directional isolate


def restore(text: str, mapping: dict[str, str], lang: str = "en") -> str:
    """Put literals back. In right-to-left languages each literal is wrapped in a
    directional isolate so "211." or "Lake Ave" cannot be reordered by the bidi algorithm."""
    wrap = (lambda v: f"{FSI}{v}{PDI}") if lang in RTL_LANGS else (lambda v: v)
    return PH_RE.sub(lambda m: wrap(localized_value(m.group(0), mapping.get(m.group(0), m.group(0)), lang)), text)
