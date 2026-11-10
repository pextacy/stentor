"""Vercel entry point for the STENTOR API (FastAPI, Python runtime).

The app lives in services/api. On Vercel the SQLite database sits in /tmp, so alert
history is not durable across cold starts: fine for the demo, not for production.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[0]
sys.path.insert(0, str(ROOT / "services" / "api"))
os.environ.setdefault("STENTOR_DB_URL", "sqlite:////tmp/stentor.db")

from stentor.main import app  # noqa: E402,F401
