# STENTOR

**Every warning, in every language, verified before it is sent.**

An emergency manager writes one alert in plain English. STENTOR reads its meaning into a
structured *Alert Intent* (hazard, action, places, times, negations), translates it into
each community language, then **reads every translation back and compares it slot by slot**.
A language goes out only if its meaning matches. If it does not, that language is blocked and
gets a pre-approved generic safe warning instead of a wrong one.

Output: CAP 1.2 XML with one `<info>` block per language, SMS segment counts, audio, a
language independent pictogram card, and a public alert page.

![Console after compiling the demo alert, with Arabic blocked by chaos mode](docs/screenshots/03-results.png)

## Why

During the January 2025 Los Angeles fires, alerts went out only in English and Spanish
([Planetizen](https://www.planetizen.com/news/2025/02/134255-language-matters-addressing-communication-gaps-disaster-response)).
Machine translation exists, but agencies do not trust it for alerts: a dropped "not" or
"evacuate" softened to "prepare to evacuate" can kill. Nobody can proofread ten languages
under pressure. STENTOR makes the check mechanical. Sources are in [docs/PRD.md](docs/PRD.md).

## How it works

```
 English alert
     │
     ▼
 1 Read      intent.extract     Claude (or rule parser) -> AlertIntent
 2 Lock      lock.apply         Altadena -> ⟦P1⟧, 6:00 PM -> ⟦T1⟧, 211 -> ⟦U1⟧
 3 Render    render.route       approved templates > Adaption model > Claude
 4 Verify    verify             placeholders exactly once
                                action phrase present, no softer action
                                negation markers >= negated instructions
                                back parse with a DIFFERENT model (or lexicon)
                                slot diff: hazard, action, places, times, expiry,
                                negations, instructions, phone/link
 5 Decide    VERIFIED | REVIEW | BLOCKED -> FALLBACK (generic safe template)
 6 Restore   literals back, time format localized, RTL isolated
 7 Channels  CAP 1.2 XML · SMS · audio · pictogram · public page
 8 Audit     every decision and its reason stored in SQLite
```

| Status | Meaning | Sent? |
|---|---|---|
| ✓ Verified | All critical slots match | Yes |
| ! Review | Critical slots match; something non critical needs a person (for example the templates drop a word) | No, operator decides |
| ✕ Blocked | A critical slot differs | No |
| ↺ Safe fallback | Blocked, replaced by the verified generic warning for that hazard | Yes, the generic text |

## Run it

```bash
cp .env.example .env                       # optional: ANTHROPIC_API_KEY, ADAPTION_API_KEY
cp apps/web/.env.example apps/web/.env.local

cd services/api && uv sync && uv run uvicorn stentor.main:app --reload --port 8000
cd apps/web && pnpm i && pnpm dev          # http://localhost:3000
```

Without any key, everything works deterministically: the rule parser reads the alert,
approved templates render it, and the lexicon back parser checks it. With
`ANTHROPIC_API_KEY`, Claude Opus 5.5 extracts and renders, and Claude Sonnet 5.5, a
different model, back parses. Claude calls use the server side refusal fallback
(`fallbacks: "default"`).

```bash
cd services/api
uv run pytest -q                                          # 85 tests
uv run python ../../eval/run_eval.py --offline            # eval, writes eval/results/latest.json
uv run python ../../eval/run_eval.py --force-model llm    # baseline LLM renderer (needs key, costs money)
pnpm --dir ../../apps/web gen:types                       # TS types from the OpenAPI schema
```

Demo script: pick "Wildfire: evacuate (demo)", **Read the alert**, turn on **Chaos mode**
(drop negation in Arabic), **Translate and verify**. Arabic turns to safe fallback and the
slot ledger shows Negations ✕. Then open the citizen preview and download the CAP file
([sample](docs/samples/demo.cap.xml)).

## Eval

From `eval/results/latest.json` (60 alerts written by us, 8+ hazards, 29 with negations,
× 5 languages; deterministic path, no API key):

| Metric | Result |
|---|---|
| Injected critical errors caught | 1640 / 1640 (100%) |
| False block rate on clean renderings | 0 / 300 (0%) |
| Placeholder survival | 100% |
| Intent read correctly (hazard, action, negation count) | 60 / 60 |

Corruptions: dropped negation (145), softened action (240), changed time (55), swapped place,
wrong hazard, dropped literal, duplicated literal (300 each).

**Read these numbers with their limits.** Without a key, the renderer and the back parser
share one lexicon, so a clean result and a perfect catch rate are expected by construction;
the eval proves the checks fire on every known failure type, not that translation is good.
The corruptions are synthetic. The suite and the templates were written by the same team.
The real test is `--force-model llm` (and `adaption`) with a key, which renders with a model
and back parses with a second model; those numbers are not in this README because they have
not been run yet.

## Limitations

- **Lexicons are LLM seeded and unreviewed.** Every language card says so. A native speaker
  should check the action phrases and negation markers (short lists in
  `services/api/stentor/lexicon/*.json`).
- Templates cover a fixed catalog of about 20 instruction types. Anything outside it goes to
  a model renderer, or to Review when no key is set.
- Two places swapped inside the same sentence would pass the multiset check; swaps across
  sentences are caught.
- CAP status is `Exercise`. STENTOR is not certified for production alerting and does not
  connect to IPAWS or carriers.
- Audio uses the browser's voices; many devices have none for Haitian Creole or Tagalog,
  and the UI says so.

## Layout

```
docs/                 PRD, PLAN, DOCS, PHASES, DEVPOST, screenshots, sample CAP
services/api/         FastAPI: intent/ lock/ render/ verify/ channels/ lexicon/
apps/web/             Next.js console (/), public alert page (/a/[id]), eval dashboard (/eval)
eval/                 suites/clean.jsonl, run_eval.py, results/latest.json
data/adaption/        Invent-a-Dataset spec, seed_ht.jsonl, adaption_track.py
```

## Deploy

API: `render.yaml` (Docker, `services/api/Dockerfile`, build context = repo root).
Web: Vercel with root `apps/web` and `NEXT_PUBLIC_API_URL` set to the API URL; add the
Vercel URL to the API's `CORS_ORIGINS`.

## License

MIT
