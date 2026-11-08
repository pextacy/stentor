# PLAN: STENTOR

## 1. Architecture

```
 Operator (Next.js console)
        │  English alert text
        ▼
 ┌──────────────────────── FastAPI ────────────────────────┐
 │ 1. intent.extract()   Claude, strict JSON schema         │
 │ 2. lock.apply()       literals → ⟦T1⟧ ⟦P1⟧ ⟦N1⟧ ⟦U1⟧     │
 │ 3. render.route()     template │ adaption model │ llm    │
 │ 4. verify.check()     back parse (different model)       │
 │                       + lexicon checks + placeholder     │
 │                       count + slot diff → status         │
 │ 5. lock.restore()                                         │
 │ 6. channels.*()       CAP XML, SMS, audio, pictogram     │
 │ 7. audit.write()                                          │
 └──────────────────────────────────────────────────────────┘
        │
        ▼
 Citizen preview (phone mockup, audio, RTL)   Eval dashboard
```

## 2. Key technical decisions

| Decision | Choice | Reason |
|---|---|---|
| Meaning representation | `AlertIntent` Pydantic model with enums for hazard and action | Enums make diffing exact instead of fuzzy |
| Literal protection | Placeholder tokens with unusual brackets `⟦ ⟧` | Models rarely alter them; easy to count |
| Renderer priority | Template > Adaption model > LLM | Most deterministic first |
| Verifier | Back parse with a *different* model than renderer + deterministic lexicon | Avoid correlated errors |
| Negation | Lexicon of negation markers per language + `negated` boolean per instruction | Highest risk failure gets its own check |
| Output standard | CAP 1.2 (OASIS) | Real interoperability story; CAP supports one `<info>` per `<language>` |
| Status tiers | VERIFIED / REVIEW / BLOCKED | Avoids all or nothing |

## 3. Adaption platform usage

Goal: a small, specialized alert renderer for a low resource language (primary: Haitian Creole `ht`; backup: Tagalog `tl`) and a measured improvement over a baseline.

1. **Invent-a-Dataset**: describe the behaviour ("Given an English emergency alert with ⟦placeholders⟧, produce a short, plain, imperative alert in Haitian Creole that keeps every placeholder exactly once, never softens the action, preserves every negation"). Generate ~1,000 pairs covering 8 hazards x 10 actions x negation variants.
2. **Adaptive Data**: augment and translate/localize the seed English alert set (public NWS / FEMA style templates we write ourselves) into target languages; dedupe and clean.
3. **AutoScientist**: fine tune a small base model with the objective "placeholder preservation + slot match rate from our verifier". Our verifier is the eval metric, which makes the story coherent.
4. Export eval: baseline LLM vs Adaption model on the held out set, show slot match rate and placeholder survival.

Access: official Python SDK (`pip install adaption`) or the hosted MCP at `https://api.prod.adaptionlabs.ai/api/v1/mcp`. Check `docs.adaptionlabs.ai` for exact calls; always request a cost estimate before launching runs. Treat this whole track as optional for the demo path.

## 4. Verification algorithm (summary, full spec in DOCS.md)

For each language L:
1. Placeholder check: every placeholder from the source appears exactly once. Fail → BLOCKED.
2. Lexicon check: the action phrase for `intent.action` in L is present; no weaker action phrase present instead; negation markers count matches the number of negated instructions. Fail → BLOCKED.
3. Back parse: model B extracts an `AlertIntent` from the L text (told the language, not the original).
4. Slot diff: critical slots (`hazard`, `action`, `instructions[].negated`, `area_refs`, `time_refs`, `expires`) must match exactly. Non critical (`tone`, `source`, `extra_info`) may differ → REVIEW.
5. Length check per channel.
6. Status + reasons written to audit.

## 5. Demo script (2:30 to 3:00)

1. (15s) Hook: LA fires, alerts only in English and Spanish; GAO worries AI translation is not trustworthy.
2. (20s) Insight: the problem is not translating, it is *trusting* the translation.
3. (60s) Live: type "Wildfire near ⟦Altadena⟧. EVACUATE NOW via Lake Ave. Do NOT return until 6:00 PM. Info: 211." Intent card appears. Render into 5 languages. All green.
4. (30s) The catch: toggle "chaos mode" which injects a real failure seen in testing (negation dropped in one language). STENTOR turns it red, shows the slot diff, falls back to the safe template.
5. (20s) Citizen phone view in Arabic (RTL) with audio, pictogram card.
6. (20s) CAP XML export + Adaption eval chart (baseline vs fine tuned).
7. (15s) Close: works in any language, built for the people last to be warned.

## 6. Time budget (~58 hours from Sun 8 Nov 13:00 to Tue 11 Nov 01:00 GMT+3)

| Block | Hours |
|---|---|
| Phase 0 setup | 2 |
| Phase 1 core pipeline (intent, lock, render, verify) | 12 |
| Phase 2 UI console + citizen preview | 10 |
| Phase 3 channels (CAP, SMS, pictogram, audio) | 6 |
| Phase 4 eval + adversarial set | 6 |
| Phase 5 Adaption training (parallel, async) | 6 active |
| Phase 6 demo video + Devpost write up | 6 |
| Buffer + sleep | rest |

## 7. Team split (if 2 to 4 people)

- A: backend pipeline + verification
- B: frontend console + citizen preview + accessibility
- C: Adaption datasets, training, eval
- D: CAP/channels, video, Devpost text

Solo: follow PHASES.md strictly and drop the "Should have" items first.
