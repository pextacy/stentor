import os

import pytest

# Tests never call paid APIs and never touch the dev database.
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["GEMINI_API_KEY"] = ""
os.environ["ADAPTION_API_KEY"] = ""
os.environ["STENTOR_DB_URL"] = "sqlite://"
os.environ["STENTOR_RATE_LIMIT"] = "0"
os.environ["STENTOR_OPERATOR_TOKEN"] = ""

DEMO = "Wildfire near ⟦Altadena⟧. EVACUATE NOW via Lake Ave. Do NOT return until 6:00 PM. Info: 211."
LANGS = ["vi", "tl", "ko", "ar", "ht"]


@pytest.fixture
def demo():
    from stentor.intent.extract import extract

    return extract(DEMO)
