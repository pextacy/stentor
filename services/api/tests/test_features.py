"""Tests for the 35 feature expansion (docs/FEATURES.md). One section per feature."""
import hashlib
import hmac
import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from conftest import DEMO
from stentor import middleware, webhooks
from stentor.config import get_settings
from stentor.main import app, public

client = TestClient(app)
REVIEW_TEXT = "Active shooter at Lincoln High School. Shelter in place now. Lock doors and stay quiet. Call 911 if safe."


def _intent(text=DEMO):
    r = client.post("/intent", json={"text": text})
    assert r.status_code == 200, r.text
    return r.json()


def _compile(text=DEMO, langs=("vi", "ar"), chaos=None, **extra):
    ir = _intent(text)
    body = {"intent": ir["intent"], "locked_text": ir["locked_text"], "mapping": ir["mapping"], "langs": list(langs), **extra}
    r = client.post("/compile" + (f"?chaos={chaos}" if chaos else ""), json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _status(res, lang):
    return next(r["status"] for r in res["results"] if r["lang"] == lang)


# 1. operator review --------------------------------------------------------------

def test_review_approve_makes_language_sendable():
    res = _compile(REVIEW_TEXT, langs=("vi", "es"))
    assert _status(res, "vi") == "REVIEW"
    r = client.post(f"/alerts/{res['alert_id']}/review", json={"lang": "vi", "decision": "approve", "reviewer": "Lan Nguyen", "note": "reads well"})
    assert r.status_code == 200, r.text
    vi = next(x for x in r.json()["results"] if x["lang"] == "vi")
    assert vi["status"] == "APPROVED" and vi["review"]["reviewer"] == "Lan Nguyen"
    assert any(a["event"] == "operator_review" for a in r.json()["audit"])
    cap = client.post("/export/cap", json={"alert_id": res["alert_id"]}).text
    assert '<language>vi</language>' in cap and "stentorReviewer" in cap
    pub = client.get(f"/public/{res['alert_id']}").json()
    assert "vi" in [l["lang"] for l in pub["languages"]]


def test_review_reject_sends_safe_fallback_and_refuses_second_decision():
    res = _compile(REVIEW_TEXT, langs=("ko",))
    aid = res["alert_id"]
    r = client.post(f"/alerts/{aid}/review", json={"lang": "ko", "decision": "reject", "reviewer": "Min-jun", "note": "wrong tone"})
    ko = r.json()["results"][0]
    assert ko["status"] == "FALLBACK" and ko["fallback_used"] and ko["blocked_attempt"]
    assert any("Rejected by Min-jun" in x for x in ko["reasons"])
    again = client.post(f"/alerts/{aid}/review", json={"lang": "ko", "decision": "approve", "reviewer": "Min-jun"})
    assert again.status_code == 409


def test_review_rejects_non_review_language_and_bad_input():
    res = _compile(langs=("vi",))
    aid = res["alert_id"]
    assert client.post(f"/alerts/{aid}/review", json={"lang": "vi", "decision": "approve", "reviewer": "X Y"}).status_code == 409
    assert client.post(f"/alerts/{aid}/review", json={"lang": "tr", "decision": "approve", "reviewer": "X Y"}).status_code == 404
    assert client.post(f"/alerts/{aid}/review", json={"lang": "vi", "decision": "maybe", "reviewer": "X Y"}).status_code == 422


# 2. lifecycle ----------------------------------------------------------------------

def test_lifecycle_update_and_cancel():
    first = _compile(langs=("vi", "ar"))
    upd = _compile("Wildfire near ⟦Altadena⟧. EVACUATE NOW via Lake Ave. Do NOT return until 8:00 PM. Info: 211.",
                   langs=("vi", "ar"), references=first["alert_id"])
    assert upd["msg_type"] == "Update" and upd["references"] == first["alert_id"]
    assert client.get(f"/alerts/{first['alert_id']}").json()["superseded_by"] == upd["alert_id"]
    cap = client.post("/export/cap", json={"alert_id": upd["alert_id"]}).text
    assert "<msgType>Update</msgType>" in cap and f"stentor-{first['alert_id']}" in cap
    # the old one cannot be updated again
    ir = _intent()
    body = {"intent": ir["intent"], "locked_text": ir["locked_text"], "mapping": ir["mapping"], "langs": ["vi"], "references": first["alert_id"]}
    assert client.post("/compile", json=body).status_code == 409

    c = client.post(f"/alerts/{upd['alert_id']}/cancel", json={"reason": "fire contained"})
    assert c.status_code == 200, c.text
    cj = c.json()
    assert cj["msg_type"] == "Cancel" and cj["intent"]["action"] == "all_clear"
    assert "cancelled" in cj["source_text"] and "Altadena" in cj["source_text"]
    assert {r["status"] for r in cj["results"]} <= {"VERIFIED", "FALLBACK"}
    ccap = client.post("/export/cap", json={"alert_id": cj["alert_id"]}).text
    assert "<msgType>Cancel</msgType>" in ccap
    assert client.post(f"/validate/cap", json={"xml": ccap}).json()["valid"]
    assert client.post(f"/alerts/{cj['alert_id']}/cancel", json={}).status_code == 409
    assert client.get(f"/public/{upd['alert_id']}").json()["superseded_by"] == cj["alert_id"]


def test_update_of_unknown_alert_is_404():
    ir = _intent()
    body = {"intent": ir["intent"], "locked_text": ir["locked_text"], "mapping": ir["mapping"], "langs": ["vi"], "references": "nope"}
    assert client.post("/compile", json=body).status_code == 404


# 3. CAP options ---------------------------------------------------------------------

def test_cap_options_status_and_sender():
    aid = _compile(langs=("vi",))["alert_id"]
    cap = client.post("/export/cap", json={"alert_id": aid, "status": "Test", "sender": "ops@county.example", "sender_name": "County OEM"}).text
    assert "<status>Test</status>" in cap and "<sender>ops@county.example</sender>" in cap and "County OEM" in cap


def test_cap_options_refuse_actual_and_bad_sender():
    aid = _compile(langs=("vi",))["alert_id"]
    r = client.post("/export/cap", json={"alert_id": aid, "status": "Actual"})
    assert r.status_code == 422 and "not certified" in r.json()["detail"]
    assert client.post("/export/cap", json={"alert_id": aid, "sender": "has space"}).status_code == 422


# 4. CAP area geometry ----------------------------------------------------------------

def test_cap_area_polygon_circle_geocode():
    area = {"desc": "Altadena evacuation zone", "polygons": [[[34.18, -118.15], [34.20, -118.10], [34.17, -118.09]]],
            "circles": [{"lat": 34.19, "lon": -118.13, "radius_km": 2.5}], "geocodes": [{"name": "SAME", "value": "006037"}]}
    res = _compile(langs=("vi",), area=area)
    stored = client.get(f"/alerts/{res['alert_id']}").json()["area"]
    assert stored["polygons"][0][0] == stored["polygons"][0][-1]  # closed automatically
    cap = client.post("/export/cap", json={"alert_id": res["alert_id"]}).text
    assert "<polygon>34.18,-118.15 34.2,-118.1 34.17,-118.09 34.18,-118.15</polygon>" in cap
    assert "<circle>34.19,-118.13 2.5</circle>" in cap and "<valueName>SAME</valueName>" in cap
    assert "<areaDesc>Altadena evacuation zone</areaDesc>" in cap
    assert client.post("/validate/cap", json={"xml": cap}).json()["valid"]


@pytest.mark.parametrize("area", [
    {"polygons": [[[34.1, -118.1], [34.2, -118.2]]]},
    {"polygons": [[[134.1, -118.1], [34.2, -118.2], [34.3, -118.0]]]},
    {"circles": [{"lat": 34, "lon": -118, "radius_km": 0}]},
])
def test_cap_area_rejects_bad_geometry(area):
    ir = _intent()
    body = {"intent": ir["intent"], "locked_text": ir["locked_text"], "mapping": ir["mapping"], "langs": ["vi"], "area": area}
    assert client.post("/compile", json=body).status_code == 422


# 5. CAP validator ---------------------------------------------------------------------

def test_cap_validator_accepts_our_exports():
    aid = _compile(langs=("vi", "ar", "ko"), chaos="drop_negation:ar")["alert_id"]
    rep = client.get(f"/alerts/{aid}/cap/validate").json()
    assert rep["valid"], rep["errors"]
    assert rep["languages"] == ["en", "vi", "ar", "ko"]


def test_cap_validator_finds_errors():
    bad = """<?xml version="1.0"?><alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">
      <identifier>a b</identifier><sender>x</sender><status>Live</status><sent>2026-01-01T10:00:00Z</sent>
      <msgType>Update</msgType><scope>Public</scope>
      <info><category>Fire</category><event>Fire</event><urgency>Now</urgency><severity>Extreme</severity>
        <area><areaDesc>A</areaDesc><polygon>1,1 2,2 1,1</polygon><circle>1,1</circle></area></info></alert>"""
    rep = client.post("/validate/cap", json={"xml": bad}).json()
    msgs = " | ".join(e["message"] for e in rep["errors"])
    assert not rep["valid"]
    for needle in ("without spaces", "'Live'", "CAP dateTime", "out of order", "needs <references>", "'Now'", "<certainty> is required",
                   "first equal to last", "lat,lon radius"):
        assert needle in msgs, needle
    assert not client.post("/validate/cap", json={"xml": "<not xml"}).json()["valid"]


# 6. exports ------------------------------------------------------------------------------

def test_exports():
    res = _compile(langs=("vi", "ar"), chaos="drop_negation:ar")
    aid = res["alert_id"]
    j = client.get(f"/alerts/{aid}/export.json").json()
    assert j["source"]["text"].startswith("Wildfire near Altadena")
    assert {m["lang"] for m in j["messages"]} == {"vi", "ar"}
    txt = client.get(f"/alerts/{aid}/export.txt")
    assert "attachment" in txt.headers["content-disposition"] and "[vi] Vietnamese - VERIFIED" in txt.text
    csv_text = client.get(f"/alerts/{aid}/export.csv").text
    assert csv_text.startswith("﻿alert_id,lang") and "FALLBACK" in csv_text


def test_exports_never_include_withheld_text():
    res = _compile(REVIEW_TEXT, langs=("vi",))
    j = client.get(f"/alerts/{res['alert_id']}/export.json").json()
    assert j["messages"] == [] and j["withheld"] == [{"lang": "vi", "status": "REVIEW"}]
    assert "Withheld (not sent): vi REVIEW" in client.get(f"/alerts/{res['alert_id']}/export.txt").text


# 7. Atom feed ------------------------------------------------------------------------------

def test_feed():
    clean = _compile(langs=("vi",))["alert_id"]
    demo = _compile(langs=("ar",), chaos="drop_negation:ar")["alert_id"]
    r = client.get("/feed.atom")
    assert r.headers["content-type"].startswith("application/atom+xml")
    assert f"urn:stentor:alert:{clean}" in r.text and f"urn:stentor:alert:{demo}" not in r.text
    assert 'hreflang="vi"' in r.text


# 8. batch -------------------------------------------------------------------------------------

def test_batch():
    r = client.post("/batch", json={"langs": ["vi", "tl"], "items": [
        {"text": DEMO}, {"text": "Tsunami warning. Move to higher ground immediately.", "langs": ["ko"]},
        {"text": "Flood warning. Evacuate now.", "langs": ["xx"]}]})
    assert r.status_code == 200
    out = r.json()
    assert out[0]["statuses"] == {"vi": "VERIFIED", "tl": "VERIFIED"} and out[0]["alert_id"]
    assert out[1]["statuses"] == {"ko": "VERIFIED"}
    assert out[2]["error"] and out[2]["alert_id"] is None
    assert client.post("/batch", json={"items": []}).status_code == 422


# 9. drafts -------------------------------------------------------------------------------------

def test_drafts():
    d = client.post("/drafts", json={"name": "Fire template", "text": DEMO, "langs": ["vi"]}).json()
    assert d["id"] in [x["id"] for x in client.get("/drafts").json()]
    u = client.put(f"/drafts/{d['id']}", json={"name": "Fire v2", "text": DEMO, "langs": ["vi", "ar"]}).json()
    assert u["name"] == "Fire v2" and u["langs"] == ["vi", "ar"]
    assert client.post("/drafts", json={"name": "x", "text": "y", "langs": ["zz"]}).status_code == 422
    assert client.delete(f"/drafts/{d['id']}").status_code == 204
    assert client.delete(f"/drafts/{d['id']}").status_code == 404


# 10. presets ---------------------------------------------------------------------------------------

def test_presets():
    names = [p["name"] for p in client.get("/presets").json()]
    assert names[:2] == ["PRD demo set", "All languages"]
    p = client.post("/presets", json={"name": "LA County", "langs": ["es", "ko", "vi", "tl", "ko"]}).json()
    assert p["langs"] == ["es", "ko", "vi", "tl"]
    assert client.post("/presets", json={"name": "la county", "langs": ["es"]}).status_code == 409
    assert client.delete("/presets/builtin-prd").status_code == 409
    assert client.delete(f"/presets/{p['id']}").status_code == 204


# 11. search ----------------------------------------------------------------------------------------

def test_search():
    aid = _compile("Tsunami warning for Hilo. Move to higher ground immediately.", langs=("tl",))["alert_id"]
    r = client.get("/alerts", params={"q": "hilo", "hazard": "tsunami", "lang": "tl", "status": "VERIFIED"})
    assert aid in [a["id"] for a in r.json()] and int(r.headers["x-total-count"]) >= 1
    assert client.get("/alerts", params={"q": "hilo", "hazard": "wildfire"}).json() == []
    page = client.get("/alerts", params={"limit": 1, "offset": 0})
    assert len(page.json()) == 1 and int(page.headers["x-total-count"]) > 1
    assert all(a["chaos"] for a in client.get("/alerts", params={"chaos": True}).json())


# 12. stats --------------------------------------------------------------------------------------------

def test_stats():
    _compile(langs=("vi", "ar"), chaos="drop_negation:ar")
    _compile(langs=("vi",))
    s = client.get("/stats").json()
    assert s["alerts"] >= 1 and s["by_status"]["VERIFIED"] >= 1 and s["chaos_alerts"] >= 1
    s2 = client.get("/stats", params={"include_chaos": True}).json()
    assert s2["languages_compiled"] > s["languages_compiled"]
    assert any("do not" in reason.lower() for reason, _ in s2["top_block_reasons"])


# 13-15. lexicon tools ------------------------------------------------------------------------------------

def test_lexicon_explorer():
    v = client.get("/lexicon/ar").json()
    assert v["dir"] == "rtl" and v["negation_markers"]
    row = next(r for r in v["rows"] if r["key"] == "use:elevators")
    assert row["en"] == "Do NOT use elevators." and row["text"]
    assert client.get("/lexicon/en").status_code == 404 and client.get("/lexicon/xx").status_code == 404


def test_lexicon_lint():
    for lang in ("vi", "tl", "ko", "ar", "ht", "es", "tr"):
        rep = client.get(f"/lexicon/{lang}/lint").json()
        assert rep["ok"], (lang, rep["findings"][:3])
        assert rep["checked_templates"] > 200


def test_lexicon_lint_catches_broken_lexicon(monkeypatch):
    from stentor.lexicon import load
    from stentor.lexicon.tools import lint

    lx = load("vi")
    broken = json.loads(json.dumps(lx.instructions))
    broken["use:elevators"]["text"]["neg"] = "Đi thang máy."  # negation dropped
    monkeypatch.setattr(lx, "instructions", broken)
    rep = lint("vi")
    assert not rep.ok and any("without a negation marker" in f.message for f in rep.findings)


def test_signoff():
    assert client.post("/lexicon/vi/signoff", json={"reviewer": "Lan Nguyen", "native_speaker": False}).status_code == 422
    r = client.post("/lexicon/vi/signoff", json={"reviewer": "Lan Nguyen", "note": "all phrases", "native_speaker": True})
    assert r.status_code == 201
    assert client.get("/lexicon/vi/signoffs").json()[-1]["reviewer"] == "Lan Nguyen"
    vi = next(l for l in client.get("/meta").json()["languages"] if l["lang"] == "vi")
    assert "Lan Nguyen" in vi["signed_off_by"]
    assert vi["reviewed_by"] == "unreviewed"  # the lexicon file itself is not rewritten


# 16. readability ----------------------------------------------------------------------------------------------

def test_readability():
    ir = _intent()
    rd = ir["readability"]
    assert rd["sentences"] == 4 and rd["grade"] < 8 and "EVACUATE" in rd["all_caps_words"]
    long = ("Because of the rapidly intensifying and extraordinarily unpredictable conflagration conditions, residents "
            "throughout the designated evacuation corridor are hereby instructed to evacuate immediately without delay.")
    hard = _intent(long)["readability"]
    assert hard["grade"] > 8 and hard["long_sentences"] and hard["notes"]


# 17. intent lint -------------------------------------------------------------------------------------------------

def test_intent_lint_contradictions():
    ir = _intent("Chemical hazard warning for Deer Park. Shelter in place now. Do not go outside until 6 PM.")
    intent = ir["intent"]
    intent["instructions"].append({"verb": "evacuate", "object": None, "negated": False, "placeholders": []})
    intent["action"] = "shelter_in_place"
    issues = client.post("/intent/lint", json={"intent": intent, "mapping": ir["mapping"], "locked_text": ir["locked_text"]}).json()
    assert any(i["code"] == "contradiction" for i in issues)


def test_intent_lint_unused_literal_and_hazard_action():
    from stentor.intent.schema import AlertIntent
    from stentor.quality import lint_intent

    intent = AlertIntent(hazard="wildfire", action="boil_water", instructions=[{"verb": "boil", "negated": False}])
    issues = lint_intent(intent, {"⟦P1⟧": "Altadena"}, "Wildfire near ⟦P1⟧. Boil water.")
    codes = {i.code for i in issues}
    assert {"hazard_action", "unused_literal", "info"} <= codes


def test_intent_lint_past_expiry():
    from stentor.intent.schema import AlertIntent
    from stentor.quality import lint_intent

    intent = AlertIntent(hazard="tornado", action="shelter_in_place", expires="⟦T1⟧", time_refs=["⟦T1⟧"],
                         instructions=[{"verb": "shelter", "negated": False}])
    late = datetime(2026, 11, 8, 23, 0, tzinfo=timezone.utc)
    issues = lint_intent(intent, {"⟦T1⟧": "7:45 PM"}, "Tornado warning until ⟦T1⟧. Take shelter now.", now=late)
    assert any(i.code == "expires" and "already passed" in i.message for i in issues)


# 18. glossary ----------------------------------------------------------------------------------------------------------

def test_glossary():
    g = client.post("/glossary", json={"term": "Red Cross", "note": "organisation"}).json()
    assert client.post("/glossary", json={"term": "red cross"}).status_code == 409
    ir = _intent("Wildfire near Altadena. Go to the Red Cross shelter. Evacuate now.")
    assert "Red Cross" in ir["mapping"].values() and ir["glossary_locked"] == ["Red Cross"]
    assert client.delete(f"/glossary/{g['id']}").status_code == 204
    ir2 = _intent("Wildfire near Altadena. Go to the Red Cross shelter. Evacuate now.")
    assert ir2["glossary_locked"] == []


# 19. back translation ----------------------------------------------------------------------------------------------------

def test_back_english():
    res = _compile(langs=("vi", "ar"), chaos="drop_negation:ar")
    vi = next(r for r in res["results"] if r["lang"] == "vi")
    ar = next(r for r in res["results"] if r["lang"] == "ar")
    assert vi["back_english"] == "Wildfire warning for Altadena. Evacuate now via Lake Ave. Do NOT return until 6:00 PM. Info: 211."
    assert "Do NOT return" not in ar["blocked_back_english"]  # shows the dropped negation
    assert ar["back_english"] == "Wildfire warning. Evacuate now. Info: 211."


# 20. duplicate warning -----------------------------------------------------------------------------------------------------

def test_duplicate():
    text = "Flash flood warning for Ellicott City. Move to higher ground now."
    first = _compile(text, langs=("vi",))
    second = _compile(text, langs=("vi",))
    assert first["duplicate_of"] is None or first["duplicate_of"] != second["alert_id"]
    assert second["duplicate_of"] == first["alert_id"]
    audit = client.get(f"/alerts/{second['alert_id']}").json()["audit"]
    assert any(a["event"] == "duplicate" for a in audit)


# 21. channel budgets ---------------------------------------------------------------------------------------------------------

def test_channel_budget():
    res = _compile(langs=("vi",))
    ch = {c["channel"]: c for c in res["results"][0]["channels"]}
    assert set(ch) == {"wea_90", "wea_360", "sms_1"}
    assert ch["wea_360"]["fits"] and ch["wea_90"]["used"] == len(res["results"][0]["text"])

    from stentor.channels.budget import channel_budget
    short = {c.channel: c for c in channel_budget("Evacuate now.")}
    assert short["wea_90"].fits and short["sms_1"].fits


# 22. SSML ---------------------------------------------------------------------------------------------------------------------

def test_ssml():
    res = _compile(langs=("vi", "ar"))
    aid = res["alert_id"]
    s = client.get(f"/alerts/{aid}/ssml", params={"lang": "ar"})
    assert s.status_code == 200 and 'xml:lang="ar' in s.text
    assert '<say-as interpret-as="digits">211</say-as>' in s.text
    assert "⁨" not in s.text and s.text.count("<s>") == 2
    en = client.get(f"/alerts/{aid}/ssml", params={"lang": "en", "repeat": 1}).text
    assert en.count("<s>") == 1 and '<say-as interpret-as="time">' in en
    import xml.etree.ElementTree as ET
    ET.fromstring(s.text.encode())  # well formed
    review = _compile(REVIEW_TEXT, langs=("vi",))
    assert client.get(f"/alerts/{review['alert_id']}/ssml", params={"lang": "vi"}).status_code == 404


# 23. audit CSV ------------------------------------------------------------------------------------------------------------------

def test_audit_csv():
    aid = _compile(langs=("ar",), chaos="drop_negation:ar")["alert_id"]
    text = client.get(f"/alerts/{aid}/audit.csv").text
    assert text.startswith("﻿alert_id,created_at,lang,event,status,reason")
    assert "verification" in text and "FALLBACK" in text


# 24. webhooks ---------------------------------------------------------------------------------------------------------------------

def test_webhooks_signed_delivery(monkeypatch):
    sent = []
    monkeypatch.setattr(webhooks, "_post", lambda url, body, headers: sent.append((url, body, headers)) or 202)
    h = client.post("/webhooks", json={"url": "https://hooks.example.org/stentor"}).json()
    assert h["secret"] and "secret" not in json.dumps([x for x in client.get("/webhooks").json() if x["secret"]])
    try:
        res = _compile(langs=("vi",))
        assert len(sent) == 1
        url, body, headers = sent[0]
        assert headers["X-Stentor-Event"] == "compiled"
        assert webhooks.verify_signature(h["secret"], body, headers["X-Stentor-Signature"])
        assert headers["X-Stentor-Signature"] == "sha256=" + hmac.new(h["secret"].encode(), body, hashlib.sha256).hexdigest()
        payload = json.loads(body)
        assert payload["alert_id"] == res["alert_id"] and payload["data"]["messages"][0]["lang"] == "vi"
        audit = client.get(f"/alerts/{res['alert_id']}").json()["audit"]
        assert any(a["event"] == "webhook" and a["status"] == "DELIVERED" for a in audit)
        # chaos runs are never pushed downstream
        _compile(langs=("ar",), chaos="drop_negation:ar")
        assert len(sent) == 1
        assert client.post("/webhooks/test").json()[0]["ok"]
    finally:
        client.delete(f"/webhooks/{h['id']}")


def test_webhooks_failure_is_audited_not_raised(monkeypatch):
    def boom(*a):
        raise ConnectionError("refused")

    monkeypatch.setattr(webhooks, "_post", boom)
    h = client.post("/webhooks", json={"url": "http://127.0.0.1:9/hook"}).json()
    try:
        res = _compile(langs=("vi",))
        audit = client.get(f"/alerts/{res['alert_id']}").json()["audit"]
        assert any(a["event"] == "webhook" and a["status"] == "FAILED" and "refused" in a["reason"] for a in audit)
    finally:
        client.delete(f"/webhooks/{h['id']}")
    assert client.post("/webhooks", json={"url": "ftp://x.example/y"}).status_code == 422


# 25. expiry -------------------------------------------------------------------------------------------------------------------------

def test_public_expiry():
    res = _compile("Tornado warning for Moore until 7:45 PM. Take shelter now in a basement.", langs=("vi",))
    pub = client.get(f"/public/{res['alert_id']}").json()
    assert pub["expires_at"] and pub["expired"] is False
    later = public(res["alert_id"], now=datetime(2100, 1, 1, tzinfo=timezone.utc))
    assert later.expired is True
    assert client.get(f"/public/{_compile(langs=('vi',))['alert_id']}").json()["expires_at"] is None


# 26-28. auth, rate limit, request id ------------------------------------------------------------------------------------------------

@pytest.fixture
def settings_override():
    s = get_settings()
    old = (s.stentor_operator_token, s.stentor_rate_limit)
    yield s
    s.stentor_operator_token, s.stentor_rate_limit = old
    middleware.LIMITER.reset()


def test_auth_required_for_writes_only(settings_override):
    settings_override.stentor_operator_token = "s3cret"
    assert client.post("/intent", json={"text": DEMO}).status_code == 401
    assert client.post("/intent", json={"text": DEMO}, headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.post("/intent", json={"text": DEMO}, headers={"Authorization": "Bearer s3cret"}).status_code == 200
    assert client.get("/meta").status_code == 200  # reads stay open
    assert client.get("/health").json()["auth_required"] is True


def test_auth_keeps_cors_headers(settings_override):
    settings_override.stentor_operator_token = "s3cret"
    r = client.post("/intent", json={"text": DEMO}, headers={"Origin": "http://localhost:3000"})
    assert r.status_code == 401 and r.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_rate_limit(settings_override):
    settings_override.stentor_rate_limit = 3
    middleware.LIMITER.reset()
    codes = [client.post("/intent", json={"text": DEMO}).status_code for _ in range(5)]
    assert codes[:3] == [200, 200, 200] and codes[3:] == [429, 429]
    r = client.post("/intent", json={"text": DEMO})
    assert int(r.headers["retry-after"]) >= 1
    assert client.get("/meta").status_code == 200  # reads are not limited


def test_request_id():
    r = client.get("/health", headers={"X-Request-ID": "abc123"})
    assert r.headers["x-request-id"] == "abc123" and r.headers["server-timing"].startswith("app;dur=")
    assert len(client.get("/health").headers["x-request-id"]) == 16


# 29. metrics ----------------------------------------------------------------------------------------------------------------------------

def test_metrics():
    _compile(langs=("vi",))
    m = client.get("/metrics").text
    assert 'stentor_requests_total{method="POST",route="/compile",status="200"}' in m
    assert 'stentor_languages_total{lang="vi",status="VERIFIED"}' in m
    assert 'stentor_request_seconds_bucket{route="/compile",le="+Inf"}' in m
