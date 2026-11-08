"""Eval: clean suite + adversarial corruptions. Only these numbers go in the pitch."""
from __future__ import annotations

import json
import platform
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from stentor import __version__, llm
from stentor.intent.extract import coverage, extract
from stentor.pipeline import compile_lang
from stentor.render.router import route
from stentor.verify.chaos import CORRUPTIONS

SUITES = Path(__file__).resolve().parents[3] / "eval" / "suites"
SENT = ("VERIFIED", "REVIEW")  # REVIEW is not auto sent, but the corrupted text survived


def load_suite(name: str = "clean") -> list[dict]:
    path = SUITES / f"{name}.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _pct(n: int, d: int) -> float | None:
    return round(100 * n / d, 1) if d else None


def run_eval(langs: list[str], out: Path | None = None, suite: str = "clean") -> dict:
    alerts = load_suite(suite)
    clean_rows, adv_rows = [], []
    extraction_ok = 0
    extraction_rows = []

    for a in alerts:
        ir = extract(a["text"])
        exp = a.get("expect", {})
        got_neg = sum(1 for i in ir.intent.instructions if i.negated)
        ok = (ir.intent.hazard.value == exp.get("hazard") and ir.intent.action.value == exp.get("action")
              and got_neg == exp.get("negated"))
        extraction_ok += ok
        extraction_rows.append({"id": a["id"], "ok": ok, "hazard": ir.intent.hazard.value,
                                "action": ir.intent.action.value, "negated": got_neg, "expect": exp,
                                "template_coverage": ir.template_coverage})
        covered, _ = coverage(ir.locked_text, ir.intent)
        for lg in langs:
            r = compile_lang(ir.intent, ir.locked_text, ir.mapping, lg, None, covered)
            ph = next((c for c in r.checks if c.name == "placeholders"), None)
            clean_rows.append({"id": a["id"], "lang": lg, "status": r.status.value, "renderer": r.renderer,
                               "backparser": r.backparser, "placeholders_ok": bool(ph and ph.ok),
                               "critical_slots_ok": all(d.match for d in r.diff if d.critical),
                               "reasons": r.reasons if r.status.value != "VERIFIED" else []})
            base = route(ir.intent, ir.locked_text, lg, covered)
            if base.text is None:
                continue
            for kind, fn in CORRUPTIONS.items():
                if fn(base.text, ir.intent, lg) is None:
                    continue
                rr = compile_lang(ir.intent, ir.locked_text, ir.mapping, lg, kind, covered)
                caught = rr.status.value not in SENT
                adv_rows.append({"id": a["id"], "lang": lg, "corruption": kind, "status": rr.status.value,
                                 "caught": caught, "reasons": rr.reasons[:3]})

    n_clean = len(clean_rows)
    status_counts = Counter(r["status"] for r in clean_rows)
    blocked_clean = status_counts["BLOCKED"] + status_counts["FALLBACK"]
    by_corr: dict[str, list[dict]] = defaultdict(list)
    for r in adv_rows:
        by_corr[r["corruption"]].append(r)
    by_lang: dict[str, dict] = {}
    for lg in langs:
        rows = [r for r in clean_rows if r["lang"] == lg]
        adv = [r for r in adv_rows if r["lang"] == lg]
        by_lang[lg] = {
            "clean": len(rows),
            "verified_pct": _pct(sum(r["status"] == "VERIFIED" for r in rows), len(rows)),
            "false_block_pct": _pct(sum(r["status"] in ("BLOCKED", "FALLBACK") for r in rows), len(rows)),
            "catch_pct": _pct(sum(r["caught"] for r in adv), len(adv)),
            "adversarial": len(adv),
        }
    renderers = Counter(r["renderer"] for r in clean_rows)
    slot_match_by_renderer = {
        name: _pct(sum(r["critical_slots_ok"] for r in clean_rows if r["renderer"] == name), cnt)
        for name, cnt in renderers.items()
    }
    summary = {
        "catch_rate_pct": _pct(sum(r["caught"] for r in adv_rows), len(adv_rows)),
        "adversarial_cases": len(adv_rows),
        "missed": sum(not r["caught"] for r in adv_rows),
        "false_block_rate_pct": _pct(blocked_clean, n_clean),
        "review_rate_pct": _pct(status_counts["REVIEW"], n_clean),
        "verified_rate_pct": _pct(status_counts["VERIFIED"], n_clean),
        "clean_cases": n_clean,
        "placeholder_survival_pct": _pct(sum(r["placeholders_ok"] for r in clean_rows), n_clean),
        "extraction_accuracy_pct": _pct(extraction_ok, len(alerts)),
        "alerts": len(alerts),
        "langs": langs,
        "catch_by_corruption": {k: {"cases": len(v), "caught": sum(r["caught"] for r in v),
                                    "catch_pct": _pct(sum(r["caught"] for r in v), len(v))}
                                for k, v in by_corr.items()},
        "by_lang": by_lang,
        "renderers": dict(renderers),
        "slot_match_by_renderer_pct": slot_match_by_renderer,
    }
    result = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "stentor_version": __version__,
            "python": platform.python_version(),
            "extractor": llm.EXTRACT_MODEL if llm.available() else "lexicon rules",
            "backparser": llm.BACKPARSE_MODEL if llm.available() else "lexicon (deterministic)",
            "suite": suite,
            "caveats": [
                "Corruptions are synthetic and injected after rendering; they model known failure types, not every real model error.",
                "Without an API key, rendering uses approved templates and back parsing uses the same lexicon, so their errors can be correlated.",
                "The clean suite was written by the STENTOR team; templates were designed with the same phrase catalog.",
                "Lexicons are LLM seeded and unreviewed by native speakers.",
            ],
        },
        "summary": summary,
        "extraction": extraction_rows,
        "clean": clean_rows,
        "adversarial": adv_rows,
    }
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result
