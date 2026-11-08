"""Phase 5 Adaption track: seed data, cost estimate, dataset generation, training.

    cd services/api
    uv run python ../../data/adaption/adaption_track.py seed            # free, offline
    uv run python ../../data/adaption/adaption_track.py estimate        # free: prices Invent, creates nothing
    uv run python ../../data/adaption/adaption_track.py invent --confirm
    uv run python ../../data/adaption/adaption_track.py status <dataset_id>
    uv run python ../../data/adaption/adaption_track.py download <dataset_id>
    uv run python ../../data/adaption/adaption_track.py train <dataset_id> --confirm
    uv run python ../../data/adaption/adaption_track.py train-status <run_id>

Anything that spends credits requires --confirm. Endpoints follow docs.adaptionlabs.ai
(POST /api/v1/datasets/invent, GET /api/v1/datasets/{id}, POST /api/v1/autoscientist).
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "services" / "api"))

import httpx  # noqa: E402

from stentor.config import get_settings  # noqa: E402
from stentor.intent.schema import ACTION_VERB, Action, AlertIntent, Hazard, Instruction  # noqa: E402
from stentor.lexicon import load  # noqa: E402
from stentor.render.template import render  # noqa: E402

SPEC = (HERE / "invent_spec_ht.md").read_text(encoding="utf-8").split("---PROMPT---")[1].strip()


def _client() -> httpx.Client:
    s = get_settings()
    if not s.adaption_api_key:
        sys.exit("ADAPTION_API_KEY is not set in .env")
    return httpx.Client(base_url=s.adaption_base_url.rstrip("/") + "/api/v1",
                        headers={"Authorization": f"Bearer {s.adaption_api_key}"}, timeout=60)


def _show(r: httpx.Response) -> dict:
    if r.status_code >= 400:
        sys.exit(f"HTTP {r.status_code}: {r.text}")
    body = r.json()
    print(json.dumps(body, indent=1, ensure_ascii=False))
    return body


def seed(lang: str = "ht") -> Path:
    """English locked alert -> target locked alert pairs, composed from approved templates.
    Covers hazards x actions x instruction variants. Written for transparency and as an
    eval / seed set; the target side is only as good as the (unreviewed) lexicon."""
    en, tgt = load("en"), load(lang)
    rows = []
    for hz, act in itertools.product(Hazard, Action):
        for variant in en.actions[act.value]["text"]:
            for key, spec in [(None, None), *en.instructions.items()]:
                for ivar in (spec["text"] if spec else [None]):
                    count = {"P": 1}
                    head = ["⟦P1⟧"]
                    a_phs = []
                    for k in variant:
                        count[k] = count.get(k, 0) + 1
                        a_phs.append(f"⟦{k}{count[k]}⟧")
                    ins = [Instruction(verb=ACTION_VERB[act], negated=False, placeholders=a_phs)]
                    if key:
                        kinds = ivar.split("|")[1] if "|" in ivar else ""
                        i_phs = []
                        for k in kinds:
                            count[k] = count.get(k, 0) + 1
                            i_phs.append(f"⟦{k}{count[k]}⟧")
                        verb, _, obj = key.partition(":")
                        ins.append(Instruction(verb=verb, object=obj or None, negated=ivar.startswith("neg"), placeholders=i_phs))
                    phs = head + [p for i in ins for p in i.placeholders]
                    intent = AlertIntent(hazard=hz, action=act, instructions=ins,
                                         area_refs=[p for p in phs if p[1] == "P"], time_refs=[p for p in phs if p[1] == "T"],
                                         info_refs=[p for p in phs if p[1] == "U"])
                    a, b = render(intent, "en"), render(intent, lang)
                    if a.ok and b.ok:
                        rows.append({"prompt": a.text, "completion": b.text, "hazard": hz.value, "action": act.value,
                                     "negated": any(i.negated for i in ins), "source": "stentor-templates",
                                     "reviewed_by": tgt.reviewed_by})
    out = HERE / f"seed_{lang}.jsonl"
    out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    print(f"wrote {len(rows)} pairs to {out}")
    return out


def invent(estimate: bool, rows: int) -> dict:
    body = {
        "name": "stentor-alerts-ht",
        "training_type": "instruction_dataset",
        "rows": rows,
        "dataset_prompt": SPEC,
        "translate": {"languages": ["ht"], "sample_rate": 1},
        "estimate": estimate,
        "idempotency_key": f"stentor-ht-{rows}",
    }
    with _client() as c:
        return _show(c.post("/datasets/invent", json=body))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["seed", "estimate", "invent", "status", "download", "train", "train-status"])
    ap.add_argument("id", nargs="?")
    ap.add_argument("--rows", type=int, default=1000)
    ap.add_argument("--lang", default="ht")
    ap.add_argument("--confirm", action="store_true", help="required for anything that spends credits")
    a = ap.parse_args()

    if a.cmd == "seed":
        seed(a.lang)
    elif a.cmd == "estimate":
        invent(True, a.rows)
    elif a.cmd == "invent":
        if not a.confirm:
            sys.exit("This spends credits. Run `estimate` first, then repeat with --confirm.")
        invent(False, a.rows)
    elif a.cmd == "status":
        with _client() as c:
            _show(c.get(f"/datasets/{a.id}"))
    elif a.cmd == "download":
        with _client() as c:
            r = c.get(f"/datasets/{a.id}/download", follow_redirects=True)
            if r.status_code >= 400:
                sys.exit(f"HTTP {r.status_code}: {r.text}")
            out = HERE / f"dataset_{a.id}.download"
            out.write_bytes(r.content)
            print(f"saved {len(r.content)} bytes to {out}")
    elif a.cmd == "train":
        if not a.confirm:
            sys.exit("Training spends credits. Repeat with --confirm once the dataset has succeeded.")
        with _client() as c:
            _show(c.post("/autoscientist", json={"dataset_id": a.id, "training_method": "instruction",
                                                 "max_iterations": 3, "idempotency_key": f"stentor-train-{a.id}"}))
    elif a.cmd == "train-status":
        with _client() as c:
            _show(c.get(f"/autoscientist/{a.id}"))


if __name__ == "__main__":
    main()
