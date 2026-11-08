from stentor.lock import apply, placeholders_in, restore
from stentor.lock.locker import format_time


def test_demo_literals_locked():
    locked, mapping = apply("Wildfire near ⟦Altadena⟧. EVACUATE NOW via Lake Ave. Do NOT return until 6:00 PM. Info: 211.")
    assert locked == "Wildfire near ⟦P1⟧. EVACUATE NOW via ⟦P2⟧. Do NOT return until ⟦T1⟧. Info: ⟦U1⟧."
    assert mapping == {"⟦P1⟧": "Altadena", "⟦P2⟧": "Lake Ave", "⟦T1⟧": "6:00 PM", "⟦U1⟧": "211"}


def test_round_trip_english_is_identity():
    text = "Flash flood warning for Ellicott City until 11:30 PM. Call (410) 555-0199 or visit www.howardcountymd.gov."
    locked, mapping = apply(text)
    assert "Ellicott City" not in locked and "11:30" not in locked and "555" not in locked
    assert restore(locked, mapping, "en") == text


def test_each_placeholder_unique():
    locked, mapping = apply("Go to Main Street. Avoid Main Street.")
    assert placeholders_in(locked) == ["⟦P1⟧", "⟦P2⟧"]
    assert set(mapping.values()) == {"Main Street"}


def test_numbers_and_urls():
    locked, mapping = apply("Boil water for 3 minutes. Info: www.oakhills.gov/water")
    assert mapping == {"⟦N1⟧": "3", "⟦U1⟧": "www.oakhills.gov/water"}
    assert locked.endswith("Info: ⟦U1⟧")


def test_time_format_localized_value_kept():
    assert format_time("6:00 PM", "vi") == "18:00"
    assert format_time("6:00 PM", "ko") == "오후 6:00"
    assert format_time("6:00 PM", "ar") == "6:00 م"
    assert format_time("tomorrow 8am", "tl") == "8:00 AM bukas"
    assert format_time("around dusk", "vi") == "around dusk"  # unparseable: untouched
