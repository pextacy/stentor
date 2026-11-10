"""SSML for broadcast text-to-speech (radio, sirens with voice, phone trees).

Built from the *locked* verified text, so every literal is known: phone numbers and short
codes are read digit by digit, times as times, and the message is repeated once, as
broadcast alerts usually are."""
from __future__ import annotations

import re
from xml.sax.saxutils import escape

from stentor.lock import kind_of
from stentor.lock.locker import PH_RE, localized_value

ISOLATES = re.compile("[⁦-⁩]")


def _literal(ph: str, value: str, lang: str) -> str:
    v = ISOLATES.sub("", localized_value(ph, value, lang))
    kind = kind_of(ph)
    if kind == "U" and re.fullmatch(r"[\d\s().+-]+", v):
        digits = re.sub(r"\D", "", v)
        mode = "telephone" if len(digits) > 4 else "digits"
        return f'<say-as interpret-as="{mode}">{escape(v)}</say-as>'
    if kind == "U":
        return f'<say-as interpret-as="characters">{escape(v)}</say-as>' if len(v) <= 12 else escape(v)
    if kind == "T" and re.search(r"\d", v):
        return f'<say-as interpret-as="time">{escape(v)}</say-as>'
    return escape(v)


def build_ssml(locked_text: str, mapping: dict[str, str], lang: str, tts: str, repeat: int = 2, rate: str = "90%") -> str:
    def body() -> str:
        out, pos = [], 0
        for m in PH_RE.finditer(locked_text):
            out.append(escape(locked_text[pos:m.start()]))
            out.append(_literal(m.group(0), mapping.get(m.group(0), m.group(0)), lang))
            pos = m.end()
        out.append(escape(locked_text[pos:]))
        text = ISOLATES.sub("", "".join(out))
        # A short pause after each sentence helps listeners on noisy channels.
        return re.sub(r"([.!?؟。])\s+", r'\1 <break time="400ms"/> ', text)

    one = f"<s>{body()}</s>"
    parts = [one] * max(1, min(repeat, 3))
    joined = '\n    <break time="1500ms"/>\n    '.join(parts)
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<speak version="1.1" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="{escape(tts)}">\n'
            f'  <prosody rate="{rate}">\n    {joined}\n  </prosody>\n</speak>\n')
