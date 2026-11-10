"""Channel length budgets per language.

Wireless Emergency Alerts carry 90 characters on legacy handsets and 360 on newer ones
(FCC 2016 WEA order). SMS uses GSM-7 or UCS-2 segments (channels/sms.py)."""
from __future__ import annotations

from pydantic import BaseModel

from stentor.channels.sms import sms_info

WEA_LEGACY = 90
WEA_LONG = 360


class ChannelFit(BaseModel):
    channel: str
    limit: int
    used: int
    fits: bool
    note: str = ""


def channel_budget(text: str) -> list[ChannelFit]:
    n = len(text)
    sms = sms_info(text)
    return [
        ChannelFit(channel="wea_90", limit=WEA_LEGACY, used=n, fits=n <= WEA_LEGACY,
                   note="" if n <= WEA_LEGACY else "too long for legacy WEA; send the short safe version there"),
        ChannelFit(channel="wea_360", limit=WEA_LONG, used=n, fits=n <= WEA_LONG),
        ChannelFit(channel="sms_1", limit=sms.per_segment if sms.segments <= 1 else 160 if sms.encoding == "GSM-7" else 70,
                   used=sms.units, fits=sms.segments <= 1, note=f"{sms.encoding}, {sms.segments} segment(s)"),
    ]
