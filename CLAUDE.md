# CLAUDE.md

Guidance for Claude (and any coding agent) working in this repository.

## Project in one paragraph

**STENTOR** is a verified multilingual emergency alert compiler. An emergency manager writes one alert in plain English. STENTOR extracts its meaning into a structured "Alert Intent" (hazard, required action, area, time, expiry, negations), renders it into many languages, then **parses every translation back into the same structure and compares slot by slot**. Only translations whose meaning matches exactly can be sent. Output is a standards compliant CAP 1.2 XML message with one `<info>` block per language, plus SMS sized text, audio, and a pictogram card for low literacy readers.

Named after Stentor, the herald in the Iliad whose voice was as loud as fifty men. The goal is a warning everyone can hear and understand.

## Read these first, in order

1. `docs/PRD.md` : what we are building and why
2. `docs/PLAN.md` : architecture and technical decisions
3. `docs/DOCS.md` : schemas, APIs, algorithms, formats
4. `docs/PHASES.md` : the build order and current status

Always check `docs/PHASES.md` before starting work and tick items when done.

## Non negotiable rules

1. **Never ship an unverified translation.** If any critical slot (action, negation, area, time, hazard) fails verification, that language is `BLOCKED`, not "probably fine". The UI must make this impossible to bypass silently.
2. **Numbers, times, phone numbers, street names and place names are never translated by a model.** They are replaced with locked placeholders (`⟦T1⟧`, `⟦P1⟧`) before rendering and restored after. Verification checks every placeholder survives exactly once.
3. **Negation is a first class slot.** "Do NOT use elevators" losing its "not" is the worst possible failure. There are dedicated tests for it.
4. **Deterministic over generative.** Use the action lexicon and approved templates whenever they cover the message. Use model generation only for what templates cannot express, and always verify it.
5. **No fake numbers in the pitch.** Any statistic shown in the UI, README or video must come from a cited source in `docs/PRD.md` or from our own eval run in `eval/`.

## Stack

- **Frontend:** Next.js 14 (App Router) + TypeScript + Tailwind. Accessible by default (keyboard, screen reader labels, WCAG AA contrast, RTL support for Arabic).
- **Backend:** Python 3.11 + FastAPI + Pydantic v2.
- **LLM for intent extraction and back parsing:** Claude API via the `anthropic` SDK, structured output through tool use with a strict JSON schema.
- **Translation / fine tuned renderer:** Adaption platform (Invent-a-Dataset, Adaptive Data, AutoScientist) for a small alert specialized model, with a general LLM as fallback renderer.
- **TTS:** browser `speechSynthesis` for the demo, server TTS optional.
- **Storage:** SQLite via SQLModel (alerts, verification reports, audit log). No auth beyond a demo operator account.

## Repository layout

```
stentor/
  CLAUDE.md  LICENSE  README.md
  docs/                     PRD.md  PLAN.md  DOCS.md  PHASES.md
  apps/web/                 Next.js console + citizen preview
  services/api/             FastAPI app
    stentor/intent/         extraction + schema
    stentor/lock/           placeholder locking / unlocking
    stentor/render/         template renderer + model renderer
    stentor/verify/         back parse + slot diff
    stentor/channels/       CAP XML, SMS, audio, pictogram
    stentor/lexicon/        action lexicon JSON per language
  eval/                     test alerts, adversarial cases, eval script, results
  data/adaption/            dataset specs and exported datasets
```

## Commands

```bash
# backend
cd services/api && uv sync && uv run uvicorn stentor.main:app --reload --port 8000
uv run pytest -q

# frontend
cd apps/web && pnpm i && pnpm dev

# eval
uv run python eval/run_eval.py --langs vi,tl,ko,ar,ht --out eval/results/latest.json
```

## Environment variables

```
ANTHROPIC_API_KEY=
ADAPTION_API_KEY=
ADAPTION_BASE_URL=https://api.prod.adaptionlabs.ai
STENTOR_RENDERER=adaption|llm   # which model renders non template text
STENTOR_MODEL_ID=               # Adaption model id after training
```

Never commit keys. Use `.env.local` and `.env`.

## Coding conventions

- Type everything. Pydantic models are the source of truth; generate TS types from the OpenAPI schema (`pnpm gen:types`).
- Every verification decision writes an audit record with the reason. Judges and real operators both need to see *why* something was blocked.
- Small pure functions in `verify/` with unit tests. Each bug found becomes an eval case.
- UI copy is plain, calm and short. No emoji in alert output.
- Keep the demo path working at all times on `main`.

## When unsure

Pick the safer behaviour (block, flag, ask the operator), write it in the audit log, and leave a `TODO(stentor):` comment.
