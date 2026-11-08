"""Action lexicon + approved phrase templates per language.

Every file carries `reviewed_by`. Files seeded by an LLM say `unreviewed` and the UI
shows that. Only native speaker review should change it.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

LEXICON_DIR = Path(__file__).parent
TARGET_LANGS = ["vi", "tl", "ko", "ar", "ht"]  # the PRD demo set; es and tr are also available


@dataclass
class Lexicon:
    lang: str
    name: str
    english_name: str
    dir: str
    tts: str
    reviewed_by: str
    approved: bool
    fold_diacritics: bool
    word_boundary: bool
    negation_markers: list[str]
    headline: str
    headline_place: str
    hazards: dict[str, dict]
    actions: dict[str, dict]
    instructions: dict[str, dict]
    info: dict
    expires: dict
    raw: dict = field(repr=False, default_factory=dict)

    def opt(self, key: str, default=None):
        return self.raw.get(key, default)

    # ------------------------------------------------------------ matching
    def norm(self, text: str) -> str:
        """Normalize for phrase matching (case, and diacritics where safe)."""
        t = unicodedata.normalize("NFKC", text).replace("’", "'").casefold()
        if self.fold_diacritics:
            t = "".join(c for c in unicodedata.normalize("NFKD", t) if unicodedata.category(c) != "Mn")
            t = unicodedata.normalize("NFC", t)
        t = re.sub(r"⟦[^⟧]*⟧", " ", t)
        t = re.sub(r"[\-‐–—]", " ", t)
        return re.sub(r"\s+", " ", t).strip()

    def find_all(self, phrase: str, text_norm: str) -> list[tuple[int, int]]:
        """All (start, end) spans of phrase in normalized text."""
        p = self.norm(phrase)
        if not p:
            return []
        pat = re.escape(p) if not self.word_boundary else rf"(?<!\w){re.escape(p)}(?!\w)"
        return [m.span() for m in re.finditer(pat, text_norm)]

    def find(self, phrase: str, text_norm: str) -> int:
        """Position of phrase in normalized text, -1 if absent."""
        p = self.norm(phrase)
        if not p:
            return -1
        if not self.word_boundary:
            return text_norm.find(p)
        m = re.search(rf"(?<!\w){re.escape(p)}(?!\w)", text_norm)
        return m.start() if m else -1

    def has(self, phrase: str, text_norm: str) -> bool:
        return self.find(phrase, text_norm) >= 0

    def negation_hits(self, text: str) -> int:
        """Count negation markers. Diacritic *sensitive*: in Vietnamese, folding
        would turn 'dùng' (use) into a false 'đừng' (don't)."""
        t = unicodedata.normalize("NFC", text).replace("’", "'").casefold()
        t = re.sub(r"⟦[^⟧]*⟧", " ", t)
        n = 0
        for mk in self.negation_markers:
            mk = unicodedata.normalize("NFC", mk).casefold()
            if self.word_boundary:
                n += len(re.findall(rf"(?<![\w']){re.escape(mk)}(?![\w'])", t))
            else:
                n += t.count(mk)
        return n

    def hazard_terms(self, hazard: str) -> list[str]:
        h = self.hazards.get(hazard, {})
        return [h["name"], *h.get("terms", [])] if h else []

    def action_phrases(self, action: str) -> list[str]:
        return self.actions.get(action, {}).get("match", [])


@lru_cache
def load(lang: str) -> Lexicon:
    path = LEXICON_DIR / f"{lang}.json"
    if not path.exists():
        raise KeyError(f"no lexicon for language '{lang}'")
    raw = json.loads(path.read_text(encoding="utf-8"))
    return Lexicon(raw=raw, **{k: raw[k] for k in Lexicon.__dataclass_fields__ if k != "raw"})


def available() -> list[str]:
    return sorted(p.stem for p in LEXICON_DIR.glob("*.json"))


def meta(lang: str) -> dict:
    lx = load(lang)
    return {
        "lang": lx.lang,
        "name": lx.name,
        "english_name": lx.english_name,
        "dir": lx.dir,
        "tts": lx.tts,
        "reviewed_by": lx.reviewed_by,
        "approved": lx.approved,
    }
