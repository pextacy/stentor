from fastapi.testclient import TestClient

from conftest import DEMO
from stentor.main import app

client = TestClient(app)


def test_intent_compile_cap_public_flow():
    ir = client.post("/intent", json={"text": DEMO}).json()
    assert ir["intent"]["action"] == "evacuate_now"
    assert ir["method"] == "lexicon"
    body = {"intent": ir["intent"], "locked_text": ir["locked_text"], "mapping": ir["mapping"], "source_text": DEMO}
    res = client.post("/compile?chaos=drop_negation:ar", json=body).json()
    status = {r["lang"]: r["status"] for r in res["results"]}
    assert status == {"vi": "VERIFIED", "tl": "VERIFIED", "ko": "VERIFIED", "ar": "FALLBACK", "ht": "VERIFIED"}

    alert = client.get(f"/alerts/{res['alert_id']}").json()
    assert any("negation" in a["reason"] for a in alert["audit"] if a["lang"] == "ar")

    cap = client.post("/export/cap", json={"alert_id": res["alert_id"]})
    assert cap.status_code == 200 and "urn:oasis:names:tc:emergency:cap:1.2" in cap.text
    assert cap.text.count("<info>") == 6  # en + 5

    pub = client.get(f"/public/{res['alert_id']}?lang=ar").json()
    assert pub["selected"]["dir"] == "rtl"
    assert pub["selected"]["status"] == "FALLBACK"


def test_compile_rejects_unknown_placeholder():
    ir = client.post("/intent", json={"text": DEMO}).json()
    body = {"intent": ir["intent"], "locked_text": ir["locked_text"] + " ⟦P9⟧", "mapping": ir["mapping"]}
    assert client.post("/compile", json=body).status_code == 422


def test_bad_chaos_rejected():
    ir = client.post("/intent", json={"text": DEMO}).json()
    body = {"intent": ir["intent"], "locked_text": ir["locked_text"], "mapping": ir["mapping"]}
    assert client.post("/compile?chaos=explode:ar", json=body).status_code == 422


def test_meta():
    m = client.get("/meta").json()
    assert {l["lang"] for l in m["languages"]} >= {"vi", "tl", "ko", "ar", "ht"}
    assert all(l["reviewed_by"] == "unreviewed" for l in m["languages"])
