# PHASES: STENTOR build order

Deadline: **Tue 11 Nov 2026, 01:00 GMT+3**. Submission must be on Devpost before then; aim to submit by **Mon 10 Nov 22:00** and use the rest as buffer.

Rule: the demo path must work end to end after Phase 2. Everything after that is upgrades.

---

## Phase 0: Setup (Sun 8 Nov, 2h)
- [x] Create repo, add the 5 md files, MIT license
- [x] Scaffold `services/api` (FastAPI, uv) and `apps/web` (Next.js, Tailwind, pnpm)
- [x] `.env.example`, health endpoint, CORS
- [x] Get Adaption API key, confirm SDK / MCP access and cost estimate (1,000 credits; Invent 1k rows = 200)
- [ ] Email organizers for working Discord link

**Done when:** web app calls `/health` and shows OK.

## Phase 1: Core pipeline (Sun 8 to Mon 9 morning, 12h)
- [x] `AlertIntent` schema + `/intent` with Claude tool use
- [x] Placeholder locking + restore with unit tests
- [x] LLM renderer with strict prompt
- [x] Lexicons for vi, tl, ko, ar, ht (LLM seeded, `reviewed_by: unreviewed`)
- [x] Lexicon checks (action, weaker action, negation count)
- [x] Back parse with a second model + slot diff + status tiers
- [x] Safe fallback templates per hazard
- [x] `/compile` returning per language results
- [x] Unit tests: negation drop, placeholder drop, action downgrade

**Done when:** a curl request compiles the demo alert into 5 languages with correct statuses, and an injected negation drop is BLOCKED.

## Phase 2: Operator console + citizen preview (Mon 9, 10h)
- [x] Composer with example alerts dropdown
- [x] Intent card (editable enums, placeholders as chips)
- [x] Language grid: status badge (icon + word), rendered text, expandable slot diff and reasons
- [x] Chaos mode toggle (clearly labeled)
- [x] Citizen phone mockup: language switcher, RTL for Arabic, audio button
- [x] Accessibility pass (keyboard, labels, contrast)

**Done when:** full demo script in PLAN.md runs in the browser without the terminal.

## Phase 3: Channels (Mon 9 evening, 6h)
- [x] CAP 1.2 XML export + download button
- [x] SMS segment counter per language
- [x] Short alert budget + compress and re-verify
- [x] Pictogram card SVG for at least 4 hazards
- [x] Public citizen page `/a/{id}`

## Phase 4: Eval (Mon 9 night to Tue 10 morning, 6h)
- [x] 60 clean alerts, adversarial generator
- [x] `run_eval.py` + results JSON
- [x] Eval dashboard page with catch rate, false block rate, placeholder survival
- [x] Fix top failure causes, add them as tests

## Phase 5: Adaption track (start Sun night, runs in parallel)
- [x] Write Invent-a-Dataset spec for `ht` alert rendering; generate ~1k pairs (spec + 4,224 pair template seed done; Invent generation needs ADAPTION_API_KEY: `adaption_track.py estimate`, then `invent --confirm`)
- [ ] Adaptive Data: augment / localize seed set, export
- [ ] Launch AutoScientist run (cost estimate first)
- [x] Wire `STENTOR_RENDERER=adaption` path
- [x] Baseline vs fine tuned eval chart in dashboard (table fills from `run_eval.py --force-model llm|adaption`; empty until measured)
- [ ] If training is not done by Tue 10 14:00: ship datasets + partial results, keep LLM renderer

## Phase 6: Submission (Tue 10, 6h)
- [x] Record demo video (under 3 min, follow PLAN.md script), captions on (2:45, burned-in captions, not in git: video/)
- [x] Screenshots: console, blocked diff, Arabic phone view, CAP XML, eval chart
- [x] Devpost text: project name, short description, detailed description (problem, why it matters, how it works), technologies used
- [x] README with setup, architecture diagram, eval numbers, limitations
- [x] Deploy (Vercel + Railway/Render) and add link (both on Vercel: https://stentor-taupe.vercel.app, API https://stentor-api.vercel.app)
- [ ] Submit by 22:00, then sanity check the public page

---

## Cut list (drop in this order if late)
1. Short alert compression
2. Pictogram cards beyond 2 hazards
3. Public citizen page (keep in app preview)
4. Adaption trained model (keep datasets + plan)
5. Korean (keep 4 languages)

## Status log
- 2026-11-08: Idea locked, docs written.
- 2026-11-08: Phase 0 scaffold done. Web app shows `/health` OK (verified in headless Chrome). Docs live in `docs/`. Open: Adaption API key + cost estimate, Discord link email (manual).
- 2026-11-08: Phases 1 to 4 done and verified in a browser. 85 tests pass. Offline eval: 1640/1640 injected errors caught, 0/300 false blocks (deterministic path; see caveats).
- 2026-11-08: Phase 5 code ready (spec, seed_ht.jsonl, adaption_track.py, Responses API renderer). Waiting on ADAPTION_API_KEY for estimate, Invent, AutoScientist.
- 2026-11-08: Phase 6 docs ready (README, docs/DEVPOST.md, screenshots, sample CAP, Dockerfile, render.yaml). Manual: keys in .env, baseline eval with key, video, deploy, submit.
- 2026-11-08: Hardening pass. Independent code review found 11 bugs (route vs area, clause negation, abbreviations, p.m., 1-800, stale UI state, spoofable source text, duplicate langs); stress testing found more (duplicate actions, implied negation, weekdays, quantities, storm names). Parser rewritten with roles, clauses, implied negation and longest-match. Added Spanish and Turkish, 30 instruction types, realistic suite (32 alerts, also unit tests), audit log and recent alerts in the console, How it works page. 146 tests. Eval: 3486/3486 corruptions caught, 0% wrongly blocked, status as expected 100% over 644 translations.
- 2026-11-08: Feature expansion: 35 operator, channel, language quality and platform features (docs/FEATURES.md): review workflow, CAP Update/Cancel, CAP options + area + validator, exports, SSML, feed, batch, drafts, presets, search, stats, lexicon explorer/lint/sign-off, glossary, back translation, readability and intent lint, channel budgets, duplicate warning, webhooks, token, rate limit, metrics, history/stats/lexicon/settings pages, poster with QR. 211 tests; next build passes. Visual polish pending.
- 2026-11-09: Probe pass with 16 alerts a judge might type (heat, tap water, active shooter, lockdown, power outage, air quality, Amber alert). Fixes: a 'not'/'unless' the templates would drop is now BLOCKED (safe fallback), never Review; locking of zones ('Zone A'), house numbers ('120 Main St'), features ('Mount Hood'), acronyms ('UCLA'), plates and codes ('7ABC123', 'N95'); 5 new instruction types in 8 lexicons (sun, generators, bottled water, run-hide-fight, hiding place), cooling center with closing time, heat/water hazard terms. 7 new realistic cases. 227 tests. Eval: 3682/3682 caught, 0% wrongly blocked on the clean suite, status as expected 100% over 693 translations.
- 2026-11-10: Adaption key works. Estimate: 1,000 ht rows = 200 credits of 1,000. Invent launched: dataset f939bc27-f12d-4ddc-b3bd-57b488fb2752 (running). AutoScientist needs >= 1,000 effective rows; its cost and duration are not documented, decide after the dataset succeeds. Gemini provider added (GEMINI_API_KEY): gemini-3.5-flash renders and extracts, gemini-3.1-flash-lite back parses; Pro models have 0 free tier quota.
- 2026-11-10: First real model run (Gemini, free tier). Fail-safe but unusable: the demo alert was BLOCKED in vi/ar/tr because gemini-3.1-flash-lite back parses into non-canonical slots ('return until T' as until_cleared, phone as number); extraction 40-60 s, compile up to 233 s for 4 languages. Nothing wrong was sent. Demo uses STENTOR_LLM=off. TODO(stentor): give the model back parser the canonical keys per placeholder kind, or use gemini-3.5-flash for it.
- 2026-11-10: Demo video recorded (2:45, Gemini TTS narration, burned captions, real app footage). Adaption Invent dataset succeeded (1,994 rows). Deployed web + API on Vercel; production E2E in a browser: 5 languages VERIFIED, public page and eval page load.
