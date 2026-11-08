from datetime import datetime, timezone
import xml.etree.ElementTree as ET

from stentor.channels.cap import NS, build_cap
from stentor.channels.sms import sms_info
from stentor.intent.schema import Action, AlertIntent, Hazard


def test_sms_gsm7_and_ucs2():
    assert sms_info("Evacuate now.").encoding == "GSM-7"
    assert sms_info("a" * 160).segments == 1
    assert sms_info("a" * 161).segments == 2
    vi = sms_info("Sơ tán ngay.")
    assert vi.encoding == "UCS-2" and vi.per_segment == 70
    assert sms_info("ê" * 71).segments == 2


def test_cap_structure_and_filtering():
    intent = AlertIntent(hazard=Hazard.FLOOD, action=Action.MOVE_TO_HIGHER_GROUND, area_refs=["⟦P1⟧"], expires="⟦T1⟧", time_refs=["⟦T1⟧"])
    results = [
        {"lang": "vi", "status": "VERIFIED", "text": "Cảnh báo lũ lụt. Di chuyển lên vùng cao ngay.", "renderer": "template"},
        {"lang": "ar", "status": "BLOCKED", "text": None, "renderer": "llm"},
        {"lang": "ht", "status": "REVIEW", "text": "x", "renderer": "llm"},
    ]
    xml = build_cap("abc", intent, {"⟦P1⟧": "Riverside", "⟦T1⟧": "11:30 PM"}, "Flood warning.", results,
                    sent=datetime(2026, 11, 9, 20, 0, tzinfo=timezone.utc))
    root = ET.fromstring(xml)
    infos = root.findall(f"{{{NS}}}info")
    assert [i.find(f"{{{NS}}}language").text for i in infos] == ["en", "vi"]  # BLOCKED and REVIEW excluded
    assert root.find(f"{{{NS}}}sent").text == "2026-11-09T20:00:00-00:00"
    assert infos[1].find(f"{{{NS}}}expires").text == "2026-11-09T23:30:00-00:00"
    assert infos[1].find(f"{{{NS}}}area/{{{NS}}}areaDesc").text == "Riverside"
