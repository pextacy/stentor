"""Write openapi.json for `pnpm gen:types`: uv run python -m stentor.dump_openapi"""
import json
from pathlib import Path

from stentor.main import app

out = Path(__file__).resolve().parents[1] / "openapi.json"
out.write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=1), encoding="utf-8")
print(f"wrote {out}")
