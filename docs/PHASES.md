# PHASES: STENTOR build order

Deadline: **Tue 11 Nov 2026, 01:00 GMT+3**. Submission must be on Devpost before then; aim to submit by **Mon 10 Nov 22:00** and use the rest as buffer.

Rule: the demo path must work end to end after Phase 2. Everything after that is upgrades.

---

## Phase 0: Setup (Sun 8 Nov, 2h)
- [x] Create repo, add the 5 md files, MIT license
- [x] Scaffold `services/api` (FastAPI, uv) and `apps/web` (Next.js, Tailwind, pnpm)
- [x] `.env.example`, health endpoint, CORS
- [ ] Get Adaption API key, confirm SDK / MCP access and cost estimate
- [ ] Email organizers for working Discord link

**Done when:** web app calls `/health` and shows OK.

## Phase 1: Core pipeline (Sun 8 to Mon 9 morning, 12h)
- [ ] `AlertIntent` schema + `/intent` with Claude tool use
- [ ] Placeholder locking + restore with unit tests
- [ ] LLM renderer with strict prompt
- [ ] Lexicons for vi, tl, ko, ar, ht (LLM seeded, `reviewed_by: unreviewed`)
- [ ] Lexicon checks (action, weaker action, negation count)
- [ ] Back parse with a second model + slot diff + status tiers
- [ ] Safe fallback templates per hazard
- [ ] `/compile` returning per language results
- [ ] Unit tests: negation drop, placeholder drop, action downgrade

**Done when:** a curl request compiles the demo alert into 5 languages with correct statuses, and an injected negation drop is BLOCKED.

## Phase 2: Operator console + citizen preview (Mon 9, 10h)
- [ ] Composer with example alerts dropdown
- [ ] Intent card (editable enums, placeholders as chips)
- [ ] Language grid: status badge (icon + word), rendered text, expandable slot diff and reasons
- [ ] Chaos mode toggle (clearly labeled)
- [ ] Citizen phone mockup: language switcher, RTL for Arabic, audio button
- [ ] Accessibility pass (keyboard, labels, contrast)

**Done when:** full demo script in PLAN.md runs in the browser without the terminal.

## Phase 3: Channels (Mon 9 evening, 6h)
- [ ] CAP 1.2 XML export + download button
- [ ] SMS segment counter per language
- [ ] Short alert budget + compress and re-verify
- [ ] Pictogram card SVG for at least 4 hazards
- [ ] Public citizen page `/a/{id}`

## Phase 4: Eval (Mon 9 night to Tue 10 morning, 6h)
- [ ] 60 clean alerts, adversarial generator
- [ ] `run_eval.py` + results JSON
- [ ] Eval dashboard page with catch rate, false block rate, placeholder survival
- [ ] Fix top failure causes, add them as tests

## Phase 5: Adaption track (start Sun night, runs in parallel)
- [ ] Write Invent-a-Dataset spec for `ht` alert rendering; generate ~1k pairs
- [ ] Adaptive Data: augment / localize seed set, export
- [ ] Launch AutoScientist run (cost estimate first)
- [ ] Wire `STENTOR_RENDERER=adaption` path
- [ ] Baseline vs fine tuned eval chart in dashboard
- [ ] If training is not done by Tue 10 14:00: ship datasets + partial results, keep LLM renderer

## Phase 6: Submission (Tue 10, 6h)
- [ ] Record demo video (under 3 min, follow PLAN.md script), captions on
- [ ] Screenshots: console, blocked diff, Arabic phone view, CAP XML, eval chart
- [ ] Devpost text: project name, short description, detailed description (problem, why it matters, how it works), technologies used
- [ ] README with setup, architecture diagram, eval numbers, limitations
- [ ] Deploy (Vercel + Railway/Render) and add link
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
