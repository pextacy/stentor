"""Eval: clean and realistic suites + adversarial corruptions.
Only these numbers go in the pitch (CLAUDE.md rule 5)."""
from __future__ import annotations

import json
import platform
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from stentor import __version__, llm
from stentor.intent.extract import coverage, extract
from stentor.lexicon import available
from stentor.pipeline import compile_lang
from stentor.render.router import route
from stentor.verify.chaos import CORRUPTIONS

SUITES_DIR = Path(__file__).resolve().parents[3] / "eval" / "suites"
SUITES = ["clean", "realistic"]
SENT = ("VERIFIED", "REVIEW")  # REVIEW is not auto sent, but the corrupted text survived


def load_suite(name: str) -> list[dict]:
    path = SUITES_DIR / f"{name}.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _pct(n: int, d: int) -> float | None:
    return round(100 * n / d, 1) if d else None


def _run_suite(name: str, langs: list[str]) -> dict:
    alerts = load_suite(name)
    rows, adv, extraction = [], [], []
    for a in alerts:
        ir = extract(a["text"])
        exp = a.get("expect", {})
        neg = sum(1 for i in ir.intent.instructions if i.negated)
        ok = (ir.intent.hazard.value == exp.get("hazard") and ir.intent.action.value == exp.get("action")
              and neg == exp.get("negated"))
        extraction.append({"id": a["id"], "ok": ok, "hazard": ir.intent.hazard.value, "action": ir.intent.action.value,
                           "negated": neg, "expect": exp, "template_coverage": ir.template_coverage,
                           "uncovered": ir.uncovered, "text": a["text"], "note": a.get("note")})
        covered, _ = coverage(ir.locked_text, ir.intent)
        for lg in langs:
            r = compile_lang(ir.intent, ir.locked_text, ir.mapping, lg, None, covered)
            ph = next((c for c in r.checks if c.name == "placeholders"), None)
            rows.append({"suite": name, "id": a["id"], "lang": lg, "status": r.status.value,
                         "expected_status": exp.get("status"), "renderer": r.renderer, "backparser": r.backparser,
                         "placeholders_ok": bool(ph and ph.ok),
                         "critical_slots_ok": all(d.match for d in r.diff if d.critical),
                         "text": r.text, "reasons": r.reasons if r.status.value != "VERIFIED" else []})
            base = route(ir.intent, ir.locked_text, lg, covered)
            if base.text is None:
                continue
            for kind, fn in CORRUPTIONS.items():
                if fn(base.text, ir.intent, lg) is None:
                    continue
                rr = compile_lang(ir.intent, ir.locked_text, ir.mapping, lg, kind, covered)
                adv.append({"suite": name, "id": a["id"], "lang": lg, "corruption": kind, "status": rr.status.value,
                            "caught": rr.status.value not in SENT, "reasons": rr.reasons[:3]})
    status_counts = Counter(r["status"] for r in rows)
    with_exp = [r for r in rows if r["expected_status"]]
    return {
        "alerts": len(alerts),
        "cases": len(rows),
        "status_counts": dict(status_counts),
        "verified_pct": _pct(status_counts["VERIFIED"], len(rows)),
        "review_pct": _pct(status_counts["REVIEW"], len(rows)),
        "false_block_pct": _pct(status_counts["BLOCKED"] + status_counts["FALLBACK"], len(rows)),
        "status_as_expected_pct": _pct(sum(r["status"] == r["expected_status"] for r in with_exp), len(with_exp)),
        "placeholder_survival_pct": _pct(sum(r["placeholders_ok"] for r in rows), len(rows)),
        "extraction_accuracy_pct": _pct(sum(e["ok"] for e in extraction), len(extraction)),
        "adversarial_cases": len(adv),
        "catch_rate_pct": _pct(sum(r["caught"] for r in adv), len(adv)),
        "_rows": rows, "_adv": adv, "_extraction": extraction,
    }


def run_eval(langs: list[str] | None = None, out: Path | None = None, suites: list[str] | None = None) -> dict:
    langs = langs or [lg for lg in available() if lg != "en"]
    suites = suites or SUITES
    per = {name: _run_suite(name, langs) for name in suites}
    rows = [r for s in per.values() for r in s.pop("_rows")]
    adv = [r for s in per.values() for r in s.pop("_adv")]
    extraction = {name: s.pop("_extraction") for name, s in per.items()}

    by_corr: dict[str, list[dict]] = defaultdict(list)
    for r in adv:
        by_corr[r["corruption"]].append(r)
    by_lang = {}
    for lg in langs:
        lr = [r for r in rows if r["lang"] == lg]
        la = [r for r in adv if r["lang"] == lg]
        by_lang[lg] = {
            "cases": len(lr),
            "verified_pct": _pct(sum(r["status"] == "VERIFIED" for r in lr), len(lr)),
            "false_block_pct": _pct(sum(r["status"] in ("BLOCKED", "FALLBACK") for r in lr), len(lr)),
            "status_as_expected_pct": _pct(sum(r["status"] == r["expected_status"] for r in lr), len(lr)),
            "catch_pct": _pct(sum(r["caught"] for r in la), len(la)),
            "adversarial": len(la),
        }
    renderers = Counter(r["renderer"] for r in rows)
    status_counts = Counter(r["status"] for r in rows)
    n_alerts = sum(s["alerts"] for s in per.values())
    summary = {
        "catch_rate_pct": _pct(sum(r["caught"] for r in adv), len(adv)),
        "adversarial_cases": len(adv),
        "missed": sum(not r["caught"] for r in adv),
        "false_block_rate_pct": _pct(status_counts["BLOCKED"] + status_counts["FALLBACK"], len(rows)),
        "review_rate_pct": _pct(status_counts["REVIEW"], len(rows)),
        "verified_rate_pct": _pct(status_counts["VERIFIED"], len(rows)),
        "status_as_expected_pct": _pct(sum(r["status"] == r["expected_status"] for r in rows), len(rows)),
        "clean_cases": len(rows),
        "placeholder_survival_pct": _pct(sum(r["placeholders_ok"] for r in rows), len(rows)),
        "extraction_accuracy_pct": _pct(sum(e["ok"] for ex in extraction.values() for e in ex), n_alerts),
        "alerts": n_alerts,
        "langs": langs,
        "suites": per,
        "catch_by_corruption": {k: {"cases": len(v), "caught": sum(r["caught"] for r in v),
                                    "catch_pct": _pct(sum(r["caught"] for r in v), len(v))}
                                for k, v in by_corr.items()},
        "by_lang": by_lang,
        "renderers": dict(renderers),
        "slot_match_by_renderer_pct": {
            name: _pct(sum(r["critical_slots_ok"] for r in rows if r["renderer"] == name), cnt)
            for name, cnt in renderers.items()
        },
    }
    result = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "stentor_version": __version__,
            "python": platform.python_version(),
            "extractor": llm.EXTRACT_MODEL if llm.available() else "lexicon rules",
            "backparser": llm.BACKPARSE_MODEL if llm.available() else "lexicon (deterministic)",
            "suites": suites,
            "caveats": [
                "Corruptions are synthetic and injected after rendering; they model known failure types, not every real model error.",
                "Without an API key, rendering uses approved templates and back parsing uses the same lexicon, so their errors can be correlated.",
                "Both suites were written by the STENTOR team. The realistic suite holds messy wording and the bugs found in review; the templates were then extended to cover it.",
                "Lexicons are LLM seeded and unreviewed by native speakers.",
            ],
        },
        "summary": summary,
        "extraction": extraction,
        "clean": rows,
        "adversarial": adv,
    }
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result
