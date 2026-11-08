"""SMS segment calculator: GSM-7 vs UCS-2."""
from __future__ import annotations

import math

from pydantic import BaseModel

GSM7_BASIC = set(
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
)
GSM7_EXT = set("^{}\\[~]|€\f")


class SmsInfo(BaseModel):
    encoding: str  # GSM-7 | UCS-2
    units: int  # septets or UTF-16 code units
    segments: int
    per_segment: int


def sms_info(text: str) -> SmsInfo:
    if all(c in GSM7_BASIC or c in GSM7_EXT for c in text):
        units = sum(2 if c in GSM7_EXT else 1 for c in text)
        single, multi, enc = 160, 153, "GSM-7"
    else:
        units = len(text.encode("utf-16-le")) // 2
        single, multi, enc = 70, 67, "UCS-2"
    if units <= single:
        return SmsInfo(encoding=enc, units=units, segments=1 if units else 0, per_segment=single)
    return SmsInfo(encoding=enc, units=units, segments=math.ceil(units / multi), per_segment=multi)
