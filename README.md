# STENTOR

Every warning, in every language, verified before it is sent.

STENTOR compiles one English emergency alert into many languages, parses every
translation back into a structured Alert Intent, and only lets a language through
when its meaning matches slot by slot. Output is CAP 1.2 XML plus SMS, audio and a
pictogram card.

See `CLAUDE.md` and `docs/` (PRD, PLAN, DOCS, PHASES).

## Setup

```bash
cp .env.example .env                     # fill in ANTHROPIC_API_KEY etc.
cp apps/web/.env.example apps/web/.env.local

# backend
cd services/api && uv sync && uv run uvicorn stentor.main:app --reload --port 8000
uv run pytest -q

# frontend (new terminal)
cd apps/web && pnpm i && pnpm dev        # http://localhost:3000 shows API status
```

## License

MIT
