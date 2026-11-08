"""Run the STENTOR eval.

    cd services/api
    uv run python ../../eval/run_eval.py --langs vi,tl,ko,ar,ht --out ../../eval/results/latest.json

With ANTHROPIC_API_KEY set this calls Claude for every case (costs money).
Pass --offline to force the deterministic path.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--langs", default="vi,tl,ko,ar,ht,es,tr")
    ap.add_argument("--out", default=str(ROOT / "eval" / "results" / "latest.json"))
    ap.add_argument("--suites", default="clean,realistic")
    ap.add_argument("--offline", action="store_true", help="ignore API keys; deterministic path only")
    ap.add_argument("--force-model", choices=["llm", "adaption"],
                    help="skip templates and measure one model renderer; writes eval/results/renderer-<name>.json")
    args = ap.parse_args()
    if args.force_model:
        os.environ["STENTOR_FORCE_MODEL"] = "1"
        os.environ["STENTOR_RENDERER"] = args.force_model
        if args.out == ap.get_default("out"):
            args.out = str(ROOT / "eval" / "results" / f"renderer-{args.force_model}.json")
    if args.offline:
        os.environ["ANTHROPIC_API_KEY"] = ""
        os.environ["ADAPTION_API_KEY"] = ""

    from stentor.evaluation import run_eval

    res = run_eval([x for x in args.langs.split(",") if x], Path(args.out), [x for x in args.suites.split(",") if x])
    s = {k: v for k, v in res["summary"].items() if k not in ("by_lang", "catch_by_corruption", "suites")}
    print(json.dumps(s, ensure_ascii=False, indent=1))
    for name, suite in res["summary"]["suites"].items():
        print(name, json.dumps(suite, ensure_ascii=False))
    off = [r for r in res["clean"] if r["expected_status"] and r["status"] != r["expected_status"]]
    if off:
        print(f"\nSTATUS DIFFERS FROM EXPECTED ({len(off)}):")
        for r in off[:30]:
            print(" ", r["suite"], r["id"], r["lang"], r["status"], "expected", r["expected_status"], r["reasons"][:2])
    missed = [r for r in res["adversarial"] if not r["caught"]]
    if missed:
        print(f"\nMISSED {len(missed)} corruptions:")
        for r in missed[:30]:
            print(" ", r["id"], r["lang"], r["corruption"], r["status"])


if __name__ == "__main__":
    main()
